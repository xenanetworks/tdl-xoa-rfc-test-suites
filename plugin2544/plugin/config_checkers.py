"""
Read port capability and compare with input data
"""


from typing import TYPE_CHECKING, List, Union, Tuple
from xoa_driver.enums import ProtocolOption
from ..utils import exceptions, constants as const
from .common import find_dest_port_structs


if TYPE_CHECKING:
    from xoa_driver import testers as xoa_testers
    from xoa_driver.lli import commands
    from .structure import PortStruct
    from .test_config import TestConfigData
    from .test_type_config import AllTestTypeConfig
    from ..model.m_protocol_segment import ProtocolSegmentProfileConfig
    from ..model.m_port_config import PortConfiguration


def check_port_config_profile(
    capabilities: "commands.P_CAPABILITIES.GetDataAttr",
    profile: "ProtocolSegmentProfileConfig",
) -> None:
    segment_id_list = profile.segment_id_list
    if capabilities.max_protocol_segments < len(segment_id_list):
        raise exceptions.ProtocolSegmentExceed(
            len(segment_id_list), capabilities.max_protocol_segments
        )
    if ProtocolOption.TCPCHECK in segment_id_list and not capabilities.can_tcp_checksum:
        raise exceptions.ProtocolNotSupport("TCPCHECK")
    if ProtocolOption.UDPCHECK in segment_id_list and not capabilities.can_udp_checksum:
        raise exceptions.ProtocolNotSupport("UDPCHECK")

    if profile.packet_header_length > capabilities.max_header_length:
        raise exceptions.PacketHeaderExceed(
            profile.packet_header_length, capabilities.max_header_length
        )

    for header_segment in profile.segments:
        for modifier in header_segment.hw_modifiers:
            if modifier.repeat > capabilities.max_repeat:
                raise exceptions.ModifierRepeatCountExceed(
                    modifier.repeat, capabilities.max_repeat
                )


def check_can_fec(can_fec: int, fec_mode: const.FECModeStr) -> None:
    """
    FromP_CAPABILITIES.can_fec:
        [0] = RS FEC KR, [1] = RS FEC KP, [2] = FC FEC, [31] = Mandatory.
        Position [0], [1], and [2] are mutually exclusive.
        If [31] is set, the port does not support OFF.
        If [0] is set, the port supports enums ON, and supposedly RS_FEC and RS_FEC_KR.
        If [1] is set, the port supports enums ON, and supposedly RS_FEC and RS_FEC_KP.
        If [2] is set, the port supports enum FC_FEC.
        NOTE: if [0] or [1] is set, the UI should show RS FEC but the command should use ON. Upon receiving ON, the port will automatically select the corresponding RS FEC mode, either KR or KP version.
    """
    bin_str = bin(can_fec)[2:].zfill(32)
    is_mandatory = int(bin_str[-32])
    is_fc_fec_supported = int(bin_str[-3])
    # check user config and check if capability supported.
    if is_mandatory and fec_mode == const.FECModeStr.OFF:   # [31] = Mandatory which is not support OFF mode
        raise exceptions.FECModeRequired()
    elif fec_mode == const.FECModeStr.FC_FEC and not is_fc_fec_supported:
        raise exceptions.FECModeTypeNotSupport(const.FECModeStr.FC_FEC)
    elif fec_mode == const.FECModeStr.ON and bin_str[-2:] in ["00", "11"]:
        raise exceptions.FECModeTypeNotSupport(const.FECModeStr.ON)


def check_custom_port_config(
    capabilities: "commands.P_CAPABILITIES.GetDataAttr", port_conf: "PortConfiguration"
) -> None:

    if port_conf.port_rate_cap_profile.is_custom and port_conf.port_rate > capabilities.max_speed * 1_000_000:
        raise exceptions.PortRateError(
            port_conf.port_rate, capabilities.max_speed * 1_000_000
        )
    if port_conf.speed_reduction_ppm > capabilities.max_speed_reduction:
        raise exceptions.SpeedReductionError(
            port_conf.speed_reduction_ppm, capabilities.max_speed_reduction
        )
    if (
        capabilities.min_interframe_gap > port_conf.inter_frame_gap
        or port_conf.inter_frame_gap > capabilities.max_interframe_gap
    ):
        raise exceptions.InterFrameGapError(
            int(port_conf.inter_frame_gap),
            capabilities.min_interframe_gap,
            capabilities.max_interframe_gap,
        )
    check_can_fec(capabilities.can_fec, port_conf.fec_mode)
    check_port_config_profile(capabilities, port_conf.profile)


