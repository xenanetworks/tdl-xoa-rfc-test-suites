import re
from enum import Enum
from random import randint
from typing import Any, Callable, Dict, Generator, List, Optional, Annotated
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from pydantic_core import CoreSchema, core_schema
from pydantic import GetCoreSchemaHandler, TypeAdapter
from xoa_driver.enums import ProtocolOption, ModifierAction
from ..utils.exceptions import ModifierRangeError

class BinaryString(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.no_info_after_validator_function(cls, handler(str))
    
    # @classmethod
    # def __get_validators__(cls) -> Generator[Callable, None, None]:
    #     yield cls.validate

    # @classmethod
    # def validate(cls, v: str) -> "BinaryString":
    #     if not re.search("^[01]+$", v):
    #         raise ValueError("binary string must zero or one")
    #     return cls(v)

    @property
    def is_all_zero(self) -> bool:
        return bool(re.search("^[0]+$", self))


class ModifierActionOption(Enum):
    INC = "increment"
    DEC = "decrement"
    RANDOM = "random"

    def to_xmp(self) -> "ModifierAction":
        return ModifierAction[self.name]


class PortProtocolVersion(Enum):
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


class SegmentType(Enum):
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
    RTP = "rtp"
    RTCP = "rtcp"
    STP = "stp"
    SCTP = "sctp"
    MACCTRL = "macctrl"
    MPLS = "mpls"
    PBBTAG = "pbbtag"
    FCOE = "fcoe"
    FC = "fc"
    FCOETAIL = "fcoetail"
    IGMPV3L0 = "igmpv3l0"
    IGMPV3L1 = "igmpv3l1"
    UDPCHECK = "udpcheck"
    IGMPV2 = "igmpv2"
    GRE_NOCHECK = "gre_nocheck"
    GRE_CHECK = "gre_check"
    TCPCHECK = "tcp_check"
    IGMPV1 = "igmpv1"
    VXLAN = "vxlan"
    NVGRE = "nvgre"
    # Generate RAW form 1...64 bytes
    _ignore_ = "SegmentType i"
    SegmentType = vars()
    for i in range(1, 65):
        SegmentType[f"RAW_{i}"] = f"raw_{i}"  # type: ignore

    @property
    def is_raw(self) -> bool:
        if isinstance(self.value, str):
            return self.value.lower().startswith("raw")
        return False

    @property
    def raw_length(self) -> int:
        if not self.is_raw:
            return 0
        if isinstance(self.value, str):
            return int(self.value.split("_")[-1])
        return 0

    def to_xmp(self) -> "ProtocolOption":
        return ProtocolOption[self.name]

    @property
    def is_ethernet(self) -> bool:
        return self == SegmentType.ETHERNET

    @property
    def is_ipv4(self) -> bool:
        return self == SegmentType.IP

    @property
    def is_ipv6(self) -> bool:
        return self == SegmentType.IPV6


class ValueRange(BaseModel):
    start_value: int
    step_value: int = Field(gt=0)
    stop_value: int
    action: ModifierActionOption
    restart_for_each_port: bool
    _current_count: int = 0  # counter start from 0

    def reset(self) -> None:
        self._current_count = 0

    def set_current_count(self, new_value: int) -> None:
        self._current_count = new_value

    @property
    def current_count(self) -> int:
        return self._current_count

    def get_current_value(self) -> int:
        if self.action == ModifierActionOption.INC:
            current_value = self.start_value + self.current_count * self.step_value
            if current_value > self.stop_value:
                current_value = self.start_value
                self.reset()
        elif self.action == ModifierActionOption.DEC:
            current_value = self.start_value - self.current_count * self.step_value
            if current_value < self.stop_value:
                current_value = self.start_value
                self.reset()
        else:
            boundary = [self.start_value, self.stop_value]
            current_value = randint(min(boundary), max(boundary))
        self.set_current_count(self.current_count + 1)
        return current_value


class HWModifier(BaseModel):
    start_value: int
    step_value: int = Field(gt=0)
    stop_value: Annotated[int, Field(validate_default=True)]
    repeat: int
    offset: int
    action: ModifierActionOption
    mask: str  # hex string as 'FFFF'
    _byte_segment_position: int = 0  # byte position of all header segments

    @field_validator('stop_value', mode="before")
    def validate_modifier_value(cls, value: int, info: ValidationInfo):
        start_value = info.data['start_value']
        step_value = info.data['step_value']
        if (value - start_value) % step_value:
            raise ModifierRangeError(start_value, value, step_value)
        return value


    def set_byte_segment_position(self, position: int) -> None:
        self._byte_segment_position = position

    @property
    def byte_segment_position(self) -> int:
        return self._byte_segment_position


class SegmentField(BaseModel):
    name: str
    value: BinaryString
    bit_length: int
    hw_modifier: Optional[HWModifier]
    value_range: Optional[ValueRange]

    class Config:
        validate_assignment = True

    def __init__(self, **data: Dict[str, Any]) -> None:
        super().__init__(**data)
        self.check_value_range()

    def check_value_range(self) -> None:
        if not self.value_range:
            return
        max_val = max(self.value_range.start_value, self.value_range.stop_value)
        theory_max = pow(2, self.bit_length)
        if max_val >= theory_max:  # why not fvr.stop_value >= can_max?
            raise Exception("invalid value range", self.name, theory_max)

    def prepare(self) -> "BinaryString":
        if not self.value_range:
            return self.value

        value_range_str = bin(self.value_range.get_current_value())[2:].zfill(
            self.bit_length
        )
        return BinaryString(value_range_str)

    def set_field_value(self, new_value: "BinaryString") -> None:
        if len(new_value) != self.bit_length:
            raise ValueError(
                f"new value length {len(new_value)} not match field length {self.bit_length} ({self.name})"
            )
        self.value = new_value

    @property
    def is_all_zero(self) -> bool:
        return self.value.is_all_zero


class ProtocolSegment(BaseModel):
    type: SegmentType
    fields: List[SegmentField]
    checksum_offset: Optional[int]

    def __init__(self, **data: Dict[str, Any]) -> None:
        super().__init__(**data)

    @property
    def hw_modifiers(self) -> Generator["HWModifier", None, None]:
        return (f.hw_modifier for f in self.fields if f.hw_modifier)

    @property
    def value_ranges(self) -> Generator["ValueRange", None, None]:
        return (f.value_range for f in self.fields if f.value_range)

    @field_validator("checksum_offset")
    def is_digit(cls, value: int) -> int:
        if value and not isinstance(value, int):
            raise ValueError("checksum offset must digit")
        return value

    def __wrap_add_16(self, data: bytearray, offset_num: int) -> bytearray:
        checksum = 0
        data[offset_num + 0] = 0
        data[offset_num + 1] = 0
        for i in range(0, len(data), 2):
            w = (data[i + 0] << 8) + data[i + 1]
            checksum += w
            if checksum > 0xFFFF:
                checksum = (1 + checksum) & 0xFFFF  # add carry back in as lsb
        data[offset_num + 0] = 0xFF + 1 + (~(checksum >> 8))
        data[offset_num + 1] = 0xFF + 1 + (~(checksum & 0xFF))
        return data

    def prepare(self) -> bytearray:
        result = ""
        for f in self.fields:
            field_binary_string = f.prepare()
            result += field_binary_string
        result = int(result, 2).to_bytes((len(result) + 7) // 8, byteorder="big")
        result = bytearray(result)
        if self.checksum_offset:
            result = self.__wrap_add_16(result, self.checksum_offset)
        return result

    def __getitem__(self, field_name: str) -> "SegmentField":
        for field in self.fields:
            if field.name == field_name:
                return field
        raise KeyError(field_name)

    def __setitem__(self, field_name: str, new_value: "BinaryString") -> None:
        self[field_name].set_field_value(new_value)

    @property
    def bit_length(self) -> int:
        return sum(f.bit_length for f in self.fields)

    @property
    def modifier_count(self) -> int:
        return sum(1 for f in self.fields if f.hw_modifier)


class ProtocolSegmentProfileConfig(BaseModel):
    id: str = ""  
    segments: List[ProtocolSegment] = []

    def __getitem__(self, segment_type: "SegmentType") -> List["ProtocolSegment"]:
        return [
            segment
            for segment in self.segments
            if segment.type == segment_type
        ]

    def prepare(self) -> bytearray:
        result = bytearray()
        for s in self.segments:
            result.extend(s.prepare())
        return result

    def get_segment(
        self, segment_type: "SegmentType", index: int = 0
    ) -> "ProtocolSegment":
        return self[segment_type][index]

    @property
    def protocol_version(self) -> "PortProtocolVersion":
        v = PortProtocolVersion.ETHERNET
        for i in self.segments:
            if i.type == SegmentType.IPV6:
                v = PortProtocolVersion.IPV6
                break
            elif i.type == SegmentType.IP:
                v = PortProtocolVersion.IPV4
                break
        return v

    @property
    def segment_id_list(self) -> List["ProtocolOption"]:
        return [h.type.to_xmp() for h in self.segments]

    @property
    def packet_header_length(self) -> int:
        """byte header length for convenient use with xoa-driver"""
        return sum(hs.bit_length for hs in self.segments) // 8

    @property
    def modifier_count(self) -> int:
        return sum(hs.modifier_count for hs in self.segments)

    def calc_segment_position(self) -> None:
        total_bit_length = 0
        for segment in self.segments:
            for field in segment.fields:
                if modifier := field.hw_modifier:
                    modifier.set_byte_segment_position(
                        (total_bit_length // 8) + modifier.offset
                    )
                total_bit_length += field.bit_length

    def __init__(self, **data: Dict[str, Any]) -> None:
        super().__init__(**data)
        self.calc_segment_position()
