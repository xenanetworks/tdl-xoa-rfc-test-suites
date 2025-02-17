from ..utils.field import NewIPv4Address, NewIPv6Address, MacAddress
from ..utils.constants import (
    IPVersion,
    IP_V4_MULTICAST_MAC_BASE_ADDRESS,
    IP_V6_MULTICAST_MAC_BASE_ADDRESS,
)
from typing import Union


def get_multicast_mac_for_ip(mc_ip_address: Union[NewIPv4Address, NewIPv6Address]):
    ip_address_bytes = mc_ip_address.int_list
    ip_version = IPVersion.IPV4 if mc_ip_address.version == 4 else IPVersion.IPV6
    if ip_version == IPVersion.IPV4:
        mac_address = MacAddress(IP_V4_MULTICAST_MAC_BASE_ADDRESS)
        m_dic = {
            1: ip_address_bytes[1] & 0x7F,
            4: ip_address_bytes[2],
            5: ip_address_bytes[3],
        }
        new_mac = mac_address.modify(m_dic)
        return new_mac
    else:
        mac_address = MacAddress(IP_V6_MULTICAST_MAC_BASE_ADDRESS)
        m_dic = {
            2: ip_address_bytes[12],
            3: ip_address_bytes[13],
            4: ip_address_bytes[14],
            5: ip_address_bytes[15],
        }
        new_mac = mac_address.modify(m_dic)
        return new_mac


def get_link_local_uc_ipv6_address(mac_address: MacAddress) -> bytearray:
    return bytearray([0xFE, 0x80] + [0 for _ in range(6)]) + get_eui64_ident_from_mac(
        mac_address
    )


def get_eui64_ident_from_mac(mac_address: MacAddress) -> bytearray:
    mac_bytes = mac_address.bytearrays
    return bytearray(
        [
            mac_bytes[0] | 0x02,
            mac_bytes[1],
            mac_bytes[2],
            0xFF,
            0xFE,
            mac_bytes[3],
            mac_bytes[4],
            mac_bytes[5],
        ]
    )
