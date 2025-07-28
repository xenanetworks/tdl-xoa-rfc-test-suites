from typing import Union
from pydantic import BaseModel, field_validator

from ..utils.constants import IPVersion, IgmpVersion, TestTopology, TrafficDirection
from .protocol_segments import ProtocolSegmentProfileConfig
from ..utils.field import NewIPv4Address, NewIPv6Address


class UcFlowDefinition(BaseModel):
    comment: str
    topology: TestTopology
    direction: TrafficDirection
    stream_definition: ProtocolSegmentProfileConfig


class McDefinition(BaseModel):
    comments: str
    igmp_version: IgmpVersion
    igmp_join_interval: int
    igmp_leave_interval: int
    use_igmp_shaping: bool
    use_igmp_source_address: bool
    force_leave_to_all_routers_group: bool
    max_igmp_frame_rate: float
    mc_ip_v4_start_address: NewIPv4Address
    mc_ip_v6_start_address: NewIPv6Address
    mc_address_step_value: int
    stream_definition: ProtocolSegmentProfileConfig
    uc_flow_def: UcFlowDefinition
    item_id: str

    @property
    def mc_ip_start_address(self) -> Union[NewIPv4Address, NewIPv6Address]:
        return (
            self.mc_ip_v4_start_address
            if self.stream_definition.ip_version == IPVersion.IPV4
            else self.mc_ip_v6_start_address
        )

    @field_validator("mc_ip_v4_start_address", mode="before")
    def set_v4_address(cls, v):
        return NewIPv4Address(v)

    @field_validator("mc_ip_v6_start_address", mode="before")
    def set_v6_address(cls, v):
        return NewIPv6Address(v)
