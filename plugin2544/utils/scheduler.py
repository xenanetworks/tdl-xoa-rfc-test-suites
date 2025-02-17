import asyncio
from enum import Enum
from typing import Callable, Dict, Any


async def empty(count: int, *args: Any, **kw: Dict[str, Any]) -> bool:
    return False


class TimeType(Enum):
    SECOND = "s"
    MILLISECONDS = "ms"
    MINUTES = "m"
    HOUR = "h"

    @property
    def scale(self) -> float:
        return {
            TimeType.SECOND: 1,
            TimeType.MILLISECONDS: 1 / 1000,
            TimeType.MINUTES: 60,
            TimeType.HOUR: 60 * 60,
        }[self]


async def periodical_job(
    timing: float,
    unit: str = "s",
    do: Callable = empty,
    *args: Any,
    **kw: Dict[str, Any]
) -> None:
    count = 0
    time_unit = TimeType(unit).scale
    while True:
        count += 1
        should_quit = await do(count, *args, **kw)
        await asyncio.sleep(time_unit * timing)
        if should_quit:
            break


async def schedule(
    timing: float, unit: str = "s", do: Callable = empty, *args, **kw
) -> None:
    asyncio.create_task(periodical_job(timing, unit, do, *args, **kw))
