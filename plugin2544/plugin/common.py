import re
from typing import TYPE_CHECKING, Dict, List, Tuple, Union
from ..utils import constants as const, field


if TYPE_CHECKING:
    from .structure import PortStruct
    from ..model.m_port_config import PortConfiguration


def gen_macaddress(first_three_bytes: str, index: int) -> "field.MacAddress":
    hex_num = hex(index)[2:].zfill(6)
    last_three_bytes = "".join(re.findall(r".{2}", hex_num))
    return field.MacAddress(f"{first_three_bytes}:{last_three_bytes}")


def is_same_ipnetwork(port_struct: "PortStruct", peer_struct: "PortStruct") -> bool:
    port_properties = port_struct.port_conf.ip_address
    peer_properties = peer_struct.port_conf.ip_address
    if not port_properties or not peer_properties:
        return False
    return port_properties.network == peer_properties.network


class TPLDControl:
    # TPLD is relative to test port index
    def __init__(self, tid_scope: "const.TidAllocationScope") -> None:
        self.curr_tpld_index = 0
        self.curr_tpld_map: Dict[int, int] = {}
        self.tid_scope = tid_scope

    def _config_scope_add(self) -> int:
        next_index = self.curr_tpld_index
        self.curr_tpld_index += 1
        return next_index

    def _port_scope_add(self, peer_index: int) -> int:
        if peer_index not in self.curr_tpld_map:
            self.curr_tpld_map[peer_index] = 0
        next_index = self.curr_tpld_map[peer_index]
        self.curr_tpld_map[peer_index] += 1
        return next_index

    def _src_port_id_add(self, port_index: int) -> int:
        return port_index

    def get_tpldid(self, port_index: int, peer_index: int) -> int:
        if self.tid_scope == const.TidAllocationScope.CONFIGURATION_SCOPE:
            return self._config_scope_add()
        elif self.tid_scope == const.TidAllocationScope.RX_PORT_SCOPE:
            return self._port_scope_add(peer_index)
        else:
            return self._src_port_id_add(port_index)


def is_peer_port(
    topology: "const.TestTopology",
    port_config: "PortConfiguration",
    peer_config: "PortConfiguration",
) -> bool:
    if topology.is_pair_topology:
        return port_config.is_pair(peer_config) and peer_config.is_pair(port_config)
    elif topology.is_mesh_topology:
        return port_config != peer_config
    return port_config.port_group != peer_config.port_group


def get_peers_for_source(
    topology: "const.TestTopology",
    port_config: "PortConfiguration",
    control_ports: List["PortStruct"],
) -> List["PortStruct"]:
    dest_ports = []
    for peer_struct in control_ports:
        peer_config = peer_struct.port_conf
        if not peer_config.is_rx_port:
            continue
        if is_peer_port(topology, port_config, peer_config):
            dest_ports.append(peer_struct)
    return dest_ports


def find_dest_port_structs(control_ports: List["PortStruct"]) -> List["PortStruct"]:
    """ return a list of rx port structs"""
    return [
        port_struct for port_struct in control_ports if port_struct.port_conf.is_rx_port
    ]
