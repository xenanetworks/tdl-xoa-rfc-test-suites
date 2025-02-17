from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, Generic, List, Protocol, Type, TypeVar, runtime_checkable
from pydantic import BaseModel
from loguru import logger
from xoa_core.types import PortIdentity

from plugin2889.const import TestStatus
from plugin2889.plugin.dataset import BaseRunProps, TestSuiteDataSharing
from plugin2889.dataset import (
    TestSuiteConfiguration2889,
    UnionTestSuitConfiguration,
)


@runtime_checkable
class PXOAOut(Protocol):
    def send_statistics(self, data) -> None:
        ...

    def send_warning(self, warning: Exception) -> None:
        ...

    def send_progress(self, progress: int) -> None:
        ...

    def send_error(self, error: Exception) -> None:
        ...


@runtime_checkable
class PStateConditions(Protocol):
    async def wait_if_paused(self) -> None:
        ...

    async def stop_if_stopped(self) -> None:
        ...


class PluginParameter(BaseModel):
    testers: Dict[str, Any]
    port_identities: List[PortIdentity]
    xoa_out: PXOAOut
    full_test_config: TestSuiteConfiguration2889
    data_sharing: TestSuiteDataSharing
    state_conditions: PStateConditions

    class Config:
        arbitrary_types_allowed = True


T = TypeVar("T", bound=UnionTestSuitConfiguration)


class TestSuitAbstract(ABC, Generic[T]):
    def __init__(self, plugin_params: PluginParameter, test_suit_config: T) -> None:
        self.plugin_params = plugin_params
        self.testers = plugin_params.testers
        self.xoa_out = plugin_params.xoa_out
        self.port_identities = plugin_params.port_identities
        self.full_test_config = plugin_params.full_test_config
        self.test_suit_config = test_suit_config
        self.test_suit_prepare()

    @abstractmethod
    def test_suit_prepare(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def do_test_logic(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def do_testing_cycle(self) -> Generator[Type[BaseRunProps], None, None]:
        raise NotImplementedError

    @abstractmethod
    async def run_test(self, run_props: Type[BaseRunProps]) -> None:
        raise NotImplementedError

    def __set_status(self, new_status: "TestStatus") -> None:
        self.test_status = new_status

    async def start(self) -> None:
        self.__set_status(TestStatus.START)
        logger.debug(f'start {self}')
        await self.do_test_logic()
        self.__set_status(TestStatus.STOP)
