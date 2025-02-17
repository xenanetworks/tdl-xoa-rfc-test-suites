from typing import Dict
from dataclasses import dataclass, field
from decimal import Decimal
from loguru import logger


@dataclass
class TestSuiteDataSharing:
    throughput_of_frame_size: Dict[int, Decimal] = field(default_factory=dict)
    max_caching_capacity: int = 0

    def get_throughput_of_frame_size(self, frame_size: int) -> Decimal:
        return self.throughput_of_frame_size.get(frame_size, Decimal(0))

    def set_throughput_of_frame_size(self, frame_size: int, throughtput_rate: Decimal) -> None:
        current = self.get_throughput_of_frame_size(frame_size)
        self.throughput_of_frame_size[frame_size] = max(current, throughtput_rate)
        logger.debug(f"{frame_size} {throughtput_rate}")

    def get_max_caching_capacity(self) -> int:
        return self.max_caching_capacity

    def set_max_caching_capacity(self, capacity: int) -> None:
        self.max_caching_capacity = capacity


@dataclass
class BaseRunProps:
    iteration_number: int
    packet_size: int


@dataclass
class ForwadingTestRunProps(BaseRunProps):
    rate_percent: Decimal


ErroredFramesFilteringRunProps = ForwadingTestRunProps


@dataclass
class AddressLearningRateRunProps(BaseRunProps):
    address_count: int
