from typing import Any, Union
from xoa_driver import ports as xoa_ports, testers as xoa_testers
from . import constants as const


class BXMPWarning(Warning):
    def __init__(self, para: str, value: Any, port: Any, feature: str) -> None:
        self.str = f"<{para}> can only be set to {value} since Port {port} doesn't support '{feature}' feature."

    def __repr__(self) -> str:
        return self.str

    def __str__(self) -> str:
        return self.str


# class StopTestByLossSignal(Warning):
#     def __init__(self) -> None:
#         self.msg = f"Test is stopped due to the loss of signal of ports."
#         super().__init__(self.msg)


class BroadReachModeNotSupport(Warning):
    def __init__(self, port_name: str) -> None:
        self.msg = f"<BroadR-Reach Mode> can only be set to False since Port {port_name} doesn't support 'BroadR-Reach' feature."
        super().__init__(self.msg)


class MdiMdixModeNotSupport(Warning):
    def __init__(self, port_name: str) -> None:
        self.msg = f"<MDI/MDIX Mode> can only be set to False since Port {port_name} doesn't support 'MDI/MDIX' feature."
        super().__init__(self.msg)


class ANLTNotSupport(Warning):
    def __init__(self, port_name: str) -> None:
        self.msg = f"<ANLT> can only be set to False since Port {port_name} doesn't support 'ANLT' feature."
        super().__init__(self.msg)


class AutoNegotiationNotSupport(Warning):
    def __init__(self, port_name: str) -> None:
        self.msg = f"<Auto Negotiation> can only be set to False since Port {port_name} doesn't support 'Auto Negotiation' feature."
        super().__init__(self.msg)


class FecModeNotSupport(Warning):
    def __init__(self, port_name: str) -> None:
        self.msg = f"<FEC Mode> can only be set to False since Port {port_name} doesn't support 'FEC Mode' feature."
        super().__init__(self.msg)


class PortSpeedWarning(Warning):
    def __init__(self, port_speed_mode) -> None:
        self.msg = f"Port doesn't support speed mode selection ({port_speed_mode})."
        super().__init__(self.msg)


class NotSupportL47Tester(Exception):
    def __init__(self) -> None:
        self.msg = "Not supporting L47Tester."
        super().__init__(self.msg)


class IPAddressMissing(Exception):
    def __init__(self) -> None:
        self.msg = "You must assign an IP address to the port."
        super().__init__(self.msg)


class PortConfigNotEnough(Exception):
    def __init__(self, require_ports: int) -> None:
        self.msg = f"The configuration must have at least {require_ports} test port{'s'  if require_ports > 1 else ''}."
        super().__init__(self.msg)


class PortGroupError(Exception):
    def __init__(self, group: str) -> None:
        self.msg = f"At least one port must be assigned to the Port Group {group}."
        super().__init__(self.msg)


class TestTypesError(Exception):
    def __init__(self) -> None:
        self.msg = "You have not enabled any test case type."
        super().__init__(self.msg)


class ModifierBasedNotSupportPerPortResult(Exception):
    def __init__(self) -> None:
        self.msg = "Cannot use 'Per Source-Port Result' for Rate Result Scope in case of modifier-based streams."
        super().__init__(self.msg)


class ModifierBasedNotSupportL3(Exception):
    def __init__(self) -> None:
        self.msg = "Cannot use 'Modifier-based' for stream creation in case of Layer-3 traffic."
        super().__init__(self.msg)


class ModifierBasedNotSupportMultiStream(Exception):
    def __init__(self) -> None:
        self.msg = "Modifier-based stream creation doesn't support multi-stream."
        super().__init__(self.msg)


class ModifierBasedNotSupportDefineModifier(Exception):
    def __init__(self) -> None:
        self.msg = "Not possible to define modifiers when using modifier-based streams."
        super().__init__(self.msg)


class ModifierExceed(Exception):
    def __init__(self, cur: int, max: int) -> None:
        self.msg = f"Port can only have maximum {max} modifiers per stream (has {cur})."
        super().__init__(self.msg)


class StreamExceed(Exception):
    def __init__(self, cur: int, max: int) -> None:
        self.msg = f"Port only supports maximum {max} streams (needs {cur})."
        super().__init__(self.msg)


