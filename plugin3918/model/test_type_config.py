from typing import List, Generator, Optional, TypeVar
from pydantic import BaseModel
from ..utils.constants import GroupCountSel


class BaseOptions(BaseModel):
    iterations: int = 0
    duration: int = 0
    traffic_to_join_delay: int = 0
    join_to_traffic_delay: int = 0
    leave_to_stop_delay: int = 0


BaseOptionsType = TypeVar("BaseOptionsType", bound=BaseOptions)


class RateOptionsStartEndStep(BaseModel):
    start_value: float
    end_value: float
    step_value: float

    @property
    def sweep_value_list(self) -> Generator[float, None, None]:
        v = self.start_value
        has_last = False
        while v <= self.end_value:
            if v == self.end_value:
                has_last = True
            yield v
            v += self.step_value
        if not has_last:
            yield self.end_value


class RateOptionsInitialMinMax(BaseModel):
    initial_value: float
    minimum_value: float
    maximum_value: float
    value_resolution: float
    use_pass_threshold: bool
    pass_threshold: float


class GroupCountDef(BaseModel):
    group_count_sel: GroupCountSel
    group_count_start: int
    group_count_end: int
    group_count_step: int
    group_count_list: List[int]

    @property
    def count_list(self) -> List[int]:
        if self.group_count_sel == GroupCountSel.LIST:
            return self.group_count_list
        else:
            start = self.group_count_start
            end = self.group_count_end
            step = self.group_count_step
            ragin = list(range(start, end, step))
            if end not in ragin:
                ragin.append(end)
            return ragin


class GroupJoinLeaveDelay(BaseOptions):
    rate_options: RateOptionsStartEndStep


class MulticastGroupCapacity(BaseOptions):
    group_count_start: int
    group_count_end: int
    group_count_step: int
    rate_options: RateOptionsStartEndStep


class AggregatedMulticastThroughput(BaseOptions):
    rate_options: RateOptionsInitialMinMax
    group_count_def: GroupCountDef


class ScaledGroupForwardingMatrix(BaseOptions):
    group_count_start: int
    group_count_end: int
    group_count_step: int
    use_max_capacity_result: bool
    rate_options: RateOptionsStartEndStep


class MixedClassThroughput(BaseOptions):
    uc_traffic_load_ratio: float
    rate_options: RateOptionsInitialMinMax
    group_count_def: GroupCountDef


class MulticastLatency(BaseOptions):
    rate_options: RateOptionsStartEndStep
    group_count_def: GroupCountDef


class BurdenedGroupJoinDelay(BaseOptions):
    rate_options: RateOptionsStartEndStep
    uc_traffic_load_ratio: float


class BurdenedMulticastLatency(BaseOptions):
    rate_options: RateOptionsStartEndStep
    group_count_def: GroupCountDef
    uc_traffic_load_ratio: float


class TestTypeConfiguration3918(BaseModel):
    group_join_leave_delay: Optional[GroupJoinLeaveDelay] = None
    multicast_group_capacity: Optional[MulticastGroupCapacity] = None
    aggregated_multicast_throughput: Optional[AggregatedMulticastThroughput] = None
    scaled_group_forwarding_matrix: Optional[ScaledGroupForwardingMatrix] = None
    mixed_class_throughput: Optional[MixedClassThroughput] = None
    multicast_latency: Optional[MulticastLatency] = None
    burdened_group_join_delay: Optional[BurdenedGroupJoinDelay] = None
    burdened_multicast_latency: Optional[BurdenedMulticastLatency] = None
