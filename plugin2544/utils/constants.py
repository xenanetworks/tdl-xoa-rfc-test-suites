from enum import Enum
from xoa_driver import ports, enums


class CaseInsensitiveEnum(Enum):
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value == value.lower():
                    return member


MICRO_TPLD_LENGTH = 6
ETHERNET_FCS_LENGTH = 4
STANDARD_TPLD_LENGTH = 20
MIN_PAYLOAD_LENGTH = 2
MICRO_TPLD_TOTAL_LENGTH = MICRO_TPLD_LENGTH + ETHERNET_FCS_LENGTH
STANDARD_TPLD_TOTAL_LENGTH = (
    STANDARD_TPLD_LENGTH + MIN_PAYLOAD_LENGTH + ETHERNET_FCS_LENGTH
)
MIN_REFRESH_TIMER_INTERNAL = 100.0
DEFAULT_PACKET_SIZE_LIST = (64, 128, 256, 512, 1024, 1280, 1518)
MIXED_PACKET_SIZE = (
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
)
MIXED_DEFAULT_WEIGHTS = (0, 0, 0, 0, 57, 3, 5, 1, 2, 5, 1, 4, 4, 18, 0, 0)
MIXED_PACKET_CONFIG_LENGTH_INDICES = (0, 1, 14, 15)
MAX_PACKET_LIMIT_VALUE = 0x7FFFFFFF

STANDARD_SEGMENT_VALUE = (128, 256, 512, 1024, 2048)

MdixPorts = (
    ports.POdin1G3S6P,
    ports.POdin1G3S6P_b,
    ports.POdin1G3S6PE,
    ports.POdin1G3S2PT,
)

BrrPorts = (ports.POdin1G3S6PT1RJ45,)
AutoNegPorts = (
    ports.POdin1G3S6P,
    ports.POdin1G3S6P_b,
    ports.POdin1G3S6PE,
    ports.POdin1G3S2PT,
    ports.POdin5G4S6PCU,
    ports.POdin10G5S6PCU,
    ports.POdin10G5S6PCU_b,
    ports.POdin10G3S6PCU,
    ports.POdin10G3S2PCU,
)


PCSPMAPorts = (ports.PThor400G7S1P_c, ports.PThor400G7S1P_b)

# for asyncio.sleep
DELAY_LEARNING_ARP = 1
DELAY_LEARNING_MAC = 1
DELAY_STATISTICS = 5
DELAY_STOPPED_TRAFFIC = 1
DELAY_CHECK_SYNC = 1
DELAY_TEST_MUST_FINISH = 10
DELAY_CLEAR_STATISTICS = 1
INTERVAL_CHECK_LEARNING_TRAFFIC = 0.1
INTERVAL_SEND_STATISTICS = 1


class CounterType(CaseInsensitiveEnum):
    JITTER = -1
    LATENCY = -2147483648


class PortCounterType(CaseInsensitiveEnum):
    TX = 0
    RX = 1


class ResultState(CaseInsensitiveEnum):
    SUCCESS = "success"
    FAIL = "fail"
    DONE = "done"
    PENDING = "pending"


class TestTopology(CaseInsensitiveEnum):
    PAIRS = "pairs"
    BLOCKS = "blocks"
    MESH = "mesh"

    @property
    def is_mesh_topology(self) -> bool:
        return self == type(self).MESH

    @property
    def is_pair_topology(self) -> bool:
        return self == type(self).PAIRS


class TrafficDirection(CaseInsensitiveEnum):
    EAST_TO_WEST = "east_to_west"
    WEST_TO_EAST = "west_to_east"
    BIDIRECTION = "bidirectional"


