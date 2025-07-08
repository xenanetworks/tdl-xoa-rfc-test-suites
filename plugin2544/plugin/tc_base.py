import asyncio
import time
from copy import deepcopy
import math
from typing import List, Optional, Generator, TYPE_CHECKING, Tuple
from .learning import (
    AddressRefreshHandler,
    add_L2L3_learning_preamble_steps,
    add_flow_based_learning_preamble_steps,
    add_mac_learning_steps,
    schedule_arp_refresh,
    setup_address_arp_refresh,
)
from .data_model import Progress
from .setup_source_port_rates import setup_source_port_rates
from .statistics import FinalStatistic, StatisticParams
from .tc_throughput import get_initial_throughput_boundaries
from .tc_back_to_back import get_initial_back_to_back_boundaries, BackToBackBoutEntry
from .test_result import aggregate_data
from ..utils import constants as const
from .test_type_config import (
    LatencyConfig,
    ThroughputConfig,
    BackToBackConfig,
    FrameLossConfig,
    AllTestTypeConfig,
)
from loguru import logger

if TYPE_CHECKING:
    from .test_resource import ResourceManager
    from .test_config import TestConfigData
    from ..utils.interfaces import TestSuitePipe, PStateConditions


class TestCaseProcessor:
    def __init__(
        self,
        resources: "ResourceManager",
        test_conf: "TestConfigData",
        test_type_confs: List["AllTestTypeConfig"],
        state_conditions: "PStateConditions",
        xoa_out: "TestSuitePipe",
    ) -> None:
        self.resources: "ResourceManager" = resources
        self.xoa_out: "TestSuitePipe" = xoa_out
        self.__test_conf: "TestConfigData" = test_conf
        self.address_refresh_handler: Optional[AddressRefreshHandler] = None
        self.test_results = {}  # save result to calculate average
        self._all_test_type_conf: List["AllTestTypeConfig"] = test_type_confs  # all test type that need to run
        self.progress = Progress(
            total=sum(type_conf.process_count for type_conf in self._all_test_type_conf)
            * len(self.__test_conf.packet_size_list)
        )
        self._throughput_map = {}   # save throughput rate for latency relative to throughput use
        self.state_conditions = state_conditions

    def gen_loop(
        self, type_conf: "AllTestTypeConfig"
    ) -> Generator[Tuple[int, float], None, None]:
        """ get repetition and frame size according to outer loop mode """
        max_iteration = type_conf.common_options.repetition
        if self.__test_conf.is_iteration_outer_loop_mode:
            for iteration in range(1, max_iteration + 1):
                for current_packet_size in self.__test_conf.packet_size_list:
                    yield iteration, current_packet_size
        else:
            for current_packet_size in self.__test_conf.packet_size_list:
                for iteration in range(1, max_iteration + 1):
                    yield iteration, current_packet_size

    async def prepare(self) -> None:
        if (not self.resources.has_l3) or (not self.__test_conf.arp_refresh_enabled):
            # Only L3 and enable ARP Refresh can have the address refresh handler
            return None
        self.address_refresh_handler = await setup_address_arp_refresh(self.resources)

    async def start(self) -> None:
        await self.prepare()
        while True:
            self.progress.send(self.xoa_out)
            for type_conf in self._all_test_type_conf:
                for iteration, current_packet_size in self.gen_loop(type_conf):

                    await self.resources.setup_tpld_mode(current_packet_size)
                    await self.resources.setup_packet_size(current_packet_size)
                    await self.run(type_conf, current_packet_size, iteration)
                    if (
                        not self.__test_conf.is_iteration_outer_loop_mode
                        and type_conf.repetition > 1
                        and iteration == type_conf.repetition
                    ):  # calculate average
                        self.cal_average(type_conf, current_packet_size)
                if (
                    self.__test_conf.is_iteration_outer_loop_mode
                    and type_conf.repetition > 1
                ):  # calculate average at last
                    self.cal_average(type_conf)

            if not self.__test_conf.repeat_test_until_stopped:
                break
            self.progress.add_loop(self.xoa_out)

    async def run(
        self,
        test_type_conf: "AllTestTypeConfig",
        current_packet_size: float,
        iteration: int,
    ) -> None:
        if isinstance(test_type_conf, ThroughputConfig):
            await self._throughput(
                test_type_conf, current_packet_size, iteration
            )  # type:ignore
        elif isinstance(test_type_conf, LatencyConfig):
            await self._latency(
                test_type_conf, current_packet_size, iteration
            )  # type:ignore
        elif isinstance(test_type_conf, FrameLossConfig):
            await self._frame_loss(
                test_type_conf, current_packet_size, iteration
            )  # type:ignore
        elif isinstance(test_type_conf, BackToBackConfig):
            await self._back_to_back(
                test_type_conf, current_packet_size, iteration
            )  # type:ignore

    async def add_learning_steps(self, current_packet_size: float) -> None:
        await self.resources.stop_traffic()
        await add_L2L3_learning_preamble_steps(self.resources, current_packet_size)
        await add_mac_learning_steps(self.resources, const.MACLearningMode.EVERYTRIAL)
        await add_flow_based_learning_preamble_steps(
            self.resources, current_packet_size
        )

    async def start_test(
        self, test_type_conf: "AllTestTypeConfig", current_packet_size: float
    ) -> None:
        await self.state_conditions.wait_if_paused()
        await self.state_conditions.stop_if_stopped()
        await setup_source_port_rates(self.resources, current_packet_size)
        if test_type_conf.is_time_duration:
            await self.resources.set_tx_time_limit(
                test_type_conf.actual_duration * 1_000_000
            )

        await self.resources.clear_statistic()
        await self.resources.start_traffic(self.__test_conf.use_port_sync_start)
        await schedule_arp_refresh(self.resources, self.address_refresh_handler)

    async def collect(self, params: "StatisticParams") -> "FinalStatistic":
        start_time = time.time()
        each_query_fail = False
        final_fail = False
        while True:
            # handle live statistic per second
            data = await aggregate_data(self.resources, params, is_final=False)
            t = self.resources.should_quit(start_time, params.duration)
            should_quit, each_query_fail = t
            if each_query_fail:
                final_fail = True
                data.set_result_state(const.ResultState.FAIL)
            self.xoa_out.send_statistics(data)  # send live data
            if should_quit:
                break
            await asyncio.sleep(const.INTERVAL_SEND_STATISTICS)
        await asyncio.sleep(const.DELAY_STATISTICS)
        final_data = await aggregate_data(self.resources, params, is_final=True)    # handle Final data
        if final_fail:
            final_data.set_result_state(const.ResultState.FAIL)
        return final_data

    async def _latency(
        self,
        test_type_conf: "LatencyConfig",
        current_packet_size: float,
        repetition: int,
    ):
        factor = 1.0
        if test_type_conf.use_relative_to_throughput and self._throughput_map:
            factor = self._throughput_map.get(current_packet_size, 100.0) / 100.0

        for rate in test_type_conf.rate_sweep_list:
            # tx_rate_nominal_percent = rate_percent
            rate_percent = rate * factor
            params = StatisticParams(
                loop=self.progress.loop,
                test_case_type=test_type_conf.test_type,
                rate_percent=rate_percent,
                frame_size=current_packet_size,
                repetition=repetition,
                duration=test_type_conf.actual_duration,
            )
            await self.add_learning_steps(current_packet_size)
            self.resources.set_rate_percent(rate_percent)
            # set rate percent must after learning.
            await self.start_test(test_type_conf, current_packet_size)
            result = await self.collect(params)
            await self.resources.set_tx_time_limit(0)
            # result.tx_rate_nominal_percent = tx_rate_nominal_percent
            result.set_result_state(const.ResultState.DONE)
            self._add_result(result)

    async def _frame_loss(
        self,
        test_type_conf: "FrameLossConfig",
        current_packet_size: float,
        repetition: int,
    ):
        await self.resources.set_gap_monitor(test_type_conf.use_gap_monitor, test_type_conf.gap_monitor_start_microsec, test_type_conf.gap_monitor_stop_frames)
        for rate_percent in test_type_conf.rate_sweep_list:
            await self.add_learning_steps(current_packet_size)
            self.resources.set_rate_percent(rate_percent)   # must set rate after learning steps and before start test
            await self.start_test(test_type_conf, current_packet_size)
            params = StatisticParams(
                loop=self.progress.loop,
                test_case_type=test_type_conf.test_type,
                rate_percent=rate_percent,
                frame_size=current_packet_size,
                repetition=repetition,
                duration=test_type_conf.actual_duration,
            )
            result = await self.collect(params)
            await self.resources.set_tx_time_limit(0)
            test_state = check_if_frame_loss_success(test_type_conf, result)
            result.set_result_state(test_state)
            self._add_result(result)

    async def _throughput(
        self,
        test_type_conf: "ThroughputConfig",
        current_packet_size: float,
        repetition: int,
    ):
        await self.add_learning_steps(current_packet_size)
        result = None
        boundaries = get_initial_throughput_boundaries(test_type_conf, self.resources)
        params = StatisticParams(
            loop=self.progress.loop,
            test_case_type=test_type_conf.test_type,
            frame_size=current_packet_size,
            repetition=repetition,
            duration=test_type_conf.actual_duration,
            rate_result_scope=test_type_conf.result_scope,
        )
        while True:
            await asyncio.sleep(const.DELAY_STATISTICS)
            should_continue = any(
                boundary.port_should_continue for boundary in boundaries
            )
            if not should_continue:
                break
            for boundary in boundaries:
                boundary.update_rate()
            params.set_rate_percent(boundaries[0].rate_percent)
            self.resources.set_rate_percent(params.rate_percent)
            await self.start_test(test_type_conf, current_packet_size)
            result = await self.collect(params)
            result.is_final = True
            self.xoa_out.send_statistics(result)  # send intermediate data: is_final = True & result_state = 'PENDING'

            for boundary in boundaries:
                boundary.update_boundary(result)
            await self.resources.set_tx_time_limit(0)

        if not test_type_conf.is_per_source_port:
            final = boundaries[0].best_final_result
            # record the max throughput rate
            if final is not None:
                self._set_throughput_for_frame_size(
                    final.frame_size, final.tx_rate_percent
                )
            else:
                final = result

        else:   # per port result 
            # Step 1: initial counter
            for port_struct in self.resources.port_structs:
                port_struct.init_counter(
                    params.frame_size, params.duration, is_final=True
                )
            # Step 2: aggregate counter
            for port_struct in self.resources.port_structs:
                for stream_struct in port_struct.stream_structs:
                    stream_struct.aggregate_best_result()
            # Step 3: calculate rate
            for port_struct in self.resources.port_structs:
                port_struct.statistic.calculate_rate()
            # can't merge these three steps above.

            final = FinalStatistic(
                test_case_type=params.test_case_type,
                is_final=True,
                loop=self.progress.loop,
                frame_size=params.frame_size,
                repetition=params.repetition,
                tx_rate_percent=params.rate_percent,
                rate_result_scope=test_type_conf.result_scope,
                port_data=[
                    port_struct.statistic for port_struct in self.resources.port_structs
                ],
                # stream_data=aggregate_stream_result(resource),
            )
        if final:
            rs = check_if_throughput_success(test_type_conf, final)
            final.set_result_state(rs)
        self._add_result(final)

    async def _back_to_back(
        self,
        test_type_conf: "BackToBackConfig",
        current_packet_size: float,
        repetition: int,
    ) -> None:
        await self.add_learning_steps(current_packet_size)
        for rate_percent in test_type_conf.rate_sweep_list:
            result = None
            # logger.debug(f'Rate: {rate_percent}')
            params = StatisticParams(
                loop=self.progress.loop,
                test_case_type=test_type_conf.test_type,
                rate_percent=rate_percent,
                frame_size=current_packet_size,
                repetition=repetition,
                duration=test_type_conf.actual_duration,
            )
            self.resources.set_rate_percent(rate_percent)
            boundaries = get_initial_back_to_back_boundaries(
                test_type_conf,
                self.resources.tx_ports,
                current_packet_size,
                rate_percent,
            )
            while True:
                await asyncio.sleep(const.DELAY_STATISTICS)
                # if not any(boundary.port_should_continue for boundary in boundaries):
                #     logger.debug('Break Loop')
                #     break
                port_should_continue = [boundary.port_should_continue for boundary in boundaries]
                # logger.debug(port_should_continue)
                if not any(port_should_continue):
                    break
                # logger.debug(f'Packet: {boundaries[0].current}')
                await self._setup_packet_limit(boundaries)
                await self.start_test(test_type_conf, current_packet_size)
                result = await self.collect(params)
                result.is_final = True
                self.xoa_out.send_statistics(result)  # send intermediate data: is_final = True & result_state = 'PENDING'
                for boundary in boundaries:
                    boundary.update_boundaries(result)
            if result is not None:
                if all(boundary.port_test_passed for boundary in boundaries):
                    result.set_result_state(const.ResultState.DONE)
                else:
                    result.set_result_state(const.ResultState.FAIL)
                self._add_result(result)

    def _set_throughput_for_frame_size(self, frame_size: float, rate: float):
        """for latency relative to throughput use, use max throughput rate and only for throughput common result scope"""
        if frame_size not in self._throughput_map:
            self._throughput_map[frame_size] = 0
        self._throughput_map[frame_size] = max(rate, self._throughput_map[frame_size])

    def _average_statistic(
        self, statistic_lists: List[FinalStatistic]
    ) -> Optional[FinalStatistic]:
        final: Optional[FinalStatistic] = None
        for statistic in statistic_lists:
            if not final:
                final = deepcopy(statistic)
            else:
                final.sum(statistic)
        if final:
            final.repetition = "avg"
            final.avg(len(statistic_lists))
        return final

    def _average_per_frame_size(
        self, test_type_conf: "AllTestTypeConfig", frame_size: float
    ) -> None:
        final: Optional[FinalStatistic] = None
        result = self.test_results[test_type_conf.test_type][frame_size]
        if isinstance(test_type_conf, ThroughputConfig):
            """throughput test calculate average based on same frame size"""
            statistic_lists = []
            for s in result.values():
                statistic_lists.extend(s)
            final = self._average_statistic(statistic_lists)
            if final:
                self.xoa_out.send_statistics(final) # send average statistics
        else:
            """calculate average based on same frame size and same rate"""
            for statistic_lists in result.values():
                final = self._average_statistic(statistic_lists)
                if final:
                    self.xoa_out.send_statistics(final)  # send average statistics

    def cal_average(
        self, test_type_conf: "AllTestTypeConfig", frame_size: Optional[float] = None
    ) -> None:
        if frame_size:
            result = self.test_results[test_type_conf.test_type][frame_size]
            self._average_per_frame_size(test_type_conf, frame_size)
        else:
            result = self.test_results[test_type_conf.test_type]
            for f in result.keys():
                self._average_per_frame_size(test_type_conf, f)

    def _add_result(
        self, result: Optional["FinalStatistic"]
    ) -> None:
        if not (result and result.is_final):
            logger.debug('Add Result: Please check final status')
            return
        if result.test_case_type not in self.test_results:
            self.test_results[result.test_case_type] = {}
        if result.frame_size not in self.test_results[result.test_case_type]:
            self.test_results[result.test_case_type][result.frame_size] = {}
        if (
            result.tx_rate_percent
            not in self.test_results[result.test_case_type][result.frame_size]
        ):
            self.test_results[result.test_case_type][result.frame_size][
                result.tx_rate_percent
            ] = []
        self.test_results[result.test_case_type][result.frame_size][
            result.tx_rate_percent
        ].append(result)
        self.xoa_out.send_statistics(result)    # send final statistics
        self.progress.send(self.xoa_out)

    async def _setup_packet_limit(
        self, boundaries: List["BackToBackBoutEntry"]
    ) -> None:
        for _, port_struct in enumerate(self.resources.port_structs):
            for peer_struct in port_struct.properties.peers:
                stream_info_list = [
                    stream_info
                    for stream_info in port_struct.stream_structs
                    if stream_info.is_rx_port(peer_struct)
                ]  # select same tx and rx port stream
                port_stream_count = len(port_struct.properties.peers) * len(
                    stream_info_list
                )
                total_frame_count = boundaries[0].current
                stream_burst = total_frame_count / port_stream_count
                await asyncio.gather(
                    *[
                        stream_struct.set_frame_limit(math.floor(stream_burst))
                        for stream_struct in stream_info_list
                    ]
                )

