import asyncio
import functools
from typing import (
    Callable,
    Dict,
    Generator,
    List,
    Set,
    TYPE_CHECKING,
    Tuple,
)
from decimal import Decimal
from dataclasses import dataclass, fields
from xoa_driver import utils, ports

from plugin2889.dataset import PortJitter, PortLatency, StatisticsData, TxStream, RxTPLDId
from plugin2889.util.logger import logger
from plugin2889.const import DEFAULT_INTERFRAME_GAP

if TYPE_CHECKING:
    from plugin2889.resource.test_resource import TestResource
    from plugin2889.resource._port_stream import StreamManager

__all__ = ("PortStatistics",)


@dataclass(init=False, repr=False)
class PortMax:
    tx_bps_l1: int = 0
    rx_bps_l1: int = 0
    tx_bps_l2: int = 0
    rx_bps_l2: int = 0
    tx_pps: int = 0
    rx_pps: int = 0

    def reset(self) -> None:
        for field in fields(self):
            setattr(self, field.name, 0)

    def __update_value(self, name: str, value: int) -> None:
        current = getattr(self, name)
        setattr(self, name, max(current, value))

    update_tx_bps_l1 = functools.partialmethod(__update_value, "tx_bps_l1")
    update_rx_bps_l1 = functools.partialmethod(__update_value, "rx_bps_l1")
    update_tx_pps = functools.partialmethod(__update_value, "tx_pps")
    update_rx_pps = functools.partialmethod(__update_value, "rx_pps")
    update_tx_bps_l2 = functools.partialmethod(__update_value, "tx_bps_l2")
    update_rx_bps_l2 = functools.partialmethod(__update_value, "rx_bps_l2")


def _bps_l2_to_bps_l1(bps: int, packet_size: int) -> int:
    return int(bps * (packet_size + DEFAULT_INTERFRAME_GAP) / packet_size)


