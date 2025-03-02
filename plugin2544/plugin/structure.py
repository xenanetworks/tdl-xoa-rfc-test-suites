import asyncio
from typing import List, TYPE_CHECKING, Optional, Set, Tuple, Union
from dataclasses import dataclass, field
from xoa_driver import enums, misc, utils as driver_utils
from xoa_driver.misc import Hex
from .common import gen_macaddress
from .data_model import (
    ArpRefreshData,
    RXTableData,
    StreamOffset,
)
from .statistics import PortStatistic
from .stream_struct import StreamStruct
from ..utils import exceptions, constants as const
from ..utils.field import MacAddress, IPv4Address, IPv6Address
from loguru import logger
if TYPE_CHECKING:
    from xoa_core.core.test_suites.datasets import PortIdentity
    from xoa_driver import ports as xoa_ports, testers as xoa_testers
    from xoa_driver.lli import commands
    from ..utils.interfaces import TestSuitePipe
    from .test_config import TestConfigData
    from ..model.m_test_config import FrameSize
    from ..model.m_port_config import PortConfiguration
    from ..model.m_test_type_config import (
        ThroughputTest,
        LatencyTest,
        FrameLossRateTest,
        BackToBackTest,
    )


class PortStruct:
    def __init__(
        self,
        tester: "xoa_testers.L23Tester",
        port: "xoa_ports.GenericL23Port",
        port_conf: "PortConfiguration",
        port_identity: "PortIdentity",
        xoa_out: "TestSuitePipe",
    ) -> None:
        self._tester = tester
        self.port_ins = port
        self._xoa_out = xoa_out
        self._port_identity = port_identity
        self._should_stop_on_los = False
        self._port_conf = port_conf
        self.properties = Properties()
        self.lock = asyncio.Lock()
        self._stream_structs: List["StreamStruct"] = []
        self._statistic = PortStatistic()  # reset every second
        self.stop = False

    def set_should_stop_on_los(self, value: bool) -> None:
        self._should_stop_on_los = value

    @property
    def port_identity(self) -> "PortIdentity":
        return self._port_identity

    @property
    def capabilities(self) -> "commands.P_CAPABILITIES.GetDataAttr":
        return self.port_ins.info.capabilities

    async def _change_sync_status(
        self,
        port: "xoa_ports.GenericL23Port",
        get_attr: "commands.P_RECEIVESYNC.GetDataAttr",
    ) -> None:
        """
        Whenever a port status changes, e.g. from IN_SYNC to NO_SYNC, or from NO_SYNC to IN_SYNC, you will receive a BXMP push notification from the xenaserver.
        XOA-driver will call this method if you register this callback method.
        """
        before = self.properties.sync_status
        after = self.properties.sync_status = bool(get_attr.sync_status)
        # logger.debug(f'{self._should_stop_on_los} - {before} - {after}')
        if after or before == after:
            return
        e = exceptions.LossofPortSignal(port)
        if self._should_stop_on_los:
            self._xoa_out.send_error(e)
        else:
            self._xoa_out.send_warning(e)

    async def _change_traffic_status(
        self,
        _port: "xoa_ports.GenericL23Port",
        get_attr: "commands.P_TRAFFIC.GetDataAttr",
    ) -> None:
        """ update traffic_status if it changes """
        self.properties.traffic_status = bool(get_attr.on_off)

    async def __on_reservation_status(
        self, port: "xoa_ports.GenericL23Port", get_attr: "commands.P_RESERVATION.GetDataAttr"
    ) -> None:
        """
        XOA-Core will not catch exception if raise exception here. 
        Because this is a callback method for xoa-driver.
        So we can send error to notify user the reservation has changed.
        """
        if not self.stop and get_attr.status != enums.ReservedStatus.RESERVED_BY_YOU:
            e = exceptions.LossofPortOwnership(port)
            self._xoa_out.send_error(e)

    async def _change_physical_port_speed(
        self,
        _port: "xoa_ports.GenericL23Port",
        get_attr: "commands.P_SPEED.GetDataAttr",
    ) -> None:
        self.properties.physical_port_speed = get_attr.port_speed * 1e6

    async def __on_disconnect_tester(self, *args) -> None:
        e = exceptions.LossofTester(self._tester, self._port_identity.tester_id)
        self._xoa_out.send_error(e)
        raise e

    async def set_toggle_port_sync(self, state: enums.OnOff) -> None:
        await self.port_ins.tx_config.enable.set(state)

    async def set_broadr_reach_mode(self, broadr_reach_mode: const.BRRModeStr) -> None:
        if self.port_ins.info.is_brr_mode_supported == enums.YesNo.NO:
            self._xoa_out.send_warning(
                exceptions.BroadReachModeNotSupport(self._port_identity.name)
            )
        elif isinstance(self.port_ins, const.BrrPorts):
            await self.port_ins.brr_mode.set(broadr_reach_mode.to_xmp())

    async def set_mdi_mdix_mode(self, mdi_mdix_mode: const.MdiMdixMode) -> None:
        if self.port_ins.info.capabilities.can_mdi_mdix == enums.YesNo.NO:
            self._xoa_out.send_warning(
                exceptions.MdiMdixModeNotSupport(self._port_identity.name)
            )
        elif isinstance(self.port_ins, const.MdixPorts):
            await self.port_ins.mdix_mode.set(mdi_mdix_mode.to_xmp())

    async def set_anlt(self, on_off: bool) -> None:
        """Thor-400G-7S-1P support ANLT feature"""
        if not on_off or not isinstance(self.port_ins, const.PCSPMAPorts):
            return

        if bool(self.port_ins.info.capabilities.can_auto_neg_base_r):
            await self.port_ins.pcs_pma.auto_neg.settings.set(
                enums.AutoNegMode.ANEG_ON,
                enums.AutoNegTecAbility.DEFAULT_TECH_MODE,
                enums.AutoNegFECOption.DEFAULT_FEC,
                enums.AutoNegFECOption.DEFAULT_FEC,
                enums.PauseMode.NO_PAUSE,
            )
        else:
            self._xoa_out.send_warning(
                exceptions.ANLTNotSupport(self._port_identity.name)
            )
        if bool(self.port_ins.info.capabilities.can_set_link_train):
            await self.port_ins.pcs_pma.link_training.settings.set(
                enums.LinkTrainingMode.STANDALONE,
                enums.PAM4FrameSize.P16K_FRAME,
                enums.LinkTrainingInitCondition.NO_INIT,
                enums.NRZPreset.NRZ_NO_PRESET,
                enums.TimeoutMode.DEFAULT,
            )
        else:
            self._xoa_out.send_warning(
                exceptions.ANLTNotSupport(self._port_identity.name)
            )

    async def set_auto_negotiation(self, on_off: bool) -> None:
        """P_AUTONEGSELECTION"""
        if not on_off:
            return
        if not bool(self.port_ins.info.capabilities.can_set_autoneg):
            self._xoa_out.send_warning(
                exceptions.AutoNegotiationNotSupport(self._port_identity.name)
            )
        elif isinstance(self.port_ins, const.AutoNegPorts):
            await self.port_ins.autoneg_selection.set_on()  # type:ignore

    async def set_speed_mode(self, port_speed_mode: const.PortSpeedStr) -> None:
        mode = port_speed_mode.to_xmp()
        if mode not in self.port_ins.info.port_possible_speed_modes:
            self._xoa_out.send_warning(exceptions.PortSpeedWarning(mode))
        else:
            await self.port_ins.speed.mode.selection.set(mode)

    async def set_sweep_reduction(self, ppm: int) -> None:
        await self.port_ins.speed.reduction.set(ppm=ppm)

    async def set_stagger_step(self, port_stagger_steps: int) -> None:
        if not port_stagger_steps:
            return
        await self.port_ins.tx_config.delay.set(port_stagger_steps)  # P_TXDELAY

    async def set_fec_mode(self, fec_mode: const.FECModeStr) -> None:
        """Loki-100G-5S-2P  module 4 * 25G support FC_FEC mode"""
        if fec_mode == const.FECModeStr.OFF:
            return
        await self.port_ins.fec_mode.set(fec_mode.to_xmp())  # PP_FECMODE

    async def set_max_header(self, header_length: int) -> None:
        # calculate max header length
        for p in const.STANDARD_SEGMENT_VALUE:
            if header_length <= p:
                header_length = p
                break
        await self.port_ins.max_header_length.set(header_length)

    async def set_packet_size_if_mix(self, frame_sizes: "FrameSize") -> None:
        if not frame_sizes.packet_size_type.is_mix:
            return
        await self.port_ins.mix.weights.set(*frame_sizes.mixed_sizes_weights)
        if frame_sizes.mixed_length_config:
            dic = frame_sizes.mixed_length_config.dict()

            for k, v in dic.items():
                position = int(k.split("_")[-1])
                # logger.debug(f"position: {position} value: {v}")
                await self.port_ins.mix.lengths[position].set(v)

    def send_packet(self, packet: str) -> "misc.Token":
        return self.port_ins.tx_single_pkt.send.set(Hex(packet))

    def free(self, stop_test=False) -> "misc.Token":
        self.stop = stop_test
        return self.port_ins.reservation.set_release()

    async def prepare(self) -> None:

        tokens = [
            self.port_ins.sync_status.get(),
            self.port_ins.traffic.state.get(),
            self.port_ins.net_config.mac_address.get(),
            self.port_ins.speed.current.get(),
        ]
        if self.port_ins.is_reserved_by_me():
            tokens.append(self.free())
        elif self.port_ins.is_reserved_by_others():
            tokens.append(self.port_ins.reservation.set_relinquish())
        tokens.append(self.port_ins.reservation.get())
        tokens.append(self.port_ins.reservation.set_reserve())
        tokens.append(self.port_ins.reset.set())

        (sync, traffic, mac, port_speed, *_) = await driver_utils.apply(*tokens)
        self.port_ins.on_reservation_change(self.__on_reservation_status)
        self.port_ins.on_receive_sync_change(self._change_sync_status)
        self.port_ins.on_traffic_change(self._change_traffic_status)
        self.port_ins.on_speed_change(self._change_physical_port_speed)
        self._tester.on_disconnected(self.__on_disconnect_tester)
        self.properties.sync_status = bool(sync.sync_status)
        self.properties.traffic_status = bool(traffic.on_off)
        self.properties.native_mac_address = MacAddress(mac.mac_address)
        self.properties.physical_port_speed = port_speed.port_speed * 1e6

    async def clear_statistic(self) -> None:
        await driver_utils.apply(
            self.port_ins.statistics.tx.clear.set(),
            self.port_ins.statistics.rx.clear.set(),
        )

    async def set_tx_time_limit(self, tx_timelimit: int) -> None:
        await self.port_ins.tx_config.time_limit.set(int(tx_timelimit))

    async def set_gap_monitor(
        self, gap_monitor_start_microsec: int, gap_monitor_stop_frames: int
    ) -> None:
        await self.port_ins.gap_monitor.set(
            gap_monitor_start_microsec, gap_monitor_stop_frames
        )

    def set_traffic(self, traffic_state: "enums.StartOrStop") -> "misc.Token":
        return self.port_ins.traffic.state.set(traffic_state)

    async def set_arp_trucks(self, arp_datas: Set["RXTableData"]) -> None:
        arp_chunk: List["misc.ArpChunk"] = []
        for arp_data in arp_datas:
            arp_chunk.append(
                misc.ArpChunk(
                    IPv4Address(arp_data.destination_ip),
                    const.IPPrefixLength.IPv4.value,
                    enums.OnOff.OFF,
                    Hex(arp_data.dmac),
                )
            )
        await self.port_ins.arp_rx_table.set(arp_chunk)

    async def set_ndp_trucks(self, ndp_datas: Set["RXTableData"]) -> None:
        ndp_chunk: List["misc.NdpChunk"] = []
        for rx_data in ndp_datas:
            ndp_chunk.append(
                misc.NdpChunk(
                    IPv6Address(rx_data.destination_ip),
                    const.IPPrefixLength.IPv6.value,
                    enums.OnOff.OFF,
                    Hex(rx_data.dmac),
                )
            )
        await self.port_ins.ndp_rx_table.set(ndp_chunk)

    async def set_reply(self) -> None:
        await driver_utils.apply(
            self.port_ins.net_config.ipv4.arp_reply.set_on(),  # P_ARPREPLY
            self.port_ins.net_config.ipv6.arp_reply.set_on(),  # P_ARPV6REPLY
            self.port_ins.net_config.ipv4.ping_reply.set_on(),  # P_PINGREPLY
            self.port_ins.net_config.ipv6.ping_reply.set_on(),  # P_PINGV6REPLY
        )

    async def set_tpld_mode(self, use_micro_tpld: bool) -> None:
        await self.port_ins.tpld_mode.set(enums.TPLDMode(int(use_micro_tpld)))

    async def set_latency_offset(self, offset: int) -> None:
        await self.port_ins.latency_config.offset.set(offset=offset)

    async def set_interframe_gap(self, interframe_gap: int) -> None:
        await self.port_ins.interframe_gap.set(min_byte_count=interframe_gap)

    async def set_pause_mode(self, pause_mode_enabled: bool):
        await self.port_ins.pause.set(on_off=enums.OnOff(int(pause_mode_enabled)))

    async def set_latency_mode(self, latency_mode: "const.LatencyModeStr"):
        await self.port_ins.latency_config.mode.set(latency_mode.to_xmp())

    async def set_ip_address(self) -> None:
        ip_properties = self._port_conf.ip_address
        if not ip_properties:
            return
        if isinstance(ip_properties.address, IPv4Address) and isinstance(
            ip_properties.gateway, IPv4Address
        ):
            subnet_mask = ip_properties.routing_prefix.to_ipv4()
            await self.port_ins.net_config.ipv4.address.set(
                ipv4_address=ip_properties.address,
                subnet_mask=subnet_mask,
                gateway=ip_properties.gateway,
                wild=IPv4Address("0.0.0.0"),
            )
        elif isinstance(ip_properties.address, IPv6Address) and isinstance(
            ip_properties.gateway, IPv6Address
        ):
            await self.port_ins.net_config.ipv6.address.set(
                ipv6_address=ip_properties.address,
                gateway=ip_properties.gateway,
                subnet_prefix=ip_properties.routing_prefix,
                wildcard_prefix=128,
            )

    async def set_mac_address(self, mac_addr: str) -> None:
        await self.port_ins.net_config.mac_address.set(Hex(mac_addr))
        self.properties.native_mac_address = MacAddress(mac_addr)

    @property
    def local_states(self):
        return self.port_ins.local_states

    async def clear(self) -> None:
        await driver_utils.apply(self.free())
        # await self._tester.session.logoff()

    async def create_stream(self):
        return await self.port_ins.streams.create()

    async def get_traffic_status(self) -> bool:
        return bool((await self.port_ins.traffic.state.get()).on_off)

    @property
    def send_port_speed(self) -> float:
        return self.properties.send_port_speed

    def set_send_port_speed(self, speed: float) -> None:
        self.properties.send_port_speed = speed

    @property
    def rate_percent(self) -> float:
        return self.properties.rate_percent

    @property
    def stream_structs(self) -> List["StreamStruct"]:
        return self._stream_structs

    @property
    def statistic(self) -> "PortStatistic":
        return self._statistic

    @property
    def port_conf(self) -> "PortConfiguration":
        return self._port_conf

    def set_rate_percent(self, rate_percent: float) -> None:
        self.properties.rate_percent = rate_percent

    def init_counter(
        self, packet_size: float, duration: float, is_final: bool = False
    ) -> None:
        self._statistic = PortStatistic(
            port_id=self._port_identity.name,
            frame_size=packet_size,
            rate_percent=self.rate_percent,
            duration=duration,
            is_final=is_final,
            port_speed=self.send_port_speed,
            interframe_gap=self._port_conf.inter_frame_gap,
        )

    def clear_counter(self) -> None:
        self._statistic = PortStatistic()

    @property
    def protocol_version(self) -> "const.PortProtocolVersion":
        return const.PortProtocolVersion[self._port_conf.profile.protocol_version.name]

    def add_stream(
        self,
        rx_ports: List["PortStruct"],
        stream_id: int,
        tpldid: int,
        arp_mac: MacAddress = MacAddress(),
        stream_offset: Optional["StreamOffset"] = None,
    ):
        stream_struct = StreamStruct(
            self, rx_ports, stream_id, tpldid, arp_mac, stream_offset
        )
        self._stream_structs.append(stream_struct)

    async def configure_streams(self, test_conf: "TestConfigData") -> None:
        for header_segment in self._port_conf.profile.segments:
            for field_value_range in header_segment.value_ranges:
                if field_value_range.restart_for_each_port:
                    field_value_range.reset()
        for stream_struct in self._stream_structs:
            await stream_struct.configure(test_conf)

    async def set_streams_packet_size(
        self, packet_size_type: "enums.LengthType", min_size: int, max_size: int
    ) -> None:
        await asyncio.gather(
            *[
                stream_struct.set_packet_size(packet_size_type, min_size, max_size)
                for stream_struct in self._stream_structs
            ]
        )

    async def setup_port(
        self, test_conf: "TestConfigData", latency_mode: "const.LatencyModeStr"
    ) -> None:
        if not test_conf.is_stream_based:
            mac = gen_macaddress(
                test_conf.mac_base_address,
                self.properties.test_port_index,
            )
            await self.set_mac_address(str(mac))
        await self.set_speed_mode(self._port_conf.port_speed_mode)
        await self.set_latency_offset(self._port_conf.latency_offset_ms)
        await self.set_interframe_gap(int(self._port_conf.inter_frame_gap))
        await self.set_pause_mode(self._port_conf.pause_mode_enabled)
        await self.set_latency_mode(latency_mode)
        await self.set_reply()
        await self.set_ip_address()
        await self.set_broadr_reach_mode(self._port_conf.broadr_reach_mode)
        await self.set_mdi_mdix_mode(self._port_conf.mdi_mdix_mode)
        await self.set_fec_mode(self._port_conf.fec_mode)
        await self.set_anlt(self._port_conf.anlt_enabled)
        await self.set_auto_negotiation(self._port_conf.auto_neg_enabled)
        await self.set_max_header(self._port_conf.profile.packet_header_length)
        await self.set_sweep_reduction(self._port_conf.speed_reduction_ppm)
        await self.set_stagger_step(test_conf.port_stagger_steps)
        await self.set_packet_size_if_mix(test_conf.frame_sizes)
        self._get_use_port_speed()

    async def set_rx_tables(self) -> None:
        await self.set_arp_trucks(self.properties.arp_trunks)
        await self.set_ndp_trucks(self.properties.ndp_trunks)

    def get_capped_port_speed(self) -> float:
        """ compare physical port speed and custom port speed """
        port_speed = self.properties.physical_port_speed
        if self._port_conf.port_rate_cap_profile.is_custom:
            port_speed = min(self._port_conf.port_rate, port_speed)
        return port_speed

    def _get_use_port_speed(self) -> float:
        """ compare tx and rx port speed and get the min one """
        tx_speed = self.get_capped_port_speed()
        if self._port_conf.peer_slot is not None and len(self.properties.peers) == 1:
            # Only Pair Topology Need to query peer speed
            peer_struct = self.properties.peers[0]
            rx_speed = peer_struct.get_capped_port_speed()
            tx_speed = min(tx_speed, rx_speed)
        self.set_send_port_speed(
            tx_speed * (1e6 - self._port_conf.speed_reduction_ppm) / 1e6
        )
        return self.send_port_speed

    async def query(self) -> None:
        """ read port statistics """
        extra = self.port_ins.statistics.rx.extra.get()
        stream_tasks = [stream_struct.query() for stream_struct in self.stream_structs]
        extra_tasks = [extra] if self.port_conf.is_rx_port else []
        results = await asyncio.gather(*extra_tasks, *stream_tasks)
        if self.port_conf.is_rx_port:
            # Only the RX port need to read gap data. Gap Monitor is set on the RX port
            extra_r: commands.PR_EXTRA.GetDataAttr = results[0]
            self._statistic.fcs_error_frames = extra_r.fcs_error_count
            self._statistic.gap_duration = extra_r.gap_duration
            self._statistic.gap_count = extra_r.gap_count


