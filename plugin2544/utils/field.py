import re
from typing import Any, Dict, List, Union, TYPE_CHECKING
from ipaddress import (
    IPv4Address as OldIPv4Address,
    IPv6Address as OldIPv6Address,
    IPv4Network,
    IPv6Network,
)
from ..model.m_protocol_segment import BinaryString
from . import exceptions


def hex_string_to_binary_string(hex: str) -> "BinaryString":
    """binary string with leading zeros"""
    hex = hex.lower().replace("0x", "")
    return BinaryString(bin(int("1" + hex, 16))[3:])


class HexString(str):
    def to_list(self) -> List[str]:
        return [i for i in re.findall(r".{2}", self)]


class MacAddress(str):
    def __new__(cls, *args: Any, **kwargs: Dict[str, Any]) -> "MacAddress":
        value = str.__new__(cls, *args, **kwargs)
        if not value:
            value = "000000000000"
        validate_value = (
            value.upper()
            .replace("0x", "")
            .replace("0X", "")
            .replace(":", "")
            .replace("-", "")
        )
        if len(validate_value) != 12:
            raise exceptions.MacAddressNotValid(value)
        for i in validate_value:
            if i not in "0123456789ABCDEF":
                raise exceptions.MacAddressNotValid(value)

        return str.__new__(cls, "".join(re.findall(".{2}", validate_value)))

    def to_hexstring(self) -> str:
        return (
            self.replace(":", "")
            .replace("-", "")
            .replace("0x", "")
            .replace("0X", "")
            .upper()
            .zfill(12)
        )

    def first_three_bytes(self) -> str:
        return (
            self.replace(":", "")
            .replace("-", "")
            .replace("0x", "")
            .replace("0X", "")
            .upper()[:6]
            .zfill(6)
        )

    def to_bytearray(self) -> bytearray:
        return bytearray(bytes.fromhex(self.to_hexstring()))

    @property
    def is_empty(self) -> bool:
        return not self or self == MacAddress("000000000000")

    def to_binary_string(self) -> "BinaryString":
        return hex_string_to_binary_string(self.replace(":", ""))


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


IPAddress = Union[IPv4Address, IPv6Address]
