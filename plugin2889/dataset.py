import sys
from statistics import fmean
from dataclasses import dataclass, field
from decimal import Decimal
from numbers import Number
from typing import Dict, List, NamedTuple, Tuple
from operator import attrgetter
from ipaddress import (
    IPv4Address as OldIPv4Address,
    IPv6Address as OldIPv6Address,
    IPv4Network,
    IPv6Network,
)
from abc import ABC, abstractmethod
from decimal import Decimal
from collections import defaultdict
from dataclasses import dataclass, field
from ipaddress import IPv4Network, IPv6Network
from typing import (
    TYPE_CHECKING,
    Any,
    Generator,
    Iterable,
    List,
    Optional,
    Union,
    Dict,
)
from pydantic import (
    BaseModel,
    NonNegativeInt,
    Field,
    field_validator,
)
from xoa_driver import ports

from plugin2889.model import exceptions
from plugin2889 import const
from plugin2889.model.protocol_segment import BinaryString, ProtocolSegmentProfileConfig
from plugin2889.const import (
    DEFAULT_IETF_PACKET_SIZE,
    DEFAULT_MIXED_PACKET_SIZE,
    INVALID_PORT_ROLE,
    MIXED_DEFAULT_WEIGHTS,
    BRRModeStr,
    IPVersion,
    LearningPortDMacMode,
    LearningSequencePortDMacMode,
    PortGroup,
    PortRateCapProfile,
    TestPortMacMode,
    FECModeStr,
    MdiMdixMode,
    PacketSizeType,
    PortRateCapUnit,
    PortSpeedStr,
    TestType,
    StreamRateType,
    DurationTimeUnit,
    TestTopology,
    LatencyMode,
    TidAllocationScope,
    TrafficDirection,
)

if TYPE_CHECKING:
    from xoa_driver.ports import GenericL23Port


class NewRateSweepOptions(BaseModel):
    start_value: Decimal
    end_value: Decimal
    step_value: Decimal

    @field_validator("start_value", "end_value", "step_value")
    def to_decimal(cls, v):
        return Decimal(v)


class RateIterationOptions(BaseModel):
    initial_value: float
    minimum_value: float
    maximum_value: float
    value_resolution: float
    use_pass_threshold: bool
    pass_threshold: float


class PortRoleConfig(BaseModel):
    is_used: bool
    role: PortGroup
    peer_port_id: str


class PortRoleCounter(BaseModel):
    enabled: int = 0
    by_roles: Dict[PortGroup, int] = {}

    def read(self, role: PortGroup) -> int:
        return self.by_roles.get(role, 0)


class PortRoleHandler(BaseModel):
    role_map: Dict[str, PortRoleConfig]  # key is guid_{uuid} "guid_fed2f488-a81e-4bbd-9eaa-16b10748ba33"

    @property
    def used_port_count(self) -> int:
        return sum(int(port.is_used) for port in self.role_map.values())

    @property
    def role_counter(self) -> "PortRoleCounter":
        counter = PortRoleCounter()
        for port in self.role_map.values():
            if port.is_used:
                counter.enabled += 1
            current = counter.by_roles.get(port.role, 0)
            counter.by_roles[port.role] = current + 1
        return counter


