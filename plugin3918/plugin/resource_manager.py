from asyncio import gather, Lock, sleep
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List
from xoa_driver import testers as driver_testers, ports as driver_port, enums
from xoa_driver.utils import apply
from ..utils.field import MacAddress
from ..model.port_config import PortConfiguration
from ..utils.constants import IPVersion, MulticastRole, StreamTypeInfo
from ..model.port_identity import PortIdentity
from .test_result import (
    BoutInfo,
    CounterType,
    DelayData,
    ErrorCounter,
    PortResult,
    StreamCounter,
)


if TYPE_CHECKING:
    from ...plugin3918 import Model3918

NOT_AUTONEG_SUPPORTED = (
    driver_port.POdin10G1S2P,
    driver_port.POdin10G1S2P_b,
    driver_port.POdin10G1S2P_c,
    driver_port.POdin10G1S6P,
    driver_port.POdin10G1S6P_b,
    driver_port.POdin10G1S2PT,
    driver_port.POdin10G1S2P_d,
    driver_port.POdin10G1S12P,
    driver_port.POdin40G2S2P,
    driver_port.PLoki100G3S1P,
    driver_port.PLoki100G3S1P_b,
    driver_port.PLoki100G3S1PSE,
    driver_port.PLoki100G5S1P,
    driver_port.PLoki100G5S2P,
    driver_port.PThor100G5S4P,
    driver_port.PThor400G7S1P,
    driver_port.PThor400G7S1P_b,
    driver_port.PThor400G7S1P_c,
    driver_port.POdin1G3S6PT1RJ45,
)


def get_ip_property(
    port_config: PortConfiguration,
    ip_version: IPVersion,
):
    if ip_version == IPVersion.IPV4:
        ip_property = port_config.ipv4_properties
    else:
        ip_property = port_config.ipv6_properties
    return ip_property


def need_gateway_mac(
    src_config: PortConfiguration,
    dest_config: PortConfiguration,
    ip_version: IPVersion,
) -> bool:
    src_ip_property = get_ip_property(src_config, ip_version)
    src_gateway = src_ip_property.gateway
    if src_gateway.is_empty:
        return False
    return not is_in_same_subnet(src_config, dest_config, ip_version)


def is_in_same_subnet(
    src_config: PortConfiguration,
    dest_config: PortConfiguration,
    ip_version: IPVersion,
) -> bool:
    src_ip_property = get_ip_property(src_config, ip_version)
    dest_ip_property = get_ip_property(dest_config, ip_version)
    if src_ip_property.address.is_empty or dest_ip_property.address.is_empty:
        return True
    src_network = src_ip_property.address.network(src_ip_property.routing_prefix)
    dest_network = dest_ip_property.address.network(dest_ip_property.routing_prefix)
    return src_network == dest_network


class RegisterType(Enum):
    PT_STREAM = 0
    PR_TPLDTRAFFIC = 1
    PR_TPLDLATENCY = 2
    PR_TPLDJITTER = 3
    PR_TPLDERRORS = 4


