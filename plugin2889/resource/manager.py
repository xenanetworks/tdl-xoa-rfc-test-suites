import asyncio
from collections import defaultdict
from decimal import Decimal
from functools import partial
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    Generator,
    Iterable,
    Iterator,
    Optional,
    TypeVar,
    List,
)
from loguru import logger
from xoa_core.types import PortIdentity
from xoa_driver import testers, modules, enums

if TYPE_CHECKING:
    from plugin2889.resource._port_stream import StreamManager

from plugin2889.model import exceptions
from plugin2889.const import DELAY_CREATE_PORT_PAIR, DELAY_WAIT_RESET_PORT, INTERVAL_CHECK_PORT_SYNC, CHECK_SYNC_MAX_RETRY, PacketSizeType
from plugin2889.dataset import MacAddress, PortPair
from plugin2889.dataset import TestSuiteConfiguration2889
from plugin2889.plugin.utils import sleep_log
from plugin2889.resource.test_resource import TestResource


T = TypeVar("T", bound="ResourcesManager")


class ResourcesManager:
    __slots__ = ("__testers", "__resources", "__port_identities", "__port_pairs", "__test_config", "__tester_module_ports", "__get_mac_address")

    def __init__(
        self,
        testers: Dict[str, testers.L23Tester],
        test_config: TestSuiteConfiguration2889,
        port_identities: List["PortIdentity"],
        port_pairs: Iterable["PortPair"],
        get_mac_address_function: Optional[Callable[["TestResource", "MacAddress"], "MacAddress"]] = None,
    ) -> None:
        self.__testers = testers
        self.__test_config = test_config
        self.__port_identities = port_identities
        self.__port_pairs = port_pairs or []
        self.__resources: Dict[str, "TestResource"] = {}
        self.__tester_module_ports: Dict["testers.L23Tester", List[int]] = defaultdict(list)  # it is only for calling tester.traffic_sync
        self.__get_mac_address = get_mac_address_function

    async def setup(self) -> None:
        await asyncio.gather(*self.__testers.values())
        # need_ports = [pair.names for pair in self.__port_pairs]
        # need_ports = list(itertools.chain.from_iterable(need_ports))
        coroutines = []
        for port_identity in self.__port_identities:
            # if port_identity.name not in need_ports:
            #     continue

            tester = self.__testers[port_identity.tester_id]
            module = tester.modules.obtain(port_identity.module_index)
            if isinstance(module, modules.ModuleChimera):
                raise exceptions.WrongModuleTypeError(module)

            port = module.ports.obtain(port_identity.port_index)
            coroutines.append(TestResource(
                tester=tester,
                port=port,
                port_name=port_identity.name,
                port_config=self.__test_config.ports_configuration[port_identity.name],
                get_mac_address_function=self.__get_mac_address,
            ))
            self.__tester_module_ports[tester].extend([port.kind.module_id, port.kind.port_id])

        for resource in await asyncio.gather(*coroutines):
            self.__resources[resource.port_name] = resource

        logger.debug(self.__resources.items())
        # await self.map_pairs()
        self.__set_start_traffic_function()

    async def map_pairs(self) -> None:
        coroutines = []
        stream_id_counter = defaultdict(int)
        for port_pair in self.__port_pairs:
            source_resource = self[port_pair.west]
            destination_resource = self[port_pair.east]
            tpld_id = self.__test_config.general_test_configuration.alloc_new_tpld_id(source_resource.port, destination_resource.port)
            coroutines.append(source_resource.set_peer(stream_id_counter[port_pair.west], tpld_id, destination_resource))
            stream_id_counter[port_pair.west] += 1
        await asyncio.gather(*coroutines)
        await sleep_log(DELAY_CREATE_PORT_PAIR)

    def __iter__(self) -> Iterator[TestResource]:
        return iter(self.__resources.values())

    def __getitem__(self, key: str) -> "TestResource":
        return self.__resources[key]

    async def cleanup(self) -> None:
        if not self.__testers:
            return None
        await asyncio.gather(*[resource.release() for resource in self])
        # seessions_to_close = [
        #     tester.session.logoff() for tester in self.__testers.values()
        # ]
        # await asyncio.gather(*seessions_to_close)
        self.__resources.clear()
        # self.__testers.clear()

    @property
    def all_traffic_is_stop(self) -> bool:
        return all(r.traffic_is_off for r in self)

    @property
    def all_ports_is_sync(self) -> bool:
        return all(r.is_sync for r in self)

    async def set_time_limit(self, duration_sec: int) -> None:
        await asyncio.gather(*[r.traffic.set_time_duration(duration_sec) for r in self])

    async def get_time_elipsed(self) -> int:
        return max(await asyncio.gather(*[r.traffic.get_time_elipsed() for r in self]))

    async def set_frame_limit(self, duration: int) -> None:
        await asyncio.gather(*[r.traffic.set_frame_duration(duration) for r in self])

    def __set_start_traffic_function(self) -> None:
        if not self.__test_config.general_test_configuration.use_port_sync_start:
            for resource in self:
                resource.traffic.set_start_func(resource.port.traffic.state.set_start)
        else:
            tester_already_set = {}  # it is c_traffic command, just need to set one time on each tester
            for resource in self:
                if not tester_already_set.get(resource.tester):
                    resource.traffic.set_start_func(
                        partial(resource.start_traffic_sync, self.__tester_module_ports[resource.tester])
                    )
                    tester_already_set[resource.tester] = True

    async def start_traffic(self) -> None:
        await asyncio.gather(*[r.traffic.start() for r in self if r.streams])

    async def stop_traffic(self) -> None:
        await asyncio.gather(*[r.traffic.stop() for r in self])

    async def clear_statistic_counters(self) -> None:
        await asyncio.gather(*[r.statistics.clear() for r in self])

    async def prepare_streams(self) -> None:
        crooutines = []
        for stream in self.resource_streams:
            crooutines.append(stream.setup_stream())
        await asyncio.gather(*crooutines)

    @property
    def resource_streams(self) -> Generator["StreamManager", None, None]:
        for resource in self:
            for stream in resource.streams:
                yield stream

    async def set_stream_rate_and_packet_limit(self, packet_size: int, rate_percent: Decimal, traffic_duration: int) -> None:
        coroutines = [
            s.set_rate_and_packet_limit(packet_size or s.packet_size, rate_percent, traffic_duration, self.__test_config.general_test_configuration.rate_definition)
            for s in self.resource_streams
        ]
        await asyncio.gather(*coroutines)

    async def set_stream_packet_size(self, current_packet_size: int) -> None:
        coroutines = []
        frame_sizes = self.__test_config.general_test_configuration.frame_sizes
        if frame_sizes.packet_size_type.is_fix:
            coroutines.extend([s.set_fixed_packet_size(current_packet_size) for s in self.resource_streams])
        elif frame_sizes.packet_size_type in (PacketSizeType.INCREMENTING, PacketSizeType.BUTTERFLY, PacketSizeType.RANDOM, PacketSizeType.MIX):
            coroutines.extend([
                s.set_packet_size(frame_sizes.packet_size_type, frame_sizes.varying_packet_min_size, frame_sizes.varying_packet_max_size)
                for s in self.resource_streams
            ])
        await asyncio.gather(*coroutines)

    async def mac_learning(self) -> None:
        await asyncio.gather(*[r.mac_learning() for r in self])

    async def limit_ports_mac_learning(self, port_names: List[str]) -> None:
        await asyncio.gather(*[self[port_name].mac_learning() for port_name in port_names])

    async def set_tx_config_enable(self, on_ff: enums.OnOff) -> None:
        await asyncio.gather(*[r.set_tx_config_enable(on_ff) for r in self])

    async def set_tx_config_delay(self, delay: int) -> None:
        sum_delay = 0
        coroutines = []
        for resource in self:
            coroutines.append(resource.set_tx_config_delay(sum_delay))
            sum_delay += delay
        await asyncio.gather(*coroutines)

    def enable_single_port_traffic(self, single_port_name: str) -> None:
        """need to call set_start_traffic_function after calling this method if it is sync start mode"""
        for port_name, resource in self.__resources.items():
            if port_name == single_port_name:
                resource.traffic.set_start_func(resource.port.traffic.state.set_start)
            else:
                resource.traffic.set_start_func()

    async def set_port_latency_mode(self) -> None:
        await asyncio.gather(
            *[r.port.latency_config.mode.set(self.__test_config.general_test_configuration.latency_mode.to_xmp()) for r in self]
        )

    async def set_port_pause_mode(self) -> None:
        await asyncio.gather(
            *[r.port.pause.set(enums.OnOff(r.port_config.pause_mode_enabled)) for r in self]
        )

    async def set_port_interframe_gap(self) -> None:
        await asyncio.gather(*[r.set_port_interframe_gap() for r in self])

    async def set_port_speed_reduction(self) -> None:
        await asyncio.gather(
            *[r.port.speed.reduction.set(r.port_config.speed_reduction_ppm) for r in self]
        )

    async def set_port_staggering(self, resources: Optional["ResourcesManager"] = None) -> None:
        resources = resources or self
        if port_stagger_steps := self.__test_config.general_test_configuration.port_stagger_steps:
            await resources.set_tx_config_delay(port_stagger_steps * 64)

    async def set_port_latency_offset(self) -> None:
        await asyncio.gather(
            *[r.port.latency_config.offset.set(r.port_config.latency_offset_ms) for r in self]
        )

    async def set_port_mixed_packet(self) -> None:
        frame_sizes = self.__test_config.general_test_configuration.frame_sizes
        if not frame_sizes.packet_size_type.is_mix:
            return None

        logger.debug(frame_sizes)
        coroutines = []
        for resource in self:
            coroutines.append(resource.port.mix.weights.set(*frame_sizes.mixed_sizes_weights))
            for position, v in frame_sizes.mixed_length_config.dictionary.items():
                coroutines.append(resource.port.mix.lengths[position].set(v))

        asyncio.gather(*coroutines)

    async def set_port_ip_address(self) -> None:
        await asyncio.gather(*[r.set_port_ip_address() for r in self])

    async def set_port_reset(self) -> None:
        await asyncio.gather(*[r.port.reset.set() for r in self])

    async def set_port_speed_selection(self) -> None:
        await asyncio.gather(*[r.set_port_speed_selection() for r in self])

    async def set_port_autoneg(self) -> None:
        await asyncio.gather(*[r.set_port_autoneg() for r in self])

    async def set_port_anlt(self) -> None:
        await asyncio.gather(*[r.set_port_anlt() for r in self])

    async def set_port_mdi_mdix(self) -> None:
        await asyncio.gather(*[r.set_port_mdi_mdix() for r in self])

    async def set_port_brr(self) -> None:
        await asyncio.gather(*[r.set_port_brr() for r in self])

    async def set_port_fec(self) -> None:
        await asyncio.gather(*[r.set_port_fec() for r in self])

    async def set_tpld_mode(self) -> None:
        await asyncio.gather(*[
            r.set_tpld_mode(self.__test_config.general_test_configuration.use_micro_tpld_on_demand) for r in self
        ])

    async def configure_ports(self) -> None:
        coroutines = (
            self.set_port_pause_mode(),
            self.set_port_interframe_gap(),
            self.set_port_speed_reduction(),
            self.set_port_latency_offset(),
            self.set_port_staggering(),
            self.set_port_latency_mode(),
            self.set_port_mixed_packet(),
            self.set_port_ip_address(),
        )
        await asyncio.gather(*coroutines)

    async def reset_ports(self) -> None:
        coroutines = (
            self.stop_traffic(),
            self.set_port_reset(),
            self.set_port_speed_selection(),
            self.set_port_autoneg(),
            self.set_port_anlt(),
            self.set_port_mdi_mdix(),
            self.set_port_brr(),
            self.set_port_fec(),
            self.set_tpld_mode(),
        )
        await asyncio.gather(*coroutines)
        await sleep_log(DELAY_WAIT_RESET_PORT)

    async def set_stream_packet_limit(self, limit: int) -> None:
        await asyncio.gather(*[r.set_packet_limit(limit) for r in self])

    async def check_port_link(self) -> None:
        check_count = 0
        while not self.all_ports_is_sync:
            logger.debug('Detected loss of link - retrying')
            check_count += 1
            if check_count > CHECK_SYNC_MAX_RETRY:
                if self.__test_config.general_test_configuration.should_stop_on_los:
                    raise exceptions.StopTestByLossSignal()
                break
            await sleep_log(INTERVAL_CHECK_PORT_SYNC)