from enum import Enum
from xoa_driver.enums import (
    LatencyMode as XLatencyMode,
    LengthType,
    ProtocolOption as XProtocolOption,
    PayloadType as XPayloadType,
)


MIXED_DEFAULT_WEIGHTS = [0, 0, 0, 0, 57, 3, 5, 1, 2, 5, 1, 4, 4, 18, 0, 0]
MIXED_PACKET_SIZE = [
    56,
    60,
    64,
    70,
    78,
    92,
    256,
    496,
    512,
    570,
    576,
    594,
    1438,
    1518,
    9216,
    16360,
]
STANDARD_TPLD_LENGTH = 20
MICRO_TPLD_LENGTH = 6
ETHERNET_FCS_LENGTH = 4
MIN_PAYLOAD_LENGTH = 2

STANDARD_TPLD_TOTAL_LENGTH = (
    STANDARD_TPLD_LENGTH + MIN_PAYLOAD_LENGTH + ETHERNET_FCS_LENGTH
)
MICRO_TPLD_TOTAL_LENGTH = MICRO_TPLD_LENGTH + ETHERNET_FCS_LENGTH
MIN_REFRESH_TIMER_INTERNAL = 100.0

HW_PACKET_MIN_SIZE = 64
HW_PACKET_MAX_SIZE = 1500

IP_V4_MULTICAST_MAC_BASE_ADDRESS = "01005e000000"
IP_V6_MULTICAST_MAC_BASE_ADDRESS = "333300000000"

IGMP_V2_JOIN = 0x16
IGMP_V2_LEAVE = 0x17
MLD_V1_REPORT = 0x83
MLD_V1_DONE = 0x84
MLD_V2_REPORT = 0x8F

ALL_ROUTERS_MULTICAST_GROUP_V2 = "224.0.0.2"
ALL_ROUTERS_MULTICAST_GROUP_V3 = "224.0.0.22"
IPV6_LINK_SCOPE_ALL_MLD_ROUTERS_ADDRESS = "FF02::16"
ICMP_V6_IP_PROTOCOL = 0x3A
IP_V6_OPTION_ROUTER_ALERT = 0x05
IP_V6_OPTION_HOP_BY_HOP = 0x00


ETHER_TYPE_NULL = [0x00, 0x00]
ETHER_TYPE_NONE = [0xFF, 0xFF]
ETHER_TYPE_VLAN_TAGGED = [0x81, 0x00]
ETHER_TYPE_VLAN_QIN_Q = [0x91, 0x00]
ETHER_TYPE_MPLS_UNICAST = [0x88, 0x47]
ETHER_TYPE_MPLS_MULTICAST = [0x88, 0x48]
ETHER_TYPE_IPV4 = [0x08, 0x00]
ETHER_TYPE_IPV6 = [0x86, 0xDD]
ETHER_TYPE_ARP = [0x08, 0x06]

IP_V4_OPTION_ROUTER_ALERT = 0x94
MIN_PACKET_LENGTH = 60

IEEE_DEFAULT_LIST = [64, 128, 256, 512, 1024, 1280, 1518]

TRIGGER_PACKET_SIZE = 64

FILTER_M0M1_L0L1 = 196611


class MulticastRole(Enum):
    MC_SOURCE = "mc_source"
    MC_DESTINATION = "mc_destination"
    UC_BURDEN = "uc_burden"
    UNDEFINED = "undefined"


class TestTopology(Enum):
    PAIRS = "pairs"
    BLOCKS = "blocks"
    MESH = "mesh"


class TrafficDirection(Enum):
    EAST_TO_WEST = "east_to_west"
    WEST_TO_EAST = "west_to_east"
    BIDIRECTION = "bidir"


class IgmpVersion(Enum):
    IGMP_V1 = "igmp_v1"
    IGMP_V2_OR_MLD_V1 = "igmp_v2_or_mld_v1"
    IGMP_V3_OR_MLD_V2 = "igmp_v3_or_mld_v2"


