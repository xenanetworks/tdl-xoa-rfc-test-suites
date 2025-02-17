from asyncio import sleep
from typing import TYPE_CHECKING, List
from .type_base import BaseTestType, PPipeFacade
from ..utils.constants import ResultState
from .resource_manager import ResourceManager

if TYPE_CHECKING:
    from ...plugin3918 import Model3918


class ScaledGroupThroughputTest(BaseTestType):
    def __init__(
        self,
        xoa_out: "PPipeFacade",
        cfg: "Model3918",
        resource_manager: "ResourceManager",
    ) -> None:
        super().__init__(xoa_out, cfg, resource_manager)
        scaled_group_forwarding_matrix = (
            cfg.test_types_configuration.scaled_group_forwarding_matrix
        )
        if scaled_group_forwarding_matrix:
            self.model_data.set_test_type_operation(scaled_group_forwarding_matrix)

    async def add_iteration_step(self) -> None:
        sweep_list = self.model_data.get_sweep_value_list()
        for rate in sweep_list:
            self.bout_info.set_rate(rate)
            self.reset_curr_group_count()
            await self.init_trial()
            self.setup_next_group_count()
            self.allocate_new_test_result()
            await self.setup_mc_source_port_streams()
            await self.setup_mc_stream_rates()
            await self.clear_port_stats()
            await self.start_counter_poll()
            await self.send_igmp_join()
            await sleep(self.model_data.get_join_to_traffic_delay())
            await self.start_traffic(False, True)
            await sleep(self.model_data.get_duration_value())
            await self.measure_forwarding_rate()
            await self.stop_traffic()
            await sleep(self.model_data.get_delay_after_stop())
            self.stop_counter_poll()
            await self.send_igmp_leave()
            await sleep(self.model_data.get_delay_after_leave())
            await self.get_final_counters()

    async def init_trial(self) -> None:
        await super().init_trial()
        if self.model_data.get_use_capacity_result():
            group_count_end = (
                self.max_capacity_map.get(self.bout_info.packet_size, 0)
                or self.model_data.get_group_count_end()
            )
            self.model_data.set_group_count_end(group_count_end)

    async def get_final_counters(self) -> bool:
        self.bout_info.set_is_final(True)
        self.bout_info.set_result_state(ResultState.PASS)
        await self.read_counters()
        return True

    async def measure_forwarding_rate(self) -> None:
        await self.get_final_counters()

    def setup_next_group_count(self) -> None:
        if self.bout_info.mc_group_count == 0:
            self.bout_info.set_mc_group_count(self.model_data.get_group_count_start())
        else:
            steps = (
                self.bout_info.mc_group_count + self.model_data.get_group_count_step()
            )
            self.bout_info.set_mc_group_count(
                min(steps, self.model_data.get_group_count_end())
            )

    def get_group_count_list(self) -> List[int]:
        return [1]

    def get_iteration_count(self) -> range:
        return range(
            1,
            self.model_data.get_iterations() + 1,
        )

    def show_results(self):
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
                }
            )
        self.display(totals)
