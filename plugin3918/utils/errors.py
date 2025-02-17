from typing import Any


class BXMPWarning:
    def __init__(self, para: str, value: Any, port: Any, feature: str) -> None:
        self.str = f"<{para}> can only be set to {value} since port {port} does not support '{feature}' feature!"

    def __repr__(self) -> str:
        return self.str

    def __str__(self) -> str:
        return self.str


class ConfigError(Exception):
    string: str = ""

    def __repr__(self) -> str:
        return self.string

    def __str__(self) -> str:
        return self.string


class NoIpSegment(ConfigError):
    def __init__(self, port_name: str) -> None:
        self.string = f"'{port_name}' Port segment profile must contain an IP segment!"


class IpEmpty(ConfigError):
    def __init__(self, port_name: str, version: str) -> None:
        self.string = f"Port {port_name} must be assigned an {version} address!"


class NoRole(ConfigError):
    def __init__(self, port_name: str) -> None:
        self.string = f"Port {port_name} must be assigned a role!"


class NotOneMcSource(ConfigError):
    def __init__(self) -> None:
        self.string = "The configuration must include precisely one MC source port!"


class NoMcDestination(ConfigError):
    def __init__(self) -> None:
        self.string = "The configuration must include at least one MC destination port!"


class LeastTwoUcBurden(ConfigError):
    def __init__(self) -> None:
        self.string = "Burdening tests require at least two burdening ports!"

class UcTypeError(ConfigError):
    def __init__(self) -> None:
        self.string = "Not valid stream info type!"


class PacketSizeSmallerThanPacketLength(ConfigError):
    def __init__(
        self, min_packet_size: int, need_mc_packet_length: int, mode: str
    ) -> None:
        self.string = f"Packet size {min_packet_size} too small for used {mode} segment, need {need_mc_packet_length} bytes!"


class CustomMixLengthUnsupported(ConfigError):
    def __init__(self, port_name: str) -> None:
        self.string = f"Custom mix-lengths unsupported by port {port_name}!"


class MixPacketLegnthTooSmall(ConfigError):
    def __init__(
        self, port_name: str, min_packet_size: int, port_min_packet_size: int
    ) -> None:
        self.string = f"Mix frame size {min_packet_size} too small for port {port_name}, must at least be {port_min_packet_size} bytes!"


class MixPacketLegnthTooLarge(ConfigError):
    def __init__(
        self, port_name: str, max_packet_size: int, port_max_packet_size: int
    ) -> None:
        self.string = f"Mix frame size {max_packet_size} too large for port {port_name}, can at most be {port_max_packet_size} bytes!"


class IPAddressMissing(Exception):
    def __init__(self) -> None:
        self.msg = "You must assign an IP address to the port!"
        super().__init__(self.msg)


class LossSync(Exception):
    def __init__(self) -> None:
        self.msg = f"Unable to detect sync signal for all ports!"
        super().__init__(self.msg)

class UnableToObtainDmac(Exception):
    def __init__(self, name: str) -> None:
        self.msg = f"Unable to obtain DMAC for port {name}" 
        super().__init__(self.msg)


