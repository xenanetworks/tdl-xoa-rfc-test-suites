import copy
import math
from enum import Enum
from pydantic import BaseModel, field_validator, Field
from decimal import Decimal
from dataclasses import dataclass
from ..utils.constants import ResultState
from ..utils.field import MacAddress, NewIPv4Address, NewIPv6Address
from typing import Union, Annotated


class AddressCollection(BaseModel):
    smac: MacAddress = MacAddress("00:00:00:00:00:00")
    dmac: MacAddress = MacAddress("00:00:00:00:00:00")
    src_ipv4_addr: NewIPv4Address = NewIPv4Address("0.0.0.0")
    dst_ipv4_addr: NewIPv4Address = NewIPv4Address("0.0.0.0")
    src_ipv6_addr: NewIPv6Address = NewIPv6Address("::")
    dest_ipv6_addr: NewIPv6Address = NewIPv6Address("::")

    def change_dmac_address(self, mac_address: "MacAddress") -> None:
        self.dmac = mac_address

    def copy(self) -> "AddressCollection":
        return copy.deepcopy(self)


class StreamCounter(BaseModel):
    frames: int = 0  # packet_count_since_cleared
    bps: int = 0  # bit_count_last_sec
    pps: int = 0  # packet_count_last_sec
    bytes_count: int = 0  # byte_count_since_cleared
    frame_rate: Decimal = Decimal("0")
    l2_bit_rate: Decimal = Decimal("0")
    l1_bit_rate: Decimal = Decimal("0")
    tx_l1_bps: Decimal = Decimal("0")

    def update(self, counter: "StreamCounter") -> None:
        self.frames += counter.frames
        self.bps += counter.bps
        self.pps += counter.pps
        self.bytes_count += counter.bytes_count

    def reset(self) -> None:
        self.frames = 0  # packet_count_since_cleared
        self.bps = 0  # bit_count_last_sec
        self.pps = 0  # packet_count_last_sec
        self.bytes_count = 0  # byte_count_since_cleared
        self.frame_rate = Decimal("0")
        self.l2_bit_rate = Decimal("0")
        self.l1_bit_rate = Decimal("0")
        self.tx_l1_bps = Decimal("0")


class CounterType(Enum):
    JITTER = -1
    LATENCY = -2147483648


class AvgMinMax(BaseModel):
    minimum: int = 0
    maximum: int = 0
    average: int = 0


class DelayData(BaseModel):
    counter_type: CounterType = CounterType.LATENCY
    minimum: Annotated[int, Field(validate_default=True)] = 0
    maximum: Annotated[int, Field(validate_default=True)] = 0
    average: Annotated[int, Field(validate_default=True)] = 0
    is_valid: bool = True

    @field_validator("average", "minimum", "maximum")
    def check_is_valid(cls, v, values):
        if v == values["counter_type"].value:
            values["is_valid"] = False
            return 0
        return v


class DelayCounter(DelayData):
    _total: int = 0
    _count: int = 0

    def reset(self) -> None:
        self.average = 0
        self.minimum = 0
        self.maximum = 0
        self._total = 0
        self._count = 0

    class Config:
        underscore_attrs_are_private = True

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
        self.average = math.floor(
            Decimal(self._total) / Decimal(self._count) if self._count else 0
        )


class ErrorCounter(BaseModel):
    non_increm_seq_no_events: int = 0
    swapped_seq_no_events: int = 0
    non_increm_payload_events: int = 0
    _last_lost_packets: int = 0

    def get_lost_packets_delta(self) -> int:
        last_lost = self._last_lost_packets
        self._last_lost_packets = self.non_increm_seq_no_events
        return max(self.non_increm_seq_no_events - last_lost, 0)

    def update(self, data: "ErrorCounter") -> None:
        self.non_increm_seq_no_events += max(data.non_increm_seq_no_events, 0)
        self.swapped_seq_no_events += max(data.swapped_seq_no_events, 0)
        self.non_increm_payload_events += max(data.non_increm_payload_events, 0)

    def reset(self) -> None:
        self.non_increm_seq_no_events = 0
        self.swapped_seq_no_events = 0
        self.non_increm_payload_events = 0
        self._last_lost_packets = 0

    class Config:
        underscore_attrs_are_private = True


class PortResult(BaseModel):
    mc_source_data: StreamCounter = StreamCounter()
    mc_destination_data: StreamCounter = StreamCounter()
    uc_source_data: StreamCounter = StreamCounter()
    uc_destination_data: StreamCounter = StreamCounter()
    rx_mc_group_count: int = 0
    latency_counters: DelayCounter = DelayCounter(counter_type=CounterType.LATENCY)
    jitter_counters: DelayCounter = DelayCounter(counter_type=CounterType.JITTER)
    mc_error_counters: ErrorCounter = ErrorCounter()
    uc_error_counters: ErrorCounter = ErrorCounter()
    join_sent_timestamp: int = 0
    rx_data_after_join_timestamp: int = 0
    leave_sent_timestamp: int = 0
    rx_data_after_leave_timestamp: int = 0

    def set_join_sent_timestamp(self, val: int) -> None:
        if self.join_sent_timestamp == 0:
            self.join_sent_timestamp = val

    def set_leave_sent_timestamp(self, val: int) -> None:
        if self.leave_sent_timestamp == 0:
            self.leave_sent_timestamp = val

    @property
    def join_delay(self) -> float:
        return self.rx_data_after_join_timestamp - self.join_sent_timestamp

    @property
    def leave_delay(self) -> float:
        return self.rx_data_after_leave_timestamp - self.leave_sent_timestamp

    def set_rx_mc_group_count(self, val: int) -> None:
        self.rx_mc_group_count = val

    def reset(self, reset_stored_props: bool = False) -> None:
        self.mc_source_data.reset()
        self.mc_destination_data.reset()
        self.uc_source_data.reset()
        self.uc_destination_data.reset()
        self.latency_counters.reset()
        self.jitter_counters.reset()
        self.mc_error_counters.reset()
        self.uc_error_counters.reset()
        if reset_stored_props:
            self.rx_mc_group_count = 0
            self.join_sent_timestamp = 0
            self.rx_data_after_join_timestamp = 0
            self.leave_sent_timestamp = 0
            self.rx_data_after_leave_timestamp = 0


@dataclass
class BoutInfo:
    mc_group_count: int
    packet_size: int
    iter_index: int
    rate: float
    actual_rate: float = 0
    result_state: ResultState = ResultState.PENDING
    is_final: bool = False

    def set_is_final(self, final: bool) -> None:
        self.is_final = final

    def set_result_state(self, result_state: ResultState) -> None:
        self.result_state = result_state

    def set_rate(self, rate: float) -> None:
        self.rate = self.actual_rate = rate

    def set_actual_rate(self, rate: float) -> None:
        self.actual_rate = rate

    def set_mc_group_count(self, group_count: int) -> None:
        self.mc_group_count = group_count
