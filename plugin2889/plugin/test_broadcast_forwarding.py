from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from typing import Generator, List, Union

from plugin2889 import const
from plugin2889.dataset import MacAddress, PortPair
from plugin2889.plugin.base_class import BinarySearchMixin, DecimalBinarySearch, TestBase
from plugin2889.plugin.dataset import BaseRunProps
from plugin2889.plugin.utils import PortPairs, sleep_log, group_by_port_property
from plugin2889.resource.manager import ResourcesManager
from plugin2889.util.logger import logger
from plugin2889.statistics import ResultData
from plugin2889.dataset import BroadcastForwardingConfiguration


@dataclass
class PortRolePortNameMapping:
    source: str
    destination: List[str]


class BroadcastForwardingTest(TestBase[BroadcastForwardingConfiguration], BinarySearchMixin[Decimal]):
    port_name: PortRolePortNameMapping

    def test_suit_prepare(self) -> None:
        self.resources = ResourcesManager(
            testers=self.testers,
            port_identities=self.port_identities,
            test_config=self.full_test_config,
            port_pairs=self.create_port_pairs(),
        )
        self.create_statistics()

    def create_port_pairs(self) -> "PortPairs":
        assert self.test_suit_config.port_role_handler
        group_by_result = group_by_port_property(self.full_test_config.ports_configuration, self.test_suit_config.port_role_handler, self.port_identities)
        source_port_uuid = group_by_result.port_role_uuids[const.PortGroup.SOURCE][0]
        source_port_name = group_by_result.uuid_port_name[source_port_uuid]

        destination_port_names = []
        for destination_port_uuid in group_by_result.port_role_uuids[const.PortGroup.DESTINATION]:
            destination_port_name = group_by_result.uuid_port_name[destination_port_uuid]
            destination_port_names.append(destination_port_name)

        self.port_name = PortRolePortNameMapping(source=source_port_name, destination=destination_port_names)
        return [PortPair(west=source_port_name, east=source_port_name)]

    def do_testing_cycle(self) -> Generator[BaseRunProps, None, None]:
        for i in self.iterations_offset_by_1:
            for packet_size in self.full_test_config.general_test_configuration.frame_sizes.packet_size_list:
                yield BaseRunProps(i, int(packet_size))

    def check_statistic_status(self, result: ResultData, is_live: bool = False) -> const.StatisticsStatus:
        if is_live:
            is_fail = sum(port.loss for port in result.ports.values())
        else:
            is_fail = result.total.tx_packet * len(self.port_name.destination) != result.total.rx_packet
        return const.StatisticsStatus.FAIL if is_fail else const.StatisticsStatus.SUCCESS

    async def run_test(self, run_props: BaseRunProps) -> None:
        self.binary_search = DecimalBinarySearch(rate_iteration_options=self.test_suit_config.rate_iteration_options)
        self.staticstics_collect = partial(
            self.statistics.collect_data,
            duration=self.test_suit_config.duration,
            iteration=run_props.iteration_number,
            rate=Decimal(0),
            get_rate_function=self.get_binary_search_current,
            packet_size=run_props.packet_size,
        )

        await self.toggle_port_sync_state()
        await self.resources.mac_learning()
        await sleep_log(const.DELAY_LEARNING_MAC)
        await self.resources[self.port_name.source].set_stream_peer_mac_address(MacAddress("ff:ff:ff:ff:ff:ff"))

        for destination_port_name in self.port_name.destination:
            self.resources[destination_port_name].statistics.add_tx_resources(
                self.resources[self.port_name.source], tpld_id=self.resources[self.port_name.source].streams[0].tpld_id
            )

        result: Union[ResultData, None] = None
        while not self.binary_search.determine_should_end(result):
            logger.debug(self.binary_search)
            await self.toggle_port_sync_state()
            await self.resources.mac_learning()
            await sleep_log(const.DELAY_LEARNING_MAC)
            await self.resources.set_stream_packet_size(run_props.packet_size)
            await self.resources.set_stream_rate_and_packet_limit(run_props.packet_size, self.binary_search.current, self.test_suit_config.duration)

            async for traffic_info in self.generate_traffic():
                result = traffic_info.result

            await self.send_final_staticstics()