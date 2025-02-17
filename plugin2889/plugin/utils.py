import os
import asyncio
import inspect
import struct
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Union,
)
from enum import Enum
from dataclasses import dataclass
from itertools import combinations
from collections import defaultdict
from pydantic import BaseModel
from loguru import logger
from xoa_core.types import PortIdentity

from plugin2889.model import exceptions
from plugin2889.dataset import IPv4Address, IPv6Address, MacAddress, PortPair
from plugin2889.dataset import PortConfiguration, PortRoleHandler
from plugin2889.model.protocol_segment import SegmentType, PortProtocolVersion
from plugin2889.const import (
    PortGroup,
    TestTopology,
    TrafficDirection,
)

if TYPE_CHECKING:
    from ..model.protocol_segment import ProtocolSegment
    from xoa_driver.testers import L23Tester


ETHERNET_ADDRESS_SRC = 'Src MAC addr'
ETHERNET_ADDRESS_DST = 'Dst MAC addr'
IPV4_ADDRESS_SRC = 'Src IP Addr'
IPV4_ADDRESS_DST = 'Dest IP Addr'
IPV6_ADDRESS_SRC = 'Src IPv6 Addr'
IPV6_ADDRESS_DST = 'Dest IPv6 Addr'

PortPairs = Iterable[PortPair]


class EtherType(Enum):
    IPV4 = "0800"
    IPV6 = "86dd"
    ARP = "0806"


class NextHeaderOption(Enum):
    ICMP = 1
    IGMP = 2
    TCP = 6
    UDP = 17
    ICMPV6 = 58
    DEFALUT = 59
    SCTP = 132


class Padding(str):
    def __new__(cls, num) -> str:
        return "0" * num


class Packet:
    @property
    def hex(self):
        """return \x00\x00\x00"""
        pass

    @property
    def bytestring(self):
        """return b'0000000'"""
        pass

    @property
    def hexstring(self) -> str:
        """return '0000000'"""
        packet = ""
        for value in self.__dict__.values():
            if isinstance(value, (MacAddress, IPv4Address, IPv6Address)):
                packet += value.to_hexstring()
            elif isinstance(value, Enum):
                if isinstance(value.value, str):
                    packet += value.value
                elif isinstance(value.value, int):
                    packet += hex(value.value)[2:]
                else:
                    raise Exception("Not Support Enum value type Except (str, int)")
            else:
                packet += value
        return packet


@dataclass
class Ether(Packet):
    dmac: MacAddress = MacAddress("FF:FF:FF:FF:FF:FF")
    smac: MacAddress = MacAddress("FF:FF:FF:FF:FF:FF")
    type: EtherType = EtherType.IPV6


@dataclass
class IPV4Packet(Packet):
    version: str = "4"
    header_length: str = "5"
    dscp: str = "000"
    ecn: str = "0"
    total_length: str = "14"
    identification: str = "0000"
    flags_fragment: str = "0000"
    ttl: str = "7F"
    protocol: str = "FF"
    header_checksum: str = "0000"
    source_ip: IPv4Address = IPv4Address("0.0.0.0")
    destination_ip: IPv4Address = IPv4Address("0.0.0.0")


@dataclass
class IPV6Packet(Packet):
    ip_version: str = "6"
    traffic_class: str = "00"
    flow_label: str = "00000"
    payload_length: str = "0000"
    next_header: NextHeaderOption = NextHeaderOption.DEFALUT
    hop_limit: str = "ff"
    source_ip: IPv6Address = IPv6Address("::")
    destination_ip: Union[IPv6Address, str] = IPv6Address("::")


