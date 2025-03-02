import math
from typing import Any, Dict, List, Union, TYPE_CHECKING
from pydantic import BaseModel, validator
from operator import attrgetter
from ..utils import constants as const
from loguru import logger
if TYPE_CHECKING:
    from .structure import PortStruct


class AvgMinMax(BaseModel):
    minimum: int = 0
    maximum: int = 0
    average: int = 0


class DelayData(BaseModel):
    counter_type: const.CounterType = const.CounterType.LATENCY
    minimum: int = 0
    maximum: int = 0
    average: int = 0
    is_valid: bool = True

    @validator("average", "minimum", "maximum", always=True)
    def check_is_valid(cls, v: int, values: Dict[str, Any]) -> int:
        if v == values["counter_type"].value:
            values["is_valid"] = False
            return 0
        return v


class DelayCounter(AvgMinMax):
    _total: int = 0
    _count: int = 0

    def sum(self, other: "DelayCounter") -> None:
        for name, value in self:
            setattr(self, name, value + attrgetter(name)(other))

    def avg(self, count: int) -> None:
        for name, value in self:
            setattr(self, name, math.floor(value / count))

    def update(self, data: DelayData) -> None:
        if not data.is_valid:
            return
        self._total += data.average
        if self._count == 0:
            self.minimum = data.minimum
            self.maximum = data.maximum
        else:
            self.minimum = min(data.minimum, self.minimum)
            self.maximum = max(data.maximum, self.maximum)
        self._count += 1
        self.average = math.floor(self._total / self._count if self._count else 0)


class StreamCounter(BaseModel):
    frames: int = 0  # packet_count_since_cleared
    bps: int = 0  # bit_count_last_sec
    pps: int = 0  # packet_count_last_sec
    bytes_count: int = 0  # byte_count_since_cleared
    frame_rate: float = 0.0
    l2_bit_rate: float = 0.0
    l1_bit_rate: float = 0.0
    tx_l1_bps: float = 0.0

    def add_stream_counter(self, counter: "StreamCounter") -> None:
        """update stream counter by pt stream"""
        self.frames += counter.frames  # _cal_port_tx_frames  + _cal_port_rx_frames
        self.bps += counter.bps
        self.pps += counter.pps
        self.bytes_count += counter.bytes_count  # _cal_port_rx_bytes

    def calculate_stream_rate(
        self,
        is_final: bool,
        duration: float,
        frame_size: float,
        interframe_gap: float,
    ) -> None:
        """ calculate stream rate based on stream counter """
        self.frame_rate = self.frames / duration
        self.l2_bit_rate = self.frame_rate * 8.0 * frame_size
        self.l1_bit_rate = self.frame_rate * 8.0 * (frame_size + interframe_gap)
        if is_final:
            self.tx_l1_bps = self.l1_bit_rate
        else:
            self.tx_l1_bps = self.bps * (frame_size + interframe_gap) / frame_size


class PRStatistic(BaseModel):
    """pr stream statistic"""
    rx_stream_counter: StreamCounter = StreamCounter()
    latency: DelayData = DelayData(counter_type=const.CounterType.LATENCY)
    jitter: DelayData = DelayData(counter_type=const.CounterType.JITTER)
    live_loss_frames: int = 0


class StreamStatisticData(BaseModel):
    """stream statistic"""
    src_port_id: str = ""
    dest_port_id: str = ""
    src_port_addr: str = ""
    dest_port_addr: str = ""
    tx_counter: StreamCounter = StreamCounter()
    rx_counter: StreamCounter = StreamCounter()
    latency: DelayCounter = DelayCounter()
    jitter: DelayCounter = DelayCounter()
    live_loss_frames: int = 0
    burst_frames: int = 0

    def add_pr_stream_statistic(self, pr_stream_statistic: "PRStatistic") -> None:
        """aggregate pr stream statistic"""
        self.rx_counter.add_stream_counter(pr_stream_statistic.rx_stream_counter)
        self.latency.update(pr_stream_statistic.latency)
        self.jitter.update(pr_stream_statistic.jitter)
        self.live_loss_frames += max(0, pr_stream_statistic.live_loss_frames)

    def calculate(
        self, tx_port_struct: "PortStruct", rx_port_struct: "PortStruct"
    ) -> None:
        """for stream based mode to recalculate port statistic based on best result storage """
        tx_port_struct.statistic.aggregate_tx_statistic(self)
        rx_port_struct.statistic.add_rx(self.rx_counter)
        rx_port_struct.statistic.add_latency(DelayData.parse_obj(self.latency))
        rx_port_struct.statistic.add_jitter(DelayData.parse_obj(self.jitter))


