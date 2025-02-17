from dataclasses import dataclass, field
from pydantic import BaseModel
from typing import Optional, Union, Tuple, TYPE_CHECKING
import time
from ..utils.constants import PortProtocolVersion
from ..utils.field import IPv4Address, IPv6Address, MacAddress

if TYPE_CHECKING:
    from ..utils.interfaces import TestSuitePipe


@dataclass(frozen=True)
class ArpRefreshData:
    # is_ipv4: bool
    source_ip: Union[IPv4Address, IPv6Address, None]
    source_mac: Optional[MacAddress]
    addr_range: Optional[range]


@dataclass(frozen=True)
class RXTableData:
    destination_ip: Union[IPv4Address, IPv6Address]
    dmac: MacAddress


class StreamOffset(BaseModel):
    tx_offset: int
    rx_offset: int

    def reverse(self) -> "StreamOffset":
        return StreamOffset(tx_offset=self.rx_offset, rx_offset=self.tx_offset)


@dataclass
class AddressCollection:
    smac: MacAddress = MacAddress()
    dmac: MacAddress = MacAddress()
    arp_mac: MacAddress = MacAddress()
    src_addr: Union[IPv4Address, IPv6Address, None] = None
    dst_addr: Union[IPv4Address, IPv6Address, None] = None

    def get_addr_pair_by_protocol(
        self, protocol: PortProtocolVersion
    ) -> Tuple[Union[IPv4Address, IPv6Address, MacAddress, None], ...]:
        if protocol.is_ipv4:
            return self.src_addr, self.dst_addr
        elif protocol.is_ipv6:
            return self.src_addr, self.dst_addr
        return self.smac, self.dmac

@dataclass
class Progress:
    total: int
    loop: int = 1
    current: int = 0

    def send(self, xoa: "TestSuitePipe") -> None:
        xoa.send_progress(self.current, self.total, self.loop)
        self.current += 1

    def add_loop(self, xoa: "TestSuitePipe") -> None:
        self.current = 0
        self.loop += 1