def check_ports(control_ports: List["PortStruct"]) -> None:
    for port_struct in control_ports:
        check_custom_port_config(port_struct.capabilities, port_struct.port_conf)


def check_port_modifiers(
    capabilities: "commands.P_CAPABILITIES.GetDataAttr",
    port_conf: "PortConfiguration",
    is_stream_based: bool,
) -> None:
    
    if not port_conf.is_tx_port:
        # Modifers only set for tx port
        return

    modifier_count = port_conf.profile.modifier_count
    if is_stream_based:
        if modifier_count > capabilities.max_modifiers:
            raise exceptions.ModifierExceed(modifier_count, capabilities.max_modifiers)
    else:
        # not support to configure modifier if flow creation type is modifier based
        if modifier_count > 0:
            raise exceptions.ModifierBasedNotSupportDefineModifier()


def check_stream_limitations(
    port_struct: "PortStruct", per_port_stream_count: int, is_stream_based: bool
) -> None:
    if (not is_stream_based) or (not port_struct.port_conf.is_tx_port):
        return
    stream_count = len(port_struct.properties.peers) * per_port_stream_count
    if stream_count > port_struct.capabilities.max_streams_per_port:
        raise exceptions.StreamExceed(
            stream_count, port_struct.capabilities.max_streams_per_port
        )


def count_source_port(
    control_ports: List["PortStruct"], peer_struct: "PortStruct"
) -> int:
    count = 0
    for port_struct in control_ports:
        if peer_struct in port_struct.properties.peers:
            count += 1
    return count


def check_tid_limitations(
    control_ports: List["PortStruct"],
    scope: "const.TidAllocationScope",
    is_stream_based: bool,
) -> None:
    if (not is_stream_based) or (not scope.is_config_scope):
        return

    tid_value = 0
    dest_port_structs = find_dest_port_structs(control_ports)
    for peer_struct in dest_port_structs:
        src_port_count = count_source_port(control_ports, peer_struct)
        tid_value += src_port_count
        max_tpld_stats = peer_struct.capabilities.max_tpld_stats
        if tid_value > max_tpld_stats:
            raise exceptions.TPLDIDExceed(tid_value, max_tpld_stats)


def check_port_min_packet_length(
    capabilities: "commands.P_CAPABILITIES.GetDataAttr",
    min_packet_size: Union[float, int],
    packet_size_type: "const.PacketSizeType",
) -> None:
    if capabilities.min_packet_length > min_packet_size:
        raise exceptions.MinPacketLengthExceed(
            packet_size_type.value,
            int(min_packet_size),
            capabilities.min_packet_length,
        )


def check_port_max_packet_length(
    capabilities: "commands.P_CAPABILITIES.GetDataAttr",
    max_packet_size: Union[float, int],
    packet_size_type: "const.PacketSizeType",
) -> None:
    if capabilities.max_packet_length < max_packet_size:
        raise exceptions.MaxPacketLengthExceed(
            packet_size_type.value,
            int(max_packet_size),
            capabilities.max_packet_length,
        )


def get_tpld_total_length(
    capabilities: "commands.P_CAPABILITIES.GetDataAttr", use_micro_tpld_on_demand: bool
) -> int:
    if use_micro_tpld_on_demand and capabilities.can_micro_tpld:
        return const.MICRO_TPLD_TOTAL_LENGTH
    return const.STANDARD_TPLD_TOTAL_LENGTH