class PortCounter(StreamCounter):
    counter_type: const.PortCounterType = const.PortCounterType.TX
    _tx_l1_bps: float = 0.0
    l2_bps: int = 0
    l1_bps: int = 0
    fps: int = 0

    def sum(self, other: "PortCounter") -> None:
        for name, value in self:
            if name == "counter_type":
                continue
            setattr(self, name, value + attrgetter(name)(other))

    def avg(self, count: int) -> None:
        for name, value in self:
            if name == "counter_type":
                continue
            setattr(self, name, math.floor(value / count))

    def add_stream_counter(self, counter: "StreamCounter") -> None:
        """aggregate stream statistic"""
        self.frames += counter.frames  # _cal_port_tx_frames  + _cal_port_rx_frames
        self.bps += counter.bps
        self.pps += counter.pps
        self.bytes_count += counter.bytes_count  # _cal_port_rx_bytes
        self._tx_l1_bps += counter.tx_l1_bps

    def calculate_port_rate(
        self,
        is_final: bool,
        duration: float,
        frame_size: float,
        interframe_gap: float,
    ) -> None:
        """ calculate port rate based on port statistics """
        super().calculate_stream_rate(is_final, duration, frame_size, interframe_gap)
        self.l2_bps = math.floor(self.l2_bit_rate) if is_final else self.bps
        self.fps = math.floor(self.frame_rate) if is_final else self.pps
        self.l1_bps = math.floor(
            self.l2_bps * (frame_size + interframe_gap) / frame_size
            if self.counter_type == const.PortCounterType.RX
            else self._tx_l1_bps
        )