class PortStatistics:
    __slots__ = ("__tx_resources", "__port", "max", "__streams_sending_out", "__tx_tpld_ids", "__only_collect_rx_total", "__port_name", "__collect_rx_function")

    def __init__(self, port: "ports.GenericL23Port", streams: List["StreamManager"], port_name: str) -> None:
        self.__port = port
        self.__streams_sending_out = streams
        self.__port_name = port_name
        self.__tx_resources: List["TestResource"] = []  # source ports that sends traffic to self.__port
        self.__tx_tpld_ids: Set[int] = set()  # source stream tpld_id
        self.max = PortMax()
        self.__only_collect_rx_total: bool = False  # do not collect data from each tpld_id
        self.__collect_rx_function: Callable = self.collect_rx_by_streams

    async def clear(self) -> None:
        logger.debug("invoked")
        await utils.apply(
            self.__port.statistics.tx.clear.set(), self.__port.statistics.rx.clear.set()
        )

    @property
    def __streams_sending_in(self) -> Generator["StreamManager", None, None]:
        if self.__only_collect_rx_total:
            return None
        for resource in self.__tx_resources:
            for stream in resource.streams:
                if stream.tpld_id in self.__tx_tpld_ids:
                    yield stream

    async def collect_rx_single_stream(self, rx_tpld_statistics, packet_size, tpld_id) -> Tuple[int, int, int, int, int, int]:
        receive, latency, jitter, error = await utils.apply(
            rx_tpld_statistics.traffic.get(),
            rx_tpld_statistics.latency.get(),
            rx_tpld_statistics.jitter.get(),
            rx_tpld_statistics.errors.get(),

        )
        return packet_size, tpld_id, receive, latency, jitter, error

    async def collect_rx_by_streams(self, statistics: StatisticsData, packet_size: int) -> None:
        rx_bit_count_last_sec = rx_packet_count_last_sec = non_incre_seq_event_count = rx_packet = rx_bps_l1 = 0

        port_latency = PortLatency()
        port_jitter = PortJitter()
        per_rx_tpld_id: Dict[int, RxTPLDId]  = {}
        coroutines = []
        for rx_stream in self.__streams_sending_in:
            rx_tpld_statistics = self.__port.statistics.rx.access_tpld(rx_stream.tpld_id)
            coroutines.append(self.collect_rx_single_stream(rx_tpld_statistics=rx_tpld_statistics, packet_size=rx_stream.packet_size, tpld_id=rx_stream.tpld_id))

        for (stream_packet_size, tpld_id, receive, latency, jitter, error) in await asyncio.gather(*coroutines):
            rx_bps_l1 += _bps_l2_to_bps_l1(receive.bit_count_last_sec, stream_packet_size or packet_size)
            self.max.update_rx_bps_l1(rx_bps_l1)

            rx_packet += int(receive.packet_count_since_cleared)
            rx_bit_count_last_sec += receive.bit_count_last_sec
            rx_packet_count_last_sec += receive.packet_count_last_sec
            non_incre_seq_event_count += int(error.non_incre_seq_event_count)

            port_latency.minimum = latency.min_val
            port_latency.maximum = latency.max_val
            port_latency.set_average(tpld_id, latency.avg_val)

            port_jitter.minimum = jitter.min_val
            port_jitter.maximum = jitter.max_val
            port_jitter.set_average(tpld_id, jitter.avg_val)

            per_rx_tpld_id[tpld_id] = RxTPLDId(packet=int(receive.packet_count_since_cleared), pps=receive.packet_count_last_sec)

        self.max.update_rx_bps_l2(rx_bit_count_last_sec)
        self.max.update_rx_pps(rx_packet_count_last_sec)
        statistics.rx_packet = sum(rx_tpld.packet for rx_tpld in per_rx_tpld_id.values())
        statistics.rx_bps_l1 = self.max.rx_bps_l1
        statistics.loss = non_incre_seq_event_count
        statistics.rx_bps_l2 = self.max.rx_bps_l2
        statistics.per_rx_tpld_id = per_rx_tpld_id
        statistics.latency = port_latency
        statistics.jitter = port_jitter

    async def collect_rx_misc_by_port(self, statistics: StatisticsData) -> None:
        extra, no_tpld = await utils.apply(
            self.__port.statistics.rx.extra.get(),
            self.__port.statistics.rx.no_tpld.get(),
        )
        statistics.fcs = int(extra.fcs_error_count)
        statistics.flood = int(no_tpld.packet_count_since_cleared)

    async def collect_tx_by_streams(self, statistics: StatisticsData, packet_size: int) -> None:
        tx_bit_count_last_sec = tx_packet_count_last_sec = tx_packet = tx_bps_l1 = 0
        per_tx_stream = {}
        tx_coroutines = []
        for idx, tx_stream in enumerate(self.__streams_sending_out):
            tx_coroutines.append(self.__port.statistics.tx.obtain_from_stream(idx).get())

        for idx, transmit in enumerate(await asyncio.gather(*tx_coroutines)):
            tx_stream = self.__streams_sending_out[idx]
            tx_packet += int(transmit.packet_count_since_cleared)
            tx_packet_count_last_sec += transmit.packet_count_last_sec
            self.max.update_tx_pps(tx_packet_count_last_sec)
            per_tx_stream[idx] = TxStream(tpld_id=tx_stream.tpld_id, packet=int(transmit.packet_count_since_cleared), pps=tx_packet_count_last_sec)

            tx_bit_count_last_sec += transmit.bit_count_last_sec
            self.max.update_tx_bps_l2(tx_bit_count_last_sec)

            # we will calculate separately if stream have specific valid packet size
            tx_bps_l1 += _bps_l2_to_bps_l1(transmit.bit_count_last_sec, tx_stream.packet_size or packet_size)
            self.max.update_tx_bps_l1(tx_bps_l1)

        statistics.tx_packet = tx_packet
        statistics.tx_bps_l1 = self.max.tx_bps_l1
        statistics.tx_bps_l2 = self.max.tx_bps_l2
        statistics.per_tx_stream = per_tx_stream

    async def collect_rx_port_total(self, statistics: StatisticsData, packet_size: int) -> None:
        total = await self.__port.statistics.rx.total.get()
        rx_packet = int(total.packet_count_since_cleared)
        self.max.update_rx_bps_l2(total.bit_count_last_sec)
        self.max.update_rx_pps(total.packet_count_last_sec)

        statistics.rx_packet = rx_packet
        statistics.rx_bps_l1 = self.max.rx_bps_l1
        statistics.rx_bps_l2 = self.max.rx_bps_l2

    async def collect_data(self, duration: int, packet_size: int = 0, is_live: bool = True) -> Tuple[str, StatisticsData]:
        statistics = StatisticsData()
        task_tx = asyncio.create_task(self.collect_tx_by_streams(statistics, packet_size))
        task_rx = asyncio.create_task(self.__collect_rx_function(statistics, packet_size))
        task_rx_misc = asyncio.create_task(self.collect_rx_misc_by_port(statistics))
        await asyncio.gather(*[task_tx, task_rx, task_rx_misc])

        if is_live:
            loss = statistics.loss
            statistics.tx_pps = self.max.tx_pps
            statistics.rx_pps = self.max.rx_pps
        else:
            loss = 0   # we will calculate loss base on Tx and Rx data on upper level code
            statistics.tx_pps = round(statistics.tx_packet / duration)
            statistics.rx_pps = round(statistics.rx_packet / duration)

        loss_percent = Decimal(loss * 100 / statistics.tx_packet if statistics.tx_packet else -1)
        statistics.loss_percent = loss_percent
        return self.__port_name, statistics

    def add_tx_resources(self, resource: "TestResource", tpld_id: int) -> None:
        if resource not in self.__tx_resources:
            self.__tx_resources.append(resource)
        self.__tx_tpld_ids.add(tpld_id)

    def enable_only_collect_tx_total(self) -> None:
        self.__only_collect_rx_total = True
        self.__collect_rx_function = self.collect_rx_port_total
