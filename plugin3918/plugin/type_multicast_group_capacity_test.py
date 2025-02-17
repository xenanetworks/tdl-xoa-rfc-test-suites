from asyncio import sleep, gather
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Set
from xoa_driver.utils import apply, apply_iter
from .resource_manager import PortInstance, ResourceManager
from .type_base import BaseTestType, PPipeFacade
from ..utils.constants import ResultState
from ..utils.scheduler import schedule

if TYPE_CHECKING:
    from ...plugin3918 import Model3918


@dataclass
class CaptureSwitch:
    capture_check_enabled: bool
    capture_check_in_progress: bool

    def set_capture_check_enabled(self, enabled: bool) -> None:
        self.capture_check_enabled = enabled

    def set_capture_check_in_progress(self, in_progress: bool) -> None:
        self.capture_check_in_progress = in_progress


class MulticastGroupCapacityTest(BaseTestType):
    def __init__(
        self,
        xoa_out: "PPipeFacade",
        cfg: "Model3918",
        resource_manager: "ResourceManager",
    ) -> None:
        super().__init__(xoa_out, cfg, resource_manager)

        self.capture_switch = CaptureSwitch(False, False)
        multicast_group_capacity = cfg.test_types_configuration.multicast_group_capacity

        if multicast_group_capacity:
            self.model_data.set_test_type_operation(multicast_group_capacity)

    def init_test_plan_data(self) -> None:
        super().init_test_plan_data()
        self.clear_max_capacity_map()

    def get_group_count_list(self) -> List[int]:
        return [1]

    def get_iteration_count(self) -> range:
        return range(
            1,
            self.model_data.get_iterations() + 1,
        )

    async def init_trial(self) -> None:
        self.multicast_group_check_map: Dict[PortInstance, Set[int]] = {}
        self.capture_switch.set_capture_check_enabled(False)
        self.capture_switch.set_capture_check_in_progress(False)
        await super().init_trial()

    def setup_next_mc_group_count(self) -> None:
        if self.bout_info.mc_group_count == 0:
            self.bout_info.mc_group_count = self.model_data.get_group_count_start()
        else:
            self.bout_info.mc_group_count = min(
                self.bout_info.mc_group_count + self.model_data.get_group_count_step(),
                self.model_data.get_group_count_end(),
            )

    def stop_capture_poll_timer(self) -> None:
        self.capture_switch.set_capture_check_enabled(False)

    async def perform_join_capture_check(self) -> None:
        if self.capture_switch.capture_check_in_progress:
            return
        self.capture_switch.set_capture_check_in_progress(True)
        tokens_stop = []
        for dest_instance in self.resource_manager.mc_dest_ports():
            tokens_stop.append(dest_instance.port.capturer.state.set_stop())
        await apply(*tokens_stop)

        # OnGotCaptureStatsForCheck
        stats_port = []
        task_stats = []

        for dest_instance in self.resource_manager.mc_dest_ports():
            stats_port.append(dest_instance)
            task_stats.append(dest_instance.port.capturer.obtain_captured())
        result_stats = await gather(*task_stats)

        for (dest_instance), stats in zip(stats_port, result_stats):
            packet_tokens = (
                obtained_capture.packet.get() for obtained_capture in stats
            )
            async for packet_result in apply_iter(*packet_tokens):
                address_string = "".join(packet_result.hex_data[3:6])
                address_value = int(address_string, 16)
                if dest_instance not in self.multicast_group_check_map:
                    self.multicast_group_check_map[dest_instance] = set()
                self.multicast_group_check_map[dest_instance].add(address_value)
                # live set rx_mc_group_count
            group_count = len(self.multicast_group_check_map[dest_instance])
            dest_instance.test_result.set_rx_mc_group_count(group_count)

        self.capture_switch.set_capture_check_in_progress(False)

    async def setup_capacity_capture(self):
        self.capture_switch.capture_check_enabled = True
        await schedule(1, "s", self.check_capacity)

    async def check_capacity(self, count: int) -> bool:
        if not self.capture_switch.capture_check_enabled:
            return True
        if count > 1:
            await self.perform_join_capture_check()
        test_passed = self.check_capacity_result()
        if test_passed:
            return True
        else:
            await self.init_basic_igmp_capture()
            return not self.capture_switch.capture_check_enabled

    async def add_iteration_step(self) -> None:
        sweep_list = self.model_data.get_sweep_value_list()
        for rate in sweep_list:
            self.bout_info.set_rate(rate)
            self.reset_curr_group_count()
            await self.init_trial()
            self.setup_next_mc_group_count()
            self.allocate_new_test_result()
            await self.setup_mc_source_port_streams()
            await self.setup_mc_stream_rates()
            await self.send_igmp_join()
            await sleep(self.model_data.get_join_to_traffic_delay())
            await self.start_traffic(False, False)
            await sleep(1)
            await self.stop_traffic()
            await sleep(1)
            await self.clear_port_stats()
            await self.start_counter_poll()
            await self.start_traffic(False, True)
            await self.setup_capacity_capture()
            await sleep(self.model_data.get_duration_value())
            self.stop_capture_poll_timer()
            await self.stop_traffic()
            await sleep(self.model_data.get_delay_after_stop())
            self.stop_counter_poll()
            await self.send_igmp_leave()
            await sleep(self.model_data.get_delay_after_leave())
            await self.get_final_counters()

    async def get_final_counters(self) -> bool:
        await self.resource_manager.query(self.src_port_type)
        self.bout_info.set_is_final(True)
        passed = ResultState.PASS if self.check_capacity_result() else ResultState.FAIL
        self.bout_info.set_result_state(passed)
        self.show_results()
        return True

    def show_results(self) -> None:
        # [Packet Size, Iter. #, Tx Off.Rate(Percent), Group Count, Result State, Curr. Loss(Packets)]
        totals = {
            "Packet Size": self.bout_info.packet_size,
            "Iter. #": self.bout_info.iter_index,
            "Tx Off.Rate(Percent)": self.bout_info.rate,
            "Group Count": self.bout_info.mc_group_count,
            "Result State": self.bout_info.result_state.value,
            "Curr. Loss(Packets)": self.resource_manager.test_result.total_mc_frame_loss_delta,
            "Is Final": self.bout_info.is_final,
            "Source Ports": [],
            "Destination Ports": [],
        }

        for s in self.resource_manager.mc_src_ports():
            r = s.test_result.mc_source_data
            # [Tx Packets, Tx Rate(Bit/s), Tx Rate(Pps)]
            totals["Source Ports"].append(
                {
                    "Source Port Name": s.name,
                    "Tx Packets": r.frames,
                    "Tx Rate(Bit/s)": r.bps,
                    "Tx Rate(Pps)": r.pps,
                }
            )

        for d in self.resource_manager.mc_dest_ports():
            r = d.test_result.mc_destination_data
            # [Rx Packets, Rx Rate(Bit/s), Rx Group Count#]
            totals["Destination Ports"].append(
                {
                    "Destination Port Name": d.name,
                    "Rx Packets": r.frames,
                    "Rx Rate(Bit/s)": r.bps,
                    "Rx Group Count#": d.test_result.rx_mc_group_count,
                }
            )
        self.display(totals)
