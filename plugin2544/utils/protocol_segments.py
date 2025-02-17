from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from ..model.m_protocol_segment import ProtocolSegment
    from ..utils.field import IPv4Address, IPv6Address, MacAddress


ETHERNET_ADDRESS_SRC = "Src MAC addr"
ETHERNET_ADDRESS_DST = "Dst MAC addr"
IPV4_ADDRESS_SRC = "Src IP Addr"
IPV4_ADDRESS_DST = "Dest IP Addr"
IPV6_ADDRESS_SRC = "Src IPv6 Addr"
IPV6_ADDRESS_DST = "Dest IPv6 Addr"


def setup_segment_ethernet(
    segment: "ProtocolSegment",
    src_mac: "MacAddress",
    dst_mac: "MacAddress",
    arp_mac: Optional["MacAddress"] = None,
) -> None:
    dst_mac = dst_mac if not arp_mac or arp_mac.is_empty else arp_mac
    if not dst_mac.is_empty and segment[ETHERNET_ADDRESS_DST].is_all_zero:
        segment[ETHERNET_ADDRESS_DST] = dst_mac.to_binary_string()
    if not src_mac.is_empty and segment[ETHERNET_ADDRESS_SRC].is_all_zero:
        segment[ETHERNET_ADDRESS_SRC] = src_mac.to_binary_string()


def setup_segment_ipv4(
    segment: "ProtocolSegment", src_ipv4: "IPv4Address", dst_ipv4: "IPv4Address"
) -> None:
    if segment[IPV4_ADDRESS_SRC].is_all_zero:
        segment[IPV4_ADDRESS_SRC] = src_ipv4.to_binary_string()
    if segment[IPV4_ADDRESS_DST].is_all_zero:
        segment[IPV4_ADDRESS_DST] = dst_ipv4.to_binary_string()


def setup_segment_ipv6(
    segment: "ProtocolSegment", src_ipv6: "IPv6Address", dst_ipv6: "IPv6Address"
) -> None:
    if not src_ipv6 or segment[IPV6_ADDRESS_SRC].is_all_zero:
        segment[IPV6_ADDRESS_SRC] = src_ipv6.to_binary_string()
    if not dst_ipv6 or segment[IPV6_ADDRESS_DST].is_all_zero:
        segment[IPV6_ADDRESS_DST] = dst_ipv6.to_binary_string()
