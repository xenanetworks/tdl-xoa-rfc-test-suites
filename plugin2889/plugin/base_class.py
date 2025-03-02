import asyncio
import sys
import time
from math import ceil
from abc import ABC, abstractmethod
from decimal import ROUND_DOWN, Decimal
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Protocol,
    TypeVar,
    Union,
)

from loguru import logger
from xoa_driver.utils import apply
from xoa_driver.enums import OnOff
from xoa_driver.misc import Hex
from xoa_core.types import PortIdentity

from plugin2889 import const
from plugin2889.model import exceptions
from plugin2889.test_manager import L23TestManager
from plugin2889.statistics import ResultData, StatisticsProcessor
from plugin2889.dataset import MacAddress, PortPair
from plugin2889.dataset import (
    AddressCachingCapacityConfiguration,
    AddressLearningRateConfiguration,
    RateIterationOptions,
    TestSuiteConfiguration2889,
    UnionTestSuitConfiguration,
)
from plugin2889.plugin.utils import sleep_log, create_port_pair, group_by_port_property
from plugin2889.resource.manager import ResourcesManager
from plugin2889.model.protocol_segment import ModifierActionOption
from plugin2889.plugin.test_abstract import PluginParameter, TestSuitAbstract

if TYPE_CHECKING:
    from plugin2889.plugin.utils import PortPairs
    from plugin2889.resource.test_resource import TestResource


@dataclass
class TrafficInfo:
    progress: int
    result: ResultData


@dataclass
class AddressLearningPortRolePortNameMapping:
    """port name is like P-0-0-0"""
    test: str = ''
    learning: str = ''
    monitoring: str = ''


T = TypeVar("T", bound=Union[int, Decimal])


class PBinarySearch(Protocol, Generic[T]):
    rate_iteration_options: RateIterationOptions
    failed: T
    current: T
    left: T
    right: T
    passed: T
    is_ended: bool = False

    def determine_should_end(self, result: Optional[ResultData] = None) -> bool:
        ...

    def set_ended(self, is_test_pass: bool) -> None:
        ...


