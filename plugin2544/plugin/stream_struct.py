import asyncio
from copy import deepcopy
from typing import List, Optional, TYPE_CHECKING
from xoa_driver import utils, enums, misc
from ..model.m_protocol_segment import (
    HWModifier,
    ModifierActionOption,
)
from .common import gen_macaddress
from .data_model import (
    AddressCollection,
    RXTableData,
    StreamOffset,
)
from .learning import add_address_refresh_entry
from .statistics import (
    DelayData,
    PRStatistic,
    StreamCounter,
    StreamStatisticData,
)
from ..utils.field import MacAddress, IPv4Address, IPv6Address
from ..utils import constants as const, protocol_segments as ps, exceptions
from collections import defaultdict
from loguru import logger

if TYPE_CHECKING:
    from .structure import PortStruct
    from .test_config import TestConfigData


class PTStream:
    def __init__(self, tx_port: "PortStruct", stream_id: int) -> None:
        self.tx_port = tx_port
        self.stream_id = stream_id
        self.statistic = StreamCounter()

    async def query(self) -> None:
        """ query statistic on TX port """
        tx_frames = await self.tx_port.port_ins.statistics.tx.obtain_from_stream(
            self.stream_id
        ).get()
        self.statistic = StreamCounter(
            frames=tx_frames.packet_count_since_cleared,
            bps=tx_frames.bit_count_last_sec,
            pps=tx_frames.packet_count_last_sec,
        )


class PRStream:
    def __init__(
        self, tx_port: "PortStruct", rx_port: "PortStruct", tpld_id: int
    ) -> None:
        self.tx_port = tx_port
        self.tpld_id = tpld_id
        self.rx_port = rx_port
        self.statistic: "PRStatistic" = PRStatistic()

    async def query(self) -> None:
        """ query statistic on rx port """
        rx = self.rx_port.port_ins.statistics.rx.access_tpld(self.tpld_id)
        rx_frames, error, ji, latency = await utils.apply(
            rx.traffic.get(),
            rx.errors.get(),
            rx.jitter.get(),
            rx.latency.get(),
        )
        self.statistic = PRStatistic(
            rx_stream_counter=StreamCounter(
                frames=rx_frames.packet_count_since_cleared,
                bps=rx_frames.bit_count_last_sec,
                pps=rx_frames.packet_count_last_sec,
                bytes_count=rx_frames.byte_count_since_cleared,
            ),
            live_loss_frames=error.non_incre_seq_event_count,
            latency=DelayData(
                counter_type=const.CounterType.LATENCY,
                minimum=latency.min_val,
                average=latency.avg_val,
                maximum=latency.max_val,
            ),
            jitter=DelayData(
                counter_type=const.CounterType.JITTER,
                minimum=ji.min_val,
                average=ji.avg_val,
                maximum=ji.max_val,
            ),
        )