class PortInstance:
    def __init__(
        self,
        name: str,
        port: driver_port.GenericL23Port,
        tester: driver_testers.L23Tester,
        config: PortConfiguration,
    ) -> None:
        self.name = name
        self.port = port
        self.tester = tester
        self.config = config
        # self.port.on_traffic_change(self.__on_traffic_change)
        # self.port.on_reservation_change(self.__on_reservation_status)
        # self.port.on_receive_sync_change(self.__on_sync_change)
        self.port.on_speed_change(self.__on_speed_change)
        # self.__traffic_status = enums.TrafficOnOff(False)
        # self.__sync_status = enums.SyncStatus(self.port.info.sync_status)
        # self.__reservation_status = enums.ReservedStatus(self.port.info.reservation)
        self.__native_mac_address = MacAddress("00:00:00:00:00:00")
        # self.__can_tcp_checksum = False
        # self.__can_micro_tpld = False
        self.__port_speed = 0
        self.test_result = PortResult()
        self.tokens_result_dic = {}
        self.__arp_mac_address = MacAddress("00:00:00:00:00:00")
        self.lock = Lock()
        super().__init__()

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PortInstance):
            return False
        return self.name == other.name

    def __hash__(self) -> int:
        return sum(ord(i) for i in self.name)

    def set_arp_mac_address(self, mac: MacAddress) -> None:
        self.__arp_mac_address = mac

    @property
    def port_speed(self) -> float:
        return self.__port_speed

    @property
    def arp_mac_address(self) -> MacAddress:
        return self.__arp_mac_address

    @property
    def can_micro_tpld(self) -> bool:
        # return self.__can_micro_tpld
        return bool(self.port.info.capabilities.can_micro_tpld)

    @property
    def can_tcp_checksum(self) -> bool:
        return bool(self.port.info.capabilities.can_tcp_checksum)
        # return self.__can_tcp_checksum

    @property
    def native_mac_address(self) -> MacAddress:
        return self.__native_mac_address

    @property
    def sync_status(self) -> bool:
        # return bool(self.__sync_status)
        return bool(self.port.sync_status)

    @property
    def reservation_status(self) -> enums.ReservedStatus:
        return self.port.info.reservation

    @property
    def traffic_status(self) -> bool:
        # return bool(self.__traffic_status)
        return bool(self.port.info.traffic_state)

    @property
    def min_packet_length(self) -> int:
        return self.port.info.capabilities.min_packet_length

    @property
    def max_packet_length(self) -> int:
        return self.port.info.capabilities.max_packet_length

    # async def __on_sync_change(self, port: "driver_port.GenericL23Port", v) -> None:
    #     self.__sync_status = enums.SyncStatus(v.sync_status)

    async def __on_speed_change(self, port: "driver_port.GenericL23Port", v) -> None:
        self.__port_speed = v.port_speed * 1_000_000

    # async def __on_reservation_status(
    #     self, port: "driver_port.GenericL23Port", v
    # ) -> None:
    #     self.__reservation_status = enums.ReservedStatus(v.status)

    # async def __on_traffic_change(self, port: "driver_port.GenericL23Port", v) -> None:
    #     self.__traffic_status = enums.TrafficOnOff(v.on_off)

    def __await__(self):
        return self.__prepare().__await__()

    async def __prepare(self):
        if self.reservation_status == enums.ReservedStatus.RESERVED_BY_OTHER:
            await self.port.reservation.set_relinquish()
            while self.reservation_status != enums.ReservedStatus.RELEASED:
                await sleep(0.01)
        tokens = [
            self.port.reservation.set_reserve(),
            self.port.traffic.state.set_stop(),
            self.port.reset.set(),
            self.port.speed.mode.selection.set_auto(),
        ]
        if not isinstance(self.port, NOT_AUTONEG_SUPPORTED):
            tokens.append(self.port.autoneg_selection.set_on())
        tokens += [
            self.port.speed.current.get(),
            self.port.net_config.mac_address.get(),
        ]
        *_, speed_r, mac_r = await apply(*tokens)

        self.__port_speed = speed_r.port_speed * 1_000_000
        self.__native_mac_address = MacAddress(str(mac_r.mac_address))
        # self.__can_tcp_checksum = bool(self.port.info.capabilities.can_tcp_checksum)
        # self.__can_micro_tpld = bool(self.port.info.capabilities.can_micro_tpld)

        return self

    def reset_test_result(self, reset_stored_props: bool = False) -> None:
        self.test_result.reset(reset_stored_props)


