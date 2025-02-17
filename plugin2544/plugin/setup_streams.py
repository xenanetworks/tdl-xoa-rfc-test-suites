import asyncio
from typing import Dict, List, Tuple, TYPE_CHECKING
from .arp_request import set_arp_request
from .common import TPLDControl
from .data_model import StreamOffset
from ..utils import exceptions

if TYPE_CHECKING:
    from .structure import PortStruct
    from .test_config import TestConfigData
    from ..model.m_test_config import MultiStreamConfig


async def setup_streams(
    port_structs: List["PortStruct"], test_conf: "TestConfigData"
) -> None:
    if not test_conf.is_stream_based:   
        # add modifier on TX ports
        test_port_index_map = {
            port_struct.properties.test_port_index: port_struct
            for port_struct in port_structs
        }
        for port_struct in port_structs:
            if port_struct.port_conf.is_tx_port:
                add_modifier_based_stream(port_struct, test_port_index_map)

    else:   # configure stream based stream
        for port_struct in port_structs:
            for peer_struct in port_struct.properties.peers:
                peer_struct.properties.arp_mac_address = await set_arp_request(
                    port_struct,
                    peer_struct,
                    test_conf.use_gateway_mac_as_dmac,
                )
        if test_conf.enable_multi_stream:   # configure multi stream
            add_multi_streams(port_structs, test_conf)
        else:
            add_standard_streams(port_structs, test_conf)

    for port_struct in port_structs:
        await port_struct.configure_streams(test_conf)
        # set should stop on los before start traffic, can monitor sync status when traffic start
        port_struct.set_should_stop_on_los(test_conf.should_stop_on_los)


def get_stream_offsets(
    offset_table: Dict[Tuple[str, str], List["StreamOffset"]],
    port_index: str,
    peer_index: str,
) -> List["StreamOffset"]:
    """ stream offset is used to generate stream mac addr and ip addr"""
    if (port_index, peer_index) in offset_table:
        return offset_table[(port_index, peer_index)]
    elif (peer_index, port_index) in offset_table:
        return [
            stream_offset.reverse()
            for stream_offset in offset_table[(peer_index, port_index)]
        ]
    return []


def setup_offset_table(
    tx_ports: List["PortStruct"],
    multi_stream_config: "MultiStreamConfig",
) -> Dict[Tuple[str, str], List["StreamOffset"]]:
    """ generate a offset table for logical mac address and ip address """
    offset_table = {}
    offset = multi_stream_config.multi_stream_address_offset
    inc = multi_stream_config.multi_stream_address_increment
    for port_struct in tx_ports:
        port_name = port_struct.port_identity.name
        for peer_struct in port_struct.properties.peers:
            peer_name = peer_struct.port_identity.name
            if not (
                (port_name, peer_name) in offset_table
                or (peer_name, port_name) in offset_table
            ):
                offsets = []
                for _ in range(multi_stream_config.per_port_stream_count):
                    offsets.append(
                        StreamOffset(tx_offset=offset, rx_offset=offset + inc)
                    )
                    offset += inc * 2
                offset_table[(port_name, peer_name)] = offsets
    return offset_table


def add_modifier_based_stream(
    port_struct: "PortStruct", test_port_index_map: Dict[int, "PortStruct"]
) -> None:
    if not port_struct.port_conf.is_tx_port:
        return
    stream_id_counter = 0
    for _ in range(port_struct.properties.num_modifiersL2):
        tpldid = 2 * port_struct.properties.test_port_index + stream_id_counter
        modifier_range = port_struct.properties.get_modifier_range(stream_id_counter)
        rx_ports = [
            test_port_index_map[test_port_index]
            for test_port_index in range(modifier_range[0], modifier_range[1] + 1)
        ]
        port_struct.add_stream(rx_ports, stream_id_counter, tpldid)
        stream_id_counter += 1


def add_multi_streams(
    port_structs: List["PortStruct"], test_conf: "TestConfigData"
) -> None:
    offset_table = setup_offset_table(port_structs, test_conf.multi_stream_config)
    tpld_controller = TPLDControl(test_conf.tid_allocation_scope)
    for port_struct in port_structs:
        stream_id_counter = 0
        for peer_struct in port_struct.properties.peers:
            if test_conf.enable_multi_stream:
                peer_index = peer_struct.port_identity.name
                offsets_list = get_stream_offsets(
                    offset_table, port_struct.port_identity.name, peer_index
                )
                if not offsets_list:
                    raise exceptions.OffsetNotExist()
                for offsets in offsets_list:
                    tpldid = tpld_controller.get_tpldid(
                        port_struct.properties.test_port_index,
                        peer_struct.properties.test_port_index,
                    )
                    if tpldid > port_struct.capabilities.max_tpid:
                        raise exceptions.TPLDIDExceed(
                            tpldid, port_struct.capabilities.max_tpid
                        )
                    port_struct.add_stream(
                        [peer_struct],
                        stream_id_counter,
                        tpldid,
                        peer_struct.properties.arp_mac_address,
                        offsets,
                    )
                    stream_id_counter += 1


def add_standard_streams(
    port_structs: List["PortStruct"], test_conf: "TestConfigData"
) -> None:
    tpld_controller = TPLDControl(test_conf.tid_allocation_scope)
    for port_struct in port_structs:
        stream_id_counter = 0
        for peer_struct in port_struct.properties.peers:
            tpldid = tpld_controller.get_tpldid(
                port_struct.properties.test_port_index,
                peer_struct.properties.test_port_index,
            )
            port_struct.add_stream(
                [peer_struct],
                stream_id_counter,
                tpldid,
                peer_struct.properties.arp_mac_address,
            )
            stream_id_counter += 1
