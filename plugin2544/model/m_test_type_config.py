from typing import Any, Dict, Union
from pydantic import BaseModel, Field, validator
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
    duration_unit: DurationUnit = DurationUnit.FRAME
    repetition: int = Field(default=1, ge=1, le=1e6)

    @validator("duration_unit", always=True)
    def validate_duration(
        cls, v: "DurationUnit", values: Dict[str, Any]
    ) -> "DurationUnit":
        if "duration_type" in values and not values["duration_type"].is_time_duration:
            cur = values["duration"] * v.scale
            if cur > constants.MAX_PACKET_LIMIT_VALUE:
                raise exceptions.PacketLimitOverflow(cur)
        return v


class RateIterationOptions(BaseModel):
    search_type: SearchType
    result_scope: RateResultScopeType
    initial_value_pct: float = Field(ge=0.0, le=100.0)
    maximum_value_pct: float = Field(ge=0.0, le=100.0)
    minimum_value_pct: float = Field(ge=0.0, le=100.0)
    value_resolution_pct: float = Field(ge=0.0, le=100.0)

    @validator("initial_value_pct", "minimum_value_pct")
    def check_if_larger_than_maximun(cls, v: float, values: Dict[str, Any]) -> float:
        if "maximum_value_pct" in values:
            if v > values["maximum_value_pct"]:
                raise exceptions.RateRestriction(v, values["maximum_value_pct"])
        return v


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

    @validator("end_value_pct")
    def validate_end_value(cls, end_value_pct: float, values: Dict[str, Any]) -> float:
        if "start_value_pct" in values:
            if end_value_pct < values["start_value_pct"]:
                raise exceptions.RangeRestriction()
        return end_value_pct


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