class PortStatistic(BaseModel):
    """ 
    port statistic storage 
    PT_stream data should aggregate on TX port TX counter
    PR_stream data should aggregate on Rx port RX counter
    """
    port_id: str = ""
    is_final: bool = False  # for calculation use
    frame_size: float = 1.0  # for calculation use
    duration: float = 0.0  # for calculation use
    rate_percent: float = 0.0  # # for calculation use
    interframe_gap: float = 0.0  # for calculation use
    port_speed: float = 0.0  # for calculation use
    tx_counter: PortCounter = PortCounter(counter_type=const.PortCounterType.TX)
    rx_counter: PortCounter = PortCounter(counter_type=const.PortCounterType.RX)
    latency: DelayCounter = DelayCounter()
    jitter: DelayCounter = DelayCounter()
    stream_statistic: List[StreamStatisticData] = []
    fcs_error_frames: int = 0
    burst_frames: int = 0
    burst_bytes_count: int = 0
    loss_frames: int = 0
    loss_ratio: float = 0.0
    actual_rate_percent: float = 0.0
    tx_rate_l1_bps_theor: int = 0
    tx_rate_fps_theor: int = 0
    gap_count: int = 0
    gap_duration: int = 0

    @validator("tx_rate_l1_bps_theor", always=True)
    def set_theor_l1_bps_rate(cls, _v: int, values: Dict[str, Any]) -> int:
        return math.floor(values["port_speed"])

    @validator("tx_rate_fps_theor", always=True)
    def set_theor_fps_rate(cls, _v: int, values: Dict[str, Any]) -> int:
        return math.floor(
            values["port_speed"]
            / 8.0
            / (values["interframe_gap"] + values["frame_size"])
        )

    def sum(self, other: "PortStatistic") -> None:
        """ sum up port statistic from other finalstatistic for average calculation"""
        self.tx_counter.sum(other.tx_counter)
        self.rx_counter.sum(other.rx_counter)

        self.latency.sum(other.latency)
        self.jitter.sum(other.jitter)
        for f in [
            "fcs_error_frames",
            "burst_frames",
            "burst_bytes_count",
            "loss_frames",
            "loss_ratio",
        ]:
            value = getattr(self, f)
            setattr(self, f, value + attrgetter(f)(other))

    def avg(self, count: int) -> None:
        """ average port statistic from other finalstatistic for average calculation"""
        self.tx_counter.avg(count)
        self.rx_counter.avg(count)

        self.latency.avg(count)
        self.jitter.avg(count)
        for f in [
            "fcs_error_frames",
            "burst_frames",
            "burst_bytes_count",
            "loss_frames",
            "loss_ratio",
        ]:
            value = getattr(self, f)
            setattr(self, f, math.floor(value / count))

    def aggregate_tx_statistic(self, stream_statistic: "StreamStatisticData") -> None:
        """aggregate tx port statistic based on pt stream statistic"""
        self.add_tx(stream_statistic.tx_counter)
        self.add_burst_frames(stream_statistic.burst_frames)
        self.add_burst_bytes_count(stream_statistic.rx_counter.bytes_count)
        self.add_loss(
            stream_statistic.tx_counter.frames,
            stream_statistic.rx_counter.frames,
            stream_statistic.live_loss_frames,
        )
        self.stream_statistic.append(stream_statistic)

    def aggregate_rx_statistic(self, pr_statistic: "PRStatistic") -> None:
        """aggregate rx port statistic based on pr statistic"""
        self.add_rx(pr_statistic.rx_stream_counter)
        self.add_latency(pr_statistic.latency)
        self.add_jitter(pr_statistic.jitter)

    def add_tx(self, tx_stream_counter: "StreamCounter") -> None:
        """ add tx stream counter into port counter from pr_stream statistic """
        tx_stream_counter.calculate_stream_rate(
            self.is_final, self.duration, self.frame_size, self.interframe_gap
        )
        self.tx_counter.add_stream_counter(tx_stream_counter)

    def add_rx(self, rx_stream_counter: "StreamCounter") -> None:
        """ add rx stream counter into port counter from pr_stream statistic """
        rx_stream_counter.calculate_stream_rate(
            self.is_final, self.duration, self.frame_size, self.interframe_gap
        )
        self.rx_counter.add_stream_counter(rx_stream_counter)

    def add_latency(self, delay_data: "DelayData") -> None:
        """ add rx latency counter into port counter from pr_stream statistic """
        self.latency.update(delay_data)

    def add_jitter(self, delay_data: "DelayData") -> None:
        """ add rx jitter counter into port counter from pr_stream statistic """
        self.jitter.update(delay_data)

    def add_burst_frames(self, frame_count: int) -> None:
        self.burst_frames += frame_count

    def add_burst_bytes_count(self, bytes_count: int) -> None:
        self.burst_bytes_count += bytes_count

    def add_loss(self, tx_frames: int, rx_frames: int, live_loss_frames: int) -> None:
        if self.is_final:
            self.loss_frames += max(tx_frames - rx_frames, 0)
        else:
            self.loss_frames += max(live_loss_frames, 0)

    def calculate_rate(self) -> None:
        """ after collect data from stream, need to calculate rate"""
        self.loss_ratio = (
            self.loss_frames / self.tx_counter.frames
            if self.tx_counter.frames and self.loss_frames >= 0.0
            else 0.0
        )
        self.tx_counter.calculate_port_rate(
            self.is_final, self.duration, self.frame_size, self.interframe_gap
        )
        self.rx_counter.calculate_port_rate(
            self.is_final, self.duration, self.frame_size, self.interframe_gap
        )
        self.actual_rate_percent = 100.0 * self.tx_counter.l1_bit_rate / self.port_speed


class TotalCounter(BaseModel):
    """ Counter for TotalStatistic """
    frames: int = 0
    l1_bps: int = 0
    l2_bps: int = 0
    fps: int = 0
    bytes_count: int = 0

    def add(self, counter: "PortCounter") -> None:
        """ sum up port counter """
        self.frames += counter.frames
        self.l1_bps += counter.l1_bps
        self.l2_bps += counter.l2_bps
        self.fps += counter.fps
        self.bytes_count += counter.bytes_count

    def sum(self, other: "TotalCounter") -> None:
        """ sum up total counter for average final statistic """
        for name, value in self:
            setattr(self, name, value + attrgetter(name)(other))

    def avg(self, count: int) -> None:
        """ average total counter for average final statistic """
        for name, value in self:
            setattr(self, name, math.floor(value / count))


