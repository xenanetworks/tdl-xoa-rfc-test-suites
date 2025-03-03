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
from pydantic import field_validator
from typing import Union


class IPV6AddressProperties(BaseModel, arbitrary_types_allowed=True):
    address: NewIPv6Address|str = NewIPv6Address("::")
    routing_prefix: Prefix|int = Prefix(24)
    public_address: NewIPv6Address|str = NewIPv6Address("::")
    public_routing_prefix: Prefix|int = Prefix(24)
    gateway: NewIPv6Address|str = NewIPv6Address("::")
    remote_loop_address: NewIPv6Address|str = NewIPv6Address("::")
    ip_version: IPVersion = IPVersion.IPV6

    @staticmethod
    def is_ip_zero(ip_address: NewIPv6Address) -> bool:
        return ip_address == NewIPv6Address("::") or (not ip_address)

    @field_validator("address", "public_address", "gateway", "remote_loop_address", mode="before")
    def set_address(cls, v):
        return NewIPv6Address(v)

    @field_validator("routing_prefix", "public_routing_prefix", mode="before")
    def set_prefix(cls, v):
        return Prefix(v)

    @property
    def usable_dest_ip_address(self) -> Union[NewIPv6Address, str]:
        if not self.public_address.is_empty:
            return self.public_address
        return self.address


class IPV4AddressProperties(BaseModel, arbitrary_types_allowed=True):
    address: NewIPv4Address|str = NewIPv4Address("0.0.0.0")
    routing_prefix: Prefix|int = Prefix(24)
    public_address: NewIPv4Address|str = NewIPv4Address("0.0.0.0")
    public_routing_prefix: Prefix|int = Prefix(24)
    gateway: NewIPv4Address|str = NewIPv4Address("0.0.0.0")
    remote_loop_address: NewIPv4Address|str = NewIPv4Address("0.0.0.0")
    ip_version: IPVersion = IPVersion.IPV4

    @staticmethod
    def is_ip_zero(ip_address: NewIPv4Address) -> bool:
        return ip_address == NewIPv4Address("0.0.0.0") or (not ip_address)

    @field_validator("address", "public_address", "gateway", "remote_loop_address", mode="before")
    def set_address(cls, v):
        return NewIPv4Address(v)

    @field_validator("routing_prefix", "public_routing_prefix", mode="before")
    def set_prefix(cls, v):
        return Prefix(v)

    @property
    def usable_dest_ip_address(self) -> Union[NewIPv4Address, str]:
        if not self.public_address.is_empty:
            return self.public_address
        return self.address


class PortConfiguration(BaseModel, arbitrary_types_allowed=True):
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

    ip_gateway_mac_address: MacAddress|str
    reply_arp_requests: bool
    reply_ping_requests: bool
    remote_loop_mac_address: MacAddress|str
    ipv4_properties: IPV4AddressProperties
    ipv6_properties: IPV6AddressProperties

    is_tx_port: bool = True
    is_rx_port: bool = True

    profile: ProtocolSegmentProfileConfig
    multicast_role: MulticastRole

    @field_validator("ip_gateway_mac_address", "remote_loop_mac_address", mode="before")
    def validate_mac(cls, v):
        return MacAddress(v)

    @field_validator("multicast_role", mode="before")
    def validate_multicast_role(cls, v, values):
        if v == MulticastRole.UNDEFINED:
            raise NoRole(values["port_slot"])
        return v

    @field_validator("profile")
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
