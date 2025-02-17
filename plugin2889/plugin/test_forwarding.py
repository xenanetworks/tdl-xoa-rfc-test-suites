from decimal import Decimal
from functools import partial
from typing import Generator, TypeVar
from loguru import logger

from plugin2889 import const
from plugin2889.dataset import MaxForwardingRateConfiguration, RateSubTestConfiguration
from plugin2889.plugin.base_class import TestBase
from plugin2889.plugin.dataset import ForwadingTestRunProps
from plugin2889.plugin.utils import sleep_log


TFCFG = TypeVar("TFCFG", RateSubTestConfiguration, MaxForwardingRateConfiguration)


class ForwardingBase(TestBase[TFCFG]):
    def sweeping_rate_percents(self, packet_size: int) -> Generator[Decimal, None, None]:
        rate_sweep_options = self.test_suit_config.rate_sweep_options
        assert rate_sweep_options

        current_percent = rate_sweep_options.start_value
        if isinstance(self.test_suit_config, MaxForwardingRateConfiguration) and self.test_suit_config.use_throughput_as_start_value:
            current_percent = max(current_percent, self.plugin_params.data_sharing.get_throughput_of_frame_size(packet_size))

        while current_percent <= rate_sweep_options.end_value and current_percent <= const.DECIMAL_100:
            yield current_percent
            current_percent += rate_sweep_options.step_value

    def do_testing_cycle(self) -> Generator[ForwadingTestRunProps, None, None]:
        for i in self.iterations_offset_by_1:
            for packet_size in self.full_test_config.general_test_configuration.frame_sizes.packet_size_list:
                for percent in self.sweeping_rate_percents(packet_size):
                    yield ForwadingTestRunProps(
                        i,
                        int(packet_size),
                        percent,
                    )

    async def run_test(self, run_props: ForwadingTestRunProps) -> None:
        logger.debug(f'iter props: {run_props}')
        self.staticstics_collect = partial(
            self.statistics.collect_data,
            duration=self.test_suit_config.duration,
            iteration=run_props.iteration_number,
            rate=run_props.rate_percent,
            packet_size=run_props.packet_size,
        )
        await self.toggle_port_sync_state(self.resources)
        await self.resources.mac_learning()
        await sleep_log(const.DELAY_LEARNING_MAC)
        await self.resources.set_stream_packet_size(run_props.packet_size)
        await self.resources.set_stream_rate_and_packet_limit(run_props.packet_size, run_props.rate_percent, self.test_suit_config.duration)
        self.statistics.reset_max()

        async for _ in self.generate_traffic():
            continue

        await self.send_final_staticstics()