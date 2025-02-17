from math import ceil
from decimal import Decimal
from functools import partial
from typing import Generator, Iterable, Optional

from plugin2889.const import DECIMAL_100
from plugin2889.plugin.base_class import AddressLearningBase, DecimalBinarySearch
from plugin2889.plugin.dataset import AddressLearningRateRunProps
from plugin2889.resource.manager import ResourcesManager
from plugin2889.util.logger import logger
from plugin2889.statistics import ResultData
from plugin2889.dataset import AddressLearningRateConfiguration


class AddressLearningRateTest(AddressLearningBase[AddressLearningRateConfiguration, Decimal]):
    def test_suit_prepare(self) -> None:
        self.resources = ResourcesManager(
            testers=self.testers,
            port_identities=self.port_identities,
            test_config=self.full_test_config,
            port_pairs=self.create_port_pairs(),
            get_mac_address_function=self.get_mac_address,
        )
        self.create_statistics()

    def do_testing_cycle(self) -> Generator[AddressLearningRateRunProps, None, None]:
        packet_sizes = self.full_test_config.general_test_configuration.frame_sizes.packet_size_list
        max_capacity = self.plugin_params.data_sharing.get_max_caching_capacity()
        logger.debug(max_capacity)
        sweep_options: Iterable[int]
        if self.test_suit_config.only_use_capacity and max_capacity > 0:
            sweep_options = (max_capacity,)
        else:
            end_value = max_capacity if self.test_suit_config.set_end_address_to_capacity and max_capacity else int(self.test_suit_config.address_sweep_options.end_value)
            sweep_options = range(
                min(max_capacity, int(self.test_suit_config.address_sweep_options.start_value)),
                end_value + 1,
                int(self.test_suit_config.address_sweep_options.step_value),
            )

        for i in self.iterations_offset_by_1:
            for packet_size in packet_sizes:
                for address in sweep_options:
                    yield AddressLearningRateRunProps(i, int(packet_size), address_count=address)

    @property
    def learning_rate_pps(self) -> int:
        return ceil(Decimal(self.test_suit_config.learning_rate_fps) * self.binary_search.current / 100)

    async def run_test(self, run_props: AddressLearningRateRunProps) -> None:
        logger.debug(f'iter props: {run_props}')
        logger.debug(self.test_suit_config.rate_iteration_options)
        self.learning_adress_count = run_props.address_count
        self.binary_search = DecimalBinarySearch(rate_iteration_options=self.test_suit_config.rate_iteration_options)
        self.resources[self.port_name.monitoring].statistics.add_tx_resources(
            resource=self.resources[self.port_name.test],
            tpld_id=self.resources[self.port_name.test].streams[0].tpld_id
        )
        self.staticstics_collect = partial(
            self.statistics.collect_data,
            duration=self.traffic_duration,
            iteration=run_props.iteration_number,
            packet_size=run_props.packet_size,
            rate=DECIMAL_100,
        )

        result: Optional[ResultData] = None
        while not self.binary_search.determine_should_end(result):
            logger.debug(self.binary_search)
            logger.debug(self.learning_adress_count)
            await self.address_learning_test(run_props.packet_size)
            result = await self.send_final_staticstics()