@dataclass
class BinarySearchBase(ABC, Generic[T]):
    rate_iteration_options: RateIterationOptions
    failed: T = field(init=False)
    current: T = field(init=False)
    left: T = field(init=False)
    right: T = field(init=False)
    passed: T = field(init=False)
    is_ended: bool = False
    success_callback_function: Optional[Callable] = None

    @abstractmethod
    def _type_cast(self, value: Any) -> T:
        raise NotImplementedError

    @abstractmethod
    def _calculate_move_right(self) -> T:
        raise NotImplementedError

    @abstractmethod
    def _calculate_move_left(self) -> T:
        raise NotImplementedError

    @abstractmethod
    def _determine_should_end_in_pass(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def _determine_should_end_in_fail(self) -> None:
        raise NotImplementedError

    def __post_init__(self) -> None:
        self.failed = self._type_cast(self.rate_iteration_options.maximum_value)
        self.passed = self._type_cast(0)
        self.current = self._type_cast(self.rate_iteration_options.initial_value)
        self.left = self._type_cast(self.rate_iteration_options.minimum_value)
        self.right = self._type_cast(self.rate_iteration_options.maximum_value)

    def set_ended(self, is_test_pass: bool) -> None:
        logger.debug(f'{is_test_pass} invoked')
        self.is_ended = True

    def determine_should_end(self, result: Optional[ResultData] = None) -> bool:
        if not self.is_ended and not result:
            return False
        is_test_pass = result is not None and result.status.is_success

        if not self.is_ended and is_test_pass:
            if self.success_callback_function:
                self.success_callback_function(self.current)

        if not self.is_ended and is_test_pass:
            self.passed = self.current
            self.left = self.current
            self.current = self._calculate_move_right()
            self._determine_should_end_in_pass()
        if not self.is_ended and not is_test_pass:
            self.failed = self.current
            self.right = self.current
            self.current = self._calculate_move_left()
            self._determine_should_end_in_fail()
        return self.is_ended


class DecimalBinarySearch(BinarySearchBase[Decimal]):
    def _type_cast(self, value: Any) -> Decimal:
        return Decimal(value).quantize(Decimal('.001'), rounding=ROUND_DOWN)

    def _calculate_move_right(self) -> Decimal:
        return ((self.current + self.right) / Decimal(2.0)).quantize(Decimal('.001'), rounding=ROUND_DOWN)

    def _calculate_move_left(self) -> Decimal:
        return ((self.failed + self.left) / Decimal(2.0)).quantize(Decimal('.001'), rounding=ROUND_DOWN)

    def _determine_should_end_in_pass(self) -> None:
        if self.current >= self.rate_iteration_options.maximum_value:
            self.set_ended(is_test_pass=True)
        elif (self.failed - self.passed) <= self.rate_iteration_options.value_resolution:
            self.set_ended(is_test_pass=True)

    def _determine_should_end_in_fail(self) -> None:
        if self.failed <= (self.rate_iteration_options.minimum_value + self.rate_iteration_options.value_resolution):
            self.set_ended(is_test_pass=False)
        elif abs(self.passed - Decimal(self.rate_iteration_options.maximum_value)) < sys.float_info.epsilon:
            self.set_ended(is_test_pass=False)


class IntBinarySearch(BinarySearchBase[int]):
    def _type_cast(self, value: Any) -> int:
        return int(value)

    def _calculate_move_right(self) -> int:
        return ceil((self.current + self.right) / 2)

    def _calculate_move_left(self) -> int:
        return int((self.failed + self.left) / 2)

    def _determine_should_end_in_pass(self) -> None:
        if self.current >= self.rate_iteration_options.maximum_value:
            self.set_ended(is_test_pass=True)
        elif (self.failed - self.passed) <= int(self.rate_iteration_options.value_resolution):
            self.set_ended(is_test_pass=True)

    def _determine_should_end_in_fail(self) -> None:
        if self.failed <= self.passed:
            self.set_ended(is_test_pass=False)
        elif self.failed <= int(self.rate_iteration_options.minimum_value + self.rate_iteration_options.value_resolution):
            self.set_ended(is_test_pass=False)


class BinarySearchMixin(Generic[T]):
    binary_search: PBinarySearch[T]

    def get_binary_search_current(self) -> T:
        return self.binary_search.current


class StaticsticsCollect(Protocol):
    async def __call__(self, is_live: bool) -> "ResultData":
        ...


TCONFIG = TypeVar("TCONFIG", bound=UnionTestSuitConfiguration)


class TestBase(TestSuitAbstract[TCONFIG]):
    port_identities: List[PortIdentity]
    resources: ResourcesManager
    test_manager: L23TestManager
    full_test_config: TestSuiteConfiguration2889
    test_status: const.TestStatus
    testers: Dict[str, Any]
    plugin_params: PluginParameter
    staticstics_collect: StaticsticsCollect

    def create_port_pairs(self) -> "PortPairs":
        assert self.test_suit_config.direction and self.test_suit_config.topology, 'invalid traffic direction or topology'
        return create_port_pair(
            self.test_suit_config.direction,
            self.test_suit_config.topology,
            self.full_test_config.ports_configuration,
            self.test_suit_config.port_role_handler,
            self.port_identities,
        )

    def test_suit_prepare(self) -> None:
        self.resources = ResourcesManager(
            self.testers,
            self.full_test_config,
            self.port_identities,
            port_pairs=self.create_port_pairs()
        )
        self.create_statistics()

    async def toggle_port_sync_state(
        self,
        resources: Optional["ResourcesManager"] = None,
        is_need_toggle: bool = False,
        sync_off_duration: int = 0,
        sync_on_duration: int = 0,
    ) -> None:
        is_need_toggle = is_need_toggle or self.full_test_config.general_test_configuration.toggle_sync_state
        if not is_need_toggle:
            return None

        resources = resources or self.resources
        await resources.set_tx_config_enable(OnOff.OFF)
        await sleep_log(sync_off_duration or self.full_test_config.general_test_configuration.sync_off_duration)
        await resources.set_tx_config_enable(OnOff.ON)

        start_time = time.time()
        while not resources.all_ports_is_sync:
            await sleep_log(const.INTERVAL_CHECK_PORT_SYNC)
            if time.time() - start_time > const.WAIT_SYNC_STATE_TIMEOUT:
                raise exceptions.WaitSyncStateTimeout()
        await sleep_log(sync_on_duration or self.full_test_config.general_test_configuration.sync_on_duration)

    @property
    def is_stop_on_los(self) -> bool:
        return self.full_test_config.general_test_configuration.should_stop_on_los and not self.resources.all_ports_is_sync

    def check_statistic_status(self, result: "ResultData", is_live: bool = False) -> const.StatisticsStatus:
        statistic_status = const.StatisticsStatus.SUCCESS if not is_live else const.StatisticsStatus.PENDING
        if result.total.loss > 0:
            return const.StatisticsStatus.FAIL
        return statistic_status

    def create_statistics(self) -> None:
        self.statistics = StatisticsProcessor(
            self.resources,
            test_type=self.test_suit_config.test_type,
            check_statistic_status_function=self.check_statistic_status,
        )

    async def setup_resources(self) -> None:
        await self.resources.reset_ports()
        await self.resources.check_port_link()
        await self.resources.configure_ports()
        await self.resources.map_pairs()

    async def do_test_logic(self) -> None:
        async with L23TestManager(self.resources) as self.test_manager:
            await self.setup_resources()
            for run_props in self.do_testing_cycle():
                await self.plugin_params.state_conditions.wait_if_paused()
                await self.plugin_params.state_conditions.stop_if_stopped()
                await self.run_test(run_props)

    @property
    def traffic_duration(self) -> int:
        return self.test_suit_config.duration

    async def generate_traffic(self, sample_rate: float = 1) -> AsyncGenerator[TrafficInfo, None]:
        async for duration_progress in self.test_manager.generate_traffic(self.traffic_duration, sampling_rate=sample_rate):
            if self.is_stop_on_los:
                raise exceptions.StopTestByLossSignal()
            result = await self.staticstics_collect(is_live=True)
            self.xoa_out.send_progress(duration_progress)
            self.xoa_out.send_statistics(self.reprocess_result(result, is_live=True))
            yield TrafficInfo(progress=duration_progress, result=result)

    @property
    def iterations_offset_by_1(self) -> Iterable[int]:
        return range(1, self.test_suit_config.iterations + 1)

    def reprocess_result(self, result: "ResultData", is_live: bool = False) -> "ResultData":
        return result

    async def send_final_staticstics(self) -> "ResultData":
        await sleep_log(const.DELAY_WAIT_TRAFFIC_STOP)
        result = self.reprocess_result(await self.staticstics_collect(is_live=False))
        self.xoa_out.send_statistics(result)
        logger.debug(result)
        return result


TCFG = TypeVar("TCFG", AddressCachingCapacityConfiguration, AddressLearningRateConfiguration)


class AddressLearningBase(TestBase[TCFG], BinarySearchMixin[T]):
    port_name: AddressLearningPortRolePortNameMapping
    learning_rate_pps: int
    learning_adress_count: int

    def get_mac_address(self, resource: "TestResource", resource_current_address: "MacAddress") -> "MacAddress":
        new_address = resource_current_address
        learning_base_address = MacAddress.from_base_address(self.test_suit_config.learn_mac_base_address)

        if resource.port_name == self.port_name.test:
            logger.debug(self.test_suit_config.test_port_mac_mode)
            if self.test_suit_config.test_port_mac_mode.is_use_learning_base_address:
                new_address = MacAddress.from_base_address('0,0,0,0,0,0').partial_replace(learning_base_address)
        elif resource.port_name == self.port_name.learning:
            new_address = resource_current_address.partial_replace(learning_base_address)

        logger.debug(resource.port_name, new_address)
        return new_address

    def create_port_pairs(self) -> "PortPairs":
        assert self.test_suit_config.port_role_handler, const.INVALID_PORT_ROLE
        group_by_result = group_by_port_property(self.full_test_config.ports_configuration, self.test_suit_config.port_role_handler, self.port_identities)
        # logger.debug(group_by_result)

        test_port_uuid = group_by_result.port_role_uuids[const.PortGroup.TEST_PORT][0]
        learning_port_uuid = group_by_result.port_role_uuids[const.PortGroup.LEARNING_PORT][0]
        monitoring_port_uuid = group_by_result.port_role_uuids[const.PortGroup.MONITORING_PORT][0]

        self.port_name = AddressLearningPortRolePortNameMapping(
            test=group_by_result.uuid_port_name[test_port_uuid],
            learning=group_by_result.uuid_port_name[learning_port_uuid],
            monitoring=group_by_result.uuid_port_name[monitoring_port_uuid],
        )

        return (
            PortPair(west=self.port_name.learning, east=self.port_name.test),
            PortPair(west=self.port_name.test, east=self.port_name.learning),
        )

    @property
    def traffic_duration(self) -> int:
        return ceil(self.learning_adress_count / self.learning_rate_pps) + 1  # wait 1 second in case traffic delay

    def flood_packet_count(self, result: ResultData) -> int:
        return sum(rx.packet for rx in result.ports[self.port_name.monitoring].per_rx_tpld_id.values())

    async def learning_port_set_broadcast_mac_address(self) -> None:
        if self.test_suit_config.learning_port_dmac_mode.is_use_broadcast:
            await self.resources[self.port_name.learning].set_stream_peer_mac_address(MacAddress("ff:ff:ff:ff:ff:ff"))

    async def test_port_set_peer_mac_address(self) -> None:
        learning_port_mac_address = self.resources[self.port_name.learning].mac_address
        assert learning_port_mac_address
        await self.resources[self.port_name.test].set_stream_peer_mac_address(learning_port_mac_address)

    async def set_learning_modifiers(self, port_name: str) -> None:
        modifier_count = 2 if self.binary_search.current > 0xfffe else 1
        modifier_position = 3 if port_name == self.port_name.test else 9

        tokens = []
        stream = self.resources[port_name].port.streams.obtain(0)
        modifiers = stream.packet.header.modifiers
        if self.test_suit_config.learning_sequence_port_dmac_mode.is_incr:
            await modifiers.configure(modifier_count)
            if modifier_count == 1:
                modifier = modifiers.obtain(0)
                tokens.extend(
                    [
                        modifier.specification.set(position=modifier_position + 1, mask=Hex("ffff0000"), action=ModifierActionOption.INC.to_xmp(), repetition=1),
                        modifier.range.set(min_val=1, step=1, max_val=0xffff)
                    ]
                )
            else:
                modifier0 = modifiers.obtain(0)
                modifier1 = modifiers.obtain(1)
                tokens.extend(
                    [
                        modifier0.specification.set(position=modifier_position, mask=Hex("fff00000"), action=ModifierActionOption.INC.to_xmp(), repetition=0x1000),
                        modifier0.range.set(min_val=1, step=1, max_val=0xfff),
                        modifier1.specification.set(position=modifier_position + 1, mask=Hex("0fff0000"), action=ModifierActionOption.INC.to_xmp(), repetition=1),
                        modifier1.range.set(min_val=1, step=1, max_val=0xfff),
                    ]
                )
        else:
            await modifiers.configure(2)
            modifier0 = modifiers.obtain(0)
            modifier1 = modifiers.obtain(1)
            tokens.extend(
                [
                    modifier0.specification.set(position=modifier_position - 1, mask=Hex("ffff0000"), action=ModifierActionOption.RANDOM.to_xmp(), repetition=1),
                    modifier0.range.set(min_val=0, step=1, max_val=0xfff),
                    modifier1.specification.set(position=modifier_position + 1, mask=Hex("0fff0000"), action=ModifierActionOption.RANDOM.to_xmp(), repetition=1),
                    modifier1.range.set(min_val=1, step=1, max_val=0xfff),
                ]
            )
        await apply(*tokens)

    async def set_learning_limit(self, port_name: str) -> None:
        asyncio.gather(
            *[
                self.resources[port_name].set_rate_pps(self.learning_rate_pps),
                self.resources[port_name].set_packet_limit(self.learning_adress_count),
            ]
        )

    def reprocess_result(self, result: "ResultData", is_live: bool = True) -> "ResultData":
        result.extra['port_name'] = self.port_name
        result.extra['binary_search'] = self.binary_search
        return result

    async def setup_learning_traffic(self, port_name: str) -> None:
        await self.set_learning_modifiers(port_name)
        await self.set_learning_limit(port_name)
        self.resources.enable_single_port_traffic(port_name)

    async def reset_DUT_mac_address_table(self) -> None:
        await self.toggle_port_sync_state(
            is_need_toggle=self.test_suit_config.toggle_sync_state,
            sync_off_duration=self.test_suit_config.sync_off_duration,
            sync_on_duration=self.test_suit_config.sync_on_duration,
        )
        if not self.test_suit_config.toggle_sync_state and not self.test_suit_config.switch_test_port_roles:
            await sleep_log(self.test_suit_config.dut_aging_time)

    def check_statistic_status(self, result: ResultData, is_live: bool = False) -> const.StatisticsStatus:
        status = const.StatisticsStatus.FAIL
        if is_live or (self.flood_packet_count(result) == 0 and result.ports[self.port_name.test].tx_packet == result.ports[self.port_name.learning].rx_packet):
            status = const.StatisticsStatus.SUCCESS
        return status

    def is_should_fast_stop(self, result: ResultData) -> bool:
        return isinstance(self.test_suit_config, AddressCachingCapacityConfiguration) \
            and self.test_suit_config.fast_run_resolution_enabled \
            and result.ports[self.port_name.monitoring].rx_packet > 0

    async def switch_port_roles(self) -> None:
        if self.test_suit_config.switch_test_port_roles:
            self.port_name.learning, self.port_name.test = self.port_name.test, self.port_name.learning
            await self.test_port_set_peer_mac_address()

    async def address_learning_test(self, packet_size: int) -> Optional[ResultData]:
        result: Optional[ResultData] = None
        logger.debug(self.binary_search)
        await self.reset_DUT_mac_address_table()
        await self.resources.limit_ports_mac_learning([self.port_name.test])
        await sleep_log(const.DELAY_LEARNING_MAC)
        await self.learning_port_set_broadcast_mac_address()
        await self.resources.set_stream_packet_size(packet_size)
        await self.resources.set_stream_rate_and_packet_limit(packet_size, const.DECIMAL_100, self.test_suit_config.duration)

        await self.setup_learning_traffic(self.port_name.learning)
        traffic_info: Optional[TrafficInfo] = None
        async for traffic_info in self.generate_traffic():
            result = traffic_info.result
            if self.is_stop_on_los:
                self.binary_search.set_ended(is_test_pass=False)
                return result

        await sleep_log(const.DELAY_WAIT_TRAFFIC_STOP)
        await self.setup_learning_traffic(self.port_name.test)
        async for traffic_info in self.generate_traffic():
            result = traffic_info.result
            if self.is_stop_on_los or self.is_should_fast_stop(result):
                self.binary_search.set_ended(is_test_pass=False)
                return result

        await sleep_log(const.DELAY_WAIT_TRAFFIC_STOP)
        await sleep_log(const.DELAY_LEARNING_ADDRESS)
        result = await self.staticstics_collect(is_live=False)

        await self.switch_port_roles()
        assert result
        return result
