from asyncio import sleep, gather
from typing import TYPE_CHECKING, List
from .resource_manager import ResourceManager
from .type_base import BaseTestType, PPipeFacade
from ..utils.constants import StreamTypeInfo

if TYPE_CHECKING:
    from ...plugin3918 import Model3918


class BurdenedGroupJoinDelayTest(BaseTestType):
    def __init__(
        self,
        xoa_out: "PPipeFacade",
        cfg: "Model3918",
        resource_manager: "ResourceManager",
    ) -> None:
        super().__init__(xoa_out, cfg, resource_manager)
        self.src_port_type = StreamTypeInfo.UNICAST_BURDEN
        self.want_igmp_request_tx_time = True
        burdened_group_join_delay = (
            cfg.test_types_configuration.burdened_group_join_delay
        )
        if burdened_group_join_delay:
            self.model_data.set_test_type_operation(burdened_group_join_delay)

    def get_iteration_count(self) -> range:
        return range(1, self.model_data.get_iterations() + 1)

    def get_group_count_list(self) -> List[int]:
        return [1]

    async def init_trial(self) -> None:
        self.want_igmp_request_tx_time = True
        return await super().init_trial()

    async def add_iteration_step(self) -> None:
        sweep_list = self.model_data.get_sweep_value_list()
        for rate in sweep_list:
            self.bout_info.set_rate(rate)
            await self.init_trial()
            self.allocate_new_test_result()
            await self.setup_mc_source_port_streams()
            await self.setup_uc_burden_port_streams()
            await self.setup_mc_stream_rates()
            await self.setup_uc_stream_rates(False)
            await self.send_igmp_leave()
            await self.init_basic_igmp_capture()
            await self.clear_port_stats()
            await self.start_traffic(False, True)
            await self.start_counter_poll()
            await sleep(self.model_data.get_traffic_to_join_delay())
            await self.stop_capture_and_get_stats()
            await self.check_no_mc_data_received(False)
            await self.init_basic_igmp_capture()
            await self.send_igmp_join()
            await sleep(self.model_data.get_duration_value())
            await self.stop_capture_and_get_stats()
            await self.get_join_capture_data()
            await self.stop_traffic()
            await sleep(self.model_data.get_delay_after_stop())
            self.stop_counter_poll()
            await self.send_igmp_leave()
            await sleep(self.model_data.get_delay_after_leave())
            await self.get_final_counters()

    async def get_final_counters(self) -> bool:
        self.bout_info.set_is_final(True)
        await self.read_counters()
        return True

    def show_results(self) -> None:

        # [Packet Size, Iter. #, Tx Off.Rate(Percent), Group Count, Result State, Curr. Loss(Packets)]
        totals = {
            "Packet Size": self.bout_info.packet_size,
            "Iter. #": self.bout_info.iter_index,
            "Tx Off.Rate(Percent)": self.bout_info.rate,
            "Group Count": self.bout_info.mc_group_count,
            "Result State": self.bout_info.result_state.value,
            "Tx(Packets)": self.resource_manager.test_result.total_tx_frames,
            "Rx(Packets)": self.resource_manager.test_result.total_rx_frames,
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
                    "MC Tx Packets": r.frames,
                    "MC Tx Rate(Bit/s)": r.bps,
                    "MC Tx Rate(Pps)": r.pps,
                }
            )

        for d in self.resource_manager.mc_dest_ports():
            r = d.test_result.mc_destination_data
            # [Rx Packets, Rx Rate(Bit/s), Rx Group Count#]
            totals["Destination Ports"].append(
                {
                    "Destination Port Name": d.name,
                    "MC Rx Packets": r.frames,
                    "MC Rx Rate(Bit/s)": r.bps,
                    "Join Delay(msec)": d.test_result.join_delay
                    / self.model_data.get_latency_unit().scale,
                }
            )
        self.display(totals)