class PacketSizeType(CaseInsensitiveEnum):
    IETF_DEFAULT = "ietf_default"
    CUSTOM = "custom_sizes"
    RANGE = "specified"
    INCREMENTING = "incrementing"
    BUTTERFLY = "butterfly"
    RANDOM = "random"
    MIX = "mixed_sizes"

    @property
    def is_custom(self) -> bool:
        return self == type(self).CUSTOM

    @property
    def is_mix(self) -> bool:
        return self == type(self).MIX

    @property
    def is_fix(self) -> bool:
        return self in [type(self).IETF_DEFAULT, type(self).CUSTOM, type(self).RANGE]

    def to_xmp(self):
        if self.is_fix:
            return enums.LengthType.FIXED
        else:
            return enums.LengthType[self.name]


class PayloadTypeStr(CaseInsensitiveEnum):
    INCREMENTING = "incrementing"
    PATTERN = "pattern"
    PRBS = "prbs"

    def to_xmp(self):
        return enums.PayloadType[self.name]


class TidAllocationScope(CaseInsensitiveEnum):
    CONFIGURATION_SCOPE = "config_scope"
    RX_PORT_SCOPE = "port_scope"
    SOURCE_PORT_ID = "source_port_id"

    @property
    def is_config_scope(self) -> bool:
        return self == TidAllocationScope.CONFIGURATION_SCOPE


class OuterLoopMode(CaseInsensitiveEnum):
    ITERATION = "iterations"
    PACKET_SIZE = "packet_size"

    @property
    def is_iteration(self) -> bool:
        return self == type(self).ITERATION


class MACLearningMode(CaseInsensitiveEnum):
    NEVER = "never"
    ONCE = "once"
    EVERYTRIAL = "every_trial"


class DurationType(CaseInsensitiveEnum):
    TIME = "time"
    FRAME = "frames"

    @property
    def is_time_duration(self) -> bool:
        return self == type(self).TIME


class DurationUnit(CaseInsensitiveEnum):
    SECOND = "seconds"
    MINUTE = "minutes"
    HOUR = "hours"
    FRAME = "frames"
    K_FRAME = "10e3_frames"
    M_FRAME = "10e6_frames"
    G_FRAME = "10e9_frames"

    @property
    def scale(self) -> int:
        return {
            DurationUnit.FRAME: 1,
            DurationUnit.K_FRAME: 1_000,
            DurationUnit.M_FRAME: 1_000_000,
            DurationUnit.G_FRAME: 1_000_000_000,
            DurationUnit.SECOND: 1,
            DurationUnit.MINUTE: 60,
            DurationUnit.HOUR: 3600,
        }[self]


class TestType(CaseInsensitiveEnum):
    THROUGHPUT = "throughput"
    LATENCY_JITTER = "latency"
    FRAME_LOSS_RATE = "loss"
    BACK_TO_BACK = "back_to_back"

    @property
    def is_latency(self) -> bool:
        return self == type(self).LATENCY_JITTER

    @property
    def is_back_to_back(self) -> bool:
        return self == type(self).BACK_TO_BACK


class SearchType(CaseInsensitiveEnum):
    BINARY_SEARCH = "binary_search"
    FAST_BINARY_SEARCH = "fast_binary_search"

    @property
    def is_fast(self) -> bool:
        return self == SearchType.FAST_BINARY_SEARCH


class RateResultScopeType(CaseInsensitiveEnum):
    COMMON = "common_result"
    PER_SOURCE_PORT = "per_source_port_result"

    @property
    def is_per_source_port(self) -> bool:
        return self == RateResultScopeType.PER_SOURCE_PORT


class LatencyModeStr(CaseInsensitiveEnum):
    FIRST2LAST = "first_to_last"
    LAST2LAST = "last_to_last"
    FIRST2FIRST = "first_to_first"
    LAST2FIRST = "last_to_first"

    def to_xmp(self) -> "enums.LatencyMode":
        return enums.LatencyMode[self.name]


