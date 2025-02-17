import struct
from typing import Union
from dataclasses import dataclass
from enum import Enum
from .field import MacAddress, IPv4Address, IPv6Address
from .traffic_definitions import EtherType, NextHeaderOption


def padding(num) -> str:
    return "0" * num


class Packet:
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
    dmac: MacAddress = MacAddress("FFFFFFFFFFFF")
    smac: MacAddress = MacAddress("FFFFFFFFFFFF")
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
    smac: MacAddress = MacAddress("FFFFFFFFFFFF")
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
        for chunk in struct.unpack("!%sH" % num_words, packet[0 : num_words * 2]):
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


@dataclass
class ARPPacket(Packet):
    arp_hardware_type: str = "0001"
    arp_protocol_type: str = "0800"
    hardware_size: str = "06"
    protocol_size: str = "04"
    opcode: str = "0001"
    smac: MacAddress = MacAddress("FFFFFFFFFFFF")
    source_ip: IPv4Address = IPv4Address("0.0.0.0")
    dmac: MacAddress = MacAddress("FFFFFFFFFFFF")
    destination_ip: IPv4Address = IPv4Address("0.0.0.0")

    def make_arp_packet(self) -> str:  # FormatArpPacket
        return (
            Ether(smac=self.smac, dmac=self.dmac, type=EtherType.ARP).hexstring
            + self.hexstring
            + padding(44)
        )
