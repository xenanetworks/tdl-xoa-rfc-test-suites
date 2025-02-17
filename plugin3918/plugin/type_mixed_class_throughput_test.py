from asyncio import sleep
from typing import TYPE_CHECKING, List
from .resource_manager import ResourceManager
from .type_base import BaseTestType, PPipeFacade
from ..utils.constants import ResultState, StreamTypeInfo

if TYPE_CHECKING:
    from ...plugin3918 import Model3918


class MixedClassThroughputTest(BaseTestType):
    def __init__(
        self,
        xoa_out: "PPipeFacade",
        cfg: "Model3918",
        resource_manager: "ResourceManager",
    ) -> None:
        super().__init__(xoa_out, cfg, resource_manager)
        self.src_port_type = StreamTypeInfo.UNICAST_NOT_BURDEN
        mixed_class_throughput = cfg.test_types_configuration.mixed_class_throughput
        if mixed_class_throughput:
            self.model_data.set_test_type_operation(mixed_class_throughput)

    def get_iteration_count(self) -> range:
        return range(1, self.model_data.get_iterations() + 1)

    def get_group_count_list(self) -> List[int]:
        return self.model_data.get_group_count_list()

    async def init_trial(self) -> None:
        self.bout_info.set_rate(self.model_data.get_rate_option_initial())
        self.pass_rate_percent = self.model_data.get_rate_option_minimum()
        self.fail_rate_percent = self.model_data.get_rate_option_maximum()
        return await super().init_trial()

    async def add_iteration_step(self) -> None:
        await self.init_trial()
        await self.send_mac_learning_packets()
        await sleep(1)
        done = False
        await self.setup_mc_source_port_streams()
        await self.setup_uc_burden_port_streams()
        while not done:
            self.allocate_new_test_result()
            await self.setup_mc_stream_rates()  # SetupMixedStreamRates
            await self.setup_uc_stream_rates(True)  # SetupMixedStreamRates
            await self.start_traffic(False, False)
            await sleep(1)
            await self.stop_traffic()
            await sleep(2)
            await self.send_igmp_join()
            await sleep(self.model_data.get_join_to_traffic_delay())
            await self.clear_port_stats()
            await self.start_counter_poll()
            await self.start_traffic(False, True)
            await sleep(self.model_data.get_duration_value())
            await self.stop_traffic()
            await sleep(self.model_data.get_delay_after_stop())
            self.stop_counter_poll()
            await self.send_igmp_leave()
            await sleep(self.model_data.get_delay_after_leave())
            done = await self.get_final_counters()

    async def get_final_counters(self) -> bool:
        self.bout_info.set_is_final(True)
        await self.resource_manager.query(self.src_port_type)
        done = False
        if (
            self.resource_manager.test_result.total_mc_frame_loss == 0
            and self.resource_manager.test_result.total_uc_frame_loss == 0
        ):
            self.pass_rate_percent = self.bout_info.rate
            too_close_to_end = (
                abs(self.bout_info.rate - self.model_data.get_rate_option_maximum())
                < 1e-6
            )
            small_resolution = (
                self.fail_rate_percent - self.pass_rate_percent
                <= self.model_data.get_rate_option_resolution()
            )
            if any([too_close_to_end, small_resolution]):
                self.bout_info.set_is_final(True)
                self.bout_info.set_result_state(ResultState.PASS)
                done = True
            else:
                next_rate = (self.pass_rate_percent + self.fail_rate_percent) / 2
                self.bout_info.set_is_final(False)
                self.bout_info.set_result_state(ResultState.PENDING)
                self.bout_info.set_actual_rate(next_rate)
                done = False
        else:
            self.fail_rate_percent = self.bout_info.rate
            if (
                self.fail_rate_percent
                <= self.model_data.get_rate_option_maximum()
                + self.model_data.get_rate_option_resolution()
            ):
                self.bout_info.set_is_final(True)
                self.bout_info.set_result_state(ResultState.FAIL)
                done = True
            else:
                next_rate = (self.pass_rate_percent + self.fail_rate_percent) / 2
                self.bout_info.set_is_final(False)
                self.bout_info.set_result_state(ResultState.PENDING)
                self.bout_info.set_actual_rate(next_rate)
                done = False
        self.show_results()
        return done

    def show_results(self) -> None:

        # [Packet Size, Iter. #, Tx Off.Rate(Percent), Group Count, Result State, Curr. Loss(Packets)]
        totals = {
            "Packet Size": self.bout_info.packet_size,
            "Iter. #": self.bout_info.iter_index,
            "Tx Off.Rate(Percent)": self.bout_info.rate,
            "Group Count": self.bout_info.mc_group_count,
            "Result State": self.bout_info.result_state.value,
            "UC Tx(Packets)": self.resource_manager.test_result.total_tx_frames,
            "UC Rx(Packets)": self.resource_manager.test_result.total_rx_frames,
            "UC Loss(Packets)": self.resource_manager.test_result.total_uc_frame_loss,
            "UC Loss(Percents)": self.resource_manager.test_result.total_uc_loss_ratio_percent,
            "Loss(Packets)": self.resource_manager.test_result.total_mc_frame_loss,
            "Loss Rate(Percent)": self.resource_manager.test_result.total_mc_loss_ratio_percent,
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
                }
            )
        self.display(totals)
