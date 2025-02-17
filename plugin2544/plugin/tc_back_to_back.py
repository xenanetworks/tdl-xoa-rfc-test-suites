from .structure import PortStruct
from typing import List, Optional
from .test_type_config import BackToBackConfig
from loguru import logger
from decimal import Decimal
from .statistics import FinalStatistic

class BackToBackBoutEntry:
    def __init__(
        self,
        test_type_conf: BackToBackConfig,
        port_struct: PortStruct,
        frame_size: float,
        rate: float,
    ):
        self._test_type_conf = test_type_conf
        self._port_struct = port_struct
        self._frame_size = frame_size
        self._left_bound: float = 0.0
        self._right_bound = self.current = self.next = (
            self._test_type_conf.maximun_burst * rate / 100.0
        )
        self._last_move: int = 0
        self._port_should_continue: bool = True
        self._port_test_passed: bool = False
        self._port_struct.clear_counter()
        self._is_less_than_resolution = False

    @property
    def port_should_continue(self) -> bool:
        return self._port_should_continue

    @property
    def port_test_passed(self) -> bool:
        return self._port_test_passed

    def update_boundaries(self, result: Optional["FinalStatistic"]) -> None:
        self._port_should_continue = self._port_test_passed = False

        if not result:
            self._port_should_continue = True
            return
        
        no_frame_loss = self._port_struct.statistic.loss_frames == 0
        if self._left_bound <= self._right_bound:
            if self._port_struct.statistic and no_frame_loss:
                self.update_left_bound()
            else:
                self.update_right_bound()
            if self.compare_search_pointer():
                if no_frame_loss:
                    self._port_test_passed = True
                else:
                    self._port_test_passed = False
                # logger.debug(f'test_passed: {self._port_test_passed} should continue: {self._port_should_continue}')
                return
            else:
                self._port_should_continue = True

        self.current = self.next
        # logger.debug(f"Run this: {self.current}")

    def update_left_bound(self) -> None:
        self._left_bound = self.current
        self.next = (self._left_bound + self._right_bound) / 2
        self._last_move = -1

    def update_right_bound(self) -> None:
        self._right_bound = self.current
        self.next = (self._left_bound + self._right_bound) / 2
        self._last_move = 1

    def compare_search_pointer(self) -> bool:
        res = self._test_type_conf.burst_resolution
        # logger.debug(f"{self.next} - {self.current}")
        self._is_less_than_resolution = abs(self.next - self.current) <= res
        if not self._is_less_than_resolution:    
            # logger.debug('Continue Searching')
            return False
        # End Searching
        if self.next >= self.current:
            # make sure we report the right boundary if we are so close to it.
            if (self._right_bound - self.current) <= res:
                self.current = self._right_bound
        else:
            if (self.current - self._left_bound) <= res:
                self.current = self._left_bound
        # logger.debug(f'Founded: {self.current}')
        return True



def get_initial_back_to_back_boundaries(
    back_to_back_conf: "BackToBackConfig",
    port_structs: List[PortStruct],
    current_packet_size: float,
    rate_percent: float,
) -> List["BackToBackBoutEntry"]:
    return [
        BackToBackBoutEntry(
            back_to_back_conf, port_structs[0], current_packet_size, rate_percent
        )
    ]
