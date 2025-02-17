from asyncio import gather, sleep, Lock as AsyncLock
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterable,
    Generator,
    List,
    Tuple,
    Union,
    Protocol as Interface,
)
from xoa_driver.utils import apply
from xoa_driver.enums import (
    TPLDMode,
    ModifierAction,
    OnOff,
    StartTrigger,
    StopTrigger,
    PacketType,
)
from xoa_driver.lli import commands
from xoa_driver.misc import Token
from ..utils.field import MacAddress, NewIPv6Address
from ..utils.scheduler import schedule
from ..plugin.mc_operations import get_multicast_mac_for_ip
from .icmp_header import IgmpMld
from .protocol_change import ProtocolChange
from ..utils.constants import (
    HW_PACKET_MAX_SIZE,
    HW_PACKET_MIN_SIZE,
    STANDARD_TPLD_TOTAL_LENGTH,
    IgmpRequestType,
    IPVersion,
    PortRateCapProfile,
    PortSpeedMode,
    RateType,
    StreamTypeInfo,
    ResultState,
)
from ..plugin.resource_manager import (
    PortInstance,
    ResourceManager,
    get_ip_property,
    is_in_same_subnet,
    Resource,
)
from ..utils.errors import LossSync, UcTypeError, UnableToObtainDmac
from .id_control import IDControl
from .l3_learning import make_address_collection, send_gateway_learning_request
from .fast_access import Data3918
from .test_result import BoutInfo

if TYPE_CHECKING:
    from ...plugin3918 import Model3918
    from pydantic import BaseModel


class PPipeFacade(Interface):
    def send_statistics(self, data: Union[Dict, "BaseModel"]) -> None:
        """Method used for push statistics data into the messages pipe for future distribution"""


