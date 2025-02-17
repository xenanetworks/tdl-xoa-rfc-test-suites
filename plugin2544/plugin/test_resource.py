from __future__ import annotations
import asyncio
import time
from typing import TYPE_CHECKING, Union, Tuple
from xoa_driver import testers as xoa_testers, modules, enums, utils
from .learning import add_mac_learning_steps
from .config_checkers import check_config
from .common import get_peers_for_source
from .setup_streams import setup_streams
from .structure import PortStruct

from ..utils import constants as const, exceptions

if TYPE_CHECKING:
    from xoa_core.core.test_suites.datasets import PortIdentity
    from .test_config import TestConfigData
    from ..model.m_port_config import PortConfiguration
    from ..utils.interfaces import TestSuitePipe


class ResourceManager:
    def __init__(
        self,
        testers: dict[str, "xoa_testers.GenericAnyTester"],
        all_confs: list["PortConfiguration"],
        port_identities: list["PortIdentity"],
        test_conf: "TestConfigData",
        xoa_out: "TestSuitePipe",
    ):
        self.all_confs = all_confs
        self.__port_identities = port_identities
        self._validate_tester_type(testers.values(), xoa_testers.L23Tester)
        # type: ignore
        self.__testers: dict[str, "xoa_testers.L23Tester"] = testers
        self.port_structs: list["PortStruct"] = []
        self.xoa_out: "TestSuitePipe" = xoa_out
        self.__test_conf: "TestConfigData" = test_conf
        self.mapping: dict[str, list[int]] = {}

    @property
    def test_conf(self):
        return self.__test_conf

    @property
    def has_l3(self) -> bool:
        return any(conf.profile.protocol_version.is_l3 for conf in self.all_confs)

    @staticmethod
    def _validate_tester_type(testers, valid_type) -> None:
        if not all(isinstance(t, valid_type) for t in testers):
            raise ValueError("")

    @property
    def tx_ports(self) -> list["PortStruct"]:
        return [
            port_struct
            for port_struct in self.port_structs
            if port_struct.port_conf.is_tx_port
        ]

    @property
    def rx_ports(self) -> list["PortStruct"]:
        return [
            port_struct
            for port_struct in self.port_structs
            if port_struct.port_conf.is_rx_port
        ]

    async def setup_ports(self, latency_mode: "const.LatencyModeStr") -> None:
        await asyncio.gather(
            *[
                port_struct.setup_port(self.__test_conf, latency_mode)
                for port_struct in self.port_structs
            ]
        )

    async def free(self) -> None:
        await asyncio.gather(*[port_struct.free(stop_test=True) for port_struct in self.port_structs])

    def build_map(self) -> None:
        for port_struct in self.tx_ports:
            tester_id = port_struct.port_identity.tester_id
            if tester_id not in self.mapping:
                self.mapping[tester_id] = []
            self.mapping[tester_id] += [
                port_struct.port_identity.module_index,
                port_struct.port_identity.port_index,
            ]

    async def init_resource(self, latency_mode: "const.LatencyModeStr") -> None:
        await self.collect_control_ports()
        self.resolve_port_relations()
        check_config(list(self.__testers.values()), self.port_structs, self.__test_conf)
        self.build_map()
        await self.stop_traffic()
        await asyncio.sleep(self.__test_conf.delay_after_port_reset_second) # delay after reset
        await self.setup_ports(latency_mode)
        await self.setup_sweep_reduction()
        await self.add_toggle_port_sync_state_steps()
        await setup_streams(self.port_structs, self.__test_conf)
        await add_mac_learning_steps(self, const.MACLearningMode.ONCE)

    async def stop_traffic(self) -> None:
        await utils.apply(
            *[
                port_struct.set_traffic(enums.StartOrStop.STOP)
                for port_struct in self.port_structs
            ]
        )
        await asyncio.sleep(const.DELAY_STOPPED_TRAFFIC)

    async def setup_sweep_reduction(self) -> None:
        if (
            not self.__test_conf.enable_speed_reduction_sweep
            or self.__test_conf.is_pair_topology
        ):
            return
        await asyncio.gather(
            *[
                port.set_sweep_reduction(10 * (i + 1))
                for i, port in enumerate(self.port_structs)
            ]
        )

    async def collect_control_ports(self) -> None:
        await asyncio.gather(*self.__testers.values())
        for index, port_conf in enumerate(self.all_confs):
            port_identity = self.__port_identities[index]
            tester = self.__testers[port_identity.tester_id]
            if not isinstance(tester, xoa_testers.L23Tester):
                raise exceptions.WrongModuleTypeError(tester)
            module = tester.modules.obtain(port_identity.module_index)
            if isinstance(module, modules.ModuleChimera):
                raise exceptions.WrongModuleTypeError(module)
            port = module.ports.obtain(port_identity.port_index)
            port_struct = PortStruct(
                tester, port, port_conf, port_identity, self.xoa_out
            )
            self.port_structs.append(port_struct)
        await asyncio.gather(
            *[port_struct.prepare() for port_struct in self.port_structs]
        )

    async def add_toggle_port_sync_state_steps(self) -> None:
        # AddTogglePortSyncStateSteps

        if not self.__test_conf.toggle_port_sync:
            return
        await asyncio.gather(
            *[
                port_struct.set_toggle_port_sync(enums.OnOff.OFF)
                for port_struct in self.port_structs
            ]
        )
        await asyncio.sleep(self.__test_conf.sync_off_duration_second)
        await asyncio.gather(
            *[
                port_struct.set_toggle_port_sync(enums.OnOff.ON)
                for port_struct in self.port_structs
            ]
        )
        # Delay After Sync On
        start_time = time.time()
        for port_struct in self.port_structs:
            while not port_struct.properties.sync_status:
                await asyncio.sleep(const.DELAY_CHECK_SYNC)
                if time.time() - start_time > 30:
                    raise TimeoutError(
                        f"Waiting for {port_struct.port_identity.name} sync timeout!"
                    )
        await asyncio.sleep(self.__test_conf.delay_after_sync_on_second)

    def resolve_port_relations(self) -> None:
        """ 
        resolve port relations according to topology and direction, and register peer for port;
        test_port_index is for calculating tid & logical macaddress use
        """
        topology = self.__test_conf.topology
        test_port_index = 0
        if topology.is_mesh_topology:
            for port_struct in self.port_structs:
                port_struct.properties.test_port_index = test_port_index
                test_port_index += 1
        else:
            east_ports = [
                port_struct
                for port_struct in self.port_structs
                if port_struct.port_conf.port_group.is_east
            ]
            west_ports = [
                port_struct
                for port_struct in self.port_structs
                if port_struct.port_conf.port_group.is_west
            ]
            for port_struct in east_ports:
                port_struct.properties.test_port_index = test_port_index
                test_port_index += 1
            for port_struct in west_ports:
                port_struct.properties.test_port_index = test_port_index
                test_port_index += 1

        for port_struct in self.tx_ports:
            port_config = port_struct.port_conf
            dest_ports = get_peers_for_source(topology, port_config, self.port_structs)
            for peer_struct in dest_ports:
                port_struct.properties.register_peer(peer_struct)

    async def setup_tpld_mode(self, current_packet_size: float) -> None:
        """use_micro_tpld_on_demand and can use micro tpld"""
        use_micro_tpld_on_demand = self.test_conf.use_micro_tpld_on_demand
        use_micro_tpld = False
        if use_micro_tpld_on_demand:
            for port_struct in self.port_structs:
                if current_packet_size == 0:
                    break
                if not port_struct.capabilities.can_micro_tpld:
                    break
                packet_header = port_struct.stream_structs[0]._packet_header
                header_length = len(packet_header)
                min_length = header_length + const.STANDARD_TPLD_TOTAL_LENGTH
                use_micro_tpld = current_packet_size < min_length
                if use_micro_tpld:
                    break
        tasks = (
            port_struct.set_tpld_mode(use_micro_tpld)
            for port_struct in self.port_structs
        )
        await asyncio.gather(*tasks)

    async def setup_packet_size(self, current_packet_size: Union[float, int]) -> None:
        if self.__test_conf.frame_sizes.packet_size_type.is_fix:
            min_size = max_size = int(current_packet_size)
        else:
            (
                min_size,
                max_size,
            ) = self.__test_conf.size_range
        await asyncio.gather(
            *[
                port_struct.set_streams_packet_size(
                    self.__test_conf.frame_sizes.packet_size_type.to_xmp(),
                    min_size,
                    max_size,
                )
                for port_struct in self.port_structs
            ]
        )

    async def set_gap_monitor(
        self,
        use_gap_monitor: bool,
        gap_monitor_start_microsec: int,
        gap_monitor_stop_frames: int,
    ) -> None:
        if not use_gap_monitor:
            return
        await asyncio.gather(
            *[
                port_struct.set_gap_monitor(
                    gap_monitor_start_microsec, gap_monitor_stop_frames
                )
                for port_struct in self.rx_ports
            ]
        )

    def test_running(self) -> bool:
        return any(
            port_struct.properties.traffic_status for port_struct in self.tx_ports
        )

    def test_finished(self) -> bool:
        return all(
            not port_struct.properties.traffic_status for port_struct in self.tx_ports
        )

    def los(self) -> bool:
        if self.__test_conf.should_stop_on_los:
            return not all(
                port_struct.properties.sync_status for port_struct in self.port_structs
            )
        return False

    def should_quit(
        self, start_time: float, actual_duration: float
    ) -> Tuple[bool, bool]:
        test_finished = self.test_finished()
        elapsed = time.time() - start_time
        actual_duration_elapsed = (
            elapsed >= actual_duration + const.DELAY_TEST_MUST_FINISH
        )
        los = self.los()
        if los:
            raise exceptions.TestAbort()
        should_quit = test_finished or los or actual_duration_elapsed
        port_should_stop = [port._should_stop_on_los for port in self.port_structs]
        should_fail = los and any(port_should_stop)
        return should_quit, should_fail

    def set_rate_percent(self, rate: float) -> None:
        for port_struct in self.tx_ports:
            port_struct.set_rate_percent(rate)

    async def set_tx_time_limit(self, tx_timelimit: Union[float, int]) -> None:
        """throughput & latency & frame loss support txtimelimit"""
        await asyncio.gather(
            *[
                port_struct.set_tx_time_limit(int(tx_timelimit))
                for port_struct in self.tx_ports
            ]
        )

    async def set_frame_limit(self, frame_count: int) -> None:
        """back to back supoort packetlimit"""
        await asyncio.gather(
            *[
                stream_struct.set_frame_limit(frame_count)
                for port_struct in self.tx_ports
                for stream_struct in port_struct.stream_structs
            ]
        )

    async def clear_statistic(self) -> None:
        await asyncio.gather(
            *[port_struct.clear_statistic() for port_struct in self.port_structs]
        )
        await asyncio.sleep(const.DELAY_CLEAR_STATISTICS)

    async def query_traffic_status(self) -> None:
        await asyncio.gather(
            *[port_struct.get_traffic_status() for port_struct in self.tx_ports]
        )

    async def start_traffic_sync(
        self, tester: "xoa_testers.L23Tester", module_port_list: list[int]
    ) -> None:
        local_time = (await tester.time.get()).local_time
        delay_seconds = 2
        await tester.traffic_sync.set(
            enums.OnOff.ON, local_time + delay_seconds, module_port_list
        )

    async def start_traffic(self, port_sync: bool = False) -> None:
        if not port_sync:
            # send P_TRAFFIC every port
            await utils.apply(
                *[
                    port_struct.set_traffic(enums.StartOrStop.START)
                    for port_struct in self.tx_ports
                ]
            )
        elif len(self.mapping) == 1:
            # same tester send C_TRAFFIC
            tester_id = list(self.mapping.keys())[0]
            tester = self.__testers[tester_id]
            await tester.traffic.set(
                enums.OnOff(enums.StartOrStop.START), self.mapping[tester_id]
            )

        else:
            # multi tester need to use c_trafficsync cmd
            await asyncio.gather(
                *[
                    self.start_traffic_sync(self.__testers[tester_id], module_port_list)
                    for tester_id, module_port_list in self.mapping.items()
                ]
            )

    async def collect(
        self, packet_size: float, duration: float, is_final: bool = False
    ) -> None:
        for port_struct in self.port_structs:
            port_struct.init_counter(packet_size, duration, is_final)
        await asyncio.gather(
            *[port_struct.query() for port_struct in self.port_structs]
        )
        for port_struct in self.port_structs:
            port_struct.statistic.calculate_rate()
