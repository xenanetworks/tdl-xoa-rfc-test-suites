from typing import TYPE_CHECKING, Dict, List
from ..model.protocol_segments import ProtocolSegmentProfileConfig
from ..model.test_type_config import (
    AggregatedMulticastThroughput,
    BaseOptionsType,
    BaseOptions,
    BurdenedGroupJoinDelay,
    BurdenedMulticastLatency,
    GroupJoinLeaveDelay,
    MixedClassThroughput,
    MulticastLatency,
    ScaledGroupForwardingMatrix,
)
from ..model.mc_uc_definition import McDefinition, UcFlowDefinition
from ..model.test_suit import TestConfiguration3918
from ..model.test_type_config import MulticastGroupCapacity
from ..utils.constants import (
    PacketSizeType,
    TidAllocationScope,
)

if TYPE_CHECKING:
    from xoa_driver.enums import LatencyMode, LengthType, PayloadType


class Data3918:
    def __init__(
        self, test_configuration: TestConfiguration3918, mc_definition: McDefinition
    ) -> None:
        self.test_configuration = test_configuration
        self.mc_definition = mc_definition
        self.test_types_configuration = BaseOptions()

    def has_test_types_configuration(self) -> bool:
        return self.test_types_configuration != BaseOptions()

    def set_test_type_operation(
        self, test_types_configuration: "BaseOptionsType"
    ) -> None:
        self.test_types_configuration = test_types_configuration

    def get_tid_offset(self) -> int:
        return self.test_configuration.tid_offset

    def get_latency_mode_xoa(self) -> "LatencyMode":
        return self.test_configuration.latency_mode.xoa

    def get_packet_size_type(self) -> PacketSizeType:
        return self.test_configuration.frame_sizes.packet_size_type

    def get_packet_size_type_xoa(self) -> "LengthType":
        return self.get_packet_size_type().xoa

    def is_packet_size_type_fixed(self) -> bool:
        return self.get_packet_size_type() in {
            PacketSizeType.IEEE_DEFAULT,
            PacketSizeType.CUSTOM_SIZES,
            PacketSizeType.RANGE,
        }

    def is_packet_size_type_mixed_sizes(self) -> bool:
        return self.get_packet_size_type() == PacketSizeType.MIX

    def get_mixed_sizes_weights(self) -> List[int]:
        return self.test_configuration.frame_sizes.mixed_sizes_weights

    def get_mixed_length_config(self) -> Dict[str, int]:
        return self.test_configuration.frame_sizes.mixed_length_config.dict()

    def get_packet_size_list(self) -> List[int]:
        return self.test_configuration.frame_sizes.packet_size_list

    def get_toggle_sync_state(self) -> bool:
        return self.test_configuration.toggle_sync_state

    def get_sync_off_duration(self) -> int:
        return self.test_configuration.sync_off_duration

    def get_tid_allocation_scope(self) -> TidAllocationScope:
        return self.test_configuration.tid_allocation_scope

    def get_mc_payload_type_xoa(self) -> "PayloadType":
        return self.mc_definition.stream_definition.payload_type.xoa

    def get_mc_payload_pattern(self) -> str:
        return self.mc_definition.stream_definition.payload_pattern

    def get_uc_payload_type_xoa(self) -> "PayloadType":
        return self.mc_definition.uc_flow_def.stream_definition.payload_type.xoa

    def get_uc_payload_pattern(self) -> str:
        return self.mc_definition.uc_flow_def.stream_definition.payload_pattern

    def get_iterations(self) -> int:
        return self.test_types_configuration.iterations

    def get_join_to_traffic_delay(self) -> int:
        return self.test_types_configuration.join_to_traffic_delay

    def get_traffic_to_join_delay(self) -> int:
        return self.test_types_configuration.traffic_to_join_delay

    def get_group_count_start(self) -> int:
        if isinstance(
            self.test_types_configuration,
            (MulticastGroupCapacity, ScaledGroupForwardingMatrix),
        ):
            return self.test_types_configuration.group_count_start
        return 0

    def get_group_count_end(self) -> int:
        if isinstance(
            self.test_types_configuration,
            (MulticastGroupCapacity, ScaledGroupForwardingMatrix),
        ):
            return self.test_types_configuration.group_count_end
        return 0

    def set_group_count_end(self, group_count_end: int) -> None:
        if isinstance(
            self.test_types_configuration,
            (ScaledGroupForwardingMatrix),
        ):
            self.test_types_configuration.group_count_end = group_count_end

    def get_group_count_step(self) -> int:
        if isinstance(
            self.test_types_configuration,
            (MulticastGroupCapacity, ScaledGroupForwardingMatrix),
        ):
            return self.test_types_configuration.group_count_step
        return 0

    def get_group_count_list(self) -> List[int]:
        if isinstance(
            self.test_types_configuration,
            (
                MixedClassThroughput,
                AggregatedMulticastThroughput,
                MulticastLatency,
                BurdenedMulticastLatency,
            ),
        ):
            return self.test_types_configuration.group_count_def.count_list
        return []

    def get_sweep_value_list(self) -> List[int]:
        if isinstance(
            self.test_types_configuration,
            (
                MulticastGroupCapacity,
                ScaledGroupForwardingMatrix,
                MulticastLatency,
                BurdenedGroupJoinDelay,
                BurdenedMulticastLatency,
                GroupJoinLeaveDelay,
            ),
        ):
            return list(self.test_types_configuration.rate_options.sweep_value_list)
        return []

    def get_igmp_join_leave_rate(self) -> int:
        return int(self.mc_definition.max_igmp_frame_rate)

    def get_igmp_join_interval(self) -> int:
        return self.mc_definition.igmp_join_interval

    def get_igmp_leave_interval(self) -> int:
        return self.mc_definition.igmp_leave_interval

    def get_duration_value(self) -> int:
        return self.test_types_configuration.duration

    def get_delay_after_stop(self) -> int:
        return 5

    def get_leave_to_stop_delay(self) -> int:
        if isinstance(self.test_types_configuration, GroupJoinLeaveDelay):
            return self.test_types_configuration.leave_to_stop_delay
        return -1

    def get_delay_after_leave(self) -> int:
        return 2

    def get_mc_config(self) -> ProtocolSegmentProfileConfig:
        return self.mc_definition.stream_definition

    def get_uc_config(self) -> ProtocolSegmentProfileConfig:
        return self.mc_definition.uc_flow_def.stream_definition

    def get_uc_def(self) -> UcFlowDefinition:
        return self.mc_definition.uc_flow_def


    def get_use_gateway_mac(self) -> bool:
        return self.test_configuration.use_gateway_mac_as_dmac

    def get_uc_traffic_load_ratio(self) -> float:
        if isinstance(
            self.test_types_configuration,
            (MixedClassThroughput, BurdenedGroupJoinDelay, BurdenedMulticastLatency),
        ):
            return self.test_types_configuration.uc_traffic_load_ratio
        return 0

    def get_rate_option_initial(self) -> float:
        if isinstance(
            self.test_types_configuration,
            (MixedClassThroughput, AggregatedMulticastThroughput),
        ):
            return self.test_types_configuration.rate_options.initial_value
        return 0

    def get_rate_option_minimum(self) -> float:
        if isinstance(
            self.test_types_configuration,
            (MixedClassThroughput, AggregatedMulticastThroughput),
        ):
            return self.test_types_configuration.rate_options.minimum_value
        return 0

    def get_rate_option_maximum(self) -> float:
        if isinstance(
            self.test_types_configuration,
            (MixedClassThroughput, AggregatedMulticastThroughput),
        ):
            return self.test_types_configuration.rate_options.maximum_value
        return 0

    def get_rate_option_resolution(self) -> float:
        if isinstance(self.test_types_configuration, AggregatedMulticastThroughput):
            return self.test_types_configuration.rate_options.value_resolution
        return 0

    def get_use_capacity_result(self) -> bool:
        if isinstance(self.test_types_configuration, ScaledGroupForwardingMatrix):
            return self.test_types_configuration.use_max_capacity_result
        return False

    def get_latency_unit(self):
        return self.test_configuration.latency_display_unit

    def get_jitter_unit(self):
        return self.test_configuration.jitter_display_unit