@dataclass
class ICMPV6Packet(Packet):
    icmpv6_type: str = "88"
    icmpv6_code: str = "00"
    icmpv6_checksum: str = "0000"
    icmpv6_flags: str = "20000000"
    source_ip: IPv6Address = IPv6Address("::")
    icmpv6_option: str = "0201"
    smac: MacAddress = MacAddress("FF:FF:FF:FF:FF:FF")
    padding: str = "00000000"

    def calculate_checksum(self, destination_ip: IPv6Address):
        pseudo_header = self.build_pseudo_header(destination_ip)
        icmpv6_chunk = self.build_icmpv6_chunk()
        icmpv6_packet = pseudo_header + icmpv6_chunk
        checksum = self.calculate_icmpv6_checksum(icmpv6_packet)
        self.icmpv6_checksum = "{:>4X}".format(checksum).replace(" ", "0")
        return self

    def build_pseudo_header(self, destination_ip: Union[IPv6Address, str]) -> bytes:
        source_ip_bytes = self.source_ip.to_bytearray()
        dest_ip_bytes = (
            destination_ip.to_bytearray()
            if isinstance(destination_ip, IPv6Address)
            else bytearray.fromhex(destination_ip)
        )
        next_header = struct.pack(">I", NextHeaderOption.ICMPV6.value)
        upper_layer_len = struct.pack(">I", 32)
        return source_ip_bytes + dest_ip_bytes + upper_layer_len + next_header

    def build_icmpv6_chunk(self) -> bytes:
        type_code_bytes = bytearray.fromhex(self.icmpv6_type + self.icmpv6_code)
        checksum = struct.pack(">I", 0)
        other_bytes = bytearray.fromhex(
            "".join(
                [
                    self.icmpv6_flags,
                    self.source_ip.to_hexstring(),
                    self.icmpv6_option,
                    self.smac.to_hexstring(),
                ]
            )
        )
        return type_code_bytes + checksum + other_bytes

    @staticmethod
    def calculate_icmpv6_checksum(packet: bytes) -> int:
        """Calculate the ICMPv6 checksum for a packet.

        :param packet: The packet bytes to checksum.
        :returns: The checksum integer.
        """
        total = 0

        # Add up 16-bit words
        num_words = len(packet) // 2
        for chunk in struct.unpack("!%sH" % num_words, packet[0: num_words * 2]):
            total += chunk

        # Add any left over byte
        if len(packet) % 2:
            total += packet[-1] << 8

        # Fold 32-bits into 16-bits
        total = (total >> 16) + (total & 0xFFFF)
        total += total >> 16
        return ~total + 0x10000 & 0xFFFF


@dataclass
class NDPPacket(Packet):
    source_ip: IPv6Address
    destination_ip: IPv6Address
    smac: MacAddress
    dmac: MacAddress

    def make_ndp_packet(self) -> str:  # FormatNdpPacket
        icmp_packet = ICMPV6Packet(
            source_ip=self.source_ip, smac=self.smac
        ).calculate_checksum(self.destination_ip)
        return (
            Ether(smac=self.smac, dmac=self.dmac, type=EtherType.IPV6).hexstring
            + IPV6Packet(
                source_ip=self.source_ip,
                destination_ip=self.destination_ip,
                payload_length="0020",
            ).hexstring
            + icmp_packet.hexstring
        )


class GroupByPortProperty(BaseModel):
    uuid_role: Dict[str, str] = {}
    port_role_uuids: Dict[PortGroup, List[str]] = defaultdict(list)
    uuid_slot: Dict[str, str] = {}
    port_name_role: Dict[str, str] = {}
    uuid_port_name: Dict[str, str] = {}
    port_peer: Dict[str, str] = {}

def group_by_port_property(
    port_configuration: Dict[str, PortConfiguration],
    port_role: PortRoleHandler,
    port_identities: List[PortIdentity],
) -> "GroupByPortProperty":
    result = GroupByPortProperty()

    not_use_port_uuid = []
    for guid, port_role_config in port_role.role_map.items():
        uuid = guid.split("guid_", 1)[1]
        result.uuid_role[uuid] = port_role_config.role.value
        result.port_role_uuids[port_role_config.role].append(uuid)
        if not port_role_config.is_used:
            not_use_port_uuid.append(uuid)
        result.port_peer[uuid] = port_role_config.peer_port_id

    for port_name, port_config in port_configuration.items():
        uuid = port_config.item_id
        if uuid in not_use_port_uuid:
            continue
        result.uuid_slot[port_config.item_id] = port_config.port_slot
        result.uuid_port_name[port_config.item_id] = port_name

    # logger.debug(result)
    return result


def create_pairs_mesh(group_by_property: GroupByPortProperty) -> PortPairs:
    pairs = []
    for slot1, slot2 in combinations(group_by_property.uuid_port_name.values(), 2):
        pairs.append(PortPair(west=slot1, east=slot2))
        pairs.append(PortPair(west=slot2, east=slot1))
    return pairs


def create_pairs_pair(group_by_property: GroupByPortProperty, traffic_direction: TrafficDirection, role_source: PortGroup) -> PortPairs:
    pairs = []
    for port_uuid in group_by_property.port_role_uuids[role_source]:
        peer_uuid = group_by_property.port_peer[port_uuid]
        pairs.append(PortPair(west=group_by_property.uuid_port_name[port_uuid], east=group_by_property.uuid_port_name[peer_uuid]))
        if traffic_direction == TrafficDirection.BIDIR:
            pairs.append(PortPair(east=group_by_property.uuid_port_name[port_uuid], west=group_by_property.uuid_port_name[peer_uuid]))
    return pairs


def create_pairs_blocks(group_by_property: GroupByPortProperty, traffic_direction: TrafficDirection, role_source: PortGroup, role_destination: PortGroup) -> PortPairs:
    pairs = []
    for port_uuid in group_by_property.port_role_uuids[role_source]:
        for peer_uuid in group_by_property.port_role_uuids[role_destination]:
            pairs.append(PortPair(west=group_by_property.uuid_port_name[port_uuid], east=group_by_property.uuid_port_name[peer_uuid]))
            if traffic_direction == TrafficDirection.BIDIR:
                pairs.append(PortPair(east=group_by_property.uuid_port_name[port_uuid], west=group_by_property.uuid_port_name[peer_uuid]))

    return pairs


