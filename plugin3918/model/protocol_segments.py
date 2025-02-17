from typing import List, Optional
from pydantic import validator, BaseModel, NonNegativeInt
from xoa_driver.enums import ProtocolOption as XProtocolOption
from ..utils.errors import NoIpSegment
from ..utils.constants import (
    IPVersion,
    PayloadType,
    ProtocolOption,
    RateType,
)


class FieldDefinition(BaseModel):
    name: str
    bit_length: int
    display_type: Optional[str]
    default_value: Optional[str]
    value_map_name: Optional[str]
    is_reserved: Optional[bool]
    bit_offset: int = 0
    byte_offset: int = 0
    bit_padding: int = 0

    @property
    def byte_length(self) -> int:
        offset = 1 if self.bit_length % 8 > 0 else 0
        byte_length = self.bit_length // 8 + offset
        return byte_length


class SegmentDefinition(BaseModel):
    name: str
    description: str
    segment_type: ProtocolOption
    enclosed_type_index: int
    checksum_offset: int
    field_definitions: List[FieldDefinition]

    class Config:
        arbitrary_types_allowed = True

    @validator("field_definitions")
    def set_field_properties(cls, v):  # FixupDependencies
        curr_bit_offset = 0
        # curr_byte_offset = 0
        for field_def in v:
            field_def.bit_offset = curr_bit_offset
            field_def.byte_offset = curr_bit_offset // 8
            field_def.bit_padding = (
                8 - (curr_bit_offset % 8) if curr_bit_offset % 8 else 0
            )

            curr_bit_offset += field_def.bit_length
        return v

    @property
    def default_value(self) -> bytearray:
        step = 8
        result = []
        modulus = len(self.default_value_bin) % step
        if modulus:
            default_value_bin = [
                0 for _ in range(step - modulus)
            ] + self.default_value_bin
        else:
            default_value_bin = self.default_value_bin
        for i in range(0, len(default_value_bin), step):
            bit_list = default_value_bin[i : i + step]
            result.append(int("".join(str(i) for i in bit_list), 2))
        return bytearray(result)

    @property
    def default_value_bin(self) -> List[int]:
        all_bits = []
        all_bits_length = 0
        for f in self.field_definitions:
            default_value = f.default_value
            all_bits_length += f.bit_length
            if default_value:
                if default_value.startswith("0x"):
                    base = 16
                elif default_value.startswith("0b"):
                    base = 2
                else:
                    base = 10
                default_list = [i for i in default_value.split(",") if i]
                each_length = f.bit_length // len(default_list)
                for i in default_list:
                    bits = bin(int(i, base)).replace("0b", "").zfill(each_length)
                    all_bits += list(int(i) for i in bits)

            else:
                bits = [0 for _ in range(f.bit_length)]
                all_bits += bits
            if all_bits_length - len(all_bits) >= 1:
                all_bits += [0 for _ in range(all_bits_length - len(all_bits))]

        return all_bits


ETHERNET_SEG = SegmentDefinition(
    name="Ethernet",
    description="Ethernet II",
    segment_type=ProtocolOption.ETHERNET,
    enclosed_type_index=2,
    checksum_offset=-1,
    field_definitions=[
        FieldDefinition(
            name="Dst MAC addr",
            bit_length=48,
            display_type="MacAddress",
            default_value="0,0,0,0,0,0",
            value_map_name=None,
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Src MAC addr",
            bit_length=48,
            display_type="MacAddress",
            default_value="0,0,0,0,0,0",
            value_map_name=None,
            is_reserved=None,
            bit_offset=48,
            byte_offset=6,
            bit_padding=0,
        ),
        FieldDefinition(
            name="EtherType",
            bit_length=16,
            display_type="Hex",
            default_value="0xff,0xff",
            value_map_name="EtherType",
            is_reserved=None,
            bit_offset=96,
            byte_offset=12,
            bit_padding=0,
        ),
    ],
)