@dataclass
class Resource:
    def __init__(
        self,
        src_instance: PortInstance,
        dest_instance: PortInstance,
        stream_info_type: StreamTypeInfo,
    ) -> None:
        self.src_instance = src_instance
        self.dest_instance = dest_instance
        self.stream_info_type = stream_info_type
        self.stream_index = -1
        self.tpld_id = -1
        super().__init__()

    def set_stream_index(self, s: int) -> None:
        self.stream_index = s

    def set_tpld_id(self, tpld_id: int) -> None:
        self.tpld_id = tpld_id

    async def query_src(self) -> None:
        tx = self.src_instance.port.statistics.tx.obtain_from_stream(self.stream_index)
        pt_stream = await tx.get()
        async with self.src_instance.lock:
            pt_stream_counter = StreamCounter(
                frames=pt_stream.packet_count_since_cleared,
                bps=pt_stream.bit_count_last_sec,
                pps=pt_stream.packet_count_last_sec,
            )
            if self.stream_info_type == StreamTypeInfo.MULTICAST:
                self.src_instance.test_result.mc_source_data.update(pt_stream_counter)
            else:
                self.src_instance.test_result.uc_source_data.update(pt_stream_counter)

    async def query_dst(self) -> None:
        tpld = self.dest_instance.port.statistics.rx.access_tpld(self.tpld_id)
        (pr_tpldtraffic, pr_tplderrors, pr_tpldlatency, pr_tpldjitter) = await apply(
            *[
                tpld.traffic.get(),
                tpld.errors.get(),
                tpld.latency.get(),
                tpld.jitter.get(),
            ]
        )

        async with self.dest_instance.lock:
            pr_tpldtraffic_counter = StreamCounter(
                frames=pr_tpldtraffic.packet_count_since_cleared,
                bps=pr_tpldtraffic.bit_count_last_sec,
                pps=pr_tpldtraffic.packet_count_last_sec,
            )
            pr_tpldlatency_counter = DelayData(
                counter_type=CounterType.LATENCY,
                minimum=pr_tpldlatency.min_val,
                average=pr_tpldlatency.avg_val,
                maximum=pr_tpldlatency.max_val,
            )
            pr_tpldjitter_counter = DelayData(
                counter_type=CounterType.JITTER,
                minimum=pr_tpldjitter.min_val,
                average=pr_tpldjitter.avg_val,
                maximum=pr_tpldjitter.max_val,
            )
            pr_tplderrors_counter = ErrorCounter(
                non_increm_seq_no_events=pr_tplderrors.non_incre_seq_event_count,
                swapped_seq_no_events=pr_tplderrors.swapped_seq_misorder_event_count,
                non_increm_payload_events=pr_tplderrors.non_incre_payload_packet_count,
            )
            if self.stream_info_type == StreamTypeInfo.MULTICAST:
                self.dest_instance.test_result.mc_destination_data.update(
                    pr_tpldtraffic_counter
                )

                self.dest_instance.test_result.latency_counters.update(
                    pr_tpldlatency_counter
                )

                self.dest_instance.test_result.jitter_counters.update(
                    pr_tpldjitter_counter
                )

                self.dest_instance.test_result.mc_error_counters.update(
                    pr_tplderrors_counter
                )
            else:
                self.dest_instance.test_result.uc_destination_data.update(
                    pr_tpldtraffic_counter
                )
                self.dest_instance.test_result.uc_error_counters.update(
                    pr_tplderrors_counter
                )


@dataclass
class ArpObject:
    src_instance: PortInstance
    stream_type: StreamTypeInfo


