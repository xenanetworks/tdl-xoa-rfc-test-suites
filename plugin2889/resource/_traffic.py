from typing import TYPE_CHECKING, Callable, Optional
from loguru import logger

if TYPE_CHECKING:
    from xoa_driver import ports


class Traffic:
    __slots__ = ("__port", "__start_func",)

    def __init__(self, port: "ports.GenericL23Port") -> None:
        self.__port = port
        self.__start_func: Optional[Callable] = None

    async def set_time_duration(self, duration_sec: int) -> None:
        await self.__port.tx_config.time_limit.set(int(duration_sec * 1e6))

    async def get_time_elipsed(self) -> int:
        return int((await self.__port.tx_config.time.get()).microseconds / 1e6)

    async def set_frame_duration(self, packets_limit: int) -> None:
        await self.__port.tx_config.packet_limit.set(packets_limit)

    async def start(self) -> None:
        logger.debug(f'invoked {self.__start_func}')
        if self.__start_func:
            await self.__start_func()

    async def stop(self) -> None:
        logger.debug('invoked')
        await self.__port.traffic.state.set_stop()

    def set_start_func(self, func: Optional[Callable] = None) -> None:
        self.__start_func = func
