from pydantic import BaseModel, NonNegativeInt
from ..utils.errors import IpEmpty, NoIpSegment, NoRole

from ..utils.constants import (
    BRRMode,
    IPVersion,
    MdiMdixMode,
    PortRateCapProfile,
    MulticastRole,
    PortRateCapUnit,
    PortSpeedMode,
    ProtocolOption,
)
from ..utils.field import MacAddress, NewIPv4Address, NewIPv6Address, Prefix
from .protocol_segments import ProtocolSegmentProfileConfig
from pydantic import validator


class IPV6AddressProperties(BaseModel):
    address: NewIPv6Address = NewIPv6Address("::")
    routing_prefix: Prefix = Prefix(24)
    public_address: NewIPv6Address = NewIPv6Address("::")
    public_routing_prefix: Prefix = Prefix(24)
    gateway: NewIPv6Address = NewIPv6Address("::")
    remote_loop_address: NewIPv6Address = NewIPv6Address("::")
    ip_version: IPVersion = IPVersion.IPV6

    @staticmethod
    def is_ip_zero(ip_address: NewIPv6Address) -> bool:
        return ip_address == NewIPv6Address("::") or (not ip_address)

    @validator("address", "public_address", "gateway", "remote_loop_address", pre=True)
    def set_address(cls, v):
        return NewIPv6Address(v)

    @validator("routing_prefix", "public_routing_prefix", pre=True)
    def set_prefix(cls, v):
        return Prefix(v)

    @property
    def usable_dest_ip_address(self) -> NewIPv6Address:
        if not self.public_address.is_empty:
            return self.public_address
        return self.address


class IPV4AddressProperties(BaseModel):
    address: NewIPv4Address = NewIPv4Address("0.0.0.0")
    routing_prefix: Prefix = Prefix(24)
    public_address: NewIPv4Address = NewIPv4Address("0.0.0.0")
    public_routing_prefix: Prefix = Prefix(24)
    gateway: NewIPv4Address = NewIPv4Address("0.0.0.0")
    remote_loop_address: NewIPv4Address = NewIPv4Address("0.0.0.0")
    ip_version: IPVersion = IPVersion.IPV4

    @staticmethod
    def is_ip_zero(ip_address: NewIPv4Address) -> bool:
        return ip_address == NewIPv4Address("0.0.0.0") or (not ip_address)

    @validator("address", "public_address", "gateway", "remote_loop_address", pre=True)
    def set_address(cls, v):
        return NewIPv4Address(v)

    @validator("routing_prefix", "public_routing_prefix", pre=True)
    def set_prefix(cls, v):
        return Prefix(v)

    @property
    def usable_dest_ip_address(self) -> NewIPv4Address:
        if not self.public_address.is_empty:
            return self.public_address
        return self.address


class PortConfiguration(BaseModel):
    port_slot: str
    port_config_slot: str = ""
    # port_group: PortGroup
    port_speed_mode: PortSpeedMode

    # PeerNegotiation
    auto_neg_enabled: bool
    anlt_enabled: bool
    mdi_mdix_mode: MdiMdixMode
    broadr_reach_mode: BRRMode

    # PortRateCap
    port_rate_cap_enabled: bool
    port_rate_cap_value: float
    port_rate_cap_profile: PortRateCapProfile
    port_rate_cap_unit: PortRateCapUnit

    # PhysicalPortProperties
    inter_frame_gap: NonNegativeInt
    speed_reduction_ppm: NonNegativeInt
    pause_mode_enabled: bool
    latency_offset_ms: int  # QUESTION: can be negative?
    fec_mode: bool

    ip_gateway_mac_address: MacAddress
    reply_arp_requests: bool
    reply_ping_requests: bool
    remote_loop_mac_address: MacAddress
    ipv4_properties: IPV4AddressProperties
    ipv6_properties: IPV6AddressProperties

    is_tx_port: bool = True
    is_rx_port: bool = True

    profile: ProtocolSegmentProfileConfig
    multicast_role: MulticastRole

    @validator("ip_gateway_mac_address", "remote_loop_mac_address", pre=True)
    def validate_mac(cls, v):
        return MacAddress(v)

    @validator("multicast_role", pre=True)
    def validate_multicast_role(cls, v, values):
        if v == MulticastRole.UNDEFINED:
            raise NoRole(values["port_slot"])
        return v

    @validator("profile")
    def validate_ip(cls, v, values):
        has_ip_segment = False
        segment_types = [i.type for i in v.header_segments]
        if ProtocolOption.IPV4 in segment_types:
            has_ip_segment = True
            if values["ipv4_properties"].address in {NewIPv4Address("0.0.0.0"), ""}:
                raise IpEmpty(values["port_slot"], "IPv4")
        elif ProtocolOption.IPV6 in segment_types:
            has_ip_segment = True
            if values["ipv6_properties"].address in {NewIPv6Address("::"), ""}:
                raise IpEmpty(values["port_slot"], "IPv6")
        if not has_ip_segment:
            raise NoIpSegment(values["port_slot"])

        return v

    def change_ip_gateway_mac_address(self, gateway_mac: MacAddress):
        self.ip_gateway_mac_address = gateway_mac

    @property
    def cap_port_rate(self) -> float:
        return self.port_rate_cap_unit.scale * self.port_rate_cap_value
