import asyncio
from decimal import Decimal
from pydantic import BaseModel
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Optional,
)

if TYPE_CHECKING:
    from .resource.manager import ResourcesManager

from . import const
from .dataset import StatisticsData


class ResultData(BaseModel):
    test_type: const.TestType
    iteration: int
    packet_size: int
    rate: Decimal
    total: StatisticsData
    status: const.StatisticsStatus
    ports: Dict[str, StatisticsData] = {}
    is_live: bool
    extra: Dict[str, Any] = {}


class StatisticsProcessor:
    __slots__ = ("is_used_criteria", "acceptable_loss_unit", "acceptable_loss", "__resources", "__check_statistic_status_function", "__test_type")

    def __init__(
        self,
        resources: "ResourcesManager",
        test_type: const.TestType,
        check_statistic_status_function: Callable,
        is_used_criteria: bool = False,
        acceptable_loss_unit: "const.AcceptableType" = const.AcceptableType.PERCENT,
        acceptable_loss: float = 0.0,
    ) -> None:
        self.is_used_criteria = is_used_criteria
        self.acceptable_loss_unit = acceptable_loss_unit
        self.acceptable_loss = acceptable_loss
        self.__check_statistic_status_function = check_statistic_status_function
        self.__resources = resources
        self.__test_type = test_type

    async def collect_data(
        self,
        iteration: int,
        duration: int,
        rate: Decimal = Decimal(0),
        packet_size: int = 0,
        is_live=True,
        get_rate_function: Optional[Callable[[], Decimal]] = None,
    ) -> "ResultData":
        total: StatisticsData = StatisticsData()
        row_data = ResultData(
            test_type=self.__test_type,
            iteration=iteration,
            packet_size=packet_size,
            rate=get_rate_function() if get_rate_function else rate,
            total=total,
            status=const.StatisticsStatus.PENDING,
            is_live=is_live,
        )
        coroutines = [r.statistics.collect_data(duration, packet_size, is_live) for r in self.__resources]
        for port_name, statistics in await asyncio.gather(*coroutines):
            total += statistics
            row_data.ports[port_name] = statistics
            if not is_live:
                total.loss = total.tx_packet - total.rx_packet

        total.loss_percent = round(Decimal(total.loss * 100 / total.tx_packet if total.tx_packet else 0), 2)
        row_data.total = total
        row_data.status = self.__check_statistic_status_function(row_data, is_live)
        return row_data

    def reset_max(self) -> None:
        for r in self.__resources:
            r.statistics.max.reset()
