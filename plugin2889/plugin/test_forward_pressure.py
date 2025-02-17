from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from functools import partial
from typing import Generator, List
from loguru import logger

from plugin2889 import const
from plugin2889.dataset import ForwardPressureConfiguration
from plugin2889.plugin import rate_helper
from plugin2889.plugin.base_class import TestBase
from plugin2889.plugin.utils import PortPairs, sleep_log, group_by_port_property
from plugin2889.dataset import CurrentIterProps, PortPair, StatisticsData
from plugin2889.resource.manager import ResourcesManager
from plugin2889.statistics import ResultData


class Direction(Enum):
    TX = 'tx'
    RX = 'rx'


@dataclass
class TestInterframeGap:
    delta: int
    default: int = const.DEFAULT_INTERFRAME_GAP

    @property
    def reduced(self) -> int:
        return self.default - self.delta


@dataclass
class TestPortName:
    source: str
    destination: str


@dataclass
class PortRateAverage:
    rx_rates: List[int] = field(default_factory=list)
    tx_rates: List[int] = field(default_factory=list)

    def add(self, direction: Direction, rate: int) -> None:
        if rate:
            getattr(self, f"{direction.value}_rates").append(rate)

    def read(self, direction: Direction) -> int:
        values = getattr(self, f"{direction.value}_rates")
        if values:
            return int(sum(values) / len(values))
        return 0


class ForwardPressureTest(TestBase[ForwardPressureConfiguration]):
    def test_suit_prepare(self) -> None:
        self.resources = ResourcesManager(
            self.testers,
            self.full_test_config,
            self.port_identities,
            port_pairs=self.__create_port_pair(),
        )
        self.interframe_gap = TestInterframeGap(delta=int(self.test_suit_config.interframe_gap_delta))
        self.port_rate_average = PortRateAverage()
        self.create_statistics()

    def __create_port_pair(self) -> "PortPairs":
        assert self.test_suit_config.port_role_handler
        group_by_result = group_by_port_property(self.full_test_config.ports_configuration, self.test_suit_config.port_role_handler, self.port_identities)
        logger.debug(group_by_result.port_role_uuids)
        source_port_uuid = group_by_result.port_role_uuids[const.PortGroup.SOURCE][0]
        destination_port_uuid = group_by_result.port_role_uuids[const.PortGroup.DESTINATION][0]
        self.port_name = TestPortName(
            source=group_by_result.uuid_port_name[source_port_uuid],
            destination=group_by_result.uuid_port_name[destination_port_uuid],
        )
        pairs = (PortPair(west=self.port_name.source, east=self.port_name.destination),)
        # logger.debug(pairs)
        return pairs

    async def __set_port_interframe_gap(self) -> None:
        await self.resources[self.port_name.source].set_port_interframe_gap(self.interframe_gap.reduced)

    async def setup_resources(self) -> None:
        await self.resources.reset_ports()
        await self.resources.check_port_link()
        await self.resources.configure_ports()
        await self.__set_port_interframe_gap()
        await self.resources.map_pairs()

    def do_testing_cycle(self) -> Generator[CurrentIterProps, None, None]:
        packet_sizes = self.full_test_config.general_test_configuration.frame_sizes.packet_size_list
        for i in self.iterations_offset_by_1:
            for packet_size in packet_sizes:
                yield CurrentIterProps(
                    i,
                    int(packet_size),
                )

    def __calc_max_port_util(self, bit_rate: Decimal) -> Decimal:
        return const.DECIMAL_100 * bit_rate / Decimal(1000 * 1e6)

    def __calc_max_port_util_from_result(self, pps: int, packet_size: int) -> Decimal:
        port_l1_bit_rate = rate_helper.calc_l1_bit_rate(pps, packet_size, self.interframe_gap.default)
        return self.__calc_max_port_util(port_l1_bit_rate)

    def check_statistic_status(self, result: ResultData, is_live: bool = False) -> const.StatisticsStatus:
        status = const.StatisticsStatus.SUCCESS
        if not is_live:
            rx_util = self.__calc_max_port_util_from_result(result.ports[self.port_name.destination].rx_pps, result.packet_size)
            logger.debug(rx_util)
            if rx_util > const.DECIMAL_100 + Decimal(self.test_suit_config.acceptable_rx_max_util_delta):
                status = const.StatisticsStatus.FAIL
        return status

    def reprocess_result(self, result: "ResultData", is_live: bool = True) -> "ResultData":
        tx_result = result.ports[self.port_name.source]
        rx_result = result.ports[self.port_name.destination]

        tx_util = self.__calc_max_port_util_from_result(result.ports[self.port_name.source].tx_pps, result.packet_size)
        logger.debug(tx_util)

        if is_live and tx_result.per_tx_stream and rx_result.per_rx_tpld_id:
            tx_pps = list(tx_result.per_tx_stream.values())[0].pps
            rx_pps = list(rx_result.per_rx_tpld_id.values())[0].pps
            self.port_rate_average.add(Direction.TX, tx_pps)
            self.port_rate_average.add(Direction.RX, rx_pps)

        tx_result.tx_pps = self.port_rate_average.read(Direction.TX)
        rx_result.rx_pps = self.port_rate_average.read(Direction.RX)

        result.extra.update({
            Direction.TX.value: tx_result,
            Direction.RX.value: rx_result,
            'tx_util': tx_util,
        })
        return result

    async def run_test(self, run_props: CurrentIterProps) -> None:
        logger.debug(f'iter props: {run_props}')
        self.staticstics_collect = partial(
            self.statistics.collect_data,
            duration=self.test_suit_config.duration,
            iteration=run_props.iteration_number,
            rate=const.DECIMAL_100,
            packet_size=run_props.packet_size,
        )

        await self.toggle_port_sync_state(self.resources)
        await self.resources.mac_learning()
        await sleep_log(const.DELAY_LEARNING_MAC)
        await self.resources.set_stream_packet_size(run_props.packet_size)
        await self.resources.set_stream_rate_and_packet_limit(run_props.packet_size, const.DECIMAL_100, self.test_suit_config.duration)

        self.statistics.reset_max()
        async for traffic_info in self.generate_traffic(sample_rate=0.5):
            logger.debug(traffic_info)

        await self.send_final_staticstics()
