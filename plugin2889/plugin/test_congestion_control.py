from dataclasses import dataclass, field
from functools import partial
from typing import Generator
from loguru import logger

from plugin2889 import const
from plugin2889.dataset import CongestionControlConfiguration
from plugin2889.plugin.base_class import TestBase
from plugin2889.plugin.utils import PortPairs, sleep_log, group_by_port_property
from plugin2889.dataset import CurrentIterProps, PortPair, StatisticsData
from plugin2889.resource.manager import ResourcesManager
from plugin2889.statistics import ResultData


@dataclass
class TestPortName:
    source_split: str = field(init=False)
    source_single: str = field(init=False)
    destination_uncongested: str = field(init=False)
    destination_congested: str = field(init=False)


class CongestionControlTest(TestBase[CongestionControlConfiguration]):
    def test_suit_prepare(self):
        self.port_name = TestPortName()
        self.uncongested_stream_index = -1
        self.resources = ResourcesManager(
            self.testers,
            self.full_test_config,
            port_identities=self.port_identities,
            port_pairs=self.__create_port_pairs(),
        )
        self.create_statistics()

    def __create_port_pairs(self) -> "PortPairs":
        assert self.test_suit_config.port_role_handler
        group_by_property = group_by_port_property(self.full_test_config.ports_configuration, self.test_suit_config.port_role_handler, self.port_identities)
        # if it is not exact 2 source ports with 2 destination ports, following unpack value would throw error
        source_port_uuid_split, source_port_uuid_single = group_by_property.port_role_uuids[const.PortGroup.SOURCE]
        self.port_name.source_split = group_by_property.uuid_port_name[source_port_uuid_split]
        self.port_name.source_single = group_by_property.uuid_port_name[source_port_uuid_single]

        destination_port_uuid_uncongested, destination_port_uuid_congested = group_by_property.port_role_uuids[const.PortGroup.DESTINATION]
        self.port_name.destination_uncongested = group_by_property.uuid_port_name[destination_port_uuid_uncongested]
        self.port_name.destination_congested = group_by_property.uuid_port_name[destination_port_uuid_congested]

        pairs = (
            PortPair(west=self.port_name.source_split, east=self.port_name.destination_uncongested),
            PortPair(west=self.port_name.source_split, east=self.port_name.destination_congested),
            PortPair(west=self.port_name.source_single, east=self.port_name.destination_congested),
        )
        logger.debug(pairs)
        return pairs

    def check_statistic_status(self, result: ResultData, is_live: bool = False) -> const.StatisticsStatus:
        status = const.StatisticsStatus.SUCCESS
        if result.ports[self.port_name.destination_uncongested].loss:
            status = const.StatisticsStatus.FAIL
        return status

    async def reprocess_result(self, result: "ResultData", is_live: bool = True) -> "ResultData":
        resource_source_split = self.resources[self.port_name.source_split]

        # find the exact stream that from split port to uncongested port
        if self.uncongested_stream_index == -1:
            for idx, stream in enumerate(resource_source_split.streams):
                if stream.is_match_peer_mac_address(self.resources[self.port_name.destination_uncongested].mac_address):
                    self.uncongested_stream_index = idx

        assert self.uncongested_stream_index != -1, "uncongested stream not found"
        uncongested_stream_tx = resource_source_split.port.statistics.tx.obtain_from_stream(self.uncongested_stream_index)
        tx = await uncongested_stream_tx.get()
        uncongested_tx_packet = int(tx.packet_count_since_cleared)
        congested_result = StatisticsData(
            tx_packet=result.ports[self.port_name.source_single].tx_packet + uncongested_tx_packet,
            rx_packet=result.ports[self.port_name.destination_congested].rx_packet,
        )
        congested_result.loss = congested_result.tx_packet - congested_result.rx_packet
        uncongested_result = StatisticsData(
            rx_packet=result.ports[self.port_name.destination_uncongested].rx_packet,
            tx_packet=uncongested_tx_packet,
            loss=result.ports[self.port_name.destination_uncongested].loss,
        )

        result.total.loss = uncongested_result.loss
        result.total.loss_percent = uncongested_result.loss_percent
        result.extra.update({
            'congested': congested_result,
            'uncongested': uncongested_result,
        })
        return result

    def do_testing_cycle(self) -> Generator[CurrentIterProps, None, None]:
        packet_sizes = self.full_test_config.general_test_configuration.frame_sizes.packet_size_list
        for i in self.iterations_offset_by_1:
            for packet_size in packet_sizes:
                yield CurrentIterProps(i, int(packet_size))

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
        await self.resources.set_stream_packet_limit(-1)
        await self.resources.set_time_limit(self.test_suit_config.duration)

        self.statistics.reset_max()
        async for traffic_info in self.generate_traffic():
            logger.debug(traffic_info)

        result = await self.send_final_staticstics()