class TotalStatistic(BaseModel):
    """ Total Statistic for a FinalStatistic """
    tx_counter: TotalCounter = TotalCounter()
    rx_counter: TotalCounter = TotalCounter()
    fcs_error_frames: int = 0
    rx_loss_percent: float = 0.0
    rx_loss_frames: int = 0
    tx_rate_l1_bps_theor: int = 0
    tx_rate_fps_theor: int = 0
    tx_burst_frames: int = 0
    tx_burst_bytes: int = 0
    ber_percent: float = 0.0
    latency: DelayCounter = DelayCounter()
    jitter: DelayCounter = DelayCounter()
    gap_count: int = 0
    gap_duration: int = 0

    def sum(self, other: "TotalStatistic") -> None:
        """ To calculate average from all final statistics, need to sum up all statistic first"""
        for name, value in self:    # nested structure
            if name in ["tx_counter", "rx_counter", "latency", "jitter"]:
                getattr(self, name).sum(attrgetter(name)(other))
            else:   # int / float type
                setattr(self, name, value + attrgetter(name)(other))

    def avg(self, count: int) -> None:
        """ To calculate average from all final statistics, after sum up all statistic, need to average them"""
        for name, value in self:
            if name in ["tx_counter", "rx_counter", "latency", "jitter"]:   # nested structure
                getattr(self, name).avg(count)
            else:
                setattr(self, name, math.floor(value / count))  

    def add(self, port_data: "PortStatistic") -> None:
        """ aggregate all port statistic to get the total statistic """
        self.tx_counter.add(port_data.tx_counter)
        self.rx_counter.add(port_data.rx_counter)
        self.latency.sum(port_data.latency)
        self.jitter.sum(port_data.jitter)
        self.fcs_error_frames += port_data.fcs_error_frames
        self.tx_rate_l1_bps_theor += port_data.tx_rate_l1_bps_theor
        self.tx_rate_fps_theor += port_data.tx_rate_fps_theor
        self.rx_loss_frames += max(port_data.loss_frames, 0)
        self.tx_burst_bytes += port_data.burst_bytes_count
        self.tx_burst_frames += port_data.burst_frames
        self.gap_count += port_data.gap_count
        self.gap_duration += port_data.gap_duration
        self.rx_loss_percent = (
            self.rx_loss_frames / self.tx_counter.frames
            if self.tx_counter.frames and self.rx_loss_frames >= 0.0
            else 0.0
        )

        if (
            self.rx_counter.bytes_count == 0
            or self.rx_counter.frames == 0
            or self.rx_loss_frames <= 0
        ):
            self.ber_percent = 0.0
        else:
            divisor = (
                8.0
                * self.rx_counter.bytes_count
                * (self.rx_counter.frames + self.rx_loss_frames)
            )
            self.ber_percent = self.rx_loss_frames * self.rx_counter.frames / divisor


class FinalStatistic(BaseModel):
    """ Statistic Result for every query """
    test_case_type: const.TestType
    loop: int
    test_suite_type: str = "RFC-2544"
    result_state: const.ResultState = const.ResultState.PENDING
    tx_rate_percent: float
    is_final: bool = True
    frame_size: float
    repetition: Union[int, str] = "avg"
    rate_result_scope: const.RateResultScopeType = const.RateResultScopeType.COMMON
    port_data: List[PortStatistic] = []
    total: TotalStatistic = TotalStatistic()

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {float: lambda x: float("{:.3f}".format(x).rstrip("0"))}

    @validator("total", always=True)
    def calculate_total(
        cls, _v: "TotalStatistic", values: Dict[str, Any]
    ) -> TotalStatistic:
        """ aggregate all the port result """
        total = TotalStatistic()
        for port_data in values["port_data"]:
            total.add(port_data)
        total.jitter.avg(len(values["port_data"]))
        total.latency.avg(len(values["port_data"]))
        return total

    def set_result_state(self, state: "const.ResultState") -> None:
        self.result_state = state

    def sum(self, final: "FinalStatistic") -> None:
        """ for repetition larger than one, need to sum up all the finalstatistic to calculate average """
        for k, port_statistic in enumerate(self.port_data):
            port_statistic.sum(final.port_data[k])
        self.total.sum(final.total)

    def avg(self, count: int) -> None:
        """ for repetition larger than one, need to sum up all the finalstatistic to calculate average """
        for port_statistic in self.port_data:
            port_statistic.avg(count)
        self.total.avg(count)



class StatisticParams(BaseModel):
    test_case_type: const.TestType
    loop: int
    result_state: const.ResultState = const.ResultState.PENDING
    frame_size: float
    duration: float
    repetition: Union[int, str]
    rate_percent: float = 0.0
    rate_result_scope: const.RateResultScopeType = const.RateResultScopeType.COMMON

    def set_rate_percent(self, rate: float) -> None:
        self.rate_percent = rate