class TestCaseBaseConfiguration(ABC, BaseModel):
    enabled: bool
    topology: Optional[TestTopology] = None
    direction: Optional[TrafficDirection] = None
    rate_iteration_options: Optional[RateIterationOptions] = None
    rate_sweep_options: Optional[NewRateSweepOptions] = None
    port_role_handler: Optional[PortRoleHandler]
    duration: int
    duration_time_unit: DurationTimeUnit
    iterations: int
    item_id: str
    label: str

    def check_src_dest_port_roles(self, require_src_ports: int, require_dest_ports: int) -> None:
        assert self.port_role_handler, INVALID_PORT_ROLE
        if self.port_role_handler.role_counter.enabled != require_src_ports + require_dest_ports:
            raise exceptions.PortRoleEnabledNotEnough(require_src_ports + require_dest_ports)

        if self.port_role_handler.role_counter.read(PortGroup.SOURCE) != require_src_ports:
            raise exceptions.PortRoleNotEnough('source', require_src_ports)

        if self.port_role_handler.role_counter.read(PortGroup.DESTINATION) != require_dest_ports:
            raise exceptions.PortRoleNotEnough('destination', require_src_ports)

    def check_address_test_port_roles(self) -> None:
        assert self.port_role_handler, INVALID_PORT_ROLE
        if self.port_role_handler.role_counter.enabled != 3:
            raise exceptions.PortRoleEnabledNotEnough(3)

        for role in (PortGroup.LEARNING_PORT, PortGroup.MONITORING_PORT, PortGroup.TEST_PORT):
            if self.port_role_handler.role_counter.read(role) != 1:
                raise exceptions.PortRoleNotEnough(role.value, 1)

    @abstractmethod
    def check_configuration(self) -> None:
        raise NotImplementedError(type(self).__name__)


class RateSubTestConfiguration(TestCaseBaseConfiguration):
    topology: TestTopology
    direction: TrafficDirection
    test_type: TestType = TestType.RATE_TEST
    throughput_test_enabled: bool
    forwarding_test_enabled: bool

    def check_configuration(self) -> None:
        pass


class RateTestConfiguration(TestCaseBaseConfiguration):
    test_type: TestType = TestType.RATE_TEST
    sub_test: List[RateSubTestConfiguration]

    def check_port_roles(self, sub_test: RateSubTestConfiguration) -> None:
        assert sub_test.port_role_handler, INVALID_PORT_ROLE
        seen_east = seen_west = False
        for port in sub_test.port_role_handler.role_map.values():
            if not port.is_used:
                continue
            if port.role.is_east:
                seen_east = True
            elif port.role.is_west:
                seen_west = True
            elif port.role.is_undefined:
                raise exceptions.RateTestPortRoleUndefined()

            if sub_test.topology.is_pair_topology and not port.peer_port_id:
                raise exceptions.RateTestPortRoleEmptyPair()

        if not (seen_east and seen_west):
            raise exceptions.RateTestPortRoleEmptyGroupRole()

    def check_configuration(self) -> None:
        for test in self.sub_test:
            if not test.enabled:
                continue
            if not (test.forwarding_test_enabled or test.throughput_test_enabled):
                raise exceptions.RateTestEmptySubTest()
            if not test.port_role_handler or (test.port_role_handler and test.port_role_handler.used_port_count < 2):
                raise exceptions.RateTestPortConfigNotEnough()
            if not test.topology.is_mesh_topology:
                self.check_port_roles(test)


class CongestionControlConfiguration(TestCaseBaseConfiguration):
    test_type: TestType = TestType.CONGESTION_CONTROL

    def check_configuration(self) -> None:
        self.check_src_dest_port_roles(2, 2)


class ForwardPressureConfiguration(TestCaseBaseConfiguration):
    test_type: TestType = TestType.FORWARD_PRESSURE
    interframe_gap_delta: float
    acceptable_rx_max_util_delta: float

    def check_configuration(self) -> None:
        self.check_src_dest_port_roles(1, 1)


class MaxForwardingRateConfiguration(TestCaseBaseConfiguration):
    test_type: TestType = TestType.MAX_FORWARDING_RATE
    use_throughput_as_start_value: bool

    def check_configuration(self) -> None:
        self.check_src_dest_port_roles(1, 1)


class AddressCachingCapacityConfiguration(TestCaseBaseConfiguration):
    test_type: TestType = TestType.ADDRESS_CACHING_CAPACITY
    address_iteration_options: RateIterationOptions
    learn_mac_base_address: str
    test_port_mac_mode: TestPortMacMode
    learning_port_dmac_mode: LearningPortDMacMode
    learning_sequence_port_dmac_mode: LearningSequencePortDMacMode
    learning_rate_fps: float
    toggle_sync_state: bool
    sync_off_duration: int
    sync_on_duration: int
    switch_test_port_roles: bool
    dut_aging_time: int
    fast_run_resolution_enabled: bool

    def check_configuration(self) -> None:
        self.check_address_test_port_roles()


