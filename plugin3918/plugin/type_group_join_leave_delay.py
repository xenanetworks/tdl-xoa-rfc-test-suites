from asyncio import sleep, gather
from typing import TYPE_CHECKING, List
from xoa_driver.utils import apply
from xoa_driver.enums import (
    ProtocolOption,
    LengthCheckType,
    StartTrigger,
    StopTrigger,
    PacketType,
)
from ..utils.constants import FILTER_M0M1_L0L1, TRIGGER_PACKET_SIZE
from .type_base import BaseTestType, PPipeFacade
from .resource_manager import ResourceManager

if TYPE_CHECKING:
    from ...plugin3918 import Model3918


class GroupJoinLeaveDelayTest(BaseTestType):
    def __init__(
        self,
        xoa_out: "PPipeFacade",
        cfg: "Model3918",
        resource_manager: "ResourceManager",
    ) -> None:
        super().__init__(xoa_out, cfg, resource_manager)
        group_join_leave_delay = cfg.test_types_configuration.group_join_leave_delay
        if group_join_leave_delay:
            self.model_data.set_test_type_operation(group_join_leave_delay)

    def get_group_count_list(self) -> List[int]:
        return [1]

    def get_iteration_count(self) -> List[int]:
        return list(range(1, self.model_data.get_iterations() + 1))

    async def init_trial(self) -> None:
        self.want_igmp_request_tx_time = True
        await super().init_trial()

    async def add_iteration_step(self) -> None:
        sweep_list = self.model_data.get_sweep_value_list()
        for rate in sweep_list:
            self.bout_info.set_rate(rate)
            await self.init_trial()
            self.allocate_new_test_result()
            await self.setup_mc_source_port_streams()
            await self.setup_mc_stream_rates()
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
            await sleep(self.model_data.get_leave_to_stop_delay())
            await self.init_igmp_leave_capture()
            await sleep(0.1)
            await self.send_igmp_leave()
            await sleep(self.model_data.get_duration_value())
            await self.trigger_leave_capture_stop()
            await sleep(1)
            await self.stop_capture_and_get_stats()
            await self.get_leave_capture_data()
            await self.init_basic_igmp_capture()
            await sleep(self.model_data.get_traffic_to_join_delay())
            await self.stop_capture_and_get_stats()
            await self.check_no_mc_data_received(False)
            await self.stop_igmp_capture()
            self.stop_counter_poll()
            await self.stop_traffic()
            await sleep(self.model_data.get_delay_after_stop())
            await self.get_final_counters()

    async def stop_igmp_capture(self) -> None:
        tokens = []
        for mc_dest_port in self.resource_manager.mc_dest_ports():
            tokens.append(mc_dest_port.port.capturer.state.set_stop())
        await apply(*tokens)

    async def trigger_leave_capture_stop(self) -> None:
        tokens = []
        for mc_dest_port in self.resource_manager.mc_dest_ports():
            mc_dest_port.port.loop_back.set_txon2rx()
            native_mac = mc_dest_port.native_mac_address.hexstring
            trigger_packet = f"{native_mac}{native_mac}1234{(TRIGGER_PACKET_SIZE - len(native_mac) - 2 )*'00'}"
            tokens.append(mc_dest_port.port.tx_single_pkt.send.set(trigger_packet))
        await apply(*tokens)

    async def get_final_counters(self) -> bool:
        self.bout_info.set_is_final(True)
        await self.read_counters()
        return True

    async def init_igmp_leave_capture(self) -> None:
        # TODO
        for mc_dest_port in self.resource_manager.mc_dest_ports():

            await mc_dest_port.port.capturer.state.set_stop()
            await gather(
                mc_dest_port.port.match_terms.server_sync(),
                mc_dest_port.port.length_terms.server_sync(),
                mc_dest_port.port.filters.server_sync(),
            )
            await gather(
                *[m.delete() for m in mc_dest_port.port.match_terms],
                *[l.delete() for l in mc_dest_port.port.length_terms],
                *[f.delete() for f in mc_dest_port.port.filters],
            )

            ethernet_smac_match = await mc_dest_port.port.match_terms.create()
            ether_type_match = await mc_dest_port.port.match_terms.create()
            await apply(
                ethernet_smac_match.protocol.set([ProtocolOption.ETHERNET]),
                ethernet_smac_match.position.set(6),
                ethernet_smac_match.match.set(
                    "FFFFFFFFFFFF0000",
                    f"{mc_dest_port.native_mac_address.hexstring}0000",
                ),
                ether_type_match.protocol.set([ProtocolOption.ETHERNET]),
                ether_type_match.position.set(12),
                ether_type_match.match.set("FFFF000000000000", "1234000000000000"),
            )
            first = await mc_dest_port.port.length_terms.create()
            second = await mc_dest_port.port.length_terms.create()
            await apply(
                first.length.set(LengthCheckType.AT_LEAST, TRIGGER_PACKET_SIZE - 4),
                second.length.set(LengthCheckType.AT_MOST, TRIGGER_PACKET_SIZE + 4),
            )
            filter_con = await mc_dest_port.port.filters.create()
            await apply(
                filter_con.condition.set(0, 0, 0, 0, FILTER_M0M1_L0L1, 0),
                filter_con.enable.set_on(),
                mc_dest_port.port.capturer.trigger.set(
                    StartTrigger.ON, 0, StopTrigger.FILTER, 0
                ),
                mc_dest_port.port.capturer.keep.set(PacketType.TPLD, 0, -1),
                mc_dest_port.port.capturer.state.set_start(),
            )

    def show_results(self) -> None:

        # [Packet Size, Iter. #, Tx Off.Rate(Percent), Group Count, Result State, Curr. Loss(Packets)]
        totals = {
            "Packet Size": self.bout_info.packet_size,
            "Iter. #": self.bout_info.iter_index,
            "Tx Off.Rate(Percent)": self.bout_info.rate,
            "Group Count": self.bout_info.mc_group_count,
            "Result State": self.bout_info.result_state.value,
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
                    "Join Delay(msec)": d.test_result.join_delay
                    / self.model_data.get_latency_unit().scale,
                    "Leave Delay(msec)": d.test_result.leave_delay
                    / self.model_data.get_latency_unit().scale,
                }
            )
        self.display(totals)
