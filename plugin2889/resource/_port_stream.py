import asyncio
import math
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Union
from loguru import logger
from xoa_driver.utils import apply
from xoa_driver.misc import Hex

if TYPE_CHECKING:
    from xoa_driver.misc import GenuineStream
    from .test_resource import TestResource

from plugin2889.dataset import RateDefinition
from plugin2889.plugin import rate_helper
from plugin2889.plugin import utils
from plugin2889.dataset import AddressCollection, IPv4Address, IPv6Address, MacAddress
from plugin2889.const import DEFAULT_INTERFRAME_GAP, PacketSizeType


class StreamManager:
    __slots__ = ("stream_id", "tpld_id", "__resource", "__peer_mac", "packet_size", "__peer_resource", "__stream")

    def __init__(self, stream_id, tpld_id: int, resource: "TestResource", peer_resource: "TestResource") -> None:
        self.stream_id = stream_id
        self.tpld_id = tpld_id
        self.__resource = resource
        self.__peer_mac: Optional["MacAddress"] = None
        self.packet_size: int = 0
        self.__peer_resource = peer_resource
        self.__stream: Optional["GenuineStream"] = None

    def __get_address_collection(self) -> AddressCollection:
        assert self.__resource.mac_address and self.__peer_resource.mac_address
        return AddressCollection(
            smac=self.__resource.mac_address,
            dmac=self.__peer_mac or self.__peer_resource.mac_address,
            src_ipv4_addr=IPv4Address(self.__resource.port_config.ipv4_properties.address),
            dst_ipv4_addr=IPv4Address(self.__peer_resource.port_config.ipv4_properties.dst_addr),
            src_ipv6_addr=IPv6Address(self.__resource.port_config.ipv6_properties.address),
            dst_ipv6_addr=IPv6Address(self.__peer_resource.port_config.ipv6_properties.dst_addr),
        )

    @property
    def header(self) -> str:
        """Prepare Packet Header data"""
        assert self.__resource.mac_address
        addresses = self.__get_address_collection()
        profile = self.__resource.port_config.profile.copy(deep=True)
        for index, segment in enumerate(profile.header_segments):
            if segment.segment_type.is_ethernet and index == 0:
                utils.setup_segment_ethernet(segment, addresses.smac, addresses.dmac)
            if segment.segment_type.is_ipv4:
                utils.setup_segment_ipv4(segment, addresses.src_ipv4_addr, addresses.dst_ipv4_addr)
            if segment.segment_type.is_ipv6:
                utils.setup_segment_ipv6(segment, addresses.src_ipv6_addr, addresses.dst_ipv6_addr)

        return f"{profile.prepare().hex()}"

    @property
    def total_stream_count(self) -> int:
        return len(self.__resource.port.streams)

    async def setup_stream(self) -> None:
        port = self.__resource.port
        stream = await port.streams.create()
        self.__stream = stream
        assert stream
        await apply(
            stream.tpld_id.set(self.tpld_id),
            stream.packet.header.protocol.set(self.__resource.port_config.profile.segment_id_list),
            stream.packet.header.data.set(Hex(self.header)),
            stream.payload.content.set_inc_byte(f"{'0'*36}"),
            stream.insert_packets_checksum.set_on(),
            stream.enable.set_on(),
            stream.comment.set(f"Stream {self.stream_id} / {self.tpld_id}")
        )
        logger.debug(f'{port.kind}, {stream.kind}, {self.tpld_id}, from {self.__resource.mac_address} to {self.__peer_mac}')

    async def set_rate_fraction(self, rate: Decimal):
        rate /= self.total_stream_count  # set streams rate equally
        await asyncio.gather(*[s.rate.fraction.set(math.floor(rate * 10000)) for s in self.__resource.port.streams])

    async def configure_stream(self, size: int, rate: Decimal) -> None:
        rate /= self.total_stream_count  # set streams rate equally
        coroutines = []
        for stream in self.__resource.port.streams:
            coroutines.append(stream.packet.length.set_fixed(size, size))
            coroutines.append(stream.rate.fraction.set(math.floor(rate * 10000)))
        await asyncio.gather(*coroutines)

    def is_match_peer_mac_address(self, mac_address: Optional["MacAddress"] = None) -> bool:
        return self.__peer_mac == mac_address or self.__peer_resource.mac_address == mac_address

    async def set_peer_mac_address(self, new_peer_mac_address: "MacAddress") -> None:
        logger.debug(f"{self}, {new_peer_mac_address}")
        self.__peer_mac = new_peer_mac_address
        await asyncio.gather(*[stream.packet.header.data.set(Hex(self.header)) for stream in self.__resource.port.streams])

    async def set_fixed_packet_size(self, size) -> None:
        asyncio.gather(*[stream.packet.length.set_fixed(size, size) for stream in self.__resource.port.streams])

    async def set_packet_size(self, packet_size_type: PacketSizeType, min_size: int, max_size: int) -> None:
        asyncio.gather(*[stream.packet.length.set(packet_size_type.to_xmp(), min_size, max_size) for stream in self.__resource.port.streams])

    async def set_packet_limit(self, total_packets: Union[int, float, Decimal]) -> None:
        logger.debug(total_packets)
        assert self.__stream
        await self.__stream.packet.limit.set(int(total_packets))

    async def set_rate_pps(self, pps: Union[int, float, Decimal], ) -> None:
        assert self.__stream
        await self.__stream.rate.pps.set(math.floor(pps))

    async def set_rate_l2bps(self, l2bps: Decimal) -> None:
        assert self.__stream
        await self.__stream.rate.l2bps.set(math.floor(l2bps))

    async def set_rate_and_packet_limit_fraction(self, packet_size: int, rate_percent: Decimal, traffic_duration: int, rate_definition: RateDefinition) -> None:
        port_speed = await self.__resource.get_used_port_speed()
        rate_percent = rate_percent * Decimal(rate_definition.rate_fraction) / Decimal(100)
        factor = (packet_size + DEFAULT_INTERFRAME_GAP) / (packet_size + self.__resource.interframe_gap)  # if interframe gap delta
        bps_rate_l1 = Decimal(factor) * Decimal(port_speed) * rate_percent / Decimal(100) / self.total_stream_count
        stream_packet_rate = bps_rate_l1 / Decimal(8) / (packet_size + DEFAULT_INTERFRAME_GAP)
        await asyncio.gather(*(
            self.set_rate_fraction(rate_percent),
            self.set_packet_limit(math.floor(stream_packet_rate * traffic_duration)),
        ))

    async def set_rate_and_packet_limit_pps(self, rate_percent: Decimal, traffic_duration: int, rate_definition: RateDefinition) -> None:
        pps = math.floor(rate_percent * Decimal(rate_definition.rate_pps) / Decimal(100) / self.total_stream_count)
        await asyncio.gather(*(
            self.set_rate_pps(pps),
            self.set_packet_limit(pps * traffic_duration),
        ))

    async def set_rate_and_packet_limit_l1bps(self, packet_size: int, rate_percent: Decimal, traffic_duration: int, rate_definition: RateDefinition) -> None:
        bps_rate_l1 = Decimal(rate_definition.rate_bps_l1 * rate_definition.rate_bps_l1_unit.to_int)
        bps_rate_l1 = rate_percent * bps_rate_l1 / Decimal(100) / self.total_stream_count
        bps_rate_l2 = rate_helper.calc_l2_bit_rate_from_l1_bit_rate(bps_rate_l1, packet_size, self.__resource.interframe_gap)
        packet_rate = rate_helper.calc_l2_frame_rate(bps_rate_l2, packet_size)
        await asyncio.gather(*(
            self.set_rate_l2bps(bps_rate_l2),
            self.set_packet_limit(packet_rate * traffic_duration),
        ))

    async def set_rate_and_packet_limit_l2bps(self, packet_size: int, rate_percent: Decimal, traffic_duration: int, rate_definition: RateDefinition) -> None:
        bps_rate_l2 = Decimal(rate_definition.rate_bps_l2 * rate_definition.rate_bps_l2_unit.to_int)
        bps_rate_l2 = rate_percent * bps_rate_l2 / Decimal(100) / self.total_stream_count
        packet_rate = rate_helper.calc_l2_frame_rate(bps_rate_l2, packet_size)
        await asyncio.gather(*(
            self.set_rate_l2bps(bps_rate_l2),
            self.set_packet_limit(packet_rate * traffic_duration),
        ))

    async def set_rate_and_packet_limit(self, packet_size: int, rate_percent: Decimal, traffic_duration: int, rate_definition: RateDefinition) -> None:
        packet_size = packet_size or self.packet_size
        #logger.debug(f'{self}, {packet_size} {rate_percent} {traffic_duration}')

        if rate_definition.is_fraction:
            await self.set_rate_and_packet_limit_fraction(packet_size, rate_percent, traffic_duration, rate_definition)
        elif rate_definition.is_pps:
            await self.set_rate_and_packet_limit_pps(rate_percent, traffic_duration, rate_definition)
        elif rate_definition.is_l1bps:
            await self.set_rate_and_packet_limit_l1bps(packet_size, rate_percent, traffic_duration, rate_definition)
        elif rate_definition.is_l2bps:
            await self.set_rate_and_packet_limit_l2bps(packet_size, rate_percent, traffic_duration, rate_definition)