IPV4_SEG = SegmentDefinition(
    name="IPv4",
    description="Internet Protocol v4",
    segment_type=ProtocolOption.IPV4,
    enclosed_type_index=9,
    checksum_offset=10,
    field_definitions=[
        FieldDefinition(
            name="Version",
            bit_length=4,
            display_type="Decimal",
            default_value="4",
            value_map_name=None,
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Header Length",
            bit_length=4,
            display_type="Decimal",
            default_value="5",
            value_map_name=None,
            is_reserved=None,
            bit_offset=4,
            byte_offset=0,
            bit_padding=4,
        ),
        FieldDefinition(
            name="DSCP",
            bit_length=6,
            display_type="Binary",
            default_value="0x0",
            value_map_name="DiffServTypes",
            is_reserved=None,
            bit_offset=8,
            byte_offset=1,
            bit_padding=0,
        ),
        FieldDefinition(
            name="ECN",
            bit_length=2,
            display_type="Binary",
            default_value="0x0",
            value_map_name=None,
            is_reserved=None,
            bit_offset=14,
            byte_offset=1,
            bit_padding=2,
        ),
        FieldDefinition(
            name="Total Length",
            bit_length=16,
            display_type="Decimal",
            default_value="0x00,0x14",
            value_map_name=None,
            is_reserved=None,
            bit_offset=16,
            byte_offset=2,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Identification",
            bit_length=16,
            display_type="Hex",
            default_value="0x00,0x00",
            value_map_name=None,
            is_reserved=None,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Flags",
            bit_length=3,
            display_type="Binary",
            default_value="0x00",
            value_map_name=None,
            is_reserved=None,
            bit_offset=48,
            byte_offset=6,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Fragment Offset",
            bit_length=13,
            display_type="Decimal",
            default_value="0,0",
            value_map_name=None,
            is_reserved=None,
            bit_offset=51,
            byte_offset=6,
            bit_padding=5,
        ),
        FieldDefinition(
            name="TTL",
            bit_length=8,
            display_type="Decimal",
            default_value="0x7f",
            value_map_name=None,
            is_reserved=None,
            bit_offset=64,
            byte_offset=8,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Protocol",
            bit_length=8,
            display_type="Decimal",
            default_value="0xff",
            value_map_name="IpTypes",
            is_reserved=None,
            bit_offset=72,
            byte_offset=9,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Header Checksum",
            bit_length=16,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=80,
            byte_offset=10,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Src IP Addr",
            bit_length=32,
            display_type="IpV4Address",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=96,
            byte_offset=12,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Dest IP Addr",
            bit_length=32,
            display_type="IpV4Address",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=128,
            byte_offset=16,
            bit_padding=0,
        ),
    ],
)