def create_port_pair(
    traffic_direction: TrafficDirection,
    topology: TestTopology,
    port_configuration: Dict[str, PortConfiguration],
    port_role: Optional[PortRoleHandler],
    port_identities: List[PortIdentity],
) -> PortPairs:

    role_source = PortGroup.WEST
    role_destination = PortGroup.EAST
    if traffic_direction == TrafficDirection.EAST_TO_WEST:
        role_source, role_destination = role_destination, role_source

    assert port_role, 'invalid port role'
    group_by_property = group_by_port_property(port_configuration, port_role, port_identities)
    if topology.is_mesh_topology:
        pairs = create_pairs_mesh(group_by_property)
    elif topology.is_pair_topology:
        pairs = create_pairs_pair(group_by_property, traffic_direction, role_source)
    else:
        pairs = create_pairs_blocks(group_by_property, traffic_direction, role_source, role_destination)

    # logger.debug(pairs)
    assert pairs, 'empty port pairs'
    return pairs


async def sleep_log(duration: float) -> None:
    """debug helper for infinite while loop sleep"""
    caller_frame = inspect.stack()[1]
    message = f"\x1b[33;20m{caller_frame.filename.rsplit(os.path.sep, 1)[1]}:{caller_frame.lineno} {caller_frame.function} {duration}\x1B[0m"
    logger.debug(message)
    await asyncio.sleep(duration)


def is_ip_segment_exists(header_segments: List["ProtocolSegment"]) -> bool:
    for segment in header_segments:
        if segment.segment_type in (SegmentType.IPV4, SegmentType.IPV6):
            return True
    return False


IPAddress = Union[IPv4Address, IPv6Address]


def get_packet_header(
    source_ip: IPAddress, destination_ip: IPAddress, protocol_version: PortProtocolVersion, native_mac_address
) -> str:
    if protocol_version.is_ipv4:
        ether_type = EtherType.IPV4
        src_addr = IPv4Address(source_ip)
        dst_addr = IPv4Address(destination_ip)
        ip_header = IPV4Packet(source_ip=src_addr, destination_ip=dst_addr)
    else:
        ether_type = EtherType.IPV6
        src_addr = IPv6Address(source_ip)
        dst_addr = IPv6Address(destination_ip)
        ip_header = IPV6Packet(source_ip=src_addr, destination_ip=dst_addr)
    packet_header = (
        Ether(smac=native_mac_address, type=ether_type).hexstring + ip_header.hexstring
    )
    return packet_header


async def check_tester_sync_start(tester: "L23Tester", use_sync_start: bool) -> None:
    if not use_sync_start:
        return None
    cap = await tester.capabilities.get()
    if not bool(cap.can_sync_traffic_start):
        raise exceptions.NotSupportStaggering()


def setup_segment_ethernet(segment: "ProtocolSegment", src_mac: "MacAddress", dst_mac: "MacAddress") -> None:
    if not dst_mac.is_empty and segment[ETHERNET_ADDRESS_DST].is_all_zero:
        segment[ETHERNET_ADDRESS_DST] = dst_mac.to_binary_string()
    if not src_mac.is_empty and segment[ETHERNET_ADDRESS_SRC].is_all_zero:
        segment[ETHERNET_ADDRESS_SRC] = src_mac.to_binary_string()


def setup_segment_ipv4(segment: "ProtocolSegment", src_ipv4: "IPv4Address", dst_ipv4: "IPv4Address") -> None:
    if segment[IPV4_ADDRESS_SRC].is_all_zero:
        segment[IPV4_ADDRESS_SRC] = src_ipv4.to_binary_string()
    if segment[IPV4_ADDRESS_DST].is_all_zero:
        segment[IPV4_ADDRESS_DST] = dst_ipv4.to_binary_string()


def setup_segment_ipv6(segment: "ProtocolSegment", src_ipv6: "IPv6Address", dst_ipv6: "IPv6Address") -> None:
    if segment[IPV6_ADDRESS_SRC].is_all_zero:
        segment[IPV6_ADDRESS_SRC] = src_ipv6.to_binary_string()
    if segment[IPV6_ADDRESS_DST].is_all_zero:
        segment[IPV6_ADDRESS_DST] = dst_ipv6.to_binary_string()


def get_bytes_from_macaddress(dmac: "MacAddress") -> Iterator[str]:
    for i in range(0, len(dmac), 3):
        yield dmac[i: i + 2]


def get_link_local_uci_ipv6address(dmac: "MacAddress") -> str:
    b = get_bytes_from_macaddress(dmac)
    return f"FE80000000000000{int(next(b)) | 2 }{next(b)}{next(b)}FFFE{next(b)}{next(b)}{next(b)}"
