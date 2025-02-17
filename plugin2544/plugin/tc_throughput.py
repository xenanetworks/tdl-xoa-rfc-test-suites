from typing import List, Optional

from .statistics import FinalStatistic
from .test_resource import ResourceManager

from .structure import PortStruct
from .test_type_config import ThroughputConfig
from loguru import logger

class ThroughputBoutEntry:
    def __init__(self, throughput_conf: "ThroughputConfig", port_struct: "PortStruct"):
        self.current = self.rate_percent = self.next = throughput_conf.initial_value_pct
        self.left_bound: float = throughput_conf.minimum_value_pct
        self.right_bound: float = throughput_conf.maximum_value_pct
        self._last_move: int = 0
        self._port_struct: PortStruct = port_struct
        self._throughput_conf = throughput_conf
        self.best_final_result: Optional[FinalStatistic] = None
        self._port_test_passed = False
        self._port_should_continue = True
        self._is_less_than_resolution = False
        

    @property
    def port_should_continue(self) -> bool:
        return self._port_should_continue

    @property
    def port_test_passed(self) -> bool:
        return self._port_test_passed

    def update_left_bound(self):
        self.left_bound = self.current
        self._last_move = -1
        # logger.debug(f"{self.left_bound} {self.right_bound} -> {abs((self.left_bound + self.right_bound) / 2 - self.right_bound)}")
        self._is_less_than_resolution = abs((self.left_bound + self.right_bound) / 2 - self.left_bound) < self._throughput_conf.value_resolution_pct
        if self._is_less_than_resolution:
            self.next = self.right_bound
            self.left_bound = self.right_bound
        else:
            self.next = (self.left_bound + self.right_bound) / 2
        # logger.debug(f"update left bound -> {self.left_bound}")

    def update_right_bound(self, loss_ratio: float):
        self.right_bound = self.current
        self._last_move = 1
        self._is_less_than_resolution = abs((self.left_bound + self.right_bound) / 2 - self.right_bound) < self._throughput_conf.value_resolution_pct
        # logger.debug(f"{self.left_bound} {self.right_bound} -> {abs((self.left_bound + self.right_bound) / 2 - self.right_bound)}")
        if self._is_less_than_resolution:
            self.next = self.left_bound
            self.right_bound = self.left_bound
        if self._throughput_conf.search_type.is_fast:
            self.next = max(
                self.current * (1.0 - loss_ratio),
                self.left_bound,
            )
        else:
            self.next = (self.left_bound + self.right_bound) / 2
        # logger.debug(f"update right bound -> {self.right_bound}")

    def compare_search_pointer(self) -> bool:
        return self.next == self.current

    def pass_threshold(self) -> bool:
        return (
            self.current >= self._throughput_conf.pass_criteria_throughput_pct
            if self._throughput_conf.use_pass_criteria
            else True
        )

    def update_rate(self):
        self.current = self.next
        self.rate_percent = self.next
        # logger.debug(f"running rate: {self.current}")

    def update_boundary(self, result: Optional["FinalStatistic"]) -> None:
        self._port_should_continue = self._port_test_passed = False
        if not result:
            self._port_should_continue = True
            return
        if self._throughput_conf.is_per_source_port:
            loss_ratio = self._port_struct.statistic.loss_ratio
        else:
            loss_ratio = result.total.rx_loss_percent
        loss_ratio_pct = loss_ratio * 100.0
        # logger.debug(f"{loss_ratio_pct} - {self._throughput_conf.acceptable_loss_pct}")
        is_acceptable_loss = loss_ratio_pct <= self._throughput_conf.acceptable_loss_pct
        if is_acceptable_loss:
            if self._throughput_conf.is_per_source_port:
                for stream in self._port_struct.stream_structs:
                    stream.set_best_result()
            else:
                self.best_final_result = result
            if self.right_bound == self._throughput_conf.maximum_value_pct:
                self._port_should_continue = False
            self.update_left_bound()
        else:
            self.update_right_bound(loss_ratio)
        # logger.debug(f"next: {self.next}")
        if self.compare_search_pointer():
            return
            # self._port_test_passed = is_acceptable_loss and self.pass_threshold() 
        else:
            self._port_should_continue = True


def get_initial_throughput_boundaries(
    throughput_conf: "ThroughputConfig", resources: "ResourceManager"
) -> List["ThroughputBoutEntry"]:
    if throughput_conf.is_per_source_port:
        return [
            ThroughputBoutEntry(throughput_conf, port_struct)
            for port_struct in resources.tx_ports
        ]
    else:
        return [ThroughputBoutEntry(throughput_conf, resources.tx_ports[0])]
