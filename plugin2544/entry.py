from xoa_core.types import PluginAbstract
from typing import TYPE_CHECKING, List
from .plugin.config_checkers import check_test_type_config
from .plugin.tc_base import TestCaseProcessor
from .plugin.test_resource import ResourceManager
from .plugin.test_config import TestConfigData
from .plugin.test_type_config import get_available_test_type_config, AllTestTypeConfig
if TYPE_CHECKING:
    from .dataset import PluginModel2544


class TestSuite2544(PluginAbstract["PluginModel2544"]):
    def prepare(self) -> None:
        self.tpld_id = 0
        self.mac_learned = False
        self.iteration: int = 1
        self.__test_conf = TestConfigData(self.cfg.test_configuration)
        self.resources = ResourceManager(
            self.testers,
            self.cfg.ports_configuration,
            self.port_identities,
            self.__test_conf,
            self.xoa_out,
        )
        self._test_type_conf: List["AllTestTypeConfig"] = get_available_test_type_config(self.cfg.test_types_configuration) 
        self.tc = TestCaseProcessor(self.resources, self.__test_conf, self._test_type_conf, self.state_conditions, self.xoa_out)

    async def __pre_test(self) -> None:
        """ check config and configure ports and streams"""
        check_test_type_config(self._test_type_conf)
        await self.resources.init_resource(
            self.cfg.test_types_configuration.latency_test.latency_mode,
        )

    async def __do_test(self) -> None:
        """ configure tests and run traffic """
        await self.tc.start()

    async def __post_test(self) -> None:
        """ after test should release resource """
        # TODO: wait for callback exception catch
        await self.resources.free()

    async def start(self) -> None:
        await self.__pre_test()
        await self.__do_test()
        await self.__post_test()
