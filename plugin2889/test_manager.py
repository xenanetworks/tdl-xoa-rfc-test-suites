import asyncio
import contextlib
import time
from typing import Awaitable, TypeVar, AsyncGenerator

from plugin2889.const import DELAY_WAIT_RESET_STATS, INTERVAL_CHECK_SHOULD_STOP_TRAFFIC
from plugin2889.resource.manager import ResourcesManager
from plugin2889.plugin.utils import sleep_log
from plugin2889.util.logger import logger


T = TypeVar("T", bound="L23TestManager")


class L23TestManager:
    __slots__ = ("__testers", "__resources", "__lock")

    def __init__(self, resources: ResourcesManager) -> None:
        self.__resources = resources
        self.__lock = asyncio.Lock()

    async def setup(self):
        await self.__resources.setup()
        return self

    async def __aenter__(self: Awaitable[T]) -> T:
        return await self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        logger.debug(f'invoked {exc_type} {exc} {traceback}')
        async with self.__lock:
            await self.__resources.cleanup()

    def __await__(self: T):  # type: ignore
        return self.setup().__await__()

    @contextlib.asynccontextmanager
    async def __traffic_runner(self) -> AsyncGenerator[None, None]:
        logger.debug("\033[31mStart traffic...\x1B[0m")
        await self.__resources.clear_statistic_counters()
        await sleep_log(DELAY_WAIT_RESET_STATS)
        await self.__resources.start_traffic()
        try:
            yield
        finally:
            logger.debug("\033[31mTraffic STOP\x1B[0m")
            async with self.__lock:
                await self.__resources.stop_traffic()

    async def generate_traffic(self, duration: int, *, sampling_rate: float = 1.0) -> AsyncGenerator[int, None]:
        # await self.__resources.set_time_limit(duration)
        # await self.__resources.set_frame_limit(duration)
        time_clock = 0
        start_ts = time.time()
        time_step = 1.0 / sampling_rate
        duration_accived = False
        async with self.__traffic_runner():
            while time.time() - start_ts <= duration + 2:  # traffic stop delay
                begin = time.time()
                time_clock = await self.__resources.get_time_elipsed()
                if time_clock == 0 or duration_accived:
                    await sleep_log(INTERVAL_CHECK_SHOULD_STOP_TRAFFIC)
                    continue
                duration_accived = time_clock == duration
                yield int(time_clock / (duration) * 100)
                await sleep_log(round(time_step - (time.time() - begin), 3))
