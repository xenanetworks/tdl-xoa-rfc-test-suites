from typing import Union
from ..model.mc_uc_definition import McDefinition
from ..model.protocol_segments import HeaderSegment
from ..utils.field import MacAddress, NewIPv4Address, NewIPv6Address
from .protocol_change import ParseMode, ProtocolChange
from ..plugin.mc_operations import (
    get_link_local_uc_ipv6_address,
    get_multicast_mac_for_ip,
)
from ..utils.constants import (
    ALL_ROUTERS_MULTICAST_GROUP_V2,
    ALL_ROUTERS_MULTICAST_GROUP_V3,
    ETHER_TYPE_IPV4,
    ETHER_TYPE_IPV6,
    ETHER_TYPE_VLAN_TAGGED,
    ICMP_V6_IP_PROTOCOL,
    IP_V4_OPTION_ROUTER_ALERT,
    IP_V6_OPTION_HOP_BY_HOP,
    IP_V6_OPTION_ROUTER_ALERT,
    IPV6_LINK_SCOPE_ALL_MLD_ROUTERS_ADDRESS,
    MLD_V1_DONE,
    MLD_V1_REPORT,
    MLD_V2_REPORT,
    IGMPv1Type,
    IGMPv3GroupRecordTypes,
    IgmpRequestType,
    IgmpVersion,
    ProtocolOption,
)


