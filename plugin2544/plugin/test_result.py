from .statistics import (
    FinalStatistic,
    StatisticParams,
)
from .test_resource import ResourceManager


async def aggregate_data(
    resource: "ResourceManager",
    params: StatisticParams,
    is_final: bool = False,
) -> "FinalStatistic":
    await resource.collect(params.frame_size, params.duration, is_final=is_final)
    return FinalStatistic(
        test_case_type=params.test_case_type,
        is_final=is_final,
        loop=params.loop,
        frame_size=params.frame_size,
        repetition=params.repetition,
        tx_rate_percent=params.rate_percent,
        rate_result_scope=params.rate_result_scope,
        port_data=[port_struct.statistic for port_struct in resource.port_structs],
    )