class PortPeerNeeded(Exception):
    def __init__(self) -> None:
        self.msg = "You must assign a peer to the port."
        super().__init__(self.msg)


class PortPeerInconsistent(Exception):
    def __init__(self) -> None:
        self.msg = "Inconsistent port peer definition."
        super().__init__(self.msg)


class PortGroupNeeded(Exception):
    def __init__(self) -> None:
        self.msg = "You must assign the port to a port group."
        super().__init__(self.msg)


class MacAddressNotValid(Exception):
    def __init__(self, mac_addr: str) -> None:
        self.msg = f"{mac_addr} is not a valid MAC address."
        super().__init__(self.msg)


class MixWeightsNotEnough(Exception):
    def __init__(self) -> None:
        self.msg = f"Not enough mixed weights; there should be {len(const.MIXED_DEFAULT_WEIGHTS)} number of mixed weights."
        super().__init__(self.msg)


class SmallerThanZeroError(Exception):
    def __init__(self, num: Union[int, float]) -> None:
        self.msg = f"Num {num} must be non negative."
        super().__init__(self.msg)


class MixWeightsSumError(Exception):
    def __init__(self, current_sum: int) -> None:
        self.msg = (
            f"The sum of frame weights must be 100% (is currently {current_sum}%)."
        )
        super().__init__(self.msg)


class FrameSizeTypeError(Exception):
    def __init__(self, packet_size_type: str) -> None:
        self.msg = f"Frame size type {packet_size_type} not implemented."
        super().__init__(self.msg)


class RangeRestriction(Exception):
    def __init__(self) -> None:
        self.msg = "Start rate cannot be larger than the end rate."
        super().__init__(self.msg)


class StepValueRestriction(Exception):
    def __init__(self) -> None:
        self.msg = "Step value percent must be larger than 0."
        super().__init__(self.msg)


class RateRestriction(Exception):
    def __init__(self, cur_rate: float, max_rate: float) -> None:
        self.msg = f"{cur_rate} cannot be larger than the maximum rate ({max_rate})."
        super().__init__(self.msg)


class PacketLengthExceed(Exception):
    def __init__(self, cur: int, max: int) -> None:
        self.msg = (
            f"Packet length ({cur}) is larger than what the port allows (max: {max})."
        )
        super().__init__(self.msg)


class TPLDIDExceed(Exception):
    def __init__(self, cur: int, max: int) -> None:
        self.msg = (
            f"Current TPLD ID ({cur}) is larger than what the port allows (max: {max})."
        )
        super().__init__(self.msg)


class OffsetNotExist(Exception):
    def __init__(self) -> None:
        self.msg = "Offsets table calculate error (Offset not exist)."
        super().__init__(self.msg)


class ProtocolNotSupport(Exception):
    def __init__(self, proto: str) -> None:
        self.msg = f"Port doesn't support protocol {proto}."
        super().__init__(self.msg)


class InterFrameGapError(Exception):
    def __init__(self, curr: int, min: int, max: int) -> None:
        self.msg = (
            f"Custom inter-frame gap ({curr} bytes) must stay between {min} and {max}."
        )
        super().__init__(self.msg)


class PortRateError(Exception):
    def __init__(self, curr: float, max: int) -> None:
        self.msg = (
            f"Custom port rate ({curr}) must not exceed physical port rate ({max})."
        )
        super().__init__(self.msg)


class SpeedReductionError(Exception):
    def __init__(self, curr: int, max: int) -> None:
        self.msg = f"Custom speed reduction ({curr} ppm) must not exceed ({max} ppm)."
        super().__init__(self.msg)


class ProtocolSegmentExceed(Exception):
    def __init__(self, curr: int, max: int) -> None:
        self.msg = f"Custom header segment length ({curr}) must not exceed {max}."
        super().__init__(self.msg)


class PacketHeaderExceed(Exception):
    def __init__(self, curr: int, max: int) -> None:
        self.msg = f"Segment packet header length ({curr}) must not exceed ({max})."
        super().__init__(self.msg)


class ModifierRepeatCountExceed(Exception):
    def __init__(self, curr: int, max: int) -> None:
        self.msg = f"Custom modifier repeat count ({curr}) must not exceed ({max})."
        super().__init__(self.msg)


class FECModeRequired(Exception):
    def __init__(self) -> None:
        self.msg = f"Port is mandatory to set FEC Mode."
        super().__init__(self.msg)


