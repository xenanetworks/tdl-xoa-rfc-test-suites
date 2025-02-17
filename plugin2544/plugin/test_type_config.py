from typing import Union, Iterable, List
from typing import TYPE_CHECKING
from ..utils import constants as const
if TYPE_CHECKING:
    from ..model import m_test_type_config as t_model


class BaseTestType:
    def __init__(self, test_type: "t_model.AllTestType"):
        self._conf = test_type

    @property
    def common_options(self) -> "t_model.CommonOptions":
        return self._conf.common_options

    @property
    def repetition(self) -> int:
        return self._conf.common_options.repetition

    @property
    def is_time_duration(self) -> bool:
        return self.common_options.duration_type.is_time_duration

    @property
    def actual_duration(self) -> float:
        return self.common_options.duration * self.common_options.duration_unit.scale

    @property
    def is_enabled(self) -> bool:
        return self._conf.enabled


class SweepTestType(BaseTestType):
    def __init__(
        self,
        test_type: Union[
            "t_model.FrameLossRateTest", "t_model.LatencyTest", "t_model.BackToBackTest"
        ],
    ):
        self._conf = test_type

    @property
    def rate_sweep_list(self) -> Iterable[float]:
        start_value_pct = self._conf.rate_sweep_options.start_value_pct
        end_value_pct = self._conf.rate_sweep_options.end_value_pct
        step_value_pct = self._conf.rate_sweep_options.step_value_pct
        pct = start_value_pct
        while True:
            yield pct
            if pct == end_value_pct:
                break
            elif pct < end_value_pct:
                pct += step_value_pct
            if pct > end_value_pct:
                break
        if pct != end_value_pct:
            yield end_value_pct

    @property
    def rate_length(self) -> int:
        return sum(1 for _ in self.rate_sweep_list)


class ThroughputConfig(BaseTestType):
    def __init__(self, throughput_config: "t_model.ThroughputTest"):
        self._conf = throughput_config

    @property
    def test_type(self) -> "const.TestType":
        return const.TestType.THROUGHPUT

    @property
    def rate_iteration_options(self) -> "t_model.RateIterationOptions":
        return self._conf.rate_iteration_options

    @property
    def result_scope(self) -> "const.RateResultScopeType":
        return self._conf.rate_iteration_options.result_scope

    @property
    def is_per_source_port(self) -> bool:
        return self.result_scope.is_per_source_port

    @property
    def initial_value_pct(self) -> float:
        return self.rate_iteration_options.initial_value_pct

    @property
    def minimum_value_pct(self) -> float:
        return self.rate_iteration_options.minimum_value_pct

    @property
    def maximum_value_pct(self) -> float:
        return self.rate_iteration_options.maximum_value_pct

    @property
    def value_resolution_pct(self) -> float:
        return self.rate_iteration_options.value_resolution_pct

    @property
    def search_type(self) -> "const.SearchType":
        return self.rate_iteration_options.search_type

    @property
    def use_pass_criteria(self) -> bool:
        return self._conf.use_pass_criteria

    @property
    def pass_criteria_throughput_pct(self) -> float:
        return self._conf.pass_criteria_throughput_pct

    @property
    def acceptable_loss_pct(self) -> float:
        return self._conf.acceptable_loss_pct
    
    @property
    def process_count(self) -> int:
        return self.repetition


class FrameLossConfig(SweepTestType):
    def __init__(self, frame_loss_config: "t_model.FrameLossRateTest") -> None:
        self._conf = frame_loss_config

    @property
    def test_type(self) -> "const.TestType":
        return const.TestType.FRAME_LOSS_RATE

    @property
    def is_percentage_pass_criteria(self) -> bool:
        return self._conf.pass_criteria_loss_type.is_percentage

    @property
    def use_pass_criteria(self) -> bool:
        return self._conf.use_pass_criteria
    
    @property
    def pass_criteria_loss(self) -> float:
        return self._conf.pass_criteria_loss

    @property
    def use_gap_monitor(self) -> bool:
        return self._conf.use_gap_monitor

    @property
    def gap_monitor_start_microsec(self) -> int:
        return self._conf.gap_monitor_start_microsec

    @property
    def gap_monitor_stop_frames(self) -> int:
        return self._conf.gap_monitor_stop_frames

    @property
    def process_count(self) -> int:
        return self.repetition * self.rate_length

class LatencyConfig(SweepTestType):
    def __init__(self, latency_config: "t_model.LatencyTest") -> None:
        self._conf = latency_config

    @property
    def test_type(self) -> "const.TestType":
        return const.TestType.LATENCY_JITTER

    @property
    def use_relative_to_throughput(self) -> bool:
        return self._conf.use_relative_to_throughput

    @property
    def latency_mode(self) -> "const.LatencyModeStr":
        return self._conf.latency_mode

    @property
    def process_count(self) -> int:
        return self.repetition * self.rate_length

class BackToBackConfig(SweepTestType):
    def __init__(self, back_to_back_config: "t_model.BackToBackTest"):
        self._conf = back_to_back_config

    @property
    def test_type(self) -> "const.TestType":
        return const.TestType.BACK_TO_BACK

    @property
    def burst_resolution(self) -> float:
        return self._conf.burst_size_iteration_options.burst_resolution
    
    @property
    def maximun_burst(self) -> float:
        return self._conf.burst_size_iteration_options.maximum_burst
    
    @property
    def process_count(self) -> int:
        return self.repetition * self.rate_length

AllTestTypeConfig = Union[
    ThroughputConfig, LatencyConfig, FrameLossConfig, BackToBackConfig
]

AllTestTypeConfigClass = [
    ThroughputConfig,
    LatencyConfig,
    FrameLossConfig,
    BackToBackConfig,
]


def get_available_test_type_config(
    test_type_datas: "t_model.TestTypesConfiguration",
) -> List["AllTestTypeConfig"]:
    """ Get test case configs which are enabled"""
    all_data = [
        test_type_datas.throughput_test,
        test_type_datas.latency_test,
        test_type_datas.frame_loss_rate_test,
        test_type_datas.back_to_back_test,
    ]
    return [
        func(data)
        for func, data in zip(AllTestTypeConfigClass, all_data)
        if data.enabled
    ]
