from typing import Any, List, Tuple, Dict
from pydantic import BaseModel, validator
from .utils import exceptions, constants as const
from .model.m_test_config import TestConfigModel
from .model.m_test_type_config import TestTypesConfiguration
from .model.m_port_config import PortConfiguration
from .model.m_protocol_segment import ProtocolSegmentProfileConfig


PortConfType = List[PortConfiguration]


class PluginModel2544(BaseModel):  # Main Model
    test_configuration: TestConfigModel
    protocol_segments: List[ProtocolSegmentProfileConfig]
    ports_configuration: PortConfType
    test_types_configuration: TestTypesConfiguration

    def set_ports_rx_tx_type(self) -> None:
        direction = self.test_configuration.topology_config.direction
        for port_config in self.ports_configuration:
            if port_config.is_loop:
                continue
            elif direction == const.TrafficDirection.EAST_TO_WEST:
                if port_config.port_group.is_east:
                    port_config.set_rx_port(False)
                elif port_config.port_group.is_west:
                    port_config.set_tx_port(False)
            elif direction == const.TrafficDirection.WEST_TO_EAST:
                if port_config.port_group.is_east:
                    port_config.set_tx_port(False)
                elif port_config.port_group.is_west:
                    port_config.set_rx_port(False)

    def set_profile(self) -> None:
        for port_config in self.ports_configuration:
            profile_id = port_config.protocol_segment_profile_id
            profile = [i for i in self.protocol_segments if i.id == profile_id][0]
            port_config.set_profile(profile.copy(deep=True))

    def __init__(self, **data: Dict[str, Any]) -> None:
        super().__init__(**data)
        self.set_ports_rx_tx_type()

        self.check_port_groups_and_peers()
        self.set_profile()

    @validator("ports_configuration", always=True)
    def check_ip_properties(cls, v: "PortConfType", values) -> "PortConfType":
        pro_map = {v.id: v.protocol_version for v in values['protocol_segments']}
        for i, port_config in enumerate(v):
            if port_config.protocol_segment_profile_id not in pro_map:
                raise exceptions.PSPMissing()
            if (
                pro_map[port_config.protocol_segment_profile_id].is_l3
                and (not port_config.ip_address or port_config.ip_address.address.is_empty)
            ):
                raise exceptions.IPAddressMissing()
        return v

    @validator("ports_configuration", always=True)
    def check_port_count(
        cls, v: "PortConfType", values: Dict[str, Any]
    ) -> "PortConfType":
        require_ports = 2
        if "test_configuration" in values:
            topology: const.TestTopology = values[
                "test_configuration"
            ].topology_config.topology
            if topology.is_pair_topology:
                require_ports = 1
            if len(v) < require_ports:
                raise exceptions.PortConfigNotEnough(require_ports)
        return v

    def check_port_groups_and_peers(self) -> None:
        topology = self.test_configuration.topology_config.topology
        ports_in_east = ports_in_west = 0
        uses_port_peer = topology.is_pair_topology
        for port_config in self.ports_configuration:
            if not topology.is_mesh_topology:
                ports_in_east, ports_in_west = self.count_port_group(
                    port_config, uses_port_peer, ports_in_east, ports_in_west
                )
            if uses_port_peer:
                self.check_port_peer(port_config, self.ports_configuration)
        if not topology.is_mesh_topology:
            for i, group in (ports_in_east, "East"), (ports_in_west, "West"):
                if not i:
                    raise exceptions.PortGroupError(group)

    @validator("ports_configuration", always=True)
    def check_modifier_mode_and_segments(
        cls, v: "PortConfType", values: Dict[str, Any]
    ) -> "PortConfType":
        if "test_configuration" in values:
            flow_creation_type = values[
                "test_configuration"
            ].test_execution_config.flow_creation_config.flow_creation_type
            for port_config in v:
                if (
                    not flow_creation_type.is_stream_based
                ) and port_config.profile.protocol_version.is_l3:
                    raise exceptions.ModifierBasedNotSupportL3()
        return v

    @validator("ports_configuration", always=True)
    def check_port_group(
        cls, v: "PortConfiguration", values: Dict[str, Any]
    ) -> "PortConfiguration":
        if "ports_configuration" in values and "test_configuration" in values:
            for k, p in values["ports_configuration"].items():
                if (
                    p.port_group == const.PortGroup.UNDEFINED
                    and not values[
                        "test_configuration"
                    ].topology_config.topology.is_mesh_topology
                ):
                    raise exceptions.PortGroupNeeded()
        return v

    @validator("test_types_configuration", always=True)
    def check_test_type_enable(
        cls, v: "TestTypesConfiguration"
    ) -> "TestTypesConfiguration":
        if not any(
            {
                v.throughput_test.enabled,
                v.latency_test.enabled,
                v.frame_loss_rate_test.enabled,
                v.back_to_back_test.enabled,
            }
        ):
            raise exceptions.TestTypesError()
        return v

    @validator("test_types_configuration", always=True)
    def check_result_scope(
        cls, v: "TestTypesConfiguration", values: Dict[str, Any]
    ) -> "TestTypesConfiguration":
        if "test_configuration" not in values:
            return v
        if (
            v.throughput_test.enabled
            and v.throughput_test.rate_iteration_options.result_scope
            == const.RateResultScopeType.PER_SOURCE_PORT
            and not values[
                "test_configuration"
            ].test_execution_config.flow_creation_config.flow_creation_type.is_stream_based
        ):
            raise exceptions.ModifierBasedNotSupportPerPortResult()
        return v

    @staticmethod
    def count_port_group(
        port_config: "PortConfiguration",
        uses_port_peer: bool,
        ports_in_east: int,
        ports_in_west: int,
    ) -> Tuple[int, int]:
        if port_config.port_group.is_east:
            ports_in_east += 1
            if uses_port_peer and port_config.is_loop:
                ports_in_west += 1

        elif port_config.port_group.is_west:
            ports_in_west += 1
            if uses_port_peer and port_config.is_loop:
                ports_in_east += 1

        return ports_in_east, ports_in_west

    @staticmethod
    def check_port_peer(
        port_config: "PortConfiguration",
        ports_configuration: List["PortConfiguration"],
    ) -> None:
        peer_slot = port_config.peer_slot
        if peer_slot is None or peer_slot >= len(ports_configuration):
            raise exceptions.PortPeerNeeded()
        peer_config = ports_configuration[peer_slot]
        if not port_config.is_pair(peer_config) or not peer_config.is_pair(port_config):
            raise exceptions.PortPeerInconsistent()
