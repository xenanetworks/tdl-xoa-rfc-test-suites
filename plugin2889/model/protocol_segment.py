import re
from typing import List, Optional
from pydantic import BaseModel
from pydantic.class_validators import validator
from xoa_driver.enums import ProtocolOption, ModifierAction
from plugin2889.const import Enum


class BinaryString(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v) -> "BinaryString":
        if not re.search("^[01]+$", v):
            raise ValueError('binary string must zero or one')
        return cls(v)

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
    IPV4 = "ipv4"
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

    @property
    def is_raw(self) -> bool:
        return self.value.lower().startswith("raw")

    @property
    def raw_length(self) -> int:
        if not self.is_raw:
            return 0
        return int(self.value.split("_")[-1])

    def to_xmp(self) -> "ProtocolOption":
        name = 'IP' if self.name == 'IPV4' else self.name
        return ProtocolOption[name]

    @property
    def is_ethernet(self) -> bool:
        return self == SegmentType.ETHERNET

    @property
    def is_ipv4(self) -> bool:
        return self == SegmentType.IPV4

    @property
    def is_ipv6(self) -> bool:
        return self == SegmentType.IPV6


class SegmentField(BaseModel):
    name: str
    value: BinaryString
    bit_length: int

    class Config:
        validate_assignment = True

    def prepare(self) -> BinaryString:
        return self.value

    def set_field_value(self, new_value: BinaryString) -> None:
        if len(new_value) != self.bit_length:
            raise ValueError(f'new value length {len(new_value)} not match field length {self.bit_length} ({self.name})')
        self.value = new_value

    @property
    def is_all_zero(self) -> bool:
        return self.value.is_all_zero


class ProtocolSegment(BaseModel):
    segment_type: SegmentType
    fields: List[SegmentField]
    checksum_offset: Optional[int]

    @validator('checksum_offset')
    def is_digit(cls, value):
        if value and not isinstance(value, int):
            raise ValueError('checksum offset must digit')
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
        result = ''.join(f.prepare() for f in self.fields)
        result = int(result, 2).to_bytes((len(result) + 7) // 8, byteorder='big')
        result = bytearray(result)
        if self.checksum_offset:
            result = self.__wrap_add_16(result, self.checksum_offset)
        return result

    def __getitem__(self, field_name: str) -> SegmentField:
        for field in self.fields:
            if field.name == field_name:
                return field
        raise KeyError(field_name)

    def __setitem__(self, field_name: str, new_value: BinaryString) -> None:
        self[field_name].set_field_value(new_value)

    @property
    def bit_length(self) -> int:
        return sum(f.bit_length for f in self.fields)


class ProtocolSegmentProfileConfig(BaseModel):
    header_segments: List[ProtocolSegment] = []

    def __getitem__(self, segment_type: SegmentType) -> List[ProtocolSegment]:
        return [segment for segment in self.header_segments if segment.segment_type == segment_type]

    def prepare(self) -> bytearray:
        result = bytearray()
        for s in self.header_segments:
            result.extend(s.prepare())
        return result

    def get_segment(self, segment_type: SegmentType, index: int = 0) -> ProtocolSegment:
        return self[segment_type][index]

    @property
    def protocol_version(self) -> PortProtocolVersion:
        ppv = {
            SegmentType.IPV6: PortProtocolVersion.IPV6,
            SegmentType.IPV4: PortProtocolVersion.IPV4,
        }
        for i in self.header_segments:
            if v := ppv.get(i.segment_type):
                return v
        return PortProtocolVersion.ETHERNET

    @property
    def segment_id_list(self) -> List[ProtocolOption]:
        return [h.segment_type.to_xmp() for h in self.header_segments]

    @property
    def packet_header_length(self) -> int:
        """byte header length for convenient use with xoa-driver"""
        return sum(hs.bit_length for hs in self.header_segments) // 8