TypeConf = Union["ThroughputTest", "LatencyTest", "FrameLossRateTest", "BackToBackTest"]


@dataclass
class Properties:
    num_modifiersL2: int = 1
    dest_port_count: int = 0
    test_port_index: int = 0
    high_dest_port_count: int = 0
    low_dest_port_count: int = 0
    lowest_dest_port_index: int = -1
    highest_dest_port_index: int = -1
    address_refresh_data_set: Set[ArpRefreshData] = field(default_factory=set)
    peers: List["PortStruct"] = field(default_factory=list)
    arp_trunks: Set[RXTableData] = field(default_factory=set)
    ndp_trunks: Set[RXTableData] = field(default_factory=set)

    rate_percent: float = 0.0
    send_port_speed: float = 0.0
    native_mac_address: MacAddress = MacAddress()
    arp_mac_address: MacAddress = MacAddress()
    traffic_status: bool = False
    sync_status: bool = True
    physical_port_speed: float = 0.0

    def get_modifier_range(self, stream_id: int) -> Tuple[int, int]:
        """ calculate modifier range by test_port_index. """
        if stream_id == 0:
            if self.num_modifiersL2 == 2:
                modifier_range = (
                    self.lowest_dest_port_index,
                    self.test_port_index - 1,
                )
            elif self.dest_port_count > 0:
                modifier_range = (
                    self.lowest_dest_port_index,
                    self.highest_dest_port_index,
                )
            else:
                modifier_range = (
                    self.test_port_index,
                    self.test_port_index,
                )
        else:
            modifier_range = (
                self.test_port_index + 1,
                self.highest_dest_port_index,
            )

        return modifier_range

    def register_peer(self, peer: "PortStruct") -> None:
        if peer not in self.peers:
            self.peers.append(peer)
        if peer.properties.test_port_index == self.test_port_index:
            return
        self.dest_port_count += 1
        if peer.properties.test_port_index < self.test_port_index:
            self.low_dest_port_count += 1
        elif peer.properties.test_port_index > self.test_port_index:
            self.high_dest_port_count += 1
        self.num_modifiersL2 = (
            2 if (self.low_dest_port_count > 0 and self.high_dest_port_count > 0) else 1
        )
        self.lowest_dest_port_index = (
            peer.properties.test_port_index
            if self.lowest_dest_port_index == -1
            else min(self.lowest_dest_port_index, peer.properties.test_port_index)
        )
        self.highest_dest_port_index = (
            peer.properties.test_port_index
            if self.highest_dest_port_index == -1
            else max(self.highest_dest_port_index, peer.properties.test_port_index)
        )
