from ipaddress import (
    IPv4Network,
    IPv6Network,
    ip_network,
    ip_address,
    IPv4Address as OriginIPv4Address,
    IPv6Address as OriginIPv6Address,
)
from typing import Union, Optional
from pydantic import BaseModel, field_validator, Field
from ..utils import constants as const
from ..utils.field import MacAddress, IPv4Address, IPv6Address, Prefix
from .m_protocol_segment import ProtocolSegmentProfileConfig


class IPAddressProperties(BaseModel, arbitrary_types_allowed=True):
    # These will be converted to IPv4Address/IPv6Address by validators
    address: Union[IPv4Address, IPv6Address] = IPv4Address("0.0.0.0")
    routing_prefix: Prefix = Prefix(24)
    public_address: Union[IPv4Address, IPv6Address] = IPv4Address("0.0.0.0")
    public_routing_prefix: Prefix = Prefix(24)
    gateway: Union[IPv4Address, IPv6Address] = IPv4Address("0.0.0.0")
    remote_loop_address: Union[IPv4Address, IPv6Address] = IPv4Address("0.0.0.0")

    @field_validator("address", "public_address", "gateway", "remote_loop_address", mode="before")
    def set_address(
        cls, value: Union[str, "IPv4Address", "IPv6Address"]
    ) -> Union["IPv4Address", "IPv6Address"]:
        if isinstance(value, str):
            address = ip_address(value)
            return (
                IPv4Address(address)
                if isinstance(address, OriginIPv4Address)
                else IPv6Address(address)
            )
        return value
    
    @property
    def network(self) -> Union["IPv4Network", "IPv6Network"]:
        return ip_network(f"{self.address}/{self.routing_prefix}", strict=False)
    
    @field_validator("routing_prefix", "public_routing_prefix", mode="before")
    def set_prefix(cls, value: int) -> Prefix:
        return Prefix(value)

    @property
    def dst_addr(self) -> Union["IPv4Address", "IPv6Address"]:
        return self.public_address if not self.public_address.is_empty else self.address

class PortConfiguration(BaseModel, arbitrary_types_allowed=True):
    port_slot: int
    peer_slot: Optional[int]
    port_group: const.PortGroup
    port_speed_mode: const.PortSpeedStr
    ip_address: Optional[IPAddressProperties]
    ip_gateway_mac_address: MacAddress
    reply_arp_requests: bool
    reply_ping_requests: bool
    remote_loop_mac_address: MacAddress
    inter_frame_gap: float
    speed_reduction_ppm: int = Field(ge=0)
    pause_mode_enabled: bool
    latency_offset_ms: int  # QUESTION: can be negative?
    fec_mode: const.FECModeStr
    # PortRateCap
    port_rate_cap_enabled: bool
    port_rate_cap_value: float
    port_rate_cap_profile: const.PortRateCapProfile
    port_rate_cap_unit: const.PortRateCapUnit

    # PeerNegotiation
    auto_neg_enabled: bool
    anlt_enabled: bool
    mdi_mdix_mode: const.MdiMdixMode
    broadr_reach_mode: const.BRRModeStr

    # PhysicalPortProperties
    protocol_segment_profile_id: str

    _profile: ProtocolSegmentProfileConfig = ProtocolSegmentProfileConfig()
    # _port_config_slot: str = ""
    _is_tx: bool = True
    _is_rx: bool = True

    @field_validator("ip_gateway_mac_address", mode="before")
    def set_ip_gateway_mac_address(cls, value: str) -> "MacAddress":
        return MacAddress(value)

    @property
    def is_tx_port(self) -> bool:
        return self._is_tx

    def set_tx_port(self, value: bool) -> None:
        self._is_tx = value

    @property
    def is_rx_only(self) -> bool:
        return self.is_rx_port and not self.is_tx_port

    @property
    def is_rx_port(self) -> bool:
        return self._is_rx

    def set_rx_port(self, value: bool) -> None:
        self._is_rx = value

    @property
    def is_loop(self) -> bool:
        return self.port_slot == self.peer_slot

    def is_pair(self, peer_config: "PortConfiguration") -> bool:
        return peer_config.peer_slot == self.port_slot

    # def set_name(self, name: str) -> None:
    #     self._port_config_slot = name

    @property
    def port_rate(self) -> float:
        return self.port_rate_cap_value * self.port_rate_cap_unit.scale()

    @property
    def profile(self) -> "ProtocolSegmentProfileConfig":
        return self._profile

    def set_profile(self, value: "ProtocolSegmentProfileConfig") -> None:
        self._profile = value
