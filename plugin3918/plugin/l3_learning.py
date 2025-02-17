from asyncio import sleep, gather
from dataclasses import dataclass
from typing import Dict, List, Optional, Union
from xoa_driver import utils
from .test_result import AddressCollection
from ..utils.constants import (
    IPVersion,
    ProtocolOption,
)
from ..model.protocol_segments import (
    ProtocolSegmentProfileConfig,
)
from ..model.port_config import PortConfiguration
from ..utils.field import NewIPv4Address, NewIPv6Address, MacAddress
from ..plugin.resource_manager import PortInstance, get_ip_property
from .protocol_change import ProtocolChange

## SendGatewayArpRequests
@dataclass
class PortArpRefreshData:
    ip_version: IPVersion
    port_config: PortConfiguration
    stream_config: str
    gateway_mac: MacAddress = MacAddress("00:00:00:00:00:00")


def has_ip_segment(
    stream_config: "ProtocolSegmentProfileConfig",
) -> Optional[IPVersion]:
    for i in stream_config.header_segments:
        if i.type == ProtocolOption.IPV4:
            return IPVersion.IPV4
        elif i.type == ProtocolOption.IPV6:
            return IPVersion.IPV6
    return None


def add_address_refresh_entry(
    address_refresh_map: Dict[str, List["PortArpRefreshData"]],
    port_config: "PortConfiguration",
    ip_version: IPVersion,
    stream_config,
) -> Dict[str, List["PortArpRefreshData"]]:
    if not port_config.port_slot in address_refresh_map:
        address_refresh_map[port_config.port_slot] = []
    new_entry = PortArpRefreshData(
        ip_version=ip_version,
        port_config=port_config,
        stream_config=stream_config,
    )
    if new_entry not in address_refresh_map[port_config.port_slot]:
        address_refresh_map[port_config.port_slot].append(new_entry)

    return address_refresh_map


def make_address_collection(
    target_ip_address: Union["NewIPv4Address", "NewIPv6Address"],
    src_instance: "PortInstance",
    dmac: MacAddress = MacAddress("FF:FF:FF:FF:FF:FF"),
) -> AddressCollection:
    addr_coll = AddressCollection(
        smac=src_instance.native_mac_address,
        dmac=dmac,
        src_ipv4_addr=src_instance.config.ipv4_properties.address,
        src_ipv6_addr=src_instance.config.ipv6_properties.address,
    )

    if isinstance(target_ip_address, NewIPv6Address):
        addr_coll.dest_ipv6_addr = NewIPv6Address(target_ip_address)
    else:
        addr_coll.dst_ipv4_addr = NewIPv4Address(target_ip_address)
    return addr_coll


async def send_arp_learning_request(
    target_ip_address: Union["NewIPv4Address", "NewIPv6Address"],
    port_instance: "PortInstance",
    stream_config: "ProtocolSegmentProfileConfig",
):
    await port_instance.port.streams.server_sync()
    await gather(*[s.delete() for s in port_instance.port.streams])        
    stream = await port_instance.port.streams.create()
    await sleep(3)
    addr_coll = make_address_collection(target_ip_address, port_instance)
    packet_header = ProtocolChange.get_packet_header_inner(
        addr_coll, stream_config.header_segments, port_instance.can_tcp_checksum
    )
    *_, arp = await utils.apply(
        stream.packet.header.protocol.set(stream_config.header_segment_id_list),
        stream.packet.header.data.set(bytes(packet_header).hex()),
        stream.enable.set_on(),
        stream.request.arp.get(),
    )

    addr_coll.change_dmac_address(arp)


async def send_gateway_learning_request(
    address_refresh_map: Dict[str, List["PortArpRefreshData"]],
    port_instance: "PortInstance",
    stream_config: "ProtocolSegmentProfileConfig",
) -> Dict[str, List["PortArpRefreshData"]]:
    ip_version = has_ip_segment(stream_config)
    if not ip_version:
        return address_refresh_map

    gateway = port_instance.config.ip_gateway_mac_address
    gateway_not_empty = not gateway.is_empty
    if gateway_not_empty:
        address_refresh_map = add_address_refresh_entry(
            address_refresh_map, port_instance.config, ip_version, stream_config
        )

    else:
        target_ip_address = get_ip_property(port_instance.config, ip_version).gateway
        await send_arp_learning_request(target_ip_address, port_instance, stream_config)
        address_refresh_map = add_address_refresh_entry(
            address_refresh_map, port_instance.config, ip_version, stream_config
        )
    return address_refresh_map


## SendGatewayArpRequests