class IPVersion(Enum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"


class DisplayUnit(Enum):
    MILLI_SECONDS = "millisecs"
    MICRO_SECONDS = "microsecs"

    @property
    def scale(self) -> float:
        if self == DisplayUnit.MILLI_SECONDS:
            return 1e3
        else:
            return 1e6


class ProtocolOption(Enum):
    ARP = "arp"
    ETHERNET = "ethernet"
    FC = "fc"
    FCOE = "fcoe"
    FCOETAIL = "fcoetail"
    GRE_CHECK = "gre_check"
    GRE_NOCHECK = "gre_nocheck"
    GTP = "gtp"
    ICMP = "icmp"
    ICMPV6 = "icmpv6"
    IGMPV1 = "igmpv1"
    IGMPV2 = "igmpv2"
    MLDV2_AR = "mldv2_ar"
    IGMPV3_GR = "igmpv3_gr"
    IGMPV3_MR = "igmpv3_mr"
    IGMPV3L0 = "igmpv3l0"
    IGMPV3L1 = "igmpv3l1"
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    LLC = "llc"
    MACCTRL = "macctrl"
    MPLS = "mpls"
    NVGRE = "nvgre"
    PBBTAG = "pbbtag"
    RTCP = "rtcp"
    RTP = "rtp"
    SCTP = "sctp"
    SNAP = "snap"
    STP = "stp"
    TCP = "tcp"
    TCPCHECK = "tcp_check"
    UDP = "udp"
    UDPCHECK = "udp_check"
    VLAN = "vlan"
    VXLAN = "vxlan"

    RAW_1 = "raw_1"
    RAW_2 = "raw_2"
    RAW_3 = "raw_3"
    RAW_4 = "raw_4"
    RAW_5 = "raw_5"
    RAW_6 = "raw_6"
    RAW_7 = "raw_7"
    RAW_8 = "raw_8"
    RAW_9 = "raw_9"
    RAW_10 = "raw_10"
    RAW_11 = "raw_11"
    RAW_12 = "raw_12"
    RAW_13 = "raw_13"
    RAW_14 = "raw_14"
    RAW_15 = "raw_15"
    RAW_16 = "raw_16"
    RAW_17 = "raw_17"
    RAW_18 = "raw_18"
    RAW_19 = "raw_19"
    RAW_20 = "raw_20"
    RAW_21 = "raw_21"
    RAW_22 = "raw_22"
    RAW_23 = "raw_23"
    RAW_24 = "raw_24"
    RAW_25 = "raw_25"
    RAW_26 = "raw_26"
    RAW_27 = "raw_27"
    RAW_28 = "raw_28"
    RAW_29 = "raw_29"
    RAW_30 = "raw_30"
    RAW_31 = "raw_31"
    RAW_32 = "raw_32"
    RAW_33 = "raw_33"
    RAW_34 = "raw_34"
    RAW_35 = "raw_35"
    RAW_36 = "raw_36"
    RAW_37 = "raw_37"
    RAW_38 = "raw_38"
    RAW_39 = "raw_39"
    RAW_40 = "raw_40"
    RAW_41 = "raw_41"
    RAW_42 = "raw_42"
    RAW_43 = "raw_43"
    RAW_44 = "raw_44"
    RAW_45 = "raw_45"
    RAW_46 = "raw_46"
    RAW_47 = "raw_47"
    RAW_48 = "raw_48"
    RAW_49 = "raw_49"
    RAW_50 = "raw_50"
    RAW_51 = "raw_51"
    RAW_52 = "raw_52"
    RAW_53 = "raw_53"
    RAW_54 = "raw_54"
    RAW_55 = "raw_55"
    RAW_56 = "raw_56"
    RAW_57 = "raw_57"
    RAW_58 = "raw_58"
    RAW_59 = "raw_59"
    RAW_60 = "raw_60"
    RAW_61 = "raw_61"
    RAW_62 = "raw_62"
    RAW_63 = "raw_63"
    RAW_64 = "raw_64"

    @property
    def xoa(self) -> XProtocolOption:
        dic = {
            ProtocolOption.ARP: XProtocolOption.ARP,
            ProtocolOption.ETHERNET: XProtocolOption.ETHERNET,
            ProtocolOption.FC: XProtocolOption.FC,
            ProtocolOption.FCOE: XProtocolOption.FCOE,
            ProtocolOption.FCOETAIL: XProtocolOption.FCOETAIL,
            ProtocolOption.GRE_CHECK: XProtocolOption.GRE_CHECK,
            ProtocolOption.GRE_NOCHECK: XProtocolOption.GRE_NOCHECK,
            ProtocolOption.GTP: XProtocolOption.GTP,
            ProtocolOption.ICMP: XProtocolOption.ICMP,
            ProtocolOption.ICMPV6: XProtocolOption.ICMP,
            ProtocolOption.IGMPV1: XProtocolOption.IGMPV1,
            ProtocolOption.IGMPV2: XProtocolOption.IGMPV2,
            ProtocolOption.IGMPV3L0: XProtocolOption.IGMPV3L0,
            ProtocolOption.IGMPV3L1: XProtocolOption.IGMPV3L1,
            ProtocolOption.IPV4: XProtocolOption.IP,
            ProtocolOption.IPV6: XProtocolOption.IPV6,
            ProtocolOption.LLC: XProtocolOption.LLC,
            ProtocolOption.MACCTRL: XProtocolOption.MACCTRL,
            ProtocolOption.MPLS: XProtocolOption.MPLS,
            ProtocolOption.NVGRE: XProtocolOption.NVGRE,
            ProtocolOption.PBBTAG: XProtocolOption.PBBTAG,
            ProtocolOption.RTCP: XProtocolOption.RTCP,
            ProtocolOption.RTP: XProtocolOption.RTP,
            ProtocolOption.SCTP: XProtocolOption.SCTP,
            ProtocolOption.SNAP: XProtocolOption.SNAP,
            ProtocolOption.STP: XProtocolOption.STP,
            ProtocolOption.TCP: XProtocolOption.TCP,
            ProtocolOption.TCPCHECK: XProtocolOption.TCPCHECK,
            ProtocolOption.UDP: XProtocolOption.UDP,
            ProtocolOption.UDPCHECK: XProtocolOption.UDPCHECK,
            ProtocolOption.VLAN: XProtocolOption.VLAN,
            ProtocolOption.VXLAN: XProtocolOption.VXLAN,
        }
        dic.update(
            {
                ProtocolOption[f"RAW_{i}"]: XProtocolOption[f"RAW_{i}"]
                for i in range(1, 65)
            }
        )
        return dic[self]


class PortRateCapProfile(Enum):
    PHYSICAL = "physical_port_rate"
    CUSTOM = "custom_rate_cap"


class RateType(Enum):
    PPS = "pps"
    FRACTION = "fraction"


class PortRateCapUnit(Enum):
    GBPS = "1e9_bps"
    MBPS = "1e6_bps"
    KBPS = "1e3_bps"
    BPS = "bps"

    @property
    def scale(self) -> float:
        return {
            PortRateCapUnit.GBPS: 1e9,
            PortRateCapUnit.MBPS: 1e6,
            PortRateCapUnit.KBPS: 1e3,
            PortRateCapUnit.BPS: 1,
        }[self]


class FlowCreationType(Enum):
    STREAM = "stream_based"
    MODIFIER = "modifier_based"


class LatencyMode(Enum):
    FIRST2LAST = "first_to_last"
    LAST2LAST = "last_to_last"
    FIRST2FIRST = "first_to_first"
    LAST2FIRST = "last_to_first"

    @property
    def xoa(self) -> XLatencyMode:
        return {
            LatencyMode.FIRST2LAST: XLatencyMode.FIRST2LAST,
            LatencyMode.LAST2LAST: XLatencyMode.LAST2LAST,
            LatencyMode.FIRST2FIRST: XLatencyMode.FIRST2FIRST,
            LatencyMode.LAST2FIRST: XLatencyMode.LAST2FIRST,
        }[self]


class TidAllocationScope(Enum):
    CONFIGURATION_SCOPE = "config_scope"
    RX_PORT_SCOPE = "port_scope"
    SOURCE_PORT_ID = "source_port_id"


class MdiMdixMode(Enum):
    AUTO = "auto"
    MDI = "mdi"
    MDIX = "mdix"


class PortSpeedMode(Enum):
    AUTO = "AUTO"
    F100M = "F100M"
    F10M = "F10M"
    F10MHDX = "F10MHDX"
    F100MHDX = "F100MHDX"
    F10M100M = "F10M100M"
    F1G = "F1G"
    SPEED_100M1G10G = "SPEED_100M1G10G"
    SPEED_2500M = "SPEED_2500M"
    SPEED_5G = "SPEED_5G"
    F10G = "F10G"
    F40G = "F40G"
    F100G = "F100G"
    F100M1G = "F100M1G"
    SPEED_100M1G2500M = "SPEED_100M1G2500M"

    @property
    def scale(self) -> float:
        return {
            PortSpeedMode.AUTO: 0,
            PortSpeedMode.F10M: 10,
            PortSpeedMode.F100M: 100,
            PortSpeedMode.F1G: 1000,
            PortSpeedMode.F10G: 10000,
            PortSpeedMode.F40G: 40000,
            PortSpeedMode.F100G: 100000,
            PortSpeedMode.F10MHDX: 10,
            PortSpeedMode.F100MHDX: 100,
            PortSpeedMode.F10M100M: 100,
            PortSpeedMode.F100M1G: 1000,
            PortSpeedMode.SPEED_100M1G10G: 10000,
            PortSpeedMode.SPEED_2500M: 2500,
            PortSpeedMode.SPEED_5G: 5000,
            PortSpeedMode.SPEED_100M1G2500M: 2500,
        }[self] * 1_000_000


class BRRMode(Enum):
    MASTER = "master"
    SLAVE = "slave"


class PacketSizeType(Enum):
    IEEE_DEFAULT = "ietf_default"
    CUSTOM_SIZES = "custom_sizes"
    RANGE = "specified"
    INCREMENTING = "incrementing"
    BUTTERFLY = "butterfly"
    RANDOM = "random"
    MIX = "mixed_sizes"

    @property
    def xoa(self) -> LengthType:
        return {
            PacketSizeType.IEEE_DEFAULT: LengthType.FIXED,
            PacketSizeType.CUSTOM_SIZES: LengthType.FIXED,
            PacketSizeType.RANGE: LengthType.FIXED,
            PacketSizeType.INCREMENTING: LengthType.INCREMENTING,
            PacketSizeType.BUTTERFLY: LengthType.BUTTERFLY,
            PacketSizeType.RANDOM: LengthType.RANDOM,
            PacketSizeType.MIX: LengthType.MIX,
        }[self]


class PayloadType(Enum):
    PATTERN = "pattern"
    INCREMENTING = "incrementing"
    PRBS = "prbs"

    @property
    def xoa(self) -> XPayloadType:
        return {
            PayloadType.PATTERN: XPayloadType.PATTERN,
            PayloadType.INCREMENTING: XPayloadType.INCREMENTING,
            PayloadType.PRBS: XPayloadType.PRBS,
        }[self]


class GroupCountSel(Enum):
    LIST = "List"
    RANGE = "Range"


class StreamTypeInfo(Enum):
    MULTICAST = "multicast"
    UNICAST_NOT_BURDEN = "unicast_not_burden"
    UNICAST_BURDEN = "unicast_burden"


class IGMPv1Type(Enum):
    QUERY = 1
    REPORT = 2


class IGMPv3GroupRecordTypes(Enum):
    MODE_IS_INCLUDE = 1
    MODE_IS_EXCLUDE = 2
    CHANGE_TO_INCLUDE_MODE = 3
    CHANGE_TO_EXCLUDE_MODE = 4
    ALLOW_NEW_SOURCES = 5
    BLOCK_OLD_SOURCES = 6


class IgmpRequestType(Enum):
    JOIN = IGMP_V2_JOIN
    LEAVE = IGMP_V2_LEAVE


class ResultState(Enum):
    PENDING = "Pending"
    PASS = "Pass"
    FAIL = "Fail"