class AllResult:
    def __init__(
        self, resource_manager: "ResourceManager", bout_info: "BoutInfo"
    ) -> None:
        self.resource_manager = resource_manager
        self.bout_info = bout_info

    @property
    def total_mc_frame_loss_delta(self) -> int:
        return sum(
            r.test_result.mc_error_counters.get_lost_packets_delta()
            for r in self.resource_manager.mc_dest_ports()
        )

    @property
    def total_mc_rx_frames(self) -> float:
        return sum(
            r.test_result.mc_destination_data.frames
            for r in self.resource_manager.mc_dest_ports()
        )

    @property
    def total_mc_frame_loss(self) -> float:
        if not self.bout_info.is_final:
            return sum(
                r.test_result.mc_error_counters.non_increm_seq_no_events
                for r in self.resource_manager.mc_dest_ports()
            )
        else:
            return max(self.total_mc_tx_frames - self.total_mc_rx_frames, 0)

    @property
    def total_uc_frame_loss(self) -> float:
        if not self.bout_info.is_final:
            return sum(
                r.test_result.uc_error_counters.non_increm_seq_no_events
                for r in self.resource_manager.mc_dest_ports()
            )
        else:
            return self.total_frame_loss

    @property
    def total_frame_loss(self) -> float:
        return max(self.total_tx_frames - self.total_rx_frames, 0)

    @property
    def total_uc_loss_ratio_percent(self) -> float:
        if self.total_tx_frames == 0.0:
            total_uc_loss_ratio = 0.0
        elif self.bout_info.is_final:
            total_uc_loss_ratio = self.total_frame_loss / self.total_tx_frames
        else:
            total_uc_loss_ratio = self.total_uc_frame_loss / self.total_tx_frames

        return 100.0 * total_uc_loss_ratio

    @property
    def total_tx_frames(self) -> float:
        return sum(
            r.test_result.uc_source_data.frames
            for r in self.resource_manager.uc_src_ports()
        )

    @property
    def total_rx_frames(self) -> float:
        return sum(
            r.test_result.uc_destination_data.frames
            for r in self.resource_manager.uc_dest_ports()
        )

    @property
    def total_mc_tx_frames(self) -> float:
        return sum(
            r.test_result.mc_source_data.frames
            for r in self.resource_manager.mc_src_ports()
        )

    @property
    def total_mc_loss_ratio_percent(self) -> float:
        total_mc_tx_frames = self.total_mc_tx_frames
        if total_mc_tx_frames == 0:
            return 0.0
        return (
            100.0
            * self.total_mc_frame_loss
            / (total_mc_tx_frames * len(self.resource_manager.mc_dest_ports()))
        )


