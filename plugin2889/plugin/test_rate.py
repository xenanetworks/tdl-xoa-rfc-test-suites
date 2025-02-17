from typing import Generator, Union
from plugin2889.dataset import (
    RateTestConfiguration,
)
from plugin2889.plugin.base_class import TestBase
from plugin2889.util.logger import logger
from plugin2889.plugin.test_throughput import ThroughputTest
from plugin2889.plugin.test_forwarding import ForwardingBase


class RateTest(TestBase[RateTestConfiguration]):
    def test_suit_prepare(self) -> None:
        pass

    @property
    def enabled_sub_tests(self) -> Generator[Union[ThroughputTest, ForwardingBase], None, None]:
        for sub_config in self.test_suit_config.sub_test:
            if not sub_config.enabled:
                continue
            if sub_config.throughput_test_enabled:
                yield ThroughputTest(self.plugin_params, sub_config)
            if sub_config.forwarding_test_enabled:
                yield ForwardingBase(self.plugin_params, sub_config)

    async def start(self) -> None:
        for sub_class in self.enabled_sub_tests:
            logger.debug(f'start sub test: {sub_class}')
            await sub_class.start()

    def do_testing_cycle(self) -> None:
        pass

    async def run_test(self) -> None:
        pass