def get_needed_packet_length(
    port_struct: "PortStruct", use_micro_tpld_on_demand: bool
) -> int:
    packet_header_length = port_struct.port_conf.profile.packet_header_length
    return packet_header_length + get_tpld_total_length(
        port_struct.capabilities, use_micro_tpld_on_demand
    )


def check_needed_packet_length(
    port_struct: "PortStruct",
    min_packet_size: Union[float, int],
    use_micro_tpld_on_demand: bool,
) -> None:
    need_packet_length = get_needed_packet_length(port_struct, use_micro_tpld_on_demand)
    if min_packet_size < need_packet_length:
        raise exceptions.PacketSizeTooSmall(int(min_packet_size), need_packet_length)


def check_payload_pattern(
    capabilities: "commands.P_CAPABILITIES.GetDataAttr", payload_pattern: str
) -> None:
    cur = len(payload_pattern) // 2
    if capabilities.max_pattern_length < cur:
        raise exceptions.PayloadPatternExceed(cur, capabilities.max_pattern_length)


def check_micro_tpld(
    capabilities: "commands.P_CAPABILITIES.GetDataAttr", use_mocro_tpld: bool
) -> None:
    if not use_mocro_tpld:
        return
    if not bool(capabilities.can_micro_tpld):
        raise exceptions.MicroTPLDNotSupport()


def check_port_test_config(
    port_struct: "PortStruct", test_conf: "TestConfigData"
) -> None:

    if test_conf.frame_sizes.packet_size_type.is_mix:
        packet_size_list = test_conf.mixed_packet_length
    else:
        packet_size_list = test_conf.packet_size_list
    packet_size_type = test_conf.frame_sizes.packet_size_type
    min_packet_size = min(packet_size_list)
    max_packet_size = max(packet_size_list)
    per_port_stream_count = test_conf.multi_stream_config.per_port_stream_count
    check_payload_pattern(port_struct.capabilities, test_conf.payload_pattern)
    check_micro_tpld(port_struct.capabilities, test_conf.use_micro_tpld_on_demand)
    check_port_min_packet_length(
        port_struct.capabilities, min_packet_size, packet_size_type
    )
    check_port_max_packet_length(
        port_struct.capabilities, max_packet_size, packet_size_type
    )
    check_needed_packet_length(
        port_struct,
        min_packet_size,
        test_conf.use_micro_tpld_on_demand,
    )
    check_port_modifiers(
        port_struct.capabilities, port_struct.port_conf, test_conf.is_stream_based
    )
    check_stream_limitations(
        port_struct, per_port_stream_count, test_conf.is_stream_based
    )


def check_test_config(
    control_ports: List["PortStruct"], test_conf: "TestConfigData"
) -> None:
    for port_struct in control_ports:
        check_port_test_config(port_struct, test_conf)
    check_tid_limitations(
        control_ports, test_conf.tid_allocation_scope, test_conf.is_stream_based
    )


def check_tester_sync_start(
    tester: "xoa_testers.L23Tester", use_sync_start: bool
) -> None:
    if not use_sync_start:
        return
    cap = tester.info.capabilities
    if cap and not bool(cap.can_sync_traffic_start):
        raise exceptions.PortStaggeringNotSupport()


def check_testers(
    testers: List["xoa_testers.L23Tester"], test_conf: "TestConfigData"
) -> None:
    use_port_sync_start = test_conf.use_port_sync_start
    for tester in testers:
        check_tester_sync_start(tester, use_port_sync_start)


def check_test_type_config(test_type_conf: List["AllTestTypeConfig"]):
    for conf in test_type_conf:
        if conf.test_type.is_back_to_back:  # back to back require frame duration
            if conf.is_time_duration:
                raise exceptions.FrameDurationRequire(conf.test_type.value)
        else:  # other test type require time duration
            if not conf.is_time_duration:
                raise exceptions.TimeDurationRequire(conf.test_type.value)


def check_config(
    testers: List["xoa_testers.L23Tester"],
    control_ports: List["PortStruct"],
    test_conf: "TestConfigData",
) -> None:
    check_testers(testers, test_conf)
    check_ports(control_ports)
    check_test_config(control_ports, test_conf)
