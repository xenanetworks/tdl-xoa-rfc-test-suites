from decimal import Decimal
from enum import Enum as CaseSensitiveEnum
from typing import TYPE_CHECKING
from xoa_driver import enums

if TYPE_CHECKING:
    from xoa_driver.enums import (
        BRRMode,
    )

# for asyncio.sleep
DELAY_WAIT_TRAFFIC_STOP = 5
DELAY_LEARNING_MAC = 1
DELAY_LEARNING_ADDRESS = 1
DELAY_CREATE_PORT_PAIR = 3
DELAY_WAIT_RESET_PORT = 5
DELAY_WAIT_RESET_STATS = 2
INTERVAL_CHECK_SHOULD_STOP_TRAFFIC = 0.01
INTERVAL_CHECK_PORT_SYNC = 1
INTERVAL_CHECK_PORT_RESERVE = 0.5
INTERVAL_CLEAR_STATISTICS = 0.01
INTERVAL_INJECT_FCS_ERROR = 0.2

CHECK_SYNC_MAX_RETRY = 30

# https://en.wikipedia.org/wiki/Ethernet_frame
# 20 = Preamble + Start frame delimiter + Interpacket gap
DEFAULT_INTERFRAME_GAP = 20

DECIMAL_100 = Decimal(100)
WAIT_SYNC_STATE_TIMEOUT = 30
INVALID_PORT_ROLE = 'invalid port role'
DEFAULT_MIXED_PACKET_SIZE = (
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
DEFAULT_IETF_PACKET_SIZE = (
    64,
    128,
    256,
    512,
    1024,
    1280,
    1518,
)
MIXED_DEFAULT_WEIGHTS = (0, 0, 0, 0, 57, 3, 5, 1, 2, 5, 1, 4, 4, 18, 0, 0)


class Enum(CaseSensitiveEnum):
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.name == value:
                    return member


class DurationTimeUnit(Enum):
    SECOND = "seconds"
    MINUTE = "minutes"
    HOUR = "hours"
    DAY = "days"

    @property
    def scale(self) -> int:
        if self == DurationTimeUnit.SECOND:
            return 1
        elif self == DurationTimeUnit.MINUTE:
            return 60
        elif self == DurationTimeUnit.HOUR:
            return 3600
        raise ValueError("No scale!")


class TestStatus(Enum):
    STOP = 0
    START = 1
    PAUSE = 2


class AcceptableType(Enum):
    PERCENT = 1
    FRAME = 2


class StatisticsStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAIL = "fail"

    @property
    def is_success(self):
        return self == StatisticsStatus.SUCCESS

    @property
    def is_fail(self):
        return self == StatisticsStatus.FAIL


class BRRModeStr(Enum):
    MASTER = "master"
    SLAVE = "slave"

    def to_xmp(self) -> "BRRMode":
        return BRRMode[self.name]


class IPVersion(Enum):
    IPV4 = 4
    IPV6 = 6


class LearningPortDMacMode(Enum):
    USE_TEST_PORT_MAC = "UseTestPortMac"
    USE_BROADCAST = "UseBroadcast"

    @property
    def is_use_broadcast(self):
        return self == LearningPortDMacMode.USE_BROADCAST


class LearningSequencePortDMacMode(Enum):
    USE_INCREMENTING_MAC_ADDRESSES = "UseIncrementingMacAddresses"
    USE_RANDOM_MAC_ADDRESSES = "UseRandomMacAddresses"

    @property
    def is_incr(self):
        return self == LearningSequencePortDMacMode.USE_INCREMENTING_MAC_ADDRESSES

    @property
    def is_random(self):
        return self == LearningSequencePortDMacMode.USE_RANDOM_MAC_ADDRESSES


class TestPortMacMode(Enum):
    USE_PORT_NATIVE_MAC = "UsePortNativeMac"
    USE_LEARNING_MAC_BASE_ADDRESS = "UseLearnMacBaseAddress"

    @property
    def is_use_learning_base_address(self):
        return self == TestPortMacMode.USE_LEARNING_MAC_BASE_ADDRESS


class PortGroup(Enum):
    EAST = "east"
    WEST = "west"
    UNDEFINED = "undefined"
    SOURCE = "source"
    DESTINATION = "destination"
    TEST_PORT = "test_port"
    LEARNING_PORT = "learning_port"
    MONITORING_PORT = "monitoring_port"

    @property
    def is_east(self) -> bool:
        return self == PortGroup.EAST

    @property
    def is_west(self) -> bool:
        return self == PortGroup.WEST

    @property
    def is_undefined(self) -> bool:
        return self == PortGroup.UNDEFINED

    @property
    def is_source(self) -> bool:
        return self == PortGroup.SOURCE

    @property
    def is_destination(self) -> bool:
        return self == PortGroup.DESTINATION


class PortRateCapProfile(Enum):
    PHYSICAL_PORT_RATE = "physical_port_rate"
    CUSTOM = "custom"

    @property
    def is_custom(self) -> bool:
        return self == PortRateCapProfile.CUSTOM


class TestType(Enum):
    RATE_TEST = "rate_test"
    CONGESTION_CONTROL = "congestion_control"
    FORWARD_PRESSURE = "forward_pressure"
    MAX_FORWARDING_RATE = "max_forwarding_rate"
    ADDRESS_CACHING_CAPACITY = "address_caching_capacity"
    ADDRESS_LEARNING_RATE = "address_learning_rate"
    ERRORED_FRAMES_FILTERING = "errored_frames_filtering"
    BROADCAST_FORWARDING = "broadcast_forwarding"


class TrafficDirection(Enum):
    EAST_TO_WEST = "east_to_west"
    WEST_TO_EAST = "west_to_east"
    BIDIR = "bidir"


class StreamRateType(Enum):
    FRACTION = "fraction"
    PPS = "pps"
    L1BPS = "l1bps"
    L2BPS = "l2bps"


class PortRateCapUnitInt(Enum):
    FIELD_1E9_BPS = 1e9
    FIELD_1E6_BPS = 1e6
    FIELD_1E3_BPS = 1e3
    BPS = 1


class PortRateCapUnit(Enum):
    FIELD_1E9_BPS = "field_1e9_bps"
    FIELD_1E6_BPS = "field_1e6_bps"
    FIELD_1E3_BPS = "field_1e3_bps"
    BPS = "bps"

    @property
    def to_int(self) -> int:
        return PortRateCapUnitInt[self.name].value


class PortSpeedStrMps(Enum):
    AUTO = 0
    F100M = 100
    F1G = 1000
    F2500M = 2500
    F5G = 5000
    F10G = 10000
    F100M1G = 1000
    F100M1G2500M = 2500
    F10M = 10
    F40G = 40000
    F100G = 100000
    F10MHDX = 10
    F100MHDX = 100
    F10M100M = 100
    F100M1G10G = 10000
    F25G = 25000
    F50G = 50000
    F200G = 200000
    F400G = 400000
    F800G = 800000
    F1600G = 1600000
    UNKNOWN = -1


class PortSpeedStr(Enum):
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

    def to_bps(self) -> int:
        return PortSpeedStrMps[self.name].value * 1e6


class TestTopology(Enum):
    PAIRS = "pairs"
    BLOCKS = "blocks"
    MESH = "mesh"

    @property
    def is_mesh_topology(self) -> bool:
        return self == type(self).MESH

    @property
    def is_pair_topology(self) -> bool:
        return self == type(self).PAIRS


class LatencyMode(Enum):
    FIRST2LAST = "first_to_last"
    LAST2LAST = "last_to_last"
    FIRST2FIRST = "first_to_first"
    LAST2FIRST = "last_to_first"

    def to_xmp(self) -> "enums.LatencyMode":
        return enums.LatencyMode[self.name]


class MdiMdixMode(Enum):
    AUTO = "auto"
    MDI = "mdi"
    MDIX = "mdix"

    def to_xmp(self) -> "enums.MDIXMode":
        return enums.MDIXMode[self.name]


class TidAllocationScope(Enum):
    CONFIGURATION_SCOPE = "configuration_scope"
    RX_PORT_SCOPE = "port_scope"
    SOURCE_PORT_ID = "source_port_id"

    @property
    def is_config_scope(self) -> bool:
        return self == TidAllocationScope.CONFIGURATION_SCOPE


class FECModeStr(Enum):
    ON = "ON"
    OFF = "OFF"
    FC_FEC = "FIRECODE"

    def to_xmp(self) -> "enums.FECMode":
        return enums.FECMode[self.name]


class PacketSizeType(Enum):
    IETF_DEFAULT = "ietf_default"
    CUSTOM_SIZES = "custom_sizes"
    RANGE = "specified"
    INCREMENTING = "incrementing"
    BUTTERFLY = "butterfly"
    RANDOM = "random"
    MIX = "mix"

    @property
    def is_custom(self) -> bool:
        return self == type(self).CUSTOM_SIZES

    @property
    def is_mix(self) -> bool:
        return self == type(self).MIX

    @property
    def is_fix(self) -> bool:
        return self in [type(self).IETF_DEFAULT, type(self).CUSTOM_SIZES, type(self).RANGE]

    def to_xmp(self):
        if self.is_fix:
            return enums.LengthType.FIXED
        else:
            return enums.LengthType[self.name]
