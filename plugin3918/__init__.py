from xoa_core.types import PluginAbstract
from .utils.constants import (
    MICRO_TPLD_TOTAL_LENGTH,
    STANDARD_TPLD_TOTAL_LENGTH,
    MulticastRole,
)
from .plugin.config_checker import ConfigChecker
from .plugin.type_aggregated_multicast_throughput_test import AggregatedThroughputTest
from .plugin.type_burdened_group_join_delay_test import BurdenedGroupJoinDelayTest
from .plugin.type_burdened_multicast_latency_test import BurdenedMulticastLatencyTest
from .plugin.type_multicast_group_capacity_test import MulticastGroupCapacityTest
from .plugin.type_multicast_latency_test import MulticastLatencyTest
from .plugin.type_mixed_class_throughput_test import MixedClassThroughputTest
from .plugin.type_scaled_group_forwarding_matrix_test import ScaledGroupThroughputTest
from .plugin.type_group_join_leave_delay import GroupJoinLeaveDelayTest

from .plugin.resource_manager import ResourceManager
from .model.test_type_config import (
    BurdenedGroupJoinDelay,
    BurdenedMulticastLatency,
    TestTypeConfiguration3918,
)
from .model.test_suit import TestConfiguration3918
from .model.mc_uc_definition import McDefinition
from .model.port_config import PortConfiguration
from .model.protocol_segments import ProtocolSegmentProfileConfig
from .utils.errors import (
    LeastTwoUcBurden,
    NoMcDestination,
    NotOneMcSource,
    PacketSizeSmallerThanPacketLength,
)
from typing import Counter, Dict
from pydantic import BaseModel, root_validator, validator

PortConfType = Dict[str, "PortConfiguration"]


def _check_header_length(
    mc_definition: McDefinition, min_packet_size: int, tpld_length: int, mode: str
) -> None:
    assert mode in {"multicast", "unicast"}, f"Mode '{mode}' is not valid!"
    if mode == "multicast":
        header_length = mc_definition.stream_definition.packet_header_length
    else:
        header_length = mc_definition.uc_flow_def.stream_definition.packet_header_length
    need_packet_length = header_length + tpld_length
    if min_packet_size < need_packet_length:
        raise PacketSizeSmallerThanPacketLength(
            min_packet_size, need_packet_length, mode
        )


class Model3918(BaseModel):
    mc_definition: McDefinition
    protocol_segments: Dict[str, ProtocolSegmentProfileConfig]
    ports_configuration: Dict[str, PortConfiguration]
    test_configuration: TestConfiguration3918
    test_types_configuration: TestTypeConfiguration3918

    @validator("test_configuration")
    def validate_test_config(cls, v, values):
        min_packet_size = min(v.frame_sizes.packet_size_list)
        if min_packet_size < 0:
            return v

        if not v.use_micro_tpld_on_demand:
            tpld_length = STANDARD_TPLD_TOTAL_LENGTH
        else:
            tpld_length = MICRO_TPLD_TOTAL_LENGTH
        _check_header_length(
            values["mc_definition"], min_packet_size, tpld_length, "multicast"
        )
        _check_header_length(
            values["mc_definition"], min_packet_size, tpld_length, "unicast"
        )
        return v

    @root_validator(skip_on_failure=True)
    def validate_model(cls, values):
        roles = []
        for vs in values["ports_configuration"].values():
            roles.append(vs.multicast_role)
        dic = Counter(roles)
        if dic[MulticastRole.MC_SOURCE] != 1:
            raise NotOneMcSource()
        if dic[MulticastRole.MC_DESTINATION] < 1:
            raise NoMcDestination()
        if any(
            [
                values["test_types_configuration"].burdened_group_join_delay
                is not None,
                values["test_types_configuration"].burdened_multicast_latency
                is not None,
            ]
        ):
            if dic[MulticastRole.UC_BURDEN] < 2:
                raise LeastTwoUcBurden()
        return values


class TestSuite3918(PluginAbstract["Model3918"]):
    async def run_test_cases(self, resource_manager: ResourceManager) -> None:
        for test_case_class in (
            GroupJoinLeaveDelayTest,
            MulticastGroupCapacityTest,
            AggregatedThroughputTest,
            ScaledGroupThroughputTest,
            MixedClassThroughputTest,
            MulticastLatencyTest,
            BurdenedGroupJoinDelayTest,
            BurdenedMulticastLatencyTest,
        ):
            test = test_case_class(self.xoa_out, self.cfg, resource_manager)
            if test.enabled():
                await test.run()

    async def start(self):
        resource_manager = await ResourceManager(
            self.testers, self.port_identities, self.cfg
        )
        ConfigChecker(self.cfg, resource_manager).check_config()
        await self.run_test_cases(resource_manager)
