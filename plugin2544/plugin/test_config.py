from typing import List, Tuple
from ..model import m_test_config as t_model
from ..utils import constants as const, exceptions


class TestConfigData:
    """Get TestConfig Data without nested"""

    def __init__(self, test_config: "t_model.TestConfigModel"):
        self.__test_conf = test_config

    @property
    def is_stream_based(self) -> bool:
        return (
            self.__test_conf.test_execution_config.flow_creation_config.flow_creation_type.is_stream_based
        )

    @property
    def is_pair_topology(self) -> bool:
        return self.topology.is_pair_topology

    @property
    def topology(self) -> const.TestTopology:
        return self.__test_conf.topology_config.topology

    @property
    def direction(self) -> const.TrafficDirection:
        return self.__test_conf.topology_config.direction

    @property
    def is_iteration_outer_loop_mode(self) -> "bool":
        return self.__test_conf.test_execution_config.outer_loop_mode.is_iteration

    @property
    def repeat_test_until_stopped(self) -> bool:
        return self.__test_conf.test_execution_config.repeat_test_until_stopped

    @property
    def delay_after_port_reset_second(self) -> int:
        return (
            self.__test_conf.test_execution_config.reset_error_handling.delay_after_port_reset_second
        )

    @property
    def enable_multi_stream(self) -> bool:
        return self.__test_conf.multi_stream_config.enable_multi_stream

    @property
    def should_stop_on_los(self) -> bool:
        return (
            self.__test_conf.test_execution_config.reset_error_handling.should_stop_on_los
        )

    @property
    def use_gateway_mac_as_dmac(self) -> bool:
        return (
            self.__test_conf.test_execution_config.l23_learning_options.use_gateway_mac_as_dmac
        )

    @property
    def tid_allocation_scope(self) -> "const.TidAllocationScope":
        return (
            self.__test_conf.test_execution_config.flow_creation_config.tid_allocation_scope
        )

    @property
    def use_micro_tpld_on_demand(self) -> bool:
        return self.__test_conf.frame_size_config.use_micro_tpld_on_demand

    @property
    def multi_stream_mac_base_address(self) -> str:
        return self.__test_conf.multi_stream_config.multi_stream_mac_base_address

    @property
    def port_stagger_steps(self) -> int:
        return (
            self.__test_conf.test_execution_config.port_scheduling_config.port_stagger_steps
        )

    @property
    def frame_sizes(self) -> "t_model.FrameSize":
        return self.__test_conf.frame_size_config.frame_sizes

    @property
    def mac_base_address(self) -> str:
        return (
            self.__test_conf.test_execution_config.flow_creation_config.mac_base_address
        )

    @property
    def arp_refresh_enabled(self) -> bool:
        return (
            self.__test_conf.test_execution_config.l23_learning_options.arp_refresh_enabled
        )

    @property
    def payload_type(self) -> const.PayloadTypeStr:
        return self.__test_conf.frame_size_config.payload_type

    @property
    def payload_pattern(self) -> str:
        return self.__test_conf.frame_size_config.payload_pattern

    @property
    def multi_stream_config(self) -> "t_model.MultiStreamConfig":
        return self.__test_conf.multi_stream_config

    @property
    def use_port_sync_start(self) -> bool:
        return (
            self.__test_conf.test_execution_config.port_scheduling_config.use_port_sync_start
        )

    @property
    def enable_speed_reduction_sweep(self) -> bool:
        return (
            self.__test_conf.test_execution_config.port_scheduling_config.enable_speed_reduction_sweep
        )

    @property
    def sync_off_duration_second(self) -> int:
        return (
            self.__test_conf.test_execution_config.mac_learning_options.toggle_port_sync_config.sync_off_duration_second
        )

    @property
    def toggle_port_sync(self) -> bool:
        return (
            self.__test_conf.test_execution_config.mac_learning_options.toggle_port_sync_config.toggle_port_sync
        )

    @property
    def delay_after_sync_on_second(self) -> int:
        return (
            self.__test_conf.test_execution_config.mac_learning_options.toggle_port_sync_config.delay_after_sync_on_second
        )

    @property
    def learning_duration_second(self) -> int:
        return (
            self.__test_conf.test_execution_config.l23_learning_options.learning_duration_second
        )

    @property
    def learning_rate_pct(self) -> float:
        return (
            self.__test_conf.test_execution_config.l23_learning_options.learning_rate_pct
        )

    @property
    def use_flow_based_learning_preamble(self) -> bool:
        return (
            self.__test_conf.test_execution_config.flow_based_learning_options.use_flow_based_learning_preamble
        )

    @property
    def flow_based_learning_frame_count(self) -> int:
        return (
            self.__test_conf.test_execution_config.flow_based_learning_options.flow_based_learning_frame_count
        )

    @property
    def arp_refresh_period_second(self) -> float:
        return (
            self.__test_conf.test_execution_config.l23_learning_options.arp_refresh_period_second
        )

    @property
    def delay_after_flow_based_learning_ms(self) -> int:
        return (
            self.__test_conf.test_execution_config.flow_based_learning_options.delay_after_flow_based_learning_ms
        )

    @property
    def mac_learning_mode(self) -> "const.MACLearningMode":
        return (
            self.__test_conf.test_execution_config.mac_learning_options.mac_learning_mode
        )

    @property
    def mac_learning_frame_count(self) -> int:
        return (
            self.__test_conf.test_execution_config.mac_learning_options.mac_learning_frame_count
        )

    @property
    def mixed_packet_length(self) -> List[int]:
        mix_size_length_dic = self.frame_sizes.mixed_length_config.dict()
        return [
            const.MIXED_PACKET_SIZE[index]
            if not (mix_size_length_dic.get(f"field_{index}", 0))
            else mix_size_length_dic.get(f"field_{index}", 0)
            for index in range(len(const.MIXED_PACKET_SIZE))
        ]

    @property
    def mixed_average_packet_size(self) -> int:
        weighted_size = 0.0
        for index, size in enumerate(self.mixed_packet_length):
            weight = self.frame_sizes.mixed_sizes_weights[index]
            weighted_size += size * weight
        return int(round(weighted_size / 100.0))

    @property
    def packet_size_list(self) -> List[int]:
        packet_size_type = self.frame_sizes.packet_size_type
        if packet_size_type == const.PacketSizeType.IETF_DEFAULT:
            return list(const.DEFAULT_PACKET_SIZE_LIST)
        elif packet_size_type == const.PacketSizeType.CUSTOM:
            return list(sorted(self.frame_sizes.custom_packet_sizes))
        elif packet_size_type == const.PacketSizeType.MIX:
            return [self.mixed_average_packet_size]

        elif packet_size_type == const.PacketSizeType.RANGE:
            return list(
                range(
                    self.frame_sizes.fixed_packet_start_size,
                    self.frame_sizes.fixed_packet_end_size
                    + self.frame_sizes.fixed_packet_step_size,
                    self.frame_sizes.fixed_packet_step_size,
                )
            )

        elif packet_size_type in {
            const.PacketSizeType.INCREMENTING,
            const.PacketSizeType.BUTTERFLY,
            const.PacketSizeType.RANDOM,
        }:

            return [
                (
                    self.frame_sizes.varying_packet_min_size
                    + self.frame_sizes.varying_packet_max_size
                )
                // 2
            ]
        else:
            raise exceptions.FrameSizeTypeError(packet_size_type.value)

    @property
    def size_range(self) -> Tuple[int, int]:
        if self.frame_sizes.packet_size_type in [
            const.PacketSizeType.INCREMENTING,
            const.PacketSizeType.RANDOM,
            const.PacketSizeType.BUTTERFLY,
        ]:
            min_size = self.frame_sizes.varying_packet_min_size
            max_size = self.frame_sizes.varying_packet_max_size
        else:
            # Packet length is useless when mixed
            min_size = max_size = int(self.mixed_average_packet_size)
        return (min_size, max_size)
