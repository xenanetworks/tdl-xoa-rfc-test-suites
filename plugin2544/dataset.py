from typing import Any, List, Tuple, Dict, Annotated
from pydantic import BaseModel, field_validator, ValidationInfo, Field
from .utils import exceptions, constants as const
from .model.m_test_config import TestConfigModel
from .model.m_test_type_config import TestTypesConfiguration
from .model.m_port_config import PortConfiguration
from .model.m_protocol_segment import ProtocolSegmentProfileConfig


PortConfType = List[PortConfiguration]


class PluginModel2544(BaseModel):  # Main Model
    test_configuration: Annotated[TestConfigModel, Field(validate_default=True)]
    protocol_segments: List[ProtocolSegmentProfileConfig]
    ports_configuration: Annotated[PortConfType, Field(validate_default=True)]
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

    
    @field_validator("ports_configuration")
    def check_ip_properties(cls, value: "PortConfType", info: ValidationInfo) -> "PortConfType":
        pro_map = {v.id: v.protocol_version for v in info.data['protocol_segments']}
        for i, port_config in enumerate(value):
            if port_config.protocol_segment_profile_id not in pro_map:
                raise exceptions.PSPMissing()
            if (
                pro_map[port_config.protocol_segment_profile_id].is_l3
                and (not port_config.ip_address or port_config.ip_address.address.is_empty)
            ):
                raise exceptions.IPAddressMissing()
        return value

    
    @field_validator("ports_configuration")
    def check_port_count(cls, value: "PortConfType", info: ValidationInfo) -> "PortConfType":
        require_ports = 2
        if "test_configuration" in info.data:
            topology: const.TestTopology = info.data[
                "test_configuration"
            ].topology_config.topology
            if topology.is_pair_topology:
                require_ports = 1
            if len(value) < require_ports:
                raise exceptions.PortConfigNotEnough(require_ports)
        return value

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


    @field_validator("ports_configuration")
    def check_modifier_mode_and_segments(cls, value: PortConfType, info: ValidationInfo) -> PortConfType:
        if "test_configuration" in info.data:
            flow_creation_type = info.data[
                "test_configuration"
            ].test_execution_config.flow_creation_config.flow_creation_type
            for port_config in value:
                if (
                    not flow_creation_type.is_stream_based
                ) and port_config.profile.protocol_version.is_l3:
                    raise exceptions.ModifierBasedNotSupportL3()
        return value


    @field_validator("ports_configuration")
    def check_port_group(cls, value: PortConfiguration, info: ValidationInfo) -> PortConfiguration:
        if "ports_configuration" in info.data and "test_configuration" in info.data:
            for k, p in info.data["ports_configuration"].items():
                if (
                    p.port_group == const.PortGroup.UNDEFINED
                    and not info.data[
                        "test_configuration"
                    ].topology_config.topology.is_mesh_topology
                ):
                    raise exceptions.PortGroupNeeded()
        return value

    @field_validator("test_types_configuration")
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


    @field_validator("test_types_configuration")
    def check_result_scope(cls, value: "TestTypesConfiguration", info: ValidationInfo) -> "TestTypesConfiguration":
        if "test_configuration" not in info.data:
            return value
        if (
            value.throughput_test.enabled
            and value.throughput_test.rate_iteration_options.result_scope
            == const.RateResultScopeType.PER_SOURCE_PORT
            and not info.data[
                "test_configuration"
            ].test_execution_config.flow_creation_config.flow_creation_type.is_stream_based
        ):
            raise exceptions.ModifierBasedNotSupportPerPortResult()
        return value

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
