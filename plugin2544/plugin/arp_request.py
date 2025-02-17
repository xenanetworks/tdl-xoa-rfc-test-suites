"""
ARP (Address Resolution Protocol) and NDP (Neighbor Discovery Protocol) are used for discovering the link layer address, 
such as a MAC address, associated with a given internet layer address, typically an IPv4 address (ARP) and an IPv6 address (NDP).
"""

import asyncio
from typing import TYPE_CHECKING
from xoa_driver import utils, enums
from .common import is_same_ipnetwork
from ..utils.field import IPv4Address, IPv6Address, MacAddress
from ..utils.packet import Ether, IPV4Packet, IPV6Packet
from ..utils.traffic_definitions import EtherType
from ..utils.constants import DELAY_LEARNING_ARP
from ..utils.exceptions import ARPRequestError


if TYPE_CHECKING:
    from .structure import PortStruct
    from ..utils.field import IPAddress


async def set_arp_request(
    port_struct: "PortStruct",
    peer_struct: "PortStruct",
    use_gateway_mac_as_dmac: bool,
) -> "MacAddress":
    """ 
    ARP request requires:
    1. use_gateway_mac_as_dmac is true
    2. TX and a RX ports' protocol segment profiles have IPv4 or IPv6 in them
    3. ports are in different IP networks with different gateway addresses.
    """
    ip_properties = port_struct.port_conf.ip_address
    peer_ip_properties = peer_struct.port_conf.ip_address
    if any(
        (
            not use_gateway_mac_as_dmac,
            ip_properties
            and ip_properties.gateway.is_empty,
            not port_struct.port_conf.profile.protocol_version.is_l3,
            is_same_ipnetwork(port_struct, peer_struct),
        )
    ):
        # return an empty Macaddress if no arp mac
        # If the network addresses of two IP addresses are the same, then these two IP addresses are in the same network
        return MacAddress()
    if ip_properties and peer_ip_properties:
        is_gateway_scenario = not ip_properties.gateway == peer_ip_properties.gateway   # ignore
        if is_gateway_scenario: # Scenario 1 - From One IP Network to Another
            """
            When you want to send test frames from one IP network to a different IP network. 
            You will need to send ARP/NDP requests to a port's gateway address in order to resolve its gateway MAC address.
            """
            destination_ip = ip_properties.gateway

        elif ip_properties.gateway.is_empty and ip_properties.remote_loop_address:  # Scenario 2 - IP Loop Back
            """ 
            When you want to send test IP packets from port to the DUT and the packets are looped back to the port. 
            You will need to send ARP/NDP requests to a port's remote loop IP address in order to resolve MAC address of the loop port on the DUT.
            """
            destination_ip = ip_properties.remote_loop_address

        else:   # Scenario 3 - From One IP Network to Another IP Network Behind NAT
            """
            When you want to send test frames from one IP network to a different IP network that is behind a NAT router. 
            You will need to send ARP/NDP requests to the other network's NAT public address in order to resolve MAC address of the public address of that network.
            """
            destination_ip = peer_ip_properties.public_address
            
        arp_mac = await send_arp_request(port_struct, ip_properties.address, destination_ip)
        if is_gateway_scenario:
            """
            YOU have the responsibility to store the MAC address and use it in the test stream configuration phase as the DMAC of all streams on the port. 
            This dummy stream has served its purpose and can be deleted afterwards.
            """
            port_struct.port_conf.ip_gateway_mac_address = arp_mac
        return arp_mac
    else:
        return MacAddress()


def get_packet_header(
    port_struct: "PortStruct", source_ip: "IPAddress", destination_ip: "IPAddress"
) -> str:
    """ 
    return a packet header with stream src and dest mac address and ip address
    """
    if port_struct.protocol_version.is_ipv4:    
        ether_type = EtherType.IPV4
        src_addr = IPv4Address(source_ip)
        dst_addr = IPv4Address(destination_ip)
        ip_header = IPV4Packet(source_ip=src_addr, destination_ip=dst_addr)
    else:
        ether_type = EtherType.IPV6
        src_addr = IPv6Address(source_ip)
        dst_addr = IPv6Address(destination_ip)
        ip_header = IPV6Packet(source_ip=src_addr, destination_ip=dst_addr)
    mac_address = port_struct.properties.native_mac_address
    ether_header = Ether(smac=mac_address, type=ether_type)
    packet_header = ether_header.hexstring + ip_header.hexstring
    return packet_header


async def send_arp_request(
    port_struct: "PortStruct",
    source_ip: "IPAddress",
    destination_ip: "IPAddress",
) -> "MacAddress":
    """ 
    Create a stream to query arp request 
    Use PS_ARPREQUEST to let xenaserver to send out an ARP/NDP request, wait for response, and resolve the MAC address for you. 
    If the ARP/NDP is successful, you will get the MAC address from the variable. 
    If not, you will get an error response. This ARP process may take some milliseconds. You can wait until you have a result.
    """
    packet_header = get_packet_header(port_struct, source_ip, destination_ip)
    stream = await port_struct.create_stream()
    ip_protocol = enums.ProtocolOption.IP if port_struct.protocol_version.is_ipv4 else enums.ProtocolOption.IPV6
    await utils.apply(  # Make a dummy stream to send arp
        stream.packet.limit.set(-1),
        stream.comment.set("Stream 0 / 0"),
        stream.rate.fraction.set(0),
        stream.burst.burstiness.set(-1, 100),
        stream.burst.gap.set(0, 0),
        stream.packet.header.protocol.set(
            [enums.ProtocolOption.ETHERNET, ip_protocol]
        ),
        stream.packet.header.data.set(packet_header),
        stream.packet.length.set(enums.LengthType.FIXED, 64, 1518),  # PS_PACKETLENGTH
        stream.payload.content.set(enums.PayloadType.INCREMENTING, "00"),
        stream.tpld_id.set(-1),
        stream.insert_packets_checksum.set(enums.OnOff.ON),
        stream.gateway.ipv4.set("0.0.0.0"),
        stream.gateway.ipv6.set("::"),
        stream.enable.set(enums.OnOffWithSuppress.ON),
    )
    await asyncio.sleep(DELAY_LEARNING_ARP) # make sure stream config is set
    try:
        result, *_ = await utils.apply(stream.request.arp.get())
    except:
        raise ARPRequestError()
    peer_mac_address = MacAddress(result.mac_address)
    await stream.delete()   # need to delete the stream after arp request
    return peer_mac_address