class ResourceManager:
    def __init__(
        self,
        testers: Dict[str, driver_testers.L23Tester],
        port_identities: Dict[str, PortIdentity],
        cfg: "Model3918",
    ) -> None:
        self._validate_tester_type(testers.values(), driver_testers.L23Tester)
        self._testers = testers
        self._port_identities = port_identities
        self.cfg = cfg
        self._ports = {}
        self.test_result = AllResult(self, BoutInfo(0, 0, 0, 0))

    def set_test_result_bout_info(self, bout_info: BoutInfo):
        self.test_result.bout_info = bout_info

    def __await__(self):
        return self.__connect().__await__()

    def __get_instance_by_config(self, port_config: PortConfiguration) -> PortInstance:
        port_identity = [
            i for i in self._port_identities if i.name == port_config.port_config_slot
        ][0]
        if port_identity.name in self._port_instances:
            return self._port_instances[port_identity.name]

        tester_obj = self._testers[port_identity.tester_id]
        port_obj = tester_obj.modules.obtain(port_identity.module_index).ports.obtain(
            port_identity.port_index
        )
        return PortInstance(port_identity.name, port_obj, tester_obj, port_config)

    async def __connect(self):
        srcs: List[PortConfiguration] = []
        dests: List[PortConfiguration] = []
        burdens: List[PortConfiguration] = []
        not_burdens: List[PortConfiguration] = []
        self._send_resources: List[Resource] = []
        self._arp_map = {}
        self._port_instances = {}

        await gather(*self.testers(), return_exceptions=True)
        for port_config in self.cfg.ports_configuration.values():
            if port_config.multicast_role == MulticastRole.MC_SOURCE:
                srcs.append(port_config)
            if port_config.multicast_role == MulticastRole.MC_DESTINATION:
                dests.append(port_config)
            if port_config.multicast_role == MulticastRole.UC_BURDEN:
                burdens.append(port_config)
            if port_config.multicast_role != MulticastRole.UC_BURDEN:
                not_burdens.append(port_config)
            port_instance = self.__get_instance_by_config(port_config)
            self._port_instances[port_instance.name] = port_instance

        mc_ip_version = self.cfg.mc_definition.stream_definition.ip_version
        for mc_src_config in srcs:
            for mc_dest_config in dests:
                mc_src_instance = self.__get_instance_by_config(mc_src_config)
                mc_dest_instance = self.__get_instance_by_config(mc_dest_config)
                self._send_resources.append(
                    Resource(
                        mc_src_instance, mc_dest_instance, StreamTypeInfo.MULTICAST
                    )
                )
                if mc_src_instance.name in self._arp_map or (
                    not need_gateway_mac(mc_src_config, mc_dest_config, mc_ip_version)
                ):
                    continue
                self._arp_map[mc_src_instance.name] = ArpObject(
                    mc_src_instance, StreamTypeInfo.MULTICAST
                )
        uc_ip_version = self.cfg.mc_definition.uc_flow_def.stream_definition.ip_version
        for uc_src_config in not_burdens:
            for uc_dest_config in self.cfg.ports_configuration.values():
                uc_src_instance = self.__get_instance_by_config(uc_src_config)
                uc_dest_instance = self.__get_instance_by_config(uc_dest_config)
                if uc_src_instance == uc_dest_instance:
                    continue
                self._send_resources.append(
                    Resource(
                        uc_src_instance,
                        uc_dest_instance,
                        StreamTypeInfo.UNICAST_NOT_BURDEN,
                    )
                )
                if uc_src_instance.name in self._arp_map or (
                    not need_gateway_mac(uc_src_config, uc_dest_config, uc_ip_version)
                ):
                    continue
                self._arp_map[uc_src_instance.name] = ArpObject(
                    uc_src_instance, StreamTypeInfo.UNICAST_NOT_BURDEN
                )
        for bu_src_config in burdens:
            for bu_dest_config in burdens:
                bu_src_instance = self.__get_instance_by_config(bu_src_config)
                bu_dest_instance = self.__get_instance_by_config(bu_dest_config)
                if bu_src_instance == bu_dest_instance:
                    continue
                self._send_resources.append(
                    Resource(
                        bu_src_instance, bu_dest_instance, StreamTypeInfo.UNICAST_BURDEN
                    )
                )
                if bu_src_instance.name in self._arp_map or (
                    not need_gateway_mac(bu_src_config, bu_dest_config, uc_ip_version)
                ):
                    continue
                self._arp_map[bu_src_instance.name] = ArpObject(
                    bu_src_instance, StreamTypeInfo.UNICAST_BURDEN
                )
        await gather(*self.port_instances(), return_exceptions=True)
        return self

    def get_port(
        self, list_type: List[StreamTypeInfo], src: bool = True
    ) -> List[PortInstance]:
        port_instances = []
        for r in self._send_resources:
            if r.stream_info_type in list_type:
                if src:
                    p = r.src_instance
                else:
                    p = r.dest_instance
                if p not in port_instances:
                    port_instances.append(p)
        return port_instances

    def mc_src_ports(self) -> List[PortInstance]:
        return self.get_port([StreamTypeInfo.MULTICAST], True)

    def mc_and_uc_not_burden_src_ports(self) -> List[PortInstance]:
        return self.get_port(
            [StreamTypeInfo.MULTICAST, StreamTypeInfo.UNICAST_NOT_BURDEN], True
        )

    def mc_and_uc_burden_src_ports(self) -> List[PortInstance]:
        return self.get_port(
            [StreamTypeInfo.MULTICAST, StreamTypeInfo.UNICAST_BURDEN], True
        )

    def uc_burden_src_ports(self) -> List[PortInstance]:
        return self.get_port([StreamTypeInfo.UNICAST_BURDEN], True)

    def mc_and_burden_src_ports(self) -> List[PortInstance]:
        return self.get_port(
            [StreamTypeInfo.MULTICAST, StreamTypeInfo.UNICAST_BURDEN], True
        )

    def uc_src_ports(self) -> List[PortInstance]:
        return self.get_port(
            [StreamTypeInfo.UNICAST_NOT_BURDEN, StreamTypeInfo.UNICAST_BURDEN], True
        )

    def uc_dest_ports(self) -> List[PortInstance]:
        return self.get_port(
            [StreamTypeInfo.UNICAST_NOT_BURDEN, StreamTypeInfo.UNICAST_BURDEN], False
        )

    def uc_not_burden_src_ports(self) -> List[PortInstance]:
        return self.get_port([StreamTypeInfo.UNICAST_NOT_BURDEN], True)

    def mc_dest_ports(self) -> List[PortInstance]:
        return self.get_port([StreamTypeInfo.MULTICAST], False)

    def uc_not_burden_dest_ports(self) -> List[PortInstance]:
        return self.get_port([StreamTypeInfo.UNICAST_NOT_BURDEN], False)

    def get_resource(self, typings: List[StreamTypeInfo]) -> List["Resource"]:
        return [r for r in self._send_resources if r.stream_info_type in typings]

    def send_resources_mc(self) -> List["Resource"]:
        return self.get_resource([StreamTypeInfo.MULTICAST])

    def send_resources_uc(self) -> List["Resource"]:
        return self.get_resource(
            [StreamTypeInfo.UNICAST_NOT_BURDEN, StreamTypeInfo.UNICAST_BURDEN]
        )

    def send_resources_uc_not_burden(self) -> List["Resource"]:
        return self.get_resource([StreamTypeInfo.UNICAST_NOT_BURDEN])

    def send_resources_uc_burden(self) -> List["Resource"]:
        return self.get_resource([StreamTypeInfo.UNICAST_BURDEN])

    def port_instances(self) -> List["PortInstance"]:
        return list(self._port_instances.values())

    def arp_map(self) -> Dict[str, ArpObject]:
        return self._arp_map

    def testers(self) -> List[driver_testers.L23Tester]:
        return list(self._testers.values())

    @staticmethod
    def _validate_tester_type(testers, valid_type) -> None:
        if not all(isinstance(t, valid_type) for t in testers):
            raise ValueError("")

    async def query(self, src_type: StreamTypeInfo) -> None:
        for r in self.port_instances():
            r.reset_test_result(False)
        tasks = []
        mc_src_done = []
        mc_dst_done = []
        uc_src_done = []
        uc_dst_done = []
        for s in self.send_resources_mc():
            if (s.src_instance.name, s.stream_index) not in mc_src_done:
                tasks.append(s.query_src())
                mc_src_done.append((s.src_instance.name, s.stream_index))
            if (s.dest_instance.name, s.tpld_id) not in mc_dst_done:
                tasks.append(s.query_dst())
                mc_dst_done.append((s.dest_instance.name, s.tpld_id))
        if src_type == StreamTypeInfo.UNICAST_BURDEN:
            uc_resources = self.send_resources_uc_burden()
        elif src_type == StreamTypeInfo.UNICAST_NOT_BURDEN:
            uc_resources = self.send_resources_uc_not_burden()
        else:
            uc_resources = []
        for t in uc_resources:
            if (t.src_instance.name, t.stream_index) not in uc_src_done:
                tasks.append(t.query_src())
                uc_src_done.append((t.src_instance.name, t.stream_index))
            if (t.dest_instance.name, t.tpld_id) not in uc_dst_done:
                tasks.append(t.query_dst())
                uc_dst_done.append((t.dest_instance.name, t.tpld_id))
        await gather(*tasks)
