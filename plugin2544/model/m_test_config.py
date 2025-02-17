from typing import Any, Dict, List, Tuple
from pydantic import BaseModel, Field, validator
from ..utils import constants as const, exceptions


class FrameSizesOptions(BaseModel):
    field_0: int = Field(56, ge=0)
    field_1: int = Field(60, ge=0)
    field_14: int = Field(9216, ge=0)
    field_15: int = Field(16360, ge=0)


class FrameSize(BaseModel):
    # FrameSizes
    packet_size_type: const.PacketSizeType
    # FixedSizesPerTrial
    custom_packet_sizes: List[int]
    fixed_packet_start_size: int = Field(ge=0)
    fixed_packet_end_size: int = Field(ge=0)
    fixed_packet_step_size: int = Field(gt=0)
    # VaryingSizesPerTrial
    varying_packet_min_size: int = Field(ge=0)
    varying_packet_max_size: int = Field(ge=0)
    mixed_length_config: FrameSizesOptions
    mixed_sizes_weights: List[int] = list(const.MIXED_DEFAULT_WEIGHTS)

    @validator("custom_packet_sizes", pre=True, always=True)
    def is_custom_packet_sizes_valid(
        cls, v: List[int], values: Dict[str, Any]
    ) -> List[int]:
        for i in v:
            if i < 0:
                raise exceptions.SmallerThanZeroError(i)
        return v

    @validator("mixed_sizes_weights", pre=True, always=True)
    def is_mixed_weights_valid(cls, v: List[int], values: Dict[str, Any]) -> List[int]:
        if "packet_size_type" in values:
            if values["packet_size_type"] == const.PacketSizeType.MIX:
                if not v or len(v) != len(const.MIXED_DEFAULT_WEIGHTS):
                    raise exceptions.MixWeightsNotEnough()
                sum_of_weights = sum(v)
                if not sum_of_weights == 100:
                    raise exceptions.MixWeightsSumError(sum_of_weights)
            for i in v:
                if i < 0:
                    raise exceptions.SmallerThanZeroError(i)
        return v


class MultiStreamConfig(BaseModel):
    enable_multi_stream: bool
    per_port_stream_count: int = Field(gt=0)
    multi_stream_address_offset: int = Field(ge=1, le=256)
    multi_stream_address_increment: int = Field(ge=1, le=256)
    multi_stream_mac_base_address: str


class TogglePortSyncConfig(BaseModel):
    toggle_port_sync: bool
    sync_off_duration_second: int = Field(gt=0, le=60)
    delay_after_sync_on_second: int = Field(gt=0, le=60)


class TopologyConfig(BaseModel):

    # OverallTestTopology
    topology: const.TestTopology
    direction: const.TrafficDirection


class FrameSizeConfig(BaseModel):
    frame_sizes: FrameSize
    # FrameTestPayload
    use_micro_tpld_on_demand: bool
    # payload_definition PayloadDefinition
    payload_type: const.PayloadTypeStr
    payload_pattern: str  # full number string


class FlowCreationConfig(BaseModel):
    # FlowCreation
    flow_creation_type: const.FlowCreationType
    tid_allocation_scope: const.TidAllocationScope
    mac_base_address: str


class PortSchedulingConfig(BaseModel):
    # PortScheduling
    enable_speed_reduction_sweep: bool
    use_port_sync_start: bool
    port_stagger_steps: int = Field(ge=0, le=31250)
    # TestScheduling


class L23LearningOptions(BaseModel):
    # L23LearningOptions
    learning_rate_pct: float = Field(gt=0, le=100)
    learning_duration_second: int = Field(gt=0, le=60000)
    # FlowBasedLearningOptions

    # ArpNdpOptions
    arp_refresh_enabled: bool
    arp_refresh_period_second: float = Field(default=4000.0, gt=0, le=100000)
    use_gateway_mac_as_dmac: bool


class FlowBasedLearningOptions(BaseModel):
    # FlowBasedLearningOptions
    use_flow_based_learning_preamble: bool
    flow_based_learning_frame_count: int = Field(gt=0, le=100)
    delay_after_flow_based_learning_ms: int = Field(..., ge=50, le=10000)


class ResetErrorHandling(BaseModel):
    # ResetAndErrorHandling
    should_stop_on_los: bool
    delay_after_port_reset_second: int = Field(gt=0, le=60)
    # OverallTestTopology


class MacLearningOptions(BaseModel):
    # MacLearningOptions
    mac_learning_mode: const.MACLearningMode
    mac_learning_frame_count: int = Field(gt=0, le=10)
    toggle_port_sync_config: TogglePortSyncConfig


class TestExecutionConfig(BaseModel):
    flow_creation_config: FlowCreationConfig
    port_scheduling_config: PortSchedulingConfig
    outer_loop_mode: const.OuterLoopMode
    mac_learning_options: MacLearningOptions
    l23_learning_options: L23LearningOptions
    flow_based_learning_options: FlowBasedLearningOptions
    reset_error_handling: ResetErrorHandling
    repeat_test_until_stopped: bool = False


class TestConfigModel(BaseModel):
    topology_config: TopologyConfig
    frame_size_config: FrameSizeConfig
    multi_stream_config: MultiStreamConfig
    test_execution_config: TestExecutionConfig

    @validator("multi_stream_config")
    def validate_multi_stream(
        cls, v: "MultiStreamConfig", values: Dict[str, Any]
    ) -> "MultiStreamConfig":
        if "flow_creation_type" not in values:
            return v
        if not values["flow_creation_type"].is_stream_based and v.enable_multi_stream:
            raise exceptions.ModifierBasedNotSupportMultiStream()
        return v
