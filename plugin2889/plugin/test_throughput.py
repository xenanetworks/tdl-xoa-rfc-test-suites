from functools import partial
from decimal import Decimal
from typing import Generator, Optional

from plugin2889 import const
from plugin2889.dataset import RateSubTestConfiguration
from plugin2889.plugin.base_class import BinarySearchMixin, DecimalBinarySearch, TestBase, TrafficInfo
from plugin2889.plugin.utils import sleep_log
from plugin2889.util.logger import logger
from plugin2889.statistics import ResultData
from plugin2889.dataset import CurrentIterProps


class ThroughputTest(BinarySearchMixin[Decimal], TestBase[RateSubTestConfiguration]):
    def do_testing_cycle(self) -> Generator[CurrentIterProps, None, None]:
        packet_sizes = self.full_test_config.general_test_configuration.frame_sizes.packet_size_list
        for iteration_number in self.iterations_offset_by_1:
            for packet_size in packet_sizes:
                yield CurrentIterProps(iteration_number, int(packet_size))

    async def run_test(self, run_props: CurrentIterProps) -> None:
        self.staticstics_collect = partial(
            self.statistics.collect_data,
            duration=self.test_suit_config.duration,
            iteration=run_props.iteration_number,
            rate=Decimal(0),
            get_rate_function=self.get_binary_search_current,
            packet_size=run_props.packet_size,
        )
        assert self.test_suit_config.rate_iteration_options
        self.binary_search = DecimalBinarySearch(rate_iteration_options=self.test_suit_config.rate_iteration_options)

        await self.toggle_port_sync_state()
        await self.resources.mac_learning()
        await sleep_log(const.DELAY_LEARNING_MAC)

        result: Optional[ResultData] = None
        while not self.binary_search.determine_should_end(result):
            logger.debug(self.binary_search)
            await self.resources.set_stream_packet_size(run_props.packet_size)
            await self.resources.set_stream_rate_and_packet_limit(run_props.packet_size, self.binary_search.current, self.test_suit_config.duration)
            self.statistics.reset_max()
            traffic_info: Optional[TrafficInfo] = None
            async for traffic_info in self.generate_traffic():
                result = traffic_info.result
            result = await self.send_final_staticstics()

        if result and result.status.is_success and self.test_suit_config.topology.is_mesh_topology:
            self.plugin_params.data_sharing.set_throughput_of_frame_size(run_props.packet_size, self.binary_search.passed)
