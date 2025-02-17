from copy import deepcopy
from enum import Enum
from typing import List, Optional, Union
from pydantic import ConfigError
from ..utils.constants import (
    ETHER_TYPE_IPV4,
    ETHER_TYPE_IPV6,
    IPVersion,
    ProtocolOption,
    MIN_PACKET_LENGTH,
)
from ..model.protocol_segments import (
    DEFAULT_SEGMENT_DIC,
    HeaderSegment,
    SegmentDefinition,
    FieldDefinition,
)
from .test_result import AddressCollection


class ParseMode(Enum):
    BIT = 0
    BYTE = 1


class ProtocolChange:
    def __init__(self, protocol: Union[ProtocolOption, str]) -> None:
        self.segment_def = type(self).get_segment_definition_by_protocol(
            ProtocolOption(protocol)
        )
        self.value_bin = self.segment_def.default_value_bin

    @property
    def header(self) -> "HeaderSegment":
        return HeaderSegment(
            type=self.segment_def.segment_type, segment_value=self.hexstring
        )

    @classmethod
    def read_segment(cls, segment: "HeaderSegment") -> "ProtocolChange":
        instance = ProtocolChange(segment.type)
        instance.value_bin = [
            int(p)
            for i in bytes.fromhex(segment.segment_value)
            for p in bin(i).replace("0b", "").zfill(8)
        ]
        return instance

    @classmethod
    def get_segment_value(
        cls,
        header_segments: List["HeaderSegment"],
        segment_index: int,
        address_collection: "AddressCollection",
        can_tcp_checksum: bool,
    ) -> str:
        segment = header_segments[segment_index]
        if segment.type == ProtocolOption.TCP and can_tcp_checksum:
            header_segments[segment_index].type = ProtocolOption.TCPCHECK

        patched_value = ""
        if (segment.type) == ProtocolOption.ETHERNET:
            # patch first Ethernet segment with the port S/D MAC addresses
            if segment_index == 0:
                seg_types = [s.type for s in header_segments]
                e_type = (
                    ETHER_TYPE_IPV4
                    if ProtocolOption.IPV4 in seg_types
                    else ETHER_TYPE_IPV6
                )
                patched_value = (
                    ProtocolChange(ProtocolOption.ETHERNET)
                    .change_segment(
                        "Dst MAC addr",
                        address_collection.dmac.bytearrays,
                        ParseMode.BYTE,
                    )
                    .change_segment(
                        "Src MAC addr",
                        address_collection.smac.bytearrays,
                        ParseMode.BYTE,
                    )
                    .change_segment("EtherType", e_type, ParseMode.BYTE)
                ).hexstring

        elif (segment.type) == ProtocolOption.IPV4:
            change = ProtocolChange(ProtocolOption.IPV4)
            if segment_index + 1 <= len(header_segments) - 1:
                next_prot = header_segments[segment_index + 1]
                if next_prot.type == ProtocolOption.UDP:
                    change = change.change_segment("Protocol", 17, ParseMode.BIT)
                elif next_prot.type == ProtocolOption.TCP:
                    change = change.change_segment("Protocol", 6, ParseMode.BIT)
                elif next_prot.type == ProtocolOption.ICMP:
                    change = change.change_segment("Protocol", 1, ParseMode.BIT)
                elif next_prot.type == ProtocolOption.SCTP:
                    change = change.change_segment("Protocol", 132, ParseMode.BIT)
                elif next_prot.type in (
                    ProtocolOption.IGMPV1,
                    ProtocolOption.IGMPV2,
                    ProtocolOption.IGMPV3L0,
                    ProtocolOption.IGMPV3L1,
                ):
                    change = change.change_segment("Protocol", 2, ParseMode.BIT)
            patched_value = (
                change.change_segment(
                    "Src IP Addr",
                    address_collection.src_ipv4_addr.bytearrays,
                    ParseMode.BYTE,
                ).change_segment(
                    "Dest IP Addr",
                    address_collection.dst_ipv4_addr.bytearrays,
                    ParseMode.BYTE,
                )
            ).hexstring
        elif (segment.type) == ProtocolOption.IPV6:
            # patched_value = setup_ipv6_segment(segment_value_bytearray, address_collection)
            change = ProtocolChange(ProtocolOption.IPV6)
            if segment_index + 1 <= len(header_segments) - 1:
                next_prot = header_segments[segment_index + 1]
                if next_prot.type == ProtocolOption.UDP:
                    change = change.change_segment("Next Header", 17, ParseMode.BIT)
                elif next_prot.type == ProtocolOption.TCP:
                    change = change.change_segment("Next Header", 6, ParseMode.BIT)
                elif next_prot.type == ProtocolOption.ICMP:
                    change = change.change_segment("Next Header", 1, ParseMode.BIT)
                elif next_prot.type == ProtocolOption.SCTP:
                    change = change.change_segment("Next Header", 132, ParseMode.BIT)
                elif next_prot.type in (
                    ProtocolOption.IGMPV1,
                    ProtocolOption.IGMPV2,
                    ProtocolOption.IGMPV3L0,
                    ProtocolOption.IGMPV3L1,
                ):
                    change = change.change_segment("Next Header", 2, ParseMode.BIT)

            patched_value = (
                change.change_segment(
                    "Src IPv6 Addr",
                    address_collection.src_ipv6_addr.bytearrays,
                    ParseMode.BYTE,
                ).change_segment(
                    "Dest IPv6 Addr",
                    address_collection.dest_ipv6_addr.bytearrays,
                    ParseMode.BYTE,
                )
            ).hexstring

        # set to default value if not assigned
        if not patched_value:
            patched_value = segment.segment_value

        return patched_value

    @classmethod
    def get_packet_header_inner(
        cls,
        address_collection: "AddressCollection",
        header_segments: List["HeaderSegment"],
        can_tcp_checksum: bool,
        # arp_mac: "MacAddress",
    ) -> bytearray:
        packet_header_list = bytearray()

        # Insert all configured header segments in order

        for segment_index, segment in enumerate(header_segments):
            addr_coll = address_collection.copy()
            patched_value = cls.get_segment_value(
                header_segments, segment_index, addr_coll, can_tcp_checksum
            )
            real_value = ProtocolChange.calculate_checksum(
                header_segments, segment_index, patched_value
            )
            packet_header_list += real_value

        return packet_header_list

    @classmethod
    def calculate_checksum(
        cls,
        header_segments: List["HeaderSegment"],
        index: int,
        value: str,
    ) -> bytearray:
        segment = header_segments[index]
        if segment.type != ProtocolOption.ICMPV6:
            patched_value = bytearray.fromhex(value)
            offset_num = (
                ProtocolChange.get_segment_definition_by_protocol(
                    segment.type
                ).checksum_offset
                if segment.type.value in DEFAULT_SEGMENT_DIC
                else -1
            )
            if offset_num != -1:
                result = cls.wrap_add_16(patched_value, offset_num)
                segment.segment_value = result.hex()
                return result
            return patched_value
        else:
            ip_segment = ProtocolChange.read_segment(header_segments[index - 1])
            source_ip_address = ip_segment.find_value_as_bytearray("Src IPv6 Addr")
            dest_ip_address = ip_segment.find_value_as_bytearray("Dest IPv6 Addr")
            icmpv6_checksum = cls.icmp_v6_checksum(
                source_ip_address,
                dest_ip_address,
                list(bytes.fromhex(segment.segment_value)),
            )
            now_value = (
                segment.segment_value[:4] + icmpv6_checksum + segment.segment_value[8:]
            )
            segment.segment_value = now_value
            return bytearray.fromhex(now_value)

    @classmethod
    def icmp_v6_checksum(
        cls,
        source_ip_bytearray: bytearray,
        dest_ip_bytearray: bytearray,
        byte_list: List[int],
    ) -> str:
        checksum = 0
        for i in range(0, len(source_ip_bytearray), 2):
            num = (source_ip_bytearray[i] << 8) + source_ip_bytearray[i + 1]
            checksum += num
        for i in range(0, len(dest_ip_bytearray), 2):
            num = (dest_ip_bytearray[i] << 8) + dest_ip_bytearray[i + 1]
            checksum += num
        checksum += len(byte_list) >> 16
        checksum += len(byte_list)
        checksum += 0
        checksum += 0x003A
        for i in range(0, len(byte_list), 2):
            num = (byte_list[i] << 8) + byte_list[i + 1]
            checksum += num
        checksum += checksum >> 16
        c = ~checksum
        high = (c & 0xFF00) >> 8
        low = c & 0xFF
        return bytearray([high, low]).hex()

    @classmethod
    def wrap_add_16(cls, data: bytearray, offset_num: int) -> bytearray:
        # Needs validation
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

    @classmethod
    def cal_packet_header(cls, header_segments: List["HeaderSegment"]) -> bytearray:
        packet_header_list = bytearray()
        for index, segment in enumerate(header_segments):
            patched_value = segment.segment_value
            real_value = cls.calculate_checksum(header_segments, index, patched_value)
            packet_header_list += real_value

        # minimum packet length
        if MIN_PACKET_LENGTH > len(packet_header_list):
            for i in range(MIN_PACKET_LENGTH - len(packet_header_list)):
                packet_header_list.append(0)

        # add spece for Ethernet FCS
        return packet_header_list + bytearray([0, 0, 0, 0])

    @property
    def bin_int_list(self) -> List[int]:
        return self.value_bin

    @property
    def bin_str(self) -> str:
        return "".join(str(i) for i in self.value_bin)

    @property
    def bytes_int_list(self) -> List[int]:
        return type(self).bin_to_bytes_int_list(self.value_bin)

    @classmethod
    def bin_to_bytes_int_list(cls, bin_list: List[int]) -> List[int]:
        length = len(bin_list)
        step = 8
        modulus = length % step
        short_len = length // step
        long_len = short_len * step if not modulus else (short_len + 1) * step
        new_bin = cls.patch_bin_list(bin_list, long_len)
        result = []
        for i in range(0, length, step):
            part = new_bin[i : i + step]
            part_str = "".join(str(m) for m in part)
            result.append(int(part_str, 2))
        return result

    @property
    def bytearrays(self) -> bytearray:
        return bytearray(self.bytes_int_list)

    @property
    def byte(self) -> bytes:
        return bytes(self.bytearrays)

    @property
    def hexstring(self) -> str:
        return self.byte.hex()

    def keys(self) -> List[str]:
        return [i.name for i in self.segment_def.field_definitions]

    def find_field(self, key: str) -> Optional[FieldDefinition]:
        for field_def in self.segment_def.field_definitions:
            if field_def.name == key or field_def.value_map_name == field_def.name:
                return field_def
        return None

    def find_value_as_bytearray(self, key: str) -> bytearray:
        field = self.find_field(key)
        if field:
            bins = self.value_bin[
                field.bit_offset : field.bit_offset + field.bit_length
            ]
            return bytearray(type(self).bin_to_bytes_int_list(bins))
        return bytearray()

    def change_segments(self, **dic) -> "ProtocolChange":
        for key, v in dic.items():
            value, mode = v
            self.change_segment(key, value, mode)
        return self

    def change_segment(
        self,
        key: str,
        value: Union[str, list, bytearray, bytes, int],
        mode: Union[ParseMode, int] = ParseMode.BIT.value,
    ) -> "ProtocolChange":
        value_bin = self.value_bin
        mode_enum = ParseMode(mode)
        field_def = self.find_field(key)
        assert field_def, f'Cannot find the field named "{key}". '
        bit_offset = field_def.bit_offset
        bit_length = field_def.bit_length
        new_value = [0 for _ in range(bit_length)]
        if isinstance(value, (str, list, bytearray, bytes)):
            if mode_enum == ParseMode.BIT:
                new_value = [int(i) for i in value]
                assert all(
                    i in range(2) for i in new_value
                ), "Not all elements are '0' or '1'!"
            elif mode_enum == ParseMode.BYTE:
                if isinstance(value, str):
                    temp = [int(i) for i in bytes.fromhex(value)]
                else:
                    temp = list(value)
                new_value = [
                    int(i) for b in temp for i in bin(b).replace("0b", "").zfill(8)
                ]

        elif isinstance(value, int):
            new_value = [int(i) for i in bin(value).replace("0b", "")]

        result = type(self).patch_bin_list(new_value, bit_length)
        assert bit_offset + len(result) <= len(value_bin), "Modified value too long. "
        value_bin[bit_offset : bit_offset + len(result)] = result
        self.value_bin = value_bin
        return self

    @classmethod
    def get_segment_definition_by_string(cls, protocol_str: str) -> SegmentDefinition:
        if not protocol_str in DEFAULT_SEGMENT_DIC:
            raise ConfigError(f"Not Support {protocol_str}")
        else:
            return deepcopy(DEFAULT_SEGMENT_DIC[protocol_str])

    @classmethod
    def get_segment_definition_by_protocol(
        cls, protocol: ProtocolOption
    ) -> SegmentDefinition:
        protocol_str = protocol.value
        return cls.get_segment_definition_by_string(protocol_str)

    @classmethod
    def get_segment_definition_by_ip_version(
        cls, protocol: IPVersion
    ) -> SegmentDefinition:
        return cls.get_segment_definition_by_string(protocol.value)

    @classmethod
    def patch_bin_list(cls, int_01_list: List[int], patch_to_length: int) -> List[int]:
        modulus = len(int_01_list) % patch_to_length
        if len(int_01_list) > patch_to_length:
            result = int_01_list[-patch_to_length:]
        elif modulus:
            result = [0 for _ in range(patch_to_length - modulus)] + int_01_list
        else:
            result = int_01_list
        return result

    @classmethod
    def get_ip_field_byte_offset(cls, ip_version: IPVersion) -> int:
        for field_def in cls.get_segment_definition_by_ip_version(
            ip_version
        ).field_definitions:
            if (ip_version == IPVersion.IPV4 and field_def.name == "Dest IP Addr") or (
                ip_version == IPVersion.IPV6 and field_def.name == "Dest IPv6 Addr"
            ):
                return field_def.byte_offset
        raise Exception(f"Cannot find byte offset of '{ip_version}'")