class StreamStruct:
    def __init__(
        self,
        tx_port: "PortStruct",
        rx_ports: List["PortStruct"],
        stream_id: int,
        tpldid: int,
        arp_mac: MacAddress = MacAddress(),
        stream_offset: Optional["StreamOffset"] = None,
    ):
        self._tx_port: "PortStruct" = tx_port
        self._rx_ports: List["PortStruct"] = rx_ports
        self._stream_id: int = stream_id
        self._tpldid: int = tpldid
        self._arp_mac: MacAddress = arp_mac
        self.__is_stream_based: bool = True
        self._addr_coll: AddressCollection = AddressCollection()
        self._packet_header: bytearray = bytearray()
        self._stream_offset = stream_offset
        self._packet_limit: int = 0
        self._stream_statistic: StreamStatisticData = (
            StreamStatisticData()
        )  # record the latest statistic
        self._best_result: Optional[
            StreamStatisticData
        ] = None  # store best result for throughput per_port_result_scope, only for stream based

    def is_rx_port(self, peer_struct: "PortStruct"):
        return True if peer_struct in self._rx_ports else False

    @property
    def rx_port(self) -> "PortStruct":
        if self.__is_stream_based:
            return self._rx_ports[0]
        else:
            return self._tx_port

    @property
    def hw_modifiers(self) -> List["HWModifier"]:
        if self.__is_stream_based:
            return [
                modifier
                for header_segment in self._tx_port.port_conf.profile.segments
                for modifier in header_segment.hw_modifiers
            ]
        else:
            modifier_range = self._tx_port.properties.get_modifier_range(
                self._stream_id
            )
            hm = HWModifier(
                    mask="00FF",
                    start_value=modifier_range[0],
                    stop_value=modifier_range[1],
                    step_value=1,
                    action=ModifierActionOption.INC,
                    repeat=1,
                    offset=4,
            )
            hm.set_byte_segment_position(4)
            return [hm]

    @property
    def best_result(self) -> Optional["StreamStatisticData"]:
        return self._best_result

    def set_best_result(self) -> None:
        self._best_result = deepcopy(self._stream_statistic)

    def aggregate_best_result(self) -> None:
        if self._best_result:
            self._best_result.calculate(self._tx_port, self.rx_port)

    async def configure(self, test_conf: "TestConfigData") -> None:
        stream = await self._tx_port.create_stream()
        self._stream = stream
        base_mac = (
            test_conf.multi_stream_mac_base_address
            if test_conf.is_stream_based
            else test_conf.mac_base_address
        )
        self.__is_stream_based = test_conf.is_stream_based
        self._addr_coll = get_address_collection(
            self._tx_port,
            self.rx_port,
            base_mac,
            self._arp_mac,
            self._stream_offset,
        )
        await utils.apply(
            self._stream.enable.set(enums.OnOffWithSuppress.ON),
            self._stream.comment.set(f"Stream {self._stream_id} / {self._tpldid}"),
            self._stream.packet.header.protocol.set(
                self._tx_port.port_conf.profile.segment_id_list
            ),
            self._stream.payload.content.set(
                test_conf.payload_type.to_xmp(),
                misc.Hex(test_conf.payload_pattern), 
            ),
            self._stream.tpld_id.set(test_payload_identifier=self._tpldid),
            self._stream.insert_packets_checksum.set(enums.OnOff.ON),
        )
        await self.set_packet_header()
        await self.setup_modifier()
        self.init_rx_tables(
            test_conf.arp_refresh_enabled,
            test_conf.use_gateway_mac_as_dmac,
        )

    def init_rx_tables(
        self, arp_refresh_enabled: bool, use_gateway_mac_as_dmac: bool
    ) -> None:
        if not arp_refresh_enabled or not self._tx_port.protocol_version.is_l3:
            return
        if self._stream_offset and self._addr_coll.dst_addr:
            if self._tx_port.protocol_version.is_ipv4:
                self.rx_port.properties.arp_trunks.add(
                    RXTableData(self._addr_coll.dst_addr, self._addr_coll.dmac)
                )
            elif self._tx_port.protocol_version.is_ipv6:
                self.rx_port.properties.ndp_trunks.add(
                    RXTableData(self._addr_coll.dst_addr, self._addr_coll.dmac)
                )
            add_address_refresh_entry(
                self.rx_port,
                self._addr_coll.dst_addr,
                self._addr_coll.dmac,
            )
        else:
            add_address_refresh_entry(self.rx_port, None, None)

        if use_gateway_mac_as_dmac:
            add_address_refresh_entry(
                self._tx_port,
                None,
                None,
            )

    async def query(self) -> None:
        """
        aggregate pr_stream data into _stream_statistic
        pt_stream statistic should calculate in TX Port
        pr_stream statistic should calculate in RX port
        """
        pr_streams = [
            PRStream(self._tx_port, port, self._tpldid) for port in self._rx_ports
        ]
        pt_stream = PTStream(self._tx_port, self._stream_id)
        await asyncio.gather(
            pt_stream.query(), *[pr_stream.query() for pr_stream in pr_streams]
        )
        src_addr, dst_addr = self._addr_coll.get_addr_pair_by_protocol(
            self._tx_port.protocol_version
        )
        self._stream_statistic = StreamStatisticData(
            src_port_id=self._tx_port.port_identity.name,
            dest_port_id=self.rx_port.port_identity.name,
            src_port_addr=str(src_addr),
            dest_port_addr=str(dst_addr),
            burst_frames=self._packet_limit,
        )

        # polling TX and RX statistic not at the same time, may cause the rx statistic larger than tx statistic
        self._stream_statistic.tx_counter.add_stream_counter(pt_stream.statistic)
        for pr_stream in pr_streams:
            # aggregate data on rx port statistic based on pr_stream
            self._stream_statistic.add_pr_stream_statistic(pr_stream.statistic)
            async with pr_stream.rx_port.lock:
                pr_stream.rx_port.statistic.aggregate_rx_statistic(pr_stream.statistic)
        async with self._tx_port.lock:
            # aggregate data on tx port statistic based on pt_stream
            self._tx_port.statistic.aggregate_tx_statistic(self._stream_statistic)

    async def set_packet_header(self) -> None:
        """
        get packet header based on segment
        """
        # Insert all configured header segments in order
        profile = self._tx_port.port_conf.profile.copy(deep=True)
        for index, segment in enumerate(profile.segments):
            if segment.type.is_ethernet and index == 0:
                ps.setup_segment_ethernet(
                    segment,
                    self._addr_coll.smac,
                    self._addr_coll.dmac,
                    self._addr_coll.arp_mac,
                )
            if (
                segment.type.is_ipv4
                and isinstance(self._addr_coll.src_addr, IPv4Address)
                and isinstance(self._addr_coll.dst_addr, IPv4Address)
            ):
                ps.setup_segment_ipv4(
                    segment,
                    self._addr_coll.src_addr,
                    self._addr_coll.dst_addr,
                )
            if (
                segment.type.is_ipv6
                and isinstance(self._addr_coll.src_addr, IPv6Address)
                and isinstance(self._addr_coll.dst_addr, IPv6Address)
            ):
                ps.setup_segment_ipv6(
                    segment,
                    self._addr_coll.src_addr,
                    self._addr_coll.dst_addr,
                )

        self._packet_header = profile.prepare()
        await self._stream.packet.header.data.set(self._packet_header.hex())    # type: ignore

    async def setup_modifier(self) -> None:
        modifiers = self._stream.packet.header.modifiers
        await modifiers.configure(len(self.hw_modifiers))
        for mid, hw_modifier in enumerate(self.hw_modifiers):
            modifier = modifiers.obtain(mid)
            await modifier.specification.set(
                position=hw_modifier.byte_segment_position,
                mask=misc.Hex(f"{hw_modifier.mask}"),    
                action=hw_modifier.action.to_xmp(),
                repetition=hw_modifier.repeat,
            )
            await modifier.range.set(
                min_val=hw_modifier.start_value,
                step=hw_modifier.step_value,
                max_val=hw_modifier.stop_value,
            )

    async def set_packet_size(
        self, packet_size_type: enums.LengthType, min_size: int, max_size: int
    ) -> None:
        await self._stream.packet.length.set(packet_size_type, min_size, max_size)

    async def set_l2bps_rate(self, rate: int) -> None:
        await self._stream.rate.l2bps.set(rate)

    async def set_frame_limit(self, frame_count: int) -> None:
        self._packet_limit = frame_count
        if frame_count > const.MAX_PACKET_LIMIT_VALUE:
            raise exceptions.PacketLimitOverflow(frame_count)
        await self._stream.packet.limit.set(frame_count)