IGMPV1_SEG = SegmentDefinition(
    name="IGMPV1",
    description="Internet Group Mgmt Protocol v1",
    segment_type=ProtocolOption.IGMPV1,
    enclosed_type_index=-1,
    checksum_offset=2,
    field_definitions=[
        FieldDefinition(
            name="Version",
            bit_length=4,
            display_type="Hex",
            default_value="0x01",
            value_map_name=None,
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Type",
            bit_length=4,
            display_type="Hex",
            default_value="0x01",
            value_map_name="IgmpV1Types",
            is_reserved=None,
            bit_offset=4,
            byte_offset=0,
            bit_padding=4,
        ),
        FieldDefinition(
            name="(unused)",
            bit_length=8,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=True,
            bit_offset=8,
            byte_offset=1,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Checksum",
            bit_length=16,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=16,
            byte_offset=2,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Group Address",
            bit_length=32,
            display_type="IpV4Address",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
    ],
)


IGMPV2_SEG = SegmentDefinition(
    name="IGMPV2",
    description="Internet Group Mgmt Protocol v2",
    segment_type=ProtocolOption.IGMPV2,
    enclosed_type_index=-1,
    checksum_offset=2,
    field_definitions=[
        FieldDefinition(
            name="Type",
            bit_length=8,
            display_type="Hex",
            default_value="0x16",
            value_map_name="IgmpV2Types",
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Code",
            bit_length=8,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=8,
            byte_offset=1,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Checksum",
            bit_length=16,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=16,
            byte_offset=2,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Group Address",
            bit_length=32,
            display_type="IpV4Address",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
    ],
)

UDP_SEG = SegmentDefinition(
    name="UDP",
    description="User Datagram Protocol",
    segment_type=ProtocolOption.UDP,
    enclosed_type_index=-1,
    checksum_offset=-1,
    field_definitions=[
        FieldDefinition(
            name="Src Port",
            bit_length=16,
            display_type="Decimal",
            default_value=None,
            value_map_name="UdpPorts",
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Dest Port",
            bit_length=16,
            display_type="Decimal",
            default_value=None,
            value_map_name="UdpPorts",
            is_reserved=None,
            bit_offset=16,
            byte_offset=2,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Length",
            bit_length=16,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Checksum",
            bit_length=16,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=48,
            byte_offset=6,
            bit_padding=0,
        ),
    ],
)
IGMPV3_GR_SEG = SegmentDefinition(
    name="IGMPV3_GR",
    description="IGMPv3 Group Record",
    segment_type=ProtocolOption.IGMPV3_GR,
    enclosed_type_index=-1,
    checksum_offset=-1,
    field_definitions=[
        FieldDefinition(
            name="Record Type",
            bit_length=8,
            display_type="Decimal",
            default_value=None,
            value_map_name="IGMPv3GroupRecordTypes",
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Aux Data Len",
            bit_length=8,
            display_type="Decimal",
            default_value="0x00",
            value_map_name=None,
            is_reserved=None,
            bit_offset=8,
            byte_offset=1,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Number of Sources",
            bit_length=16,
            display_type="Decimal",
            default_value="0x00,0x00",
            value_map_name=None,
            is_reserved=None,
            bit_offset=16,
            byte_offset=2,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Multicast Address",
            bit_length=32,
            display_type="IpV4Address",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
    ],
)

IGMPV3_MR_SEG = SegmentDefinition(
    name="IGMPV3_MR",
    description="IGMPv3 Membership Report",
    segment_type=ProtocolOption.IGMPV3_MR,
    enclosed_type_index=-1,
    checksum_offset=2,
    field_definitions=[
        FieldDefinition(
            name="Type",
            bit_length=8,
            display_type="Hex",
            default_value="0x22",
            value_map_name=None,
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="(reserved)",
            bit_length=8,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=True,
            bit_offset=8,
            byte_offset=1,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Checksum",
            bit_length=16,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=16,
            byte_offset=2,
            bit_padding=0,
        ),
        FieldDefinition(
            name="(reserved)",
            bit_length=16,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=True,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Group Record Count",
            bit_length=16,
            display_type="Decimal",
            default_value="0x00,0x01",
            value_map_name=None,
            is_reserved=None,
            bit_offset=48,
            byte_offset=6,
            bit_padding=0,
        ),
    ],
)

IPV6_SEG = SegmentDefinition(
    name="IPv6",
    description="Internet Protocol v6",
    segment_type=ProtocolOption.IPV6,
    enclosed_type_index=4,
    checksum_offset=-1,
    field_definitions=[
        FieldDefinition(
            name="Version",
            bit_length=4,
            display_type="Decimal",
            default_value="0x06",
            value_map_name=None,
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Traffic Class",
            bit_length=8,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=4,
            byte_offset=0,
            bit_padding=4,
        ),
        FieldDefinition(
            name="Flow Label",
            bit_length=20,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=12,
            byte_offset=1,
            bit_padding=4,
        ),
        FieldDefinition(
            name="Payload Length",
            bit_length=16,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Next Header",
            bit_length=8,
            display_type="Decimal",
            default_value="59",
            value_map_name="IpTypes",
            is_reserved=None,
            bit_offset=48,
            byte_offset=6,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Hop Limit",
            bit_length=8,
            display_type="Decimal",
            default_value="255",
            value_map_name=None,
            is_reserved=None,
            bit_offset=56,
            byte_offset=7,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Src IPv6 Addr",
            bit_length=128,
            display_type="IpV6Address",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=64,
            byte_offset=8,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Dest IPv6 Addr",
            bit_length=128,
            display_type="IpV6Address",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=192,
            byte_offset=24,
            bit_padding=0,
        ),
    ],
)

ICMPV6_SEG = SegmentDefinition(
    name="ICMPv6",
    description="Internet Control Message Protocol v6",
    segment_type=ProtocolOption.ICMPV6,
    enclosed_type_index=-1,
    checksum_offset=2,
    field_definitions=[
        FieldDefinition(
            name="Type",
            bit_length=8,
            display_type="Decimal",
            default_value=None,
            value_map_name="IcmpV6Types",
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Code",
            bit_length=8,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=8,
            byte_offset=1,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Checksum",
            bit_length=16,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=16,
            byte_offset=2,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Message",
            bit_length=32,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
    ],
)

ICMP_SEG = SegmentDefinition(
    name="ICMPv4",
    description="Internet Control Message Protocol v4",
    segment_type=ProtocolOption.ICMP,
    enclosed_type_index=-1,
    checksum_offset=2,
    field_definitions=[
        FieldDefinition(
            name="Type",
            bit_length=8,
            display_type="Decimal",
            default_value=None,
            value_map_name="IcmpTypes",
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Code",
            bit_length=8,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=8,
            byte_offset=1,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Checksum",
            bit_length=16,
            display_type="Hex",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=16,
            byte_offset=2,
            bit_padding=0,
        ),
        FieldDefinition(
            name="ID",
            bit_length=16,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Sequence",
            bit_length=16,
            display_type="Decimal",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=48,
            byte_offset=6,
            bit_padding=0,
        ),
    ],
)

MLDV2_AR = SegmentDefinition(
    name="MLDV2_AR",
    description="MLDv2 Address Record",
    segment_type=ProtocolOption.MLDV2_AR,
    enclosed_type_index=-1,
    checksum_offset=-1,
    field_definitions=[
        FieldDefinition(
            name="Record Type",
            bit_length=8,
            display_type="Decimal",
            default_value=None,
            value_map_name="IGMPv3GroupRecordTypes",
            is_reserved=None,
            bit_offset=0,
            byte_offset=0,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Aux Data Len",
            bit_length=8,
            display_type="Decimal",
            default_value="0x00",
            value_map_name=None,
            is_reserved=None,
            bit_offset=8,
            byte_offset=1,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Number of Sources",
            bit_length=16,
            display_type="Decimal",
            default_value="0x00,0x00",
            value_map_name=None,
            is_reserved=None,
            bit_offset=16,
            byte_offset=2,
            bit_padding=0,
        ),
        FieldDefinition(
            name="Multicast Address",
            bit_length=128,
            display_type="IpV4Address",
            default_value=None,
            value_map_name=None,
            is_reserved=None,
            bit_offset=32,
            byte_offset=4,
            bit_padding=0,
        ),
    ],
)

DEFAULT_SEGMENT_DIC = {
    ProtocolOption.ETHERNET.value: ETHERNET_SEG,
    ProtocolOption.IPV4.value: IPV4_SEG,
    ProtocolOption.IPV6.value: IPV6_SEG,
    ProtocolOption.IGMPV1.value: IGMPV1_SEG,
    ProtocolOption.IGMPV2.value: IGMPV2_SEG,
    ProtocolOption.IGMPV3_GR: IGMPV3_GR_SEG,
    ProtocolOption.IGMPV3_MR: IGMPV3_MR_SEG,
    ProtocolOption.UDP.value: UDP_SEG,
    ProtocolOption.ICMP.value: ICMP_SEG,
    ProtocolOption.ICMPV6.value: ICMPV6_SEG,
    ProtocolOption.MLDV2_AR.value: MLDV2_AR,
}


class HwModifier(BaseModel):
    field_name: str
    mask: str
    action: str
    start_value: int
    stop_value: int
    step_value: int = 1
    repeat_count: NonNegativeInt = 1
    offset: int

    # Computed properties
    byte_offset: int = 0  # byte offset from current segment start
    position: NonNegativeInt = 0  # byte position from all segment start

    @validator("mask", pre=True, always=True)
    def set_mask(cls, v):
        v = v[2:6] if v.startswith("0x") else v
        return f"{v}"


class FieldValueRange(BaseModel):
    field_name: str
    start_value: NonNegativeInt
    stop_value: NonNegativeInt
    step_value: NonNegativeInt
    action: str
    bit_length: NonNegativeInt
    reset_for_each_port: bool

    # Computed Properties
    bit_offset: int = 0  # bit offset from current_segment start
    position: NonNegativeInt = 0  # bit position from all segment start
    current_count: NonNegativeInt = 0

    def increase_current_count(self):
        self.current_count += 1

    def reset_current_count(self):
        self.current_count = 0


class HeaderSegment(BaseModel):
    type: ProtocolOption
    segment_value: str

    @property
    def byte_length(self) -> int:
        return len(self.segment_value) // 2


class ProtocolSegmentProfileConfig(BaseModel):
    description: str = ""
    header_segments: List[HeaderSegment] = []
    payload_type: PayloadType
    payload_pattern: str
    rate_type: RateType
    rate_fraction: float
    rate_pps: float

    @property
    def packet_header_length(self) -> int:
        return (
            sum(
                [
                    len(header_segment.segment_value)
                    for header_segment in self.header_segments
                ]
            )
            // 2
        )

    @property
    def header_segment_id_list(self) -> List[XProtocolOption]:
        return [h.type.xoa for h in self.header_segments]

    @property
    def ip_version(self) -> IPVersion:
        for header_segment in self.header_segments:
            if ProtocolOption.IPV4 == header_segment.type:
                return IPVersion.IPV4
            elif ProtocolOption.IPV6 == header_segment.type:
                return IPVersion.IPV6
        raise NoIpSegment("No IP segment found")

    @property
    def segment_offset_for_ip(self) -> int:
        offset = 0
        for header_segment in self.header_segments:
            if ProtocolOption.IPV4 == header_segment.type:
                return offset
            elif ProtocolOption.IPV6 == header_segment.type:
                return offset
            offset += len(header_segment.segment_value) // 2
        return -1