class IgmpMld:
    @classmethod
    def gen_igmpv1_header(
        cls,
        dest_ip_address: Union[NewIPv4Address, NewIPv6Address],
    ) -> HeaderSegment:
        return (
            ProtocolChange(ProtocolOption.IGMPV1)
            .change_segment("Type", IGMPv1Type.REPORT.value, ParseMode.BIT)
            .change_segment("Group Address", dest_ip_address.bytearrays, ParseMode.BYTE)
            .header
        )

    @classmethod
    def gen_igmpv2_header(
        cls,
        request_type: IgmpRequestType,
        dest_ip_address: Union[NewIPv4Address, NewIPv6Address],
    ) -> HeaderSegment:
        return (
            ProtocolChange(ProtocolOption.IGMPV2)
            .change_segment("Type", request_type.value, ParseMode.BIT)
            .change_segment("Group Address", dest_ip_address.bytearrays, ParseMode.BYTE)
            .header
        )

    @classmethod
    def get_igmp_v3_or_mld_v2_request_value(
        cls, request_type: IgmpRequestType, use_source_address: bool
    ) -> int:
        if request_type == IgmpRequestType.JOIN:
            if use_source_address:
                message_type = IGMPv3GroupRecordTypes.CHANGE_TO_INCLUDE_MODE.value
            else:
                message_type = IGMPv3GroupRecordTypes.CHANGE_TO_EXCLUDE_MODE.value
        else:  # request_type == IgmpRequestType.LEAVE
            if use_source_address:
                message_type = IGMPv3GroupRecordTypes.CHANGE_TO_EXCLUDE_MODE.value
            else:
                message_type = IGMPv3GroupRecordTypes.CHANGE_TO_INCLUDE_MODE.value
        return message_type

    @classmethod
    def gen_igmpv3_header(
        cls,
        request_type: IgmpRequestType,
        mc_source_ip_address: Union[NewIPv4Address, NewIPv6Address],
        group_ip_address: Union[NewIPv4Address, NewIPv6Address],
        use_src: bool,
    ) -> HeaderSegment:
        message_type = cls.get_igmp_v3_or_mld_v2_request_value(request_type, use_src)
        address_count = int(use_src)
        add_length = len(mc_source_ip_address.bytearrays) if use_src else 0
        group_segment_org = (
            ProtocolChange(ProtocolOption.IGMPV3_GR)
            .change_segment("Record Type", message_type)
            .change_segment("Number of Sources", address_count)
            .change_segment(
                "Multicast Address", group_ip_address.bytearrays, ParseMode.BYTE
            )
            .bytearrays
        )
        group_segment_raw = group_segment_org + bytearray(add_length)
        if use_src:
            group_segment_with_ip = (
                group_segment_raw[: -len(mc_source_ip_address.bytearrays)]
                + mc_source_ip_address.bytearrays
            )
        else:
            group_segment_with_ip = group_segment_raw

        igmp_segment_org = (
            ProtocolChange(ProtocolOption.IGMPV3_MR)
            .change_segment("Group Record Count", 1)
            .bytearrays
        )
        igmp_segment_raw = igmp_segment_org + bytearray(len(group_segment_with_ip))
        igmp_segment = (
            igmp_segment_raw[: -len(group_segment_with_ip)] + group_segment_with_ip
        )
        return HeaderSegment(
            type=ProtocolOption.IGMPV3_MR, segment_value=igmp_segment.hex()
        )

    @classmethod
    def get_igmp_packet(
        cls,
        request_type: IgmpRequestType,
        group_ip_address: Union[NewIPv4Address, NewIPv6Address],
        mc_src_ip: Union[NewIPv4Address, NewIPv6Address],
        mc_dest_ip: Union[NewIPv4Address, NewIPv6Address],
        mc_definition: McDefinition,
        mc_dest_mac: MacAddress,
    ) -> str:
        mc_ip = group_ip_address
        if mc_definition.igmp_version == IgmpVersion.IGMP_V1:
            if request_type == IgmpRequestType.LEAVE:
                return ""
            igmp_header = cls.gen_igmpv1_header(mc_ip)
        elif mc_definition.igmp_version == IgmpVersion.IGMP_V2_OR_MLD_V1:
            if (
                request_type == IgmpRequestType.LEAVE
                and mc_definition.force_leave_to_all_routers_group
            ):
                mc_ip = NewIPv4Address(ALL_ROUTERS_MULTICAST_GROUP_V2)
            igmp_header = cls.gen_igmpv2_header(request_type, mc_ip)
        else:
            mc_ip = NewIPv4Address(ALL_ROUTERS_MULTICAST_GROUP_V3)
            igmp_header = cls.gen_igmpv3_header(
                request_type,
                mc_src_ip,
                group_ip_address,
                mc_definition.use_igmp_source_address,
            )
        vlan_headers = [
            hs
            for hs in mc_definition.stream_definition.header_segments
            if hs.type == ProtocolOption.VLAN
        ]
        ether_type = bytearray(
            ETHER_TYPE_VLAN_TAGGED if vlan_headers else ETHER_TYPE_IPV4
        )
        ethernet_header = (
            ProtocolChange(ProtocolOption.ETHERNET)
            .change_segment(
                "Dst MAC addr",
                get_multicast_mac_for_ip(mc_ip).bytearrays,
                ParseMode.BYTE,
            )
            .change_segment(
                "Src MAC addr",
                mc_dest_mac.bytearrays,
                ParseMode.BYTE,
            )
            .change_segment("EtherType", (ether_type), ParseMode.BYTE)
            .header
        )

        ip_total_length = 20 + 4 + igmp_header.byte_length
        ip_header = (
            ProtocolChange(ProtocolOption.IPV4)
            .change_segment("Header Length", 0x06)
            .change_segment("Total Length", ip_total_length)
            .change_segment("DSCP", 0x30)
            .change_segment("TTL", 0x1)
            .change_segment("Protocol", 0x2)
            .change_segment("Src IP Addr", mc_dest_ip.bytearrays, ParseMode.BYTE)
            .change_segment("Dest IP Addr", mc_ip.bytearrays, ParseMode.BYTE)
            .header
        )
        ip_segment_value = ip_header.segment_value
        ip_segment_value += bytearray(
            [IP_V4_OPTION_ROUTER_ALERT, 0x04, 0x00, 0x00]
        ).hex()
        ip_header.segment_value = ip_segment_value
        header_list = [ethernet_header, ip_header, igmp_header]
        if vlan_headers:
            vlan_header = vlan_headers[0]
            header_list.insert(1, vlan_header)
        packet_header = ProtocolChange.cal_packet_header(header_list)
        return packet_header.hex()

    @classmethod
    def get_mld_packet(
        cls,
        request_type: IgmpRequestType,
        group_ip_address: Union[NewIPv4Address, NewIPv6Address],
        mc_source_ip_address: Union[NewIPv4Address, NewIPv6Address],
        mc_definition: McDefinition,
        source_mac_address: MacAddress,
    ) -> str:
        src_address_bytes = get_link_local_uc_ipv6_address(source_mac_address)
        if mc_definition.igmp_version == IgmpVersion.IGMP_V2_OR_MLD_V1:
            dest_ip_address = group_ip_address
            icmp_header = cls.build_mld_v1_header(request_type, group_ip_address)
        elif mc_definition.igmp_version == IgmpVersion.IGMP_V3_OR_MLD_V2:
            dest_ip_address = NewIPv6Address(IPV6_LINK_SCOPE_ALL_MLD_ROUTERS_ADDRESS)
            icmp_header = cls.build_mld_v2_header(
                request_type,
                group_ip_address,
                mc_source_ip_address,
                mc_definition.use_igmp_source_address,
            )
        else:
            raise
        ip_option_segment = bytearray(
            [
                ICMP_V6_IP_PROTOCOL,
                0x01,
                0x01,
                0x04,
                0x00,
                0x00,
                0x00,
                0x00,
                IP_V6_OPTION_ROUTER_ALERT,
                0x02,
                0x00,
                0x00,
                0x01,
                0x02,
                0x00,
                0x00,
            ]
        )
        payload_length = icmp_header.byte_length + len(ip_option_segment)
        ip_header = (
            ProtocolChange(ProtocolOption.IPV6)
            .change_segment("Traffic Class", 0)
            .change_segment("Payload Length", payload_length)
            .change_segment("Next Header", IP_V6_OPTION_HOP_BY_HOP)
            .change_segment("Hop Limit", 1)
            .change_segment("Src IPv6 Addr", src_address_bytes, ParseMode.BYTE)
            .change_segment(
                "Dest IPv6 Addr", dest_ip_address.bytearrays, ParseMode.BYTE
            )
        ).header
        ip_header.segment_value = ip_header.segment_value + ip_option_segment.hex()

        ether_header = (
            ProtocolChange(ProtocolOption.ETHERNET)
            .change_segment(
                "Dst MAC addr",
                get_multicast_mac_for_ip(dest_ip_address).bytearrays,
                ParseMode.BYTE,
            )
            .change_segment(
                "Src MAC addr",
                source_mac_address.bytearrays,
                ParseMode.BYTE,
            )
            .change_segment("EtherType", ETHER_TYPE_IPV6, ParseMode.BYTE)
        ).header
        header_list = [ether_header, ip_header, icmp_header]
        packet_header = ProtocolChange.cal_packet_header(header_list)
        return packet_header.hex()

    @classmethod
    def build_mld_v1_header(
        cls,
        request_type: IgmpRequestType,
        group_ip_address: Union[NewIPv4Address, NewIPv6Address],
    ) -> HeaderSegment:
        mld_type = (
            MLD_V1_REPORT if request_type == IgmpRequestType.JOIN else MLD_V1_DONE
        )
        icmp_header = (
            ProtocolChange(ProtocolOption.ICMPV6)
            .change_segment("Type", mld_type)
            .change_segment("Code", 0)
        ).header
        icmp_header.segment_value = (
            icmp_header.segment_value + group_ip_address.bytearrays.hex()
        )
        return icmp_header

    @classmethod
    def build_mld_v2_header(
        cls,
        request_type: IgmpRequestType,
        group_ip_address: Union[NewIPv4Address, NewIPv6Address],
        mc_source_ip_address: Union[NewIPv4Address, NewIPv6Address],
        use_source_address: bool,
    ) -> HeaderSegment:
        source_address_bytes = mc_source_ip_address.bytearrays
        message_type = cls.get_igmp_v3_or_mld_v2_request_value(
            request_type, use_source_address
        )
        address_count = 1 if use_source_address else 0
        add_length = len(source_address_bytes) if use_source_address else 0

        group_record_value = (
            ProtocolChange(ProtocolOption.MLDV2_AR)
            .change_segment("Record Type", message_type)
            .change_segment("Number of Sources", address_count)
            .change_segment(
                "Multicast Address", group_ip_address.bytearrays, ParseMode.BYTE
            )
        ).bytearrays + bytearray(add_length)
        if use_source_address:
            group_record_value[
                len(group_record_value) - len(source_address_bytes) :
            ] = source_address_bytes

        igmp_header = (
            ProtocolChange(ProtocolOption.ICMPV6)
            .change_segment("Type", MLD_V2_REPORT)
            .change_segment("Message", 1)
            .header
        )
        igmp_header.segment_value = igmp_header.segment_value + group_record_value.hex()
        return igmp_header
