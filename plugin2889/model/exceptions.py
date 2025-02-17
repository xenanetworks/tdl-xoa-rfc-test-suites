def get_plural_postfix(count) -> str:
    return 's' if count else ''


class PortConfigNotEnough(Exception):
    def __init__(self, count: int) -> None:
        self.msg = f"The configuration must have at least {count} test ports."
        super().__init__(self.msg)


class PortConfigNotMatchExactly(Exception):
    def __init__(self, role: str, count: int) -> None:
        self.msg = f"You must specify exactly {count} {role} port{get_plural_postfix(count)}."
        super().__init__(self.msg)


class TestTypeNotEnough(Exception):
    def __init__(self) -> None:
        self.msg = "You must enable at least one test type!"
        super().__init__(self.msg)


class RateTestEmptySubTest(Exception):
    def __init__(self) -> None:
        self.msg = "Either the throughput or the forwarding test (or both) must be enabled."
        super().__init__(self.msg)


class RateTestPortConfigNotEnough(Exception):
    def __init__(self) -> None:
        self.msg = "A rate test configuration must use at least two ports."
        super().__init__(self.msg)


class RateTestPortRoleUndefined(Exception):
    def __init__(self) -> None:
        self.msg = "A used port must be assigned a group role."
        super().__init__(self.msg)


class RateTestPortRoleEmptyPair(Exception):
    def __init__(self) -> None:
        self.msg = "A used port must be paired with another port."
        super().__init__(self.msg)


class RateTestPortRoleEmptyGroupRole(Exception):
    def __init__(self) -> None:
        self.msg = "At least one port must be assigned to each of the two group roles."
        super().__init__(self.msg)


class PortRoleEnabledNotEnough(Exception):
    def __init__(self, count: int) -> None:
        self.msg = f"You must enable exactly {count} port{get_plural_postfix(count)} for use!"
        super().__init__(self.msg)


class PortRoleNotEnough(Exception):
    def __init__(self, role: str, count: int) -> None:
        self.msg = f"You must specify exactly {count} {role} port{get_plural_postfix(count)}!"
        super().__init__(self.msg)


class PortRoleNotEnoughAtLeast(Exception):
    def __init__(self, role: str, count: int) -> None:
        self.msg = f"You must specify at least {count} {role} port{get_plural_postfix(count)}!"
        super().__init__(self.msg)


class MixWeightsNotEnough(Exception):
    def __init__(self, mix_weights_count: int) -> None:
        self.msg = f"Not enough mixed weights; there should be {mix_weights_count} number of mixed weights."
        super().__init__(self.msg)


class MixWeightsSumError(Exception):
    def __init__(self, current_sum: int) -> None:
        self.msg = f"The sum of frame weights must be 100% (is currently {current_sum}%)."
        super().__init__(self.msg)


class WaitSyncStateTimeout(Exception):
    def __init__(self) -> None:
        self.msg = "Waiting for sync state timeout"
        super().__init__(self.msg)


class NotSupportStaggering(Exception):
    def __init__(self) -> None:
        self.msg = "Tester does not support port staggering"
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


class WrongModuleTypeError(Exception):
    def __init__(self, module):
        self.module_type = type(module)
        self.msg = f"Provided module of: {self.module_type} can't be used."
        super().__init__(self.msg)


class NoRxDataError(Exception):
    def __init__(self):
        self.msg = "No RX DATA"
        super().__init__(self.msg)


class MicroTPLDNotSupport(Exception):
    def __init__(self) -> None:
        self.msg = "Port doesn't support Micro-TPLD."
        super().__init__(self.msg)


class StopTestByLossSignal(Warning):
    def __init__(self) -> None:
        self.msg = "Test is stopped due to the loss of signal of ports."
        super().__init__(self.msg)