class BaseTestType:
    def __init__(
        self,
        xoa_out: "PPipeFacade",
        cfg: "Model3918",
        resource_manager: "ResourceManager",
    ) -> None:
        self.model_data = Data3918(cfg.test_configuration, cfg.mc_definition)
        self.resource_manager = resource_manager
        self.max_capacity_map = {}
        self.address_refresh_map = {}
        self.leave_retry_count = 0
        self.max_leave_retries = 10
        self.bout_info = BoutInfo(0, 0, 0, 0)
        self.id_control = IDControl(
            set(i.name for i in self.resource_manager.mc_src_ports()),
            self.model_data.get_tid_offset(),
            self.model_data.get_tid_allocation_scope(),
        )
        self.igmp_request_queue = None
        self.igmp_request_inactive = True
        self.igmp_request_sending = AsyncLock()
        self.multicast_group_check_map = {}
        self.want_igmp_request_tx_time = False
        self.counter_poll_active = False
        self.src_port_type = StreamTypeInfo.MULTICAST
        self.xoa_out = xoa_out

    def enabled(self) -> bool:
        return self.model_data.has_test_types_configuration()

    def reset_curr_group_count(self) -> None:
        self.bout_info.mc_group_count = 0

    def reset_test_parameters(self) -> None:
        pass

    def reset_stream_parameters(self) -> None:
        self.id_control.reset_tpld_index()

    def clear_max_capacity_map(self) -> None:
        self.max_capacity_map = {}

    def init_test_plan_data(self) -> None:
        self.reset_test_parameters()
        self.reset_stream_parameters()

    def _need_micro_tpld(self) -> bool:
        for port_instance in self.resource_manager.port_instances():
            if not port_instance.can_micro_tpld or self.bout_info.packet_size == 0:
                return False
            return (
                self.bout_info.packet_size
                < port_instance.config.profile.packet_header_length
                + STANDARD_TPLD_TOTAL_LENGTH
            )
        return False

    async def clean_all_resource_port_streams(self) -> None:
        await gather(
            *[
                port_ins.port.streams.server_sync()
                for port_ins in self.resource_manager.port_instances()
            ]
        )
        await gather(
            *[
                stream.delete()
                for port_ins in self.resource_manager.port_instances()
                for stream in port_ins.port.streams
            ]
        )

    async def init_trial(self) -> None:
        self.leave_retry_count = 0
        self.reset_stream_parameters()
        need_micro_tpld = self._need_micro_tpld()
        await self.clean_all_resource_port_streams()
        await apply(
            *[
                port_ins.port.tpld_mode.set(TPLDMode(need_micro_tpld))
                for port_ins in self.resource_manager.port_instances()
            ]
        )

    async def configure_ports(self) -> None:
        tokens = []
        for src_instance in self.resource_manager.port_instances():
            port = src_instance.port
            port_config = src_instance.config
            net_config = port.net_config

            # ConfigurePortIPv4Properties
            if not port_config.ipv4_properties.address.is_empty:
                tokens.append(
                    net_config.ipv4.address.set(
                        port_config.ipv4_properties.address,
                        port_config.ipv4_properties.public_routing_prefix.to_ipv4(),
                        port_config.ipv4_properties.gateway,
                        "0.0.0.0",
                    )
                )
            tokens.append(
                net_config.ipv4.arp_reply.set(
                    OnOff(port_config.reply_arp_requests))
            )
            tokens.append(
                net_config.ipv4.ping_reply.set(
                    OnOff(port_config.reply_ping_requests))
            )

            # ConfigurePortIPv6Properties
            if not port_config.ipv6_properties.address.is_empty:
                tokens.append(
                    net_config.ipv6.address.set(
                        port_config.ipv6_properties.address,
                        port_config.ipv6_properties.gateway,
                        port_config.ipv6_properties.public_routing_prefix,
                        128,
                    )
                )
            tokens.append(
                net_config.ipv6.arp_reply.set(
                    OnOff(port_config.reply_arp_requests))
            )
            tokens.append(
                net_config.ipv6.ping_reply.set(
                    OnOff(port_config.reply_ping_requests))
            )

            pause_token = port.pause.set(OnOff(port_config.pause_mode_enabled))

            tokens += [
                pause_token,
                port.interframe_gap.set(port_config.inter_frame_gap),
                port.speed.reduction.set(port_config.speed_reduction_ppm),
                port.latency_config.offset.set(port_config.latency_offset_ms),
                # SubControllerBase.cs base.ConfigurePort() 之后
                port.latency_config.mode.set(
                    self.model_data.get_latency_mode_xoa()),
            ]
            if self.model_data.is_packet_size_type_mixed_sizes():
                tokens.append(
                    port.mix.weights.set(
                        *self.model_data.get_mixed_sizes_weights())
                )
                for k, v in self.model_data.get_mixed_length_config().items():
                    position = int(k.split("_")[-1])
                    tokens.append(port.mix.lengths[position].set(v))
        await apply(*tokens)

    async def add_l3_learning_steps(self) -> None:
        address_refresh_map = {}
        for name, arp_object in self.resource_manager.arp_map().items():
            conf = (
                self.model_data.get_mc_config()
                if arp_object.stream_type == StreamTypeInfo.MULTICAST
                else self.model_data.get_uc_config()
            )
            address_refresh_map = await send_gateway_learning_request(
                address_refresh_map,
                arp_object.src_instance,
                conf,
            )

        self.address_refresh_map = address_refresh_map

    def get_group_count_list(self) -> Iterable[int]:
        return []

    def get_iteration_count(self) -> Iterable[int]:
        return []

    def gen_bout_info(self) -> Generator["BoutInfo", None, None]:
        for mc_group_count in self.get_group_count_list():
            for packet_size in self.model_data.get_packet_size_list():
                for iter_index in self.get_iteration_count():
                    yield BoutInfo(mc_group_count, packet_size, iter_index, 0)

    async def add_iteration_step(self) -> None:
        pass

    async def add_toggle_port_sync_state_step(self) -> None:
        if not self.model_data.get_toggle_sync_state():
            return
        await apply(
            *[
                port_ins.port.tx_config.enable.set_off()
                for port_ins in self.resource_manager.port_instances()
            ]
        )
        await sleep(self.model_data.get_sync_off_duration())
        await apply(
            *[
                port_ins.port.tx_config.enable.set_on()
                for port_ins in self.resource_manager.port_instances()
            ]
        )
        check_times = 0
        while True:
            await sleep(1)
            connect_status = [
                src_instance.sync_status
                for src_instance in self.resource_manager.port_instances()
            ]
            connected = all(connect_status)
            if connected:
                break
            check_times += 1
            if not connected and check_times >= 30:
                raise LossSync()
        await sleep(2)

    async def test_loop(self) -> None:
        for bout_info in self.gen_bout_info():
            self.bout_info = bout_info
            await self.add_toggle_port_sync_state_step()
            await self.add_iteration_step()

    def allocate_new_test_result(self) -> None:
        self.resource_manager.set_test_result_bout_info(self.bout_info)
        for p in self.resource_manager.port_instances():
            p.reset_test_result(True)

    def find_packet_sizes(self) -> List[int]:
        # setup_packet_size
        if not self.model_data.is_packet_size_type_fixed():
            min_val = HW_PACKET_MIN_SIZE
            max_val = HW_PACKET_MAX_SIZE
        else:
            min_val = max_val = self.bout_info.packet_size
        return [min_val, max_val]

    def get_used_port_speed(self, port_instance: PortInstance) -> float:
        physical_port_speed = port_instance.port_speed
        if port_instance.config.port_speed_mode != PortSpeedMode.AUTO:
            selected_speed = min(
                port_instance.config.port_speed_mode.scale, physical_port_speed
            )
        else:
            selected_speed = physical_port_speed
        if port_instance.config.port_rate_cap_profile == PortRateCapProfile.CUSTOM:
            capped_speed = min(
                port_instance.config.cap_port_rate, selected_speed)
        else:
            capped_speed = selected_speed
        return float(capped_speed)

    def calc_l1_frame_rate(
        self, bit_rate_bps_l1: float, packet_size: float, inter_frame_gap: float
    ) -> float:
        return bit_rate_bps_l1 / 8.0 / (packet_size + inter_frame_gap)

    def find_stream_packet_limit(
        self, src_instance: PortInstance, port_fraction: float
    ) -> int:
        port_speed = self.get_used_port_speed(src_instance)
        bps_rate_l1 = port_speed * port_fraction / 100.0
        stream_packet_rate = self.calc_l1_frame_rate(
            bps_rate_l1, self.bout_info.packet_size, src_instance.config.inter_frame_gap
        )
        total_frames_for_stream = (
            self.model_data.get_duration_value() * stream_packet_rate
        )
        return int(total_frames_for_stream)

    async def setup_uc_stream_rates(
        self, set_stream_packet_limit: bool = False
    ) -> None:
        resources = self.test_uc_resources()
        tokens = []
        dest_count = {}
        for r in resources:
            stream = r.src_instance.port.streams.obtain(r.stream_index)
            if dest_count.get(r.src_instance, 0) == 0:
                dest_port_count = len(
                    [i for i in resources if i.src_instance == r.src_instance]
                )
                dest_count[r.src_instance] = dest_port_count
            else:
                dest_port_count = dest_count[r.src_instance]

            mc_def = self.model_data.mc_definition
            rate_type = mc_def.stream_definition.rate_type
            if rate_type == RateType.FRACTION:
                fraction = (
                    self.bout_info.rate * mc_def.stream_definition.rate_fraction / 100.0
                )
                ratio_fraction = min(
                    fraction * self.model_data.get_uc_traffic_load_ratio() / 100.0,
                    100.0,
                )
                port_fraction = ratio_fraction / dest_port_count
                total_frames_for_stream = self.find_stream_packet_limit(
                    r.src_instance, port_fraction
                )
                rate_token = stream.rate.fraction.set(
                    int(10000 * port_fraction))
                limit_token = stream.packet.limit.set(
                    int(total_frames_for_stream))

            else:  # rate_type == RRateType.PPS:
                pps_value = (
                    self.bout_info.rate * mc_def.stream_definition.rate_pps / 100.0
                )
                pps_value_total = (
                    pps_value * self.model_data.get_uc_traffic_load_ratio() / 100.0
                )
                uc_pps_value = pps_value_total / dest_port_count
                total_frames_for_stream = self.find_stream_packet_limit(
                    r.src_instance, uc_pps_value
                )
                rate_token = stream.rate.pps.set(int(uc_pps_value))
                limit_token = stream.packet.limit.set(
                    int(total_frames_for_stream))
            tokens.append(stream.enable.set_on())
            tokens.append(rate_token)
            if set_stream_packet_limit:
                tokens.append(limit_token)
        await apply(*tokens)

    # async def _create_multicast_stream(self, send_resource: Resource) -> None:

    def get_dmac_address_for_port_l3(
        self,
        src_instance: "PortInstance",
        dest_instance: "PortInstance",
        ip_version: IPVersion,
    ) -> MacAddress:
        dmac = MacAddress()
        if (
            src_instance == dest_instance
            and not src_instance.config.remote_loop_mac_address.is_empty
        ):
            dmac = src_instance.config.remote_loop_mac_address
        elif not get_ip_property(
            dest_instance.config, ip_version
        ).public_address.is_empty:
            dmac = dest_instance.arp_mac_address
        elif is_in_same_subnet(src_instance.config, dest_instance.config, ip_version):
            dmac = dest_instance.native_mac_address
        elif not src_instance.config.ip_gateway_mac_address.is_empty:
            dmac = src_instance.config.ip_gateway_mac_address
        else:
            raise UnableToObtainDmac(dest_instance.name)
        return dmac

    def get_dmac_address_for_port_l2(
        self, src_instance: "PortInstance", dest_instance: "PortInstance"
    ) -> MacAddress:
        if (
            src_instance == dest_instance
            and not src_instance.config.remote_loop_mac_address.is_empty
        ):
            dmac = src_instance.config.remote_loop_mac_address
        else:
            dmac = src_instance.native_mac_address
        return dmac

    def get_dmac_address(
        self,
        src_instance: "PortInstance",
        dest_instance: "PortInstance",
        ip_version: IPVersion,
    ) -> MacAddress:
        if self.model_data.get_use_gateway_mac():
            dmac = self.get_dmac_address_for_port_l3(
                src_instance, dest_instance, ip_version
            )
        else:
            dmac = self.get_dmac_address_for_port_l2(
                src_instance, dest_instance)
        return dmac

    async def setup_mc_stream_rates(self) -> None:
        done = set()
        tokens = []
        for send_mc in self.resource_manager.send_resources_mc():
            if send_mc.src_instance.name not in done:
                stream = send_mc.src_instance.port.streams.obtain(
                    send_mc.stream_index)
                mc_def = self.model_data.mc_definition
                rate_type = mc_def.stream_definition.rate_type
                if rate_type == RateType.FRACTION:
                    fraction = (
                        self.bout_info.rate
                        * mc_def.stream_definition.rate_fraction
                        / 100.0
                    )
                    fraction = min(fraction, 100)
                    rate_token = stream.rate.fraction.set(
                        int(10000 * fraction))
                else:  # rate_type == RRateType.PPS:
                    pps_value = (
                        self.bout_info.rate * mc_def.stream_definition.rate_pps / 100.0
                    )
                    rate_token = stream.rate.pps.set(int(pps_value))
                tokens.append(stream.enable.set_on())
                tokens.append(rate_token)
                done.add(send_mc.src_instance.name)
        await apply(*tokens)

    async def setup_mc_source_port_streams(self) -> None:
        done = []
        tokens = []
        for src_instance in self.resource_manager.mc_src_ports():
            mc_def = self.model_data.mc_definition
            tpld_id = self.id_control.allocate_new_tid(src_instance.name)
            stream = await src_instance.port.streams.create()
            await stream.packet.header.modifiers.configure(2)
            for send_mc in self.resource_manager.send_resources_mc():
                if send_mc.src_instance == src_instance:
                    send_mc.set_stream_index(stream.idx)
                    send_mc.set_tpld_id(tpld_id)
            stream_config = mc_def.stream_definition

            # setup_mc_packet_header
            ip_version = mc_def.stream_definition.ip_version
            mc_start_address = mc_def.mc_ip_start_address

            dmac = get_multicast_mac_for_ip(mc_start_address)
            addr_coll = make_address_collection(
                mc_start_address, src_instance, dmac)
            packet_header = ProtocolChange.get_packet_header_inner(
                addr_coll,
                stream_config.header_segments,
                src_instance.can_tcp_checksum,
            )
            lsb_bytes = mc_start_address.bytearrays[-4:]
            start_value = int.from_bytes(bytes(lsb_bytes), "big") & 0xFFFF
            step_value = mc_def.mc_address_step_value
            end_value = start_value + step_value * \
                (self.bout_info.mc_group_count - 1)
            ip_segment_offset = stream_config.segment_offset_for_ip
            ip_byte_offset = ProtocolChange.get_ip_field_byte_offset(
                ip_version)
            min_val, max_val = self.find_packet_sizes()

            tokens += [
                stream.tpld_id.set(tpld_id),
                stream.comment.set(f"MC Src {stream.idx} / {tpld_id}"),
                stream.packet.header.protocol.set(
                    stream_config.header_segment_id_list),
                stream.packet.header.data.set(bytes(packet_header).hex()),
                # # Setup DMAC modifier.
                stream.packet.header.modifiers.obtain(0).specification.set(
                    4, "FFFF0000", ModifierAction.INC, 1
                ),
                stream.packet.header.modifiers.obtain(0).range.set(
                    start_value, step_value, end_value
                ),
                # # setup IP modifier
                stream.packet.header.modifiers.obtain(1).specification.set(
                    ip_segment_offset + ip_byte_offset + 2,
                    "FFFF0000",
                    ModifierAction.INC,
                    1,
                ),
                stream.packet.header.modifiers.obtain(1).range.set(
                    start_value, step_value, end_value
                ),
                stream.packet.length.set(
                    self.model_data.get_packet_size_type_xoa(), min_val, max_val
                ),
                stream.payload.content.set(
                    self.model_data.get_mc_payload_type_xoa(),
                    self.model_data.get_mc_payload_pattern(),
                ),
                stream.enable.set_on(),
            ]
            done.append(src_instance.name)
        await apply(*tokens)
        await sleep(2)

    def test_uc_resources(self) -> List[Resource]:
        if self.src_port_type == StreamTypeInfo.UNICAST_BURDEN:
            resources = self.resource_manager.send_resources_uc_burden()
        elif self.src_port_type == StreamTypeInfo.UNICAST_NOT_BURDEN:
            resources = self.resource_manager.send_resources_uc_not_burden()
        else:
            raise UcTypeError()
        return resources

    async def setup_uc_burden_port_streams(self) -> None:
        resources = self.test_uc_resources()
        for send_resource in resources:
            src_instance = send_resource.src_instance
            dest_instance = send_resource.dest_instance
            tpld_id = self.id_control.allocate_new_tid(dest_instance.name)
            uc_def = self.model_data.get_uc_def()
            stream_config = uc_def.stream_definition
            ip_version = stream_config.ip_version
            stream = await src_instance.port.streams.create()
            send_resource.set_stream_index(stream.idx)
            send_resource.set_tpld_id(tpld_id)
            dest_ip = get_ip_property(
                dest_instance.config, ip_version
            ).usable_dest_ip_address
            dmac = self.get_dmac_address(
                src_instance, dest_instance, ip_version)
            min_val, max_val = self.find_packet_sizes()
            addr_coll = make_address_collection(dest_ip, src_instance, dmac)
            packet_header = ProtocolChange.get_packet_header_inner(
                addr_coll, stream_config.header_segments, src_instance.can_tcp_checksum
            )

            tokens = [
                stream.tpld_id.set(tpld_id),
                stream.comment.set(f"UC {stream.idx} / {tpld_id}"),
                stream.packet.header.protocol.set(
                    stream_config.header_segment_id_list),
                stream.packet.header.data.set(bytes(packet_header).hex()),
                stream.packet.length.set(
                    self.model_data.get_packet_size_type_xoa(), min_val, max_val
                ),
                stream.payload.content.set(
                    self.model_data.get_uc_payload_type_xoa(),
                    self.model_data.get_uc_payload_pattern(),
                ),
                stream.enable.set_on(),
            ]
            await apply(*tokens)
        await sleep(2)

    async def send_igmp(self, request_type: IgmpRequestType) -> None:
        self.igmp_request_queue = self.init_igmp_request_bundle(request_type)
        interval = (
            self.model_data.get_igmp_join_interval()
            if request_type == IgmpRequestType.JOIN
            else self.model_data.get_igmp_leave_interval()
        )
        await schedule(interval, "s", self.send_request_bundle, request_type)

    async def send_request_bundle(
        self, count: int, request_type: IgmpRequestType
    ) -> bool:
        if not self.igmp_request_queue:
            return True
        async with self.igmp_request_sending:
            interval = (
                self.model_data.get_igmp_join_interval()
                if request_type == IgmpRequestType.JOIN
                else self.model_data.get_igmp_leave_interval()
            )
            join_leave_each = self.model_data.get_igmp_join_leave_rate() * interval
            for _ in range(join_leave_each):
                request, dest_instance, is_time_request = next(
                    self.igmp_request_queue)
                result = await request
                if is_time_request and self.want_igmp_request_tx_time:
                    if request_type == IgmpRequestType.JOIN:
                        dest_instance.test_result.set_join_sent_timestamp(
                            result.nanoseconds
                        )
                    else:
                        dest_instance.test_result.set_leave_sent_timestamp(
                            result.nanoseconds
                        )
        return self.igmp_request_inactive

    async def send_igmp_join(self) -> None:
        self.igmp_request_inactive = False
        await self.send_igmp(IgmpRequestType.JOIN)

    async def send_igmp_leave(self) -> None:
        self.igmp_request_inactive = True
        await self.send_igmp(IgmpRequestType.LEAVE)

    def init_igmp_request_bundle(
        self, request_type: IgmpRequestType
    ) -> Generator[Tuple[Token, PortInstance, bool], None, None]:
        mc_def = self.model_data.mc_definition
        mc_start_address = mc_def.mc_ip_start_address
        while True:
            for resource in self.resource_manager.send_resources_mc():
                mc_src_port = resource.src_instance
                mc_dest_port = resource.dest_instance
                for mc_address_index in range(self.bout_info.mc_group_count):
                    group_address = mc_start_address + mc_address_index
                    if isinstance(mc_start_address, NewIPv6Address):
                        igmp_packet = IgmpMld.get_mld_packet(
                            request_type,
                            group_address,
                            mc_src_port.config.ipv6_properties.address,
                            mc_def,
                            mc_dest_port.native_mac_address,
                        )
                    else:
                        igmp_packet = IgmpMld.get_igmp_packet(
                            request_type,
                            group_address,
                            mc_src_port.config.ipv4_properties.address,
                            mc_dest_port.config.ipv4_properties.address,
                            mc_def,
                            mc_dest_port.native_mac_address,
                        )
                    if igmp_packet:
                        yield (
                            mc_dest_port.port.tx_single_pkt.send.set(
                                igmp_packet),
                            mc_dest_port,
                            False,
                        )
                        if self.want_igmp_request_tx_time:
                            yield (
                                mc_dest_port.port.tx_single_pkt.time.get(),
                                mc_dest_port,
                                True,
                            )

    def test_src_ports(self) -> List[PortInstance]:
        if self.src_port_type == StreamTypeInfo.UNICAST_BURDEN:
            port_instances = self.resource_manager.mc_and_uc_burden_src_ports()
        elif self.src_port_type == StreamTypeInfo.UNICAST_NOT_BURDEN:
            port_instances = self.resource_manager.mc_and_uc_not_burden_src_ports()
        else:  # self.src_port_type == StreamTypeInfo.MULTICAST :
            port_instances = self.resource_manager.mc_src_ports()
        return port_instances

    async def start_traffic(self, port_sync=False, set_time_limit=False) -> None:
        tokens = []
        port_instances = self.test_src_ports()
        duration_sec = self.model_data.get_duration_value()
        duration_min_sec = round(duration_sec * 1_000_000)
        if not port_sync:
            for r in port_instances:
                if set_time_limit:
                    tokens.append(
                        r.port.tx_config.time_limit.set(duration_min_sec))
                tokens.append(r.port.traffic.state.set_start())
            await apply(*tokens)
        elif len(self.resource_manager.testers()) == 1:
            module_port_list = []
            for r in port_instances:
                module_port_list.append(r.port.kind.module_id)
                module_port_list.append(r.port.kind.port_id)
                if set_time_limit:
                    tokens.append(
                        r.port.tx_config.time_limit.set(duration_min_sec))
            for t in self.resource_manager.testers():
                tokens.append(t.traffic.set_on(module_port_list))
            await apply(*tokens)

    async def stop_traffic(self) -> None:
        port_instances = self.test_src_ports()
        tokens = [r.port.traffic.state.set_stop() for r in port_instances]
        await apply(*tokens)
        while any(
            bool(port_ins.traffic_status)
            for port_ins in self.resource_manager.port_instances()
        ):
            await sleep(0.01)

    def test_stopped(self) -> bool:
        port_instances = self.test_src_ports()
        return not all(r.traffic_status for r in port_instances)

    async def clear_port_stats(self):
        tokens = []
        for port_ins in self.resource_manager.port_instances():
            tokens.append(port_ins.port.statistics.rx.clear.set())
            tokens.append(port_ins.port.statistics.tx.clear.set())
        await apply(*tokens)

    async def send_mac_learning_packets(self) -> None:
        tokens = []
        p_instance = self.resource_manager.port_instances()
        for port_ins in p_instance:
            dmac = MacAddress("FF:FF:FF:FF:FF:FF")
            smac = port_ins.native_mac_address
            ether_type = "FFFF"
            payload = 118 * "00"
            learning_packet = f"{dmac.hexstring}{smac.hexstring}{ether_type}{payload}"
            tokens.append(
                port_ins.port.tx_single_pkt.send.set(learning_packet))
        await apply(*tokens)
        # in case of the router cannot handle so many mac learning packets
        await sleep(len(p_instance))

    async def start_counter_poll(self) -> None:
        self.counter_poll_active = True
        await schedule(1, "s", self.read_counters)

    def stop_counter_poll(self) -> None:
        self.counter_poll_active = False

    def show_results(self):
        pass

    async def read_counters(self, count: int = 0) -> bool:
        await self.resource_manager.query(self.src_port_type)
        self.show_results()
        return not self.counter_poll_active

    async def run(self) -> None:
        self.init_test_plan_data()
        await self.configure_ports()
        await self.add_l3_learning_steps()
        await self.test_loop()

    async def get_final_counters(self) -> bool:
        return False

    def check_capacity_result(self) -> bool:
        test_passed = True
        if self.leave_retry_count >= self.max_leave_retries:
            return False
        failed_port_list = []
        for dest_instance in self.resource_manager.mc_dest_ports():
            if dest_instance not in self.multicast_group_check_map:
                failed_port_list.append(dest_instance)
                test_passed = False
            elif (
                len(self.multicast_group_check_map[dest_instance])
                < self.bout_info.mc_group_count
            ):
                failed_port_list.append(dest_instance)
                test_passed = False
        return test_passed

    async def init_basic_igmp_capture(self) -> None:
        tokens = []
        for dest_instance in self.resource_manager.mc_dest_ports():
            port = dest_instance.port
            tokens.append(port.capturer.state.set_stop())
            tokens.append(
                port.capturer.trigger.set(
                    StartTrigger.ON, 0, StopTrigger.FULL, 0)
            )
            tokens.append(port.capturer.keep.set(PacketType.TPLD, 0, 16))
            tokens.append(port.capturer.state.set_start())
        await apply(*tokens)

    async def stop_capture_and_get_stats(self) -> None:
        tokens = []
        for port_instance in self.resource_manager.mc_dest_ports():
            tokens.append(port_instance.port.loop_back.set_none())
            tokens.append(port_instance.port.capturer.state.set_stop())
        await apply(*tokens)

    async def check_no_mc_data_received(self, equals: bool = True) -> bool:
        stats = []
        for port_instance in self.resource_manager.mc_dest_ports():
            stats.append(port_instance.port.capturer.stats.get())
        results: List[commands.PC_STATS.GetDataAttr] = await apply(*stats)
        for stat in results:
            if equals and stat.packets == 0:
                self.bout_info.set_result_state(ResultState.FAIL)
                return False
            elif not equals and stat.packets != 0:
                self.bout_info.set_result_state(ResultState.FAIL)
                return False
        self.bout_info.set_result_state(ResultState.PASS)
        return True

    async def get_join_capture_data(self) -> None:
        if await self.check_no_mc_data_received(True):
            for port_instance in self.resource_manager.mc_dest_ports():
                captured = await port_instance.port.capturer.obtain_captured()
                if not captured:
                    break
                extra = await captured[0].extra.get()
                port_instance.test_result.rx_data_after_join_timestamp = (
                    extra.time_captured
                )

    async def get_leave_capture_data(self) -> None:
        if await self.check_no_mc_data_received(True):
            for port_instance in self.resource_manager.mc_dest_ports():
                captured = await port_instance.port.capturer.obtain_captured()
                if not captured:
                    break
                extra = await captured[len(captured) - 1].extra.get()
                port_instance.test_result.rx_data_after_leave_timestamp = (
                    extra.time_captured
                )

    def display(self, result: Dict) -> None:
        self.xoa_out.send_statistics(result)
