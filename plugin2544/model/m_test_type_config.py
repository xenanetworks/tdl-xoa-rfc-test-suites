from typing import Any, Dict, Union, Annotated
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from ..utils.constants import (
    DurationType,
    DurationUnit,
    SearchType,
    RateResultScopeType,
    LatencyModeStr,
    AcceptableLossType,
)
from ..utils import exceptions
from ..utils import constants


class CommonOptions(BaseModel):
    duration_type: DurationType = DurationType.FRAME
    duration: float = Field(default=1, ge=1.0, le=1e9)
    duration_unit: Annotated[DurationUnit, Field(validate_default=True)] = DurationUnit.FRAME
    repetition: int = Field(default=1, ge=1, le=1e6)

    @field_validator("duration_unit")
    def validate_duration(
        cls, value: "DurationUnit", info: ValidationInfo
    ) -> "DurationUnit":
        if "duration_type" in info.data and not info.data["duration_type"].is_time_duration:
            cur = info.data["duration"] * value.scale
            if cur > constants.MAX_PACKET_LIMIT_VALUE:
                raise exceptions.PacketLimitOverflow(cur)
        return value


class RateIterationOptions(BaseModel):
    search_type: SearchType
    result_scope: RateResultScopeType
    initial_value_pct: float = Field(ge=0.0, le=100.0)
    maximum_value_pct: float = Field(ge=0.0, le=100.0)
    minimum_value_pct: float = Field(ge=0.0, le=100.0)
    value_resolution_pct: float = Field(ge=0.0, le=100.0)

    @field_validator("initial_value_pct", "minimum_value_pct")
    def check_if_larger_than_maximun(cls, value: float, info: ValidationInfo) -> float:
        if "maximum_value_pct" in info.data:
            if value > info.data["maximum_value_pct"]:
                raise exceptions.RateRestriction(value, info.data["maximum_value_pct"])
        return value


class ThroughputTest(BaseModel):
    enabled: bool
    common_options: CommonOptions
    rate_iteration_options: RateIterationOptions
    use_pass_criteria: bool
    pass_criteria_throughput_pct: float
    acceptable_loss_pct: float
    collect_latency_jitter: bool


class RateSweepOptions(BaseModel):
    start_value_pct: float
    end_value_pct: float
    step_value_pct: float = Field(gt=0.0)

    @field_validator("end_value_pct")
    def validate_end_value(cls, value: float, info: ValidationInfo) -> float:
        if "start_value_pct" in info.data:
            if value < info.data["start_value_pct"]:
                raise exceptions.RangeRestriction()
        return value


class BurstSizeIterationOptions(BaseModel):
    burst_resolution: float = 0.0
    maximum_burst: float = 0.0

    # @validator(
    #     "start_value_pct",
    #     "end_value_pct",
    #     "step_value_pct",
    #     "burst_resolution",
    #     pre=True,
    #     always=True,
    # )
    # def set_pcts(cls, v: float) -> float:
    #     return float(v)

    # def set_throughput_relative(self, throughput_rate: float) -> None:
    #     self.start_value_pct = self.start_value_pct * throughput_rate / 100
    #     self.end_value_pct = self.end_value_pct * throughput_rate / 100
    #     self.step_value_pct = self.step_value_pct * throughput_rate / 100


class LatencyTest(BaseModel):
    enabled: bool
    common_options: CommonOptions
    rate_sweep_options: RateSweepOptions
    latency_mode: LatencyModeStr
    use_relative_to_throughput: bool


class FrameLossRateTest(BaseModel):
    enabled: bool
    common_options: CommonOptions
    rate_sweep_options: RateSweepOptions

    # Convergence(BaseModel):
    use_gap_monitor: bool
    gap_monitor_start_microsec: int = Field(ge=0, le=1000)
    gap_monitor_stop_frames: int = Field(ge=0, le=1000)

    # PassCriteriaOptions
    use_pass_criteria: bool
    pass_criteria_loss: float
    pass_criteria_loss_type: AcceptableLossType


class BackToBackTest(BaseModel):
    enabled: bool
    common_options: CommonOptions
    rate_sweep_options: RateSweepOptions
    burst_size_iteration_options: BurstSizeIterationOptions


AllTestType = Union[ThroughputTest, LatencyTest, FrameLossRateTest, BackToBackTest]


class TestTypesConfiguration(BaseModel):
    throughput_test: ThroughputTest
    latency_test: LatencyTest
    frame_loss_rate_test: FrameLossRateTest
    back_to_back_test: BackToBackTest
