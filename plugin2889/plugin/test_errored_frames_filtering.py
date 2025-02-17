import time
import asyncio
from enum import IntEnum
from math import ceil
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from typing import Generator

from plugin2889 import const
from plugin2889.dataset import PortPair
from plugin2889.plugin.base_class import TestBase
from plugin2889.plugin.dataset import ErroredFramesFilteringRunProps
from plugin2889.plugin.utils import PortPairs, sleep_log, group_by_port_property
from plugin2889.resource.manager import ResourcesManager
from plugin2889.util.logger import logger
from plugin2889.statistics import ResultData
from plugin2889.dataset import ErroredFramesFilteringConfiguration


@dataclass
class PortRolePortNameMapping:
    source: str
    destination: str


class TestStreamIndex(IntEnum):
    UNDER_SIZE = 0
    VALID = 1
    OVER_SIZE = 2


@dataclass
class StreamStats:
    name: str = ''
    tx: int = 0
    rx: int = 0


class ErroredFramesFilteringTest(TestBase[ErroredFramesFilteringConfiguration]):
    def test_suit_prepare(self) -> None:
        self.port_name: PortRolePortNameMapping
        self.total_stream_count = 2 + int(self.test_suit_config.oversize_test_enabled)  # vaild stream + undersize stream + oversize stream
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
        destination_port_uuid = group_by_result.port_role_uuids[const.PortGroup.DESTINATION][0]
        self.port_name = PortRolePortNameMapping(
            source=group_by_result.uuid_port_name[source_port_uuid],
            destination=group_by_result.uuid_port_name[destination_port_uuid],
        )
        return [PortPair(west=self.port_name.source, east=self.port_name.destination)] * self.total_stream_count

    def tx_rate_iterations(self) -> Generator[Decimal, None, None]:
        rate_sweep_options = self.test_suit_config.rate_sweep_options
        current = Decimal(0)
        for i in range(1 + ceil((rate_sweep_options.end_value - rate_sweep_options.start_value) / rate_sweep_options.step_value)):
            current = rate_sweep_options.start_value + rate_sweep_options.step_value * i
            yield min(current, self.test_suit_config.rate_sweep_options.end_value)

    def do_testing_cycle(self) -> Generator[ErroredFramesFilteringRunProps, None, None]:
        for i in self.iterations_offset_by_1:
            for tx_rate in self.tx_rate_iterations():
                yield ErroredFramesFilteringRunProps(iteration_number=i, rate_percent=tx_rate, packet_size=0)

    def check_statistic_status(self, result: ResultData, is_live: bool = False) -> const.StatisticsStatus:
        source_port_tx_stream = result.ports[self.port_name.source].per_tx_stream

        pkt_has_valid = source_port_tx_stream[TestStreamIndex.VALID].packet >= 0
        pkt_has_over_sized = source_port_tx_stream[TestStreamIndex.OVER_SIZE].packet > 0
        pkt_has_under_sized = source_port_tx_stream[TestStreamIndex.UNDER_SIZE].packet > 0

        if any((pkt_has_valid, pkt_has_over_sized, pkt_has_under_sized)):
            return const.StatisticsStatus.FAIL
        return const.StatisticsStatus.SUCCESS

    def set_stream_packet_size(self) -> None:
        source_stream = self.resources[self.port_name.source].streams

        source_stream[TestStreamIndex.UNDER_SIZE].packet_size = \
            round((2 * self.test_suit_config.min_frame_size - self.test_suit_config.undersize_span - 1) / 2.0)
        source_stream[TestStreamIndex.VALID].packet_size = \
            round((self.test_suit_config.min_frame_size + self.test_suit_config.max_frame_size) / 2.0)
        if self.test_suit_config.oversize_test_enabled:
            source_stream[TestStreamIndex.OVER_SIZE].packet_size = \
                round((2 * self.test_suit_config.max_frame_size + self.test_suit_config.oversize_span + 1) / 2.0)

    async def set_stream_incrementing(self) -> None:
        coroutines = []
        source_port = self.resources[self.port_name.source].port

        under_size_stream = source_port.streams.obtain(TestStreamIndex.UNDER_SIZE)
        valid_stream = source_port.streams.obtain(TestStreamIndex.VALID)
        coroutines.extend([
            under_size_stream.packet.length.set_incrementing(
                self.test_suit_config.min_frame_size - self.test_suit_config.undersize_span,
                self.test_suit_config.min_frame_size - 1
            ),
            valid_stream.packet.length.set_incrementing(
                self.test_suit_config.min_frame_size,
                self.test_suit_config.max_frame_size
            ),
        ])

        if self.test_suit_config.oversize_test_enabled:
            over_size_stream = source_port.streams.obtain(TestStreamIndex.OVER_SIZE)
            coroutines.append(
                over_size_stream.packet.length.set_incrementing(
                    self.test_suit_config.max_frame_size + 1,
                    self.test_suit_config.max_frame_size + self.test_suit_config.oversize_span)
            )
        asyncio.gather(*coroutines)

    async def inject_fcs_error(self) -> None:
        valid_stream = self.resources[self.port_name.source].port.streams.obtain(TestStreamIndex.VALID)
        try:
            await valid_stream.inject_err.frame_checksum.set()
            self.fcs_error_injected_count += 1
        except Exception as e: # error when stream traffic off
            logger.debug(str(e))

    def reprocess_result(self, result: "ResultData", is_live: bool = True) -> "ResultData":
        stream_stats = []
        for stream_idx, tx in result.ports[self.port_name.source].per_tx_stream.items():
            stream_stats.append(StreamStats(
                name=TestStreamIndex(stream_idx).name,
                tx=tx.packet,
                rx=result.ports[self.port_name.destination].per_rx_tpld_id[tx.tpld_id].packet,
            ))
        result.extra.update({
            "fcs_tx": self.fcs_error_injected_count,
            "fcs_rx": result.total.fcs,
            "streams": stream_stats,
        })
        return result

    async def run_test(self, run_props: ErroredFramesFilteringRunProps) -> None:
        self.fcs_error_injected_count = 0
        self.staticstics_collect = partial(
            self.statistics.collect_data,
            duration=self.test_suit_config.duration,
            iteration=run_props.iteration_number,
            rate=run_props.rate_percent,
            packet_size=0,
        )

        await self.toggle_port_sync_state(self.resources)
        await self.resources.mac_learning()
        await sleep_log(const.DELAY_LEARNING_MAC)

        self.set_stream_packet_size()
        await self.set_stream_incrementing()
        await self.resources.set_stream_rate_and_packet_limit(0, run_props.rate_percent, self.test_suit_config.duration)

        async for _ in self.generate_traffic(sample_rate=5):
            await self.inject_fcs_error()

        await self.send_final_staticstics()