class AddressLearningRateConfiguration(TestCaseBaseConfiguration):
    test_type: TestType = TestType.ADDRESS_LEARNING_RATE
    address_sweep_options: NewRateSweepOptions
    rate_iteration_options: RateIterationOptions
    learn_mac_base_address: str
    test_port_mac_mode: TestPortMacMode
    learning_port_dmac_mode: LearningPortDMacMode
    learning_sequence_port_dmac_mode: LearningSequencePortDMacMode
    learning_rate_fps: float
    toggle_sync_state: bool
    sync_off_duration: int
    sync_on_duration: int
    switch_test_port_roles: bool
    dut_aging_time: int
    only_use_capacity: bool
    set_end_address_to_capacity: bool

    def check_configuration(self) -> None:
        self.check_address_test_port_roles()


class ErroredFramesFilteringConfiguration(TestCaseBaseConfiguration):
    test_type: TestType = TestType.ERRORED_FRAMES_FILTERING
    rate_sweep_options: NewRateSweepOptions
    oversize_test_enabled: bool
    max_frame_size: int
    oversize_span: int
    min_frame_size: int
    undersize_span: int

    def check_configuration(self) -> None:
        self.check_src_dest_port_roles(1, 1)


class BroadcastForwardingConfiguration(TestCaseBaseConfiguration):
    test_type: TestType = TestType.BROADCAST_FORWARDING
    rate_iteration_options: RateIterationOptions

    def check_configuration(self) -> None:
        assert self.port_role_handler, INVALID_PORT_ROLE
        if self.port_role_handler.role_counter.enabled < 2:
            raise exceptions.PortConfigNotEnough(2)

        if self.port_role_handler.role_counter.read(PortGroup.SOURCE) != 1:
            raise exceptions.PortConfigNotMatchExactly(PortGroup.SOURCE.value, 1)

        if self.port_role_handler.role_counter.read(PortGroup.DESTINATION) < 1:
            raise exceptions.PortRoleNotEnoughAtLeast(PortGroup.DESTINATION.value, 1)


UnionTestSuitConfiguration = Union[
    RateTestConfiguration,
    RateSubTestConfiguration,
    CongestionControlConfiguration,
    ForwardPressureConfiguration,
    MaxForwardingRateConfiguration,
    AddressCachingCapacityConfiguration,
    AddressLearningRateConfiguration,
    ErroredFramesFilteringConfiguration,
    BroadcastForwardingConfiguration,


]