class FECModeTypeNotSupport(Exception):
    def __init__(self, support_mode: "const.FECModeStr") -> None:
        self.msg = f"Port not supporting {support_mode} FEC Mode."
        super().__init__(self.msg)


class FieldValueRangeExceed(Exception):
    def __init__(self, field_name: str, max: int) -> None:
        self.msg = f"Field Value Range {field_name} boundary must not exceed {max}."
        super().__init__(self.msg)


class PortStaggeringNotSupport(Exception):
    def __init__(self) -> None:
        self.msg = "Tester doesn't support port staggering."
        super().__init__(self.msg)


class MinPacketLengthExceed(Exception):
    def __init__(self, type: str, cur: int, min: int) -> None:
        self.msg = f"{type} {cur} too small for port. Must at least be {min} bytes"
        super().__init__(self.msg)


class MaxPacketLengthExceed(Exception):
    def __init__(self, type: str, cur: int, max: int) -> None:
        self.msg = f"{type} {cur} too large for port. Must at most be {max} bytes."
        super().__init__(self.msg)


class MicroTPLDNotSupport(Exception):
    def __init__(self) -> None:
        self.msg = "Port doesn't support Micro-TPLD."
        super().__init__(self.msg)


class PacketSizeTooSmall(Exception):
    def __init__(self, cur: int, need: int) -> None:
        self.msg = (
            f"Packet size {cur} too small for protocol segment, need {need} bytes!"
        )
        super().__init__(self.msg)


class PayloadPatternExceed(Exception):
    def __init__(self, cur: int, max: int) -> None:
        self.msg = f"Custom payload pattern length ({cur}) must not exceed {max}."
        super().__init__(self.msg)


class WrongModuleTypeError(Exception):
    def __init__(self, module) -> None:
        self.module_type = type(module)
        self.msg = f"Provided module: {self.module_type} cannot be used."
        super().__init__(self.msg)


class WrongTesterTypeError(Exception):
    def __init__(self, tester) -> None:
        self.tester_type = type(tester)
        self.msg = f"Provided tester: {self.tester_type} cannot be used."
        super().__init__(self.msg)


class LossofPortOwnership(Exception):
    def __init__(self, port: "xoa_ports.GenericL23Port") -> None:
        self.msg = f"Lost ownership of Port <module_id: {port.kind.module_id}-port_id: {port.kind.port_id}>."
        super().__init__(self.msg)


class LossofTester(Exception):
    def __init__(self, tester: xoa_testers.L23Tester, chassis_id: str) -> None:
        self.msg = (
            f"Lost connection to Tester <{chassis_id}>."
        )
        super().__init__(self.msg)


class LossofPortSignal(Exception):
    def __init__(self, port: "xoa_ports.GenericL23Port") -> None:
        self.msg = f"Lost signal (LOS) of Port <module_id: {port.kind.module_id}-port_id: {port.kind.port_id}>."
        super().__init__(self.msg)


class FrameDurationRequire(Exception):
    def __init__(self, test_type: str) -> None:
        self.msg = f"{test_type} Test requires Frames Duration Type."
        super().__init__(self.msg)


class TimeDurationRequire(Exception):
    def __init__(self, test_type: str) -> None:
        self.msg = f"{test_type} Test requires Time Duration Type."
        super().__init__(self.msg)


class PacketLimitOverflow(Exception):
    def __init__(self, packet_count: int) -> None:
        self.msg = f"{packet_count} must not exceed 2,147,483,647."
        super().__init__(self.msg)


class ModifierRangeError(Exception):
    def __init__(self, start: int, stop: int, step: int) -> None:
        self.msg = f"Modifier range configuration must meet these rules: min <= max, and (max - min) % step = 0. Your input was min = {start}, max = {stop}, and step = {step}."
        super().__init__(self.msg)


class PSPMissing(Exception):
    def __init__(self) -> None:
        self.msg = f"Protocol Segment Profile selected is missing."
        super().__init__(self.msg)


class ARPRequestError(Exception):
    def __init__(self) -> None:
        self.msg = f"Test aborted: ARP Failure - Unable to resolve all gateway MAC addresses."
        super().__init__(self.msg)


class TestAbort(Exception):
    def __init__(self) -> None:
        self.msg = "Test Abort."
        super().__init__(self.msg)


        