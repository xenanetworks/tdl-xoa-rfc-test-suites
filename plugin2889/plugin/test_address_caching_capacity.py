from math import ceil
from functools import partial
from typing import Generator, Optional

from plugin2889.const import DECIMAL_100
from plugin2889.plugin.base_class import AddressLearningBase, IntBinarySearch
from plugin2889.plugin.dataset import BaseRunProps
from plugin2889.resource.manager import ResourcesManager
from plugin2889.util.logger import logger
from plugin2889.statistics import ResultData
from plugin2889.dataset import AddressCachingCapacityConfiguration


class AddressCachingCapacityTest(AddressLearningBase[AddressCachingCapacityConfiguration, int]):
    def __update_max_capacity(self, max_capacity: int) -> None:
        self.plugin_params.data_sharing.set_max_caching_capacity(max_capacity)

    def test_suit_prepare(self) -> None:
        self.binary_search = IntBinarySearch(
            rate_iteration_options=self.test_suit_config.address_iteration_options,
            success_callback_function=self.__update_max_capacity,
        )
        self.resources = ResourcesManager(
            testers=self.testers,
            port_identities=self.port_identities,
            test_config=self.full_test_config,
            port_pairs=self.create_port_pairs(),
            get_mac_address_function=self.get_mac_address,
        )
        self.create_statistics()

    def do_testing_cycle(self) -> Generator[BaseRunProps, None, None]:
        packet_sizes = self.full_test_config.general_test_configuration.frame_sizes.packet_size_list
        for current_iteration_number in self.iterations_offset_by_1:
            for packet_size in packet_sizes:
                yield BaseRunProps(current_iteration_number, int(packet_size))

    @property
    def learning_rate_pps(self) -> int:
        return ceil(self.test_suit_config.learning_rate_fps)

    async def run_test(self, run_props: BaseRunProps) -> None:
        logger.debug(f'iter props: {run_props}')
        logger.debug(self.test_suit_config.address_iteration_options)
        self.resources[self.port_name.monitoring].statistics.add_tx_resources(
            resource=self.resources[self.port_name.test],
            tpld_id=self.resources[self.port_name.test].streams[0].tpld_id
        )

        result: Optional["ResultData"] = None
        while not self.binary_search.determine_should_end(result):
            logger.debug(self.binary_search)
            self.learning_adress_count = int(self.binary_search.current)
            self.staticstics_collect = partial(
                self.statistics.collect_data,
                duration=self.traffic_duration,
                iteration=run_props.iteration_number,
                packet_size=run_props.packet_size,
                rate=DECIMAL_100,
            )
            await self.address_learning_test(run_props.packet_size)
            logger.debug(self.binary_search.is_ended)
            logger.debug(self.binary_search.current)
            result = await self.send_final_staticstics()