class TestSuitesConfiguration(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        validate_assignment = True

    rate_test: RateTestConfiguration
    congestion_control: CongestionControlConfiguration
    forward_pressure: ForwardPressureConfiguration
    max_forwarding_rate: MaxForwardingRateConfiguration
    address_caching_capacity: AddressCachingCapacityConfiguration
    address_learning_rate: AddressLearningRateConfiguration
    errored_frames_filtering: ErroredFramesFilteringConfiguration
    broadcast_forwarding: BroadcastForwardingConfiguration

    def __init__(self, **data: Any):
        super().__init__(**data)
        for test_name in self.__fields__:
            test_config = getattr(self, test_name)
            if not test_config.enabled:
                continue

            test_config.check_configuration()


class RateDefinition(BaseModel):
    rate_type: StreamRateType
    rate_fraction: float
    rate_pps: float
    rate_bps_l1: float
    rate_bps_l1_unit: PortRateCapUnit
    rate_bps_l2: float
    rate_bps_l2_unit: PortRateCapUnit

    @ property
    def is_fraction(self):
        return self.rate_type == StreamRateType.FRACTION

    @ property
    def is_pps(self):
        return self.rate_type == StreamRateType.PPS

    @ property
    def is_l1bps(self):
        return self.rate_type == StreamRateType.L1BPS

    @ property
    def is_l2bps(self):
        return self.rate_type == StreamRateType.L2BPS


@ dataclass
class TPLDIDController:
    tid_allocation_scope: TidAllocationScope
    current_rx_port_tid: Dict["GenericL23Port", int] = field(default_factory=lambda: defaultdict(lambda: 0))
    current_tid: int = 0
    next_tid: int = 0

    def alloc_new_tpld_id(self, source_port: "GenericL23Port", destination_port: "GenericL23Port") -> int:
        if self.tid_allocation_scope == TidAllocationScope.CONFIGURATION_SCOPE:
            self.next_tid = self.current_tid
            self.current_tid += 1
        elif self.tid_allocation_scope == TidAllocationScope.RX_PORT_SCOPE:
            self.next_tid = self.current_rx_port_tid[destination_port]
            self.current_rx_port_tid[destination_port] += 1
        elif self.tid_allocation_scope == TidAllocationScope.SOURCE_PORT_ID:
            self.next_tid = source_port.kind.port_id

        if self.next_tid > source_port.info.capabilities.max_tpld_stats:
            exceptions.TPLDIDExceed(self.next_tid, source_port.info.capabilities.max_tpld_stats)
        return self.next_tid


class FrameSizesOptions(BaseModel):
    class Config:
        allow_population_by_field_name = True

    field_0: NonNegativeInt = Field(56, alias="0")
    field_1: NonNegativeInt = Field(60, alias="1")
    field_14: NonNegativeInt = Field(9216, alias="14")
    field_15: NonNegativeInt = Field(16360, alias="15")

    @ property
    def dictionary(self) -> Dict[int, NonNegativeInt]:
        return {
            0: self.field_0,
            1: self.field_1,
            14: self.field_14,
            15: self.field_15,
        }


class FrameSizeConfiguration(BaseModel):
    # FrameSizes
    packet_size_type: PacketSizeType
    # FixedSizesPerTrial
    custom_packet_sizes: List[NonNegativeInt]
    fixed_packet_start_size: NonNegativeInt
    fixed_packet_end_size: NonNegativeInt
    fixed_packet_step_size: NonNegativeInt
    # VaryingSizesPerTrial
    varying_packet_min_size: NonNegativeInt
    varying_packet_max_size: NonNegativeInt
    mixed_sizes_weights: List[NonNegativeInt]
    mixed_length_config: FrameSizesOptions

    def check_mixed_weights_valid(self) -> None:
        if self.packet_size_type == PacketSizeType.MIX:
            if len(self.mixed_sizes_weights) != len(MIXED_DEFAULT_WEIGHTS):
                raise exceptions.MixWeightsNotEnough(len(MIXED_DEFAULT_WEIGHTS))
            if sum(self.mixed_sizes_weights) != 100:
                raise exceptions.MixWeightsSumError(sum(self.mixed_sizes_weights))

    @property
    def mixed_packet_length(self) -> List[int]:
        mix_size_lengths = self.mixed_length_config.dict()
        return [
            DEFAULT_MIXED_PACKET_SIZE[index]
            if not (mix_size_lengths.get(f"field_{index}", 0))
            else mix_size_lengths.get(f"field_{index}", 0)
            for index in range(len(DEFAULT_MIXED_PACKET_SIZE))
        ]

    @property
    def mixed_average_packet_size(self) -> int:
        weighted_size = 0.0
        for index, size in enumerate(self.mixed_packet_length):
            weight = self.mixed_sizes_weights[index]
            weighted_size += size * weight
        return int(round(weighted_size / 100.0))

    @property
    def packet_size_list(self) -> Iterable[int]:
        packet_size_type = self.packet_size_type
        if packet_size_type == PacketSizeType.IETF_DEFAULT:
            return DEFAULT_IETF_PACKET_SIZE
        elif packet_size_type == PacketSizeType.CUSTOM_SIZES:
            return list(sorted(self.custom_packet_sizes))
        elif packet_size_type == PacketSizeType.MIX:
            return [self.mixed_average_packet_size]

        elif packet_size_type == PacketSizeType.RANGE:
            return list(range(
                self.fixed_packet_start_size,
                self.fixed_packet_end_size + self.fixed_packet_step_size,
                self.fixed_packet_step_size,
            ))

        elif packet_size_type in (PacketSizeType.INCREMENTING, PacketSizeType.BUTTERFLY, PacketSizeType.RANDOM):
            return [(self.varying_packet_min_size + self.varying_packet_max_size) // 2]
        else:
            raise ValueError(packet_size_type.value)

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.check_mixed_weights_valid()


class GeneralTestConfiguration(BaseModel):
    frame_sizes: FrameSizeConfiguration
    rate_definition: RateDefinition
    latency_mode: LatencyMode
    toggle_sync_state: bool
    sync_off_duration: int
    sync_on_duration: int
    should_stop_on_los: bool
    port_reset_delay: int
    use_port_sync_start: bool
    port_stagger_steps: int
    use_micro_tpld_on_demand: bool
    tid_allocation_scope: TidAllocationScope
    tpld_id_controller: Any = None

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.tpld_id_controller = TPLDIDController(self.tid_allocation_scope)

    def alloc_new_tpld_id(self, source_port, destination_port) -> int:
        assert self.tpld_id_controller
        return self.tpld_id_controller.alloc_new_tpld_id(source_port, destination_port)



class PortIdentity(BaseModel):
    tester_id: str
    chassis_id: str
    module_index: NonNegativeInt
    port_index: NonNegativeInt

    @property
    def name(self) -> str:
        return f"P-{self.tester_id}-{self.module_index}-{self.port_index}"

    @property
    def identity(self) -> str:
        return f"{self.tester_id}-{self.module_index}-{self.port_index}"


def hex_string_to_binary_string(hex: str) -> "BinaryString":
    """binary string with leading zeros
    """
    hex = hex.lower().replace('0x', '')
    return BinaryString(bin(int('1' + hex, 16))[3:])


class MacAddress(str):
    def to_hexstring(self):
        return self.replace(":", "").replace("-", "").upper()

    def first_three_bytes(self):
        return self.replace(":", "").replace("-", "").upper()[:6]

    def partial_replace(self, new_mac_address: "MacAddress"):
        return MacAddress(f"{new_mac_address}{self[len(new_mac_address):]}".lower())

    @classmethod
    def from_base_address(cls, base_address: str):
        prefix = [hex(int(i)) for i in base_address.split(",")]
        return cls("".join([p.replace("0x", "").zfill(2).upper() for p in prefix]))

    @property
    def is_empty(self) -> bool:
        return not self or self == MacAddress("00:00:00:00:00:00")

    def to_bytearray(self) -> bytearray:
        return bytearray(bytes.fromhex(self.to_hexstring()))

    def to_binary_string(self) -> "BinaryString":
        return hex_string_to_binary_string(self.replace(':', ''))


class PortPair(BaseModel):
    west: str
    east: str

    @property
    def names(self) -> Tuple[str, str]:
        return self.west, self.east


class ResultData(BaseModel):
    result: List


class TestStatusModel(BaseModel):
    status: const.TestStatus = const.TestStatus.STOP


class TxStream(BaseModel):
    tpld_id: int
    packet: int = 0
    pps: int = 0


class RxTPLDId(BaseModel):
    packet: int = 0
    pps: int = 0


@dataclass
class PortLatency:
    check_value_ = True
    average_: Dict[int, Decimal] = field(default_factory=dict)
    minimum_: Decimal = Decimal(0)
    maximum_: Decimal = Decimal(0)

    def _pre_process(self, value: Decimal) -> Decimal:
        value = round(value / Decimal(1000), 3)
        if self.check_value_ and not value > ~sys.maxsize:
            value = Decimal(0)
        return value

    @property
    def minimum(self) -> Decimal:
        return self.minimum_

    @minimum.setter
    def minimum(self, value: Decimal) -> None:
        if value := self._pre_process(value):
            self.minimum_ = min(value, self.minimum_) if self.minimum_ else value

    @property
    def maximum(self) -> Decimal:
        return self.maximum_

    @maximum.setter
    def maximum(self, value: Decimal) -> None:
        self.maximum_ = max(self._pre_process(value), self.maximum_)

    @property
    def average(self) -> Decimal:
        return Decimal(fmean(self.average_.values()))

    def set_average(self, tpld_id: int, value: Decimal) -> None:
        if value := self._pre_process(value):
            self.average_[tpld_id] = value


class PortJitter(PortLatency):
    check_value_ = False


class StatisticsData(BaseModel):
    tx_packet: int = 0
    tx_bps_l1: int = 0
    tx_bps_l2: int = 0
    tx_pps: int = 0
    rx_packet: int = 0
    rx_bps_l1: int = 0
    rx_bps_l2: int = 0
    rx_pps: int = 0
    loss: int = 0
    loss_percent: Decimal = Decimal(0)
    fcs: int = 0
    flood: int = 0  # no tpld
    per_tx_stream: Dict[int, TxStream] = {}
    per_rx_tpld_id: Dict[int, RxTPLDId] = {}
    latency: PortLatency = PortLatency()
    jitter: PortJitter = PortJitter()

    def __add__(self, other: "StatisticsData") -> "StatisticsData":
        for name, value in self:
            if isinstance(value, Number):
                setattr(self, name, value + attrgetter(name)(other))
        return self


class CurrentIterProps(NamedTuple):
    iteration_number: int
    packet_size: int


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

MdixPorts = (
    ports.POdin1G3S6P,
    ports.POdin1G3S6P_b,
    ports.POdin1G3S6PE,
    ports.POdin1G3S2PT,
)


class IPv4Address(OldIPv4Address):
    def to_hexstring(self) -> str:
        return self.packed.hex().upper()

    def last_three_bytes(self) -> str:
        return self.to_hexstring()[-6:]

    def to_bytearray(self) -> bytearray:
        return bytearray(self.packed)

    def network(self, prefix: int) -> IPv4Network:
        return IPv4Network(f"{self}/{prefix}", strict=False)

    @property
    def is_empty(self) -> bool:
        return not self or self == IPv4Address("0.0.0.0")

    def to_binary_string(self) -> "BinaryString":
        return hex_string_to_binary_string(self.to_hexstring())


class IPv6Address(OldIPv6Address):
    def to_hexstring(self) -> str:
        return self.packed.hex().upper()

    def last_three_bytes(self) -> str:
        return self.to_hexstring()[-6:]

    def to_bytearray(self) -> bytearray:
        return bytearray(self.packed)

    @property
    def is_empty(self) -> bool:
        return not self or self == IPv6Address("::")

    def network(self, prefix: int) -> IPv6Network:
        return IPv6Network(f"{self}/{prefix}", strict=False)

    def to_binary_string(self) -> "BinaryString":
        return hex_string_to_binary_string(self.to_hexstring())

class Prefix(int):
    def to_ipv4(self) -> IPv4Address:
        return IPv4Address(int(self * "1" + (32 - self) * "0", 2))



@dataclass
class AddressCollection:
    smac: MacAddress
    dmac: MacAddress
    src_ipv4_addr: IPv4Address
    dst_ipv4_addr: IPv4Address
    src_ipv6_addr: IPv6Address
    dst_ipv6_addr: IPv6Address

class IPV6AddressProperties(BaseModel):
    address: IPv6Address | str
    routing_prefix: Prefix | int = Prefix(24)
    public_address: IPv6Address | str
    public_routing_prefix: Prefix|int = Prefix(24)
    gateway: IPv6Address|str
    remote_loop_address: IPv6Address|str
    ip_version: IPVersion = IPVersion.IPV6

    @property
    def network(self) -> IPv6Network:
        return IPv6Network(f"{self.address}/{self.routing_prefix}", strict=False)

    @field_validator("address", "public_address", "gateway", "remote_loop_address", mode="before")
    def set_address(cls, v) -> IPv6Address:
        return IPv6Address(v)

    @field_validator("routing_prefix", "public_routing_prefix", mode="before")
    def set_prefix(cls, v) -> Prefix:
        return Prefix(v)

    @property
    def dst_addr(self):
        return self.public_address if not self.public_address.is_empty else self.address


class IPV4AddressProperties(BaseModel):
    address: IPv4Address|str
    routing_prefix: Prefix|int = Prefix(24)
    public_address: IPv4Address|str
    public_routing_prefix: Prefix|int = Prefix(24)
    gateway: IPv4Address|str
    remote_loop_address: IPv4Address|str
    ip_version: IPVersion = IPVersion.IPV4

    @property
    def network(self) -> "IPv4Network":
        return IPv4Network(f"{self.address}/{self.routing_prefix}", strict=False)

    @staticmethod
    def is_ip_zero(ip_address: IPv4Address) -> bool:
        return ip_address == IPv4Address("0.0.0.0") or (not ip_address)

    @field_validator("address", "public_address", "gateway", "remote_loop_address", mode="before")
    def set_address(cls, v):
        return IPv4Address(v)

    @field_validator("routing_prefix", "public_routing_prefix", mode="before")
    def set_prefix(cls, v):
        return Prefix(v)

    @property
    def dst_addr(self) -> Union["IPv4Address", str]:
        return self.public_address if not self.public_address.is_empty else self.address




class PortConfiguration(BaseModel):
    port_slot: str
    port_config_slot: str = ""
    peer_config_slot: str
    port_group: PortGroup
    port_speed_mode: PortSpeedStr

    # PeerNegotiation
    auto_neg_enabled: bool
    anlt_enabled: bool
    mdi_mdix_mode: MdiMdixMode
    broadr_reach_mode: BRRModeStr

    # PortRateCap
    port_rate_cap_enabled: bool
    port_rate_cap_value: float
    port_rate_cap_profile: PortRateCapProfile
    port_rate_cap_unit: PortRateCapUnit

    # PhysicalPortProperties
    interframe_gap: NonNegativeInt
    speed_reduction_ppm: NonNegativeInt
    pause_mode_enabled: bool
    latency_offset_ms: int  # QUESTION: can be negative?
    fec_mode: FECModeStr

    profile_id: str

    ip_gateway_mac_address: MacAddress | str
    reply_arp_requests: bool
    reply_ping_requests: bool
    remote_loop_mac_address: MacAddress | str
    ipv4_properties: IPV4AddressProperties
    ipv6_properties: IPV6AddressProperties
    item_id: str

    # Computed Properties
    is_tx_port: bool = True
    is_rx_port: bool = True
    port_rate: Decimal = Decimal("0.0")
    profile: ProtocolSegmentProfileConfig = ProtocolSegmentProfileConfig()

    @property
    def ip_properties(self) -> Union[IPV4AddressProperties, IPV6AddressProperties]:
        if self.profile.protocol_version.is_ipv6:
            return self.ipv6_properties
        return self.ipv4_properties

    class Config:
        underscore_attrs_are_private = True

class TestSuiteConfiguration2889(BaseModel):
    ports_configuration: Dict[str, PortConfiguration]
    protocol_segments: Dict[str, ProtocolSegmentProfileConfig]
    general_test_configuration: GeneralTestConfiguration
    test_suites_configuration: TestSuitesConfiguration

    @property
    def enabled_test_suit_config_list(self) -> Generator[UnionTestSuitConfiguration, None, None]:
        for _, test_type_config in self.test_suites_configuration:
            if test_type_config and test_type_config.enabled:
                yield test_type_config

    def check_port_config(self) -> None:
        if len(self.ports_configuration) < 2:
            raise exceptions.PortConfigNotEnough(2)

    def check_tests_enabled(self) -> None:
        if len(list(self.enabled_test_suit_config_list)) == 0:
            raise exceptions.TestTypeNotEnough()

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.check_port_config()
        self.check_tests_enabled()

        for port_conf in self.ports_configuration.values():
            port_conf.profile = self.protocol_segments[port_conf.profile_id].copy(deep=True)