def get_address_collection(
    port_struct: "PortStruct",
    peer_struct: "PortStruct",
    mac_base_address: str,
    arp_mac: MacAddress,
    stream_offset: Optional[StreamOffset] = None,
) -> "AddressCollection":
    default_none = defaultdict(None)
    if (
        port_struct.port_conf.ip_address is None
        or peer_struct.port_conf.ip_address is None
    ):
        src_network = dst_network = default_none
        src_addr = dst_addr = None
        cls_src = cls_dst = None
    else:
        src_network = port_struct.port_conf.ip_address.network
        dst_network = peer_struct.port_conf.ip_address.network
        cls_src = port_struct.port_conf.ip_address.address.__class__
        cls_dst = peer_struct.port_conf.ip_address.address.__class__
        # TODO: Need to compare src and dst class?
        src_addr = port_struct.port_conf.ip_address.address
        dst_addr = peer_struct.port_conf.ip_address.dst_addr
    if stream_offset:
        return AddressCollection(
            arp_mac=arp_mac,
            smac=gen_macaddress(mac_base_address, stream_offset.tx_offset),
            dmac=gen_macaddress(mac_base_address, stream_offset.rx_offset),
            src_addr=cls_src(src_network[stream_offset.tx_offset]) if cls_src else None,
            dst_addr=cls_dst(dst_network[stream_offset.rx_offset]) if cls_dst else None,
        )
    else:
        return AddressCollection(
            arp_mac=arp_mac,
            smac=port_struct.properties.native_mac_address,
            dmac=peer_struct.properties.native_mac_address,
            src_addr=src_addr,
            dst_addr=dst_addr,
        )
