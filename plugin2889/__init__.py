import hashlib
import traceback
from pathlib import Path
from typing import TYPE_CHECKING
from xoa_core.types import PluginAbstract

if TYPE_CHECKING:
    from plugin2889.dataset import TestSuiteConfiguration2889

from plugin2889.plugin.dataset import TestSuiteDataSharing
from plugin2889.const import TestType
from plugin2889.util.logger import logger
from plugin2889.plugin.test_abstract import PluginParameter
from plugin2889.plugin.test_rate import RateTest
from plugin2889.plugin.test_congestion_control import CongestionControlTest
from plugin2889.plugin.test_forward_pressure import ForwardPressureTest
from plugin2889.plugin.test_max_forwarding_rate import MaxForwardingRateTest
from plugin2889.plugin.test_address_caching_capacity import AddressCachingCapacityTest
from plugin2889.plugin.test_address_learning_rate import AddressLearningRateTest
from plugin2889.plugin.test_errored_frames_filtering import ErroredFramesFilteringTest
from plugin2889.plugin.test_broadcast_forwarding import BroadcastForwardingTest


TEST_TYPE_CLASS = {
    TestType.RATE_TEST: RateTest,
    TestType.CONGESTION_CONTROL: CongestionControlTest,
    TestType.FORWARD_PRESSURE: ForwardPressureTest,
    TestType.MAX_FORWARDING_RATE: MaxForwardingRateTest,
    TestType.ADDRESS_CACHING_CAPACITY: AddressCachingCapacityTest,
    TestType.ADDRESS_LEARNING_RATE: AddressLearningRateTest,
    TestType.ERRORED_FRAMES_FILTERING: ErroredFramesFilteringTest,
    TestType.BROADCAST_FORWARDING: BroadcastForwardingTest,
}

TEST_ERROR_PATH = Path().resolve() / 'test_error'


class TestSuite2889(PluginAbstract["TestSuiteConfiguration2889"]):
    def prepare(self) -> None:
        pass

    async def __do_test(self) -> None:
        plugin_params = PluginParameter(
            testers=self.testers,
            port_identities=self.port_identities,
            xoa_out=self.xoa_out,
            full_test_config=self.cfg,
            data_sharing=TestSuiteDataSharing(),
            state_conditions=self.state_conditions,
        )
        for test_suit_config in self.cfg.enabled_test_suit_config_list:
            test_suit_class = TEST_TYPE_CLASS[test_suit_config.test_type]
            logger.debug(f"init {test_suit_class}")
            await test_suit_class(plugin_params, test_suit_config).start()

    async def __post_test(self) -> None:
        logger.info("test finish")

    async def start(self) -> None:
        await self.__do_test()
        await self.__post_test()






class TestSuite2889Testing(TestSuite2889):
    def get_error_id(self, tb_exc: str) -> str:
        return hashlib.md5(tb_exc.encode('utf-8')).hexdigest()

    async def start(self) -> None:
        TEST_ERROR_PATH.mkdir(exist_ok=True)
        try:
            await super().start()
        except Exception:
            tb_exc = traceback.format_exc()
            error_id = self.get_error_id(tb_exc)
            current_error_path = TEST_ERROR_PATH / error_id
            current_error_path.mkdir(exist_ok=True)
            with open(current_error_path / 'traceback.txt', 'w') as error_log:
                traceback.print_exc(file=error_log)
            self.xoa_out.send_statistics({
                    'error_id': error_id
            })