class TestResultState(CaseInsensitiveEnum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"


class AcceptableLossType(CaseInsensitiveEnum):
    PERCENT = "percent"
    FRAME = "frames"

    @property
    def is_percentage(self) -> bool:
        return self == AcceptableLossType.PERCENT

class PortRateCapProfile(CaseInsensitiveEnum):
    PHYSICAL = "physical_port_rate"
    CUSTOM = "custom_rate_cap"

    @property
    def is_custom(self) -> bool:
        return self == PortRateCapProfile.CUSTOM


class PortRateCapUnit(CaseInsensitiveEnum):
    GBPS = "1e9_bps"
    MBPS = "1e6_bps"
    KBPS = "1e3_bps"
    BPS = "bps"

    def scale(self) -> int:
        return {
            PortRateCapUnit.GBPS: 1e9,
            PortRateCapUnit.MBPS: 1e6,
            PortRateCapUnit.KBPS: 1e3,
            PortRateCapUnit.BPS: 1,
        }[self]


class MdiMdixMode(CaseInsensitiveEnum):
    AUTO = "auto"
    MDI = "mdi"
    MDIX = "mdix"

    def to_xmp(self) -> "enums.MDIXMode":
        return enums.MDIXMode[self.name]


class BRRModeStr(CaseInsensitiveEnum):
    MASTER = "master"
    SLAVE = "slave"

    def to_xmp(self) -> "enums.BRRMode":
        return enums.BRRMode[self.name]


class FECModeStr(CaseInsensitiveEnum):
    ON = "on"
    OFF = "off"
    FC_FEC = "fc_fec"

    def to_xmp(self) -> "enums.FECMode":
        return enums.FECMode[self.name]


class PortSpeedStr(CaseInsensitiveEnum):
    AUTO = "auto"
    F100M = "f100m"
    F1G = "f1g"
    F2500M = "f2500m"
    F5G = "f5g"
    F10G = "f10g"
    F100M1G = "f100m1g"
    F100M1G2500M = "f100m1g2500m"
    F10M = "f10m"
    F40G = "f40g"
    F100G = "f100g"
    F10MHDX = "f10mhdx"
    F100MHDX = "f100mhdx"
    F10M100M = "f10m100m"
    F100M1G10G = "f100m1g10g"
    F25G = "f25g"
    F50G = "f50g"
    F200G = "f200g"
    F400G = "f400g"
    F800G = "f800g"
    F1600G = "f1600g"
    UNKNOWN = "unknown"

    @property
    def is_auto(self):
        return self == PortSpeedStr.AUTO

    def to_xmp(self) -> "enums.PortSpeedMode":
        return enums.PortSpeedMode[self.name]


class PortGroup(CaseInsensitiveEnum):
    EAST = "east"
    WEST = "west"
    UNDEFINED = "undefined"

    @property
    def is_east(self):
        return self == PortGroup.EAST

    @property
    def is_west(self):
        return self == PortGroup.WEST


class ModifierActionOption(CaseInsensitiveEnum):
    INC = "increment"
    DEC = "decrement"
    RANDOM = "random"

    def to_xmp(self) -> "enums.ModifierAction":
        return enums.ModifierAction[self.name]


class FlowCreationType(CaseInsensitiveEnum):
    STREAM = "stream_based"
    MODIFIER = "modifier_based"

    @property
    def is_stream_based(self):
        return self == FlowCreationType.STREAM


class ThroughputUnit(CaseInsensitiveEnum):
    BIT_PER_SEC = "bps"
    FRAME_PER_SEC = "fps"


class MulticastRole(CaseInsensitiveEnum):
    UNDEFINED = "undefined"


class SegmentType(CaseInsensitiveEnum):
    # RAW = "raw"
    ETHERNET = "ethernet"
    VLAN = "vlan"
    ARP = "arp"
    IP = "ipv4"
    IPV6 = "ipv6"
    UDP = "udp"
    TCP = "tcp"
    LLC = "llc"
    SNAP = "snap"
    GTP = "gtp"
    ICMP = "icmp"
    # ICMPV6 = "icmpv6"
    RTP = "rtp"
    RTCP = "rtcp"
    STP = "stp"
    SCTP = "sctp"  # added
    MACCTRL = "macctrl"
    MPLS = "mpls"
    PBBTAG = "pbbtag"
    FCOE = "fcoe"  # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
    FC = "fc"
    # FCOEHEAD = "fcoehead"  # added
    FCOETAIL = "fcoetail"
    IGMPV3L0 = "igmpv3l0"
    IGMPV3L1 = "igmpv3l1"
    # IGMPV3GR = "igmpv3gr"
    # IGMPV3MR = "igmpv3mr"
    # MLDV2AR = "mldv2ar"
    UDPCHECK = "udpcheck"
    IGMPV2 = "igmpv2"
    # "MPLS_TP_OAM"
    GRE_NOCHECK = "gre_nocheck"
    GRE_CHECK = "gre_check"
    TCPCHECK = "tcp_check"
    # "GTPV1L0"
    # "GTPV1L1"
    # "GTPV2L0"
    # "GTPV2L1"
    IGMPV1 = "igmpv1"
    # "PWETHCTRL"
    VXLAN = "vxlan"
    # "ETHERNET_8023"
    NVGRE = "nvgre"
    # "DHCPV4"
    # "GENEVE"
    # "XENA_TPLD"
    # "XENA_TPLD_PI"
    # "XENA_MICROTPLD"
    # "ETHERNET_FCS"
    # "MACCTRLPFC"
    # "ECPRI"
    # "ROE"
    # "ETHERTYPE"
    # Generat RAW form 1...64 bytes
    _ignore_ = "SegmentType i"
    SegmentType = vars()
    for i in range(1, 65):
        SegmentType[f"RAW_{i}"] = f"raw_{i}"  # type: ignore

    def to_xmp(self) -> "enums.ProtocolOption":
        return enums.ProtocolOption[self.name]

    @property
    def is_raw(self) -> bool:
        return self.value.lower().startswith("raw")

    @property
    def raw_length(self) -> int:
        if not self.is_raw:
            return 0
        return int(self.value.split("_")[-1])


class StreamState(CaseInsensitiveEnum):
    OFF = "off"
    ON = "on"
    SUPPRESS = "suppress"


class StreamRateType(CaseInsensitiveEnum):
    FRACTION = "fraction"
    PPS = "pps"
    L2MBPS = "l2mbps"


class StreamPacketLengthType(CaseInsensitiveEnum):
    FIXED = "fixed"
    INCREMENTING = "incrementing"
    BUTTERFLY = "butterfly"
    RANDOM = "random"
    MIX = "mix"


class FramePacketTerminology(CaseInsensitiveEnum):
    FRAME = "fps"
    PACKET = "pps"


class PassDisplayType(CaseInsensitiveEnum):
    PASS = "pass"
    DONE = "done"


class PortProtocolVersion(CaseInsensitiveEnum):
    ETHERNET = 0
    IPV4 = 4
    IPV6 = 6

    @property
    def is_ipv4(self) -> bool:
        return self == type(self).IPV4

    @property
    def is_ipv6(self) -> bool:
        return self == type(self).IPV6

    @property
    def is_l3(self) -> bool:
        return self != type(self).ETHERNET


class IPVersion(CaseInsensitiveEnum):
    IPV4 = 4
    IPV6 = 6

    @property
    def is_ipv4(self) -> bool:
        return self == type(self).IPV4


class ARPSenarioType(CaseInsensitiveEnum):
    DEFAULT = 0
    GATEWAY = 1
    REMOTE = 2
    PUBLIC = 3


class IPPrefixLength(CaseInsensitiveEnum):
    IPv4 = 32
    IPv6 = 128


class TestState(CaseInsensitiveEnum):
    L3_LEARNING = 3
    RUNNING_TEST = 5