def check_if_frame_loss_success(
    frame_loss_conf: "FrameLossConfig", result: "FinalStatistic"
) -> const.ResultState:
    if not frame_loss_conf.use_pass_criteria:
        return const.ResultState.DONE
    if (frame_loss_conf.is_percentage_pass_criteria and result.total.rx_loss_percent * 100 > frame_loss_conf.pass_criteria_loss) or \
        (not frame_loss_conf.is_percentage_pass_criteria and result.total.rx_loss_frames > frame_loss_conf.pass_criteria_loss):
        return const.ResultState.FAIL
    return const.ResultState.SUCCESS

def check_if_throughput_success(
        throughput_conf: "ThroughputConfig", result: "FinalStatistic"
) -> const.ResultState:
    result_state = const.ResultState.DONE
    if result.total.rx_loss_percent > throughput_conf.acceptable_loss_pct:  # check acceptable loss
        result_state = const.ResultState.FAIL
    elif throughput_conf.use_pass_criteria:     # check pass criteria
        if result.tx_rate_percent >= throughput_conf.pass_criteria_throughput_pct:
            result_state = const.ResultState.SUCCESS
        else:
            result_state = const.ResultState.FAIL
        if throughput_conf.is_per_source_port:  # check actual_rate_percent for each port
            for port_data in result.port_data:
                if port_data.actual_rate_percent < throughput_conf.pass_criteria_throughput_pct:
                    result_state = const.ResultState.FAIL
                    break
    return result_state