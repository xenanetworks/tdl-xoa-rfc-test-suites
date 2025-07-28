from decimal import Decimal
import re
from typing import Any, Dict, List, Union
from .errors import ConfigError
from ipaddress import (
    IPv4Address as OldIPv4Address,
    IPv6Address as OldIPv6Address,
    IPv4Network,
    IPv6Network,
)
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from pydantic_core import CoreSchema, core_schema
from pydantic import GetCoreSchemaHandler, TypeAdapter

class HexString(str):
    def to_list(self) -> List[str]:
        return [i for i in re.findall(r".{2}", self)]


class MacAddress(str):
    @classmethod
    def from_bytes(cls, b: Union[bytes, bytearray]) -> "MacAddress":
        return cls("".join([hex(i).replace("0x", "").upper().zfill(2) for i in b]))

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.no_info_after_validator_function(cls, handler(str))

    @classmethod
    def validate(cls, value) -> "MacAddress":
        if not value:
            value = "00:00:00:00:00:00"
        validate_value = (
            value.upper()
            .replace("0x", "")
            .replace("0X", "")
            .replace(":", "")
            .replace("-", "")
        )
        if len(validate_value) != 12:
            raise ConfigError(f"{value} is not a valid mac address!")
        for i in validate_value:
            if i not in "0123456789ABCDEF":
                raise ConfigError(f"{value} is not a valid mac address!")

        return cls(":".join(re.findall(".{2}", validate_value)))

    @property
    def hexstring(self) -> str:
        return (
            self.replace(":", "")
            .replace("-", "")
            .replace("0x", "")
            .replace("0X", "")
            .upper()
            .zfill(12)
        )

    def first_three_bytes(self):
        return (
            self.replace(":", "")
            .replace("-", "")
            .replace("0x", "")
            .replace("0X", "")
            .upper()[:6]
            .zfill(6)
        )

    @property
    def bytearrays(self) -> bytearray:
        return bytearray.fromhex(self.hexstring)

    @property
    def is_empty(self) -> bool:
        return not self or self == MacAddress("00:00:00:00:00:00")

    def modify(self, change_dic: Dict[int, int]) -> "MacAddress":
        int_list = list(self.bytearrays)
        for k, v in change_dic.items():
            int_list[k] = v
        return MacAddress.from_bytes(bytearray(int_list))


class NewIPv4Address(OldIPv4Address):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value) -> "NewIPv4Address":
        return NewIPv4Address(value)

    @property
    def hexstring(self) -> str:
        return self.packed.hex().upper()

    def last_three_bytes(self) -> str:
        return self.hexstring[-6:]

    @property
    def bytearrays(self) -> bytearray:
        return bytearray(self.packed)

    def network(self, prefix: int) -> IPv4Network:
        return IPv4Network(f"{self}/{prefix}", strict=False)

    @property
    def is_empty(self) -> bool:
        return not self or self == NewIPv4Address("0.0.0.0")

    @property
    def int_list(self) -> List[int]:
        return list(self.bytearrays)

    @property
    def bin_int_list(self) -> List[int]:
        result = []
        for i in self.int_list:
            for t in bin(i).replace("0b", "").zfill(8):
                result.append(int(t))
        return result


class NewIPv6Address(OldIPv6Address):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value) -> "NewIPv6Address":
        return NewIPv6Address(value)

    @property
    def hexstring(self) -> str:
        return self.packed.hex().upper()

    @property
    def bytearrays(self) -> bytearray:
        return bytearray(self.packed)

    @property
    def is_empty(self) -> bool:
        return not self or self == NewIPv6Address("::")

    def network(self, prefix: int) -> IPv6Network:
        return IPv6Network(f"{self}/{prefix}", strict=False)

    @property
    def int_list(self) -> List[int]:
        return list(self.bytearrays)

    @property
    def bin_int_list(self) -> List[int]:
        return [
            int(t) for i in self.int_list for t in bin(i).replace("0b", "").zfill(8)
        ]


class Prefix(int):
    def to_ipv4(self) -> NewIPv4Address:
        return NewIPv4Address(int(self * "1" + (32 - self) * "0", 2))


class NonNegativeDecimal(Decimal):
    def __init__(self, v: Any) -> None:
        Decimal.__init__(v)
        if self < 0:
            raise ValueError("Please pass in positive Value.")
