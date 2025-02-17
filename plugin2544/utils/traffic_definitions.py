
from enum import Enum


class EtherType(Enum):
    IPV4 = "0800"
    IPV6 = "86dd"
    ARP = "0806"

class NextHeaderOption(Enum):
    ICMP = 1
    IGMP = 2
    TCP = 6
    UDP = 17
    ICMPV6 = 58
    DEFALUT = 59
    SCTP = 132