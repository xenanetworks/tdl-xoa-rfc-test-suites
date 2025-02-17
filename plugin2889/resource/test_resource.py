import asyncio
import math
from typing import TYPE_CHECKING, Callable, Generator, List, Optional, Union
from decimal import Decimal

if TYPE_CHECKING:
    from xoa_driver import ports, testers

from xoa_driver import enums
from xoa_driver.utils import apply
from xoa_driver.ports import PThor400G7S1P_b, PThor400G7S1P_c, POdin1G3S6PT1RJ45

from plugin2889.const import DELAY_LEARNING_MAC, INTERVAL_CHECK_PORT_RESERVE, FECModeStr
from plugin2889.model import exceptions
from plugin2889.dataset import AutoNegPorts, IPv4Address, IPv6Address, MacAddress, MdixPorts
from plugin2889.resource._port_stream import StreamManager
from plugin2889.resource._port_statistics import PortStatistics
from plugin2889.resource._traffic import Traffic
from plugin2889.util.logger import logger
from plugin2889.plugin.utils import sleep_log
from plugin2889.dataset import PortConfiguration


class TestResource:
    __slots__ = (
        "tester",
        "port",
        "port_name",
        "streams",
        "statistics",
        "mac_address",
        "traffic",
        "peers",
        "__get_mac_address_function",
        "interframe_gap",
        "port_config",
        "__port_speed",
    )

    def __init__(
        self,
        tester: "testers.L23Tester",
        port: "ports.GenericL23Port",
        port_name: str,
        port_config: PortConfiguration,
        mac_address: Optional[MacAddress] = None,
        get_mac_address_function: Optional[Callable[["TestResource", "MacAddress"], "MacAddress"]] = None,
    ) -> None:
        self.tester = tester
        self.port = port
        self.port_name = port_name
        self.port_config = port_config
        self.traffic = Traffic(port)

        self.streams: List[StreamManager] = []
        self.statistics = PortStatistics(port=self.port, streams=self.streams, port_name=self.port_name)
        self.peers: List[TestResource] = []
        self.mac_address = mac_address or None  # it could be partial or whole address
        self.__get_mac_address_function = get_mac_address_function
        self.interframe_gap = self.port_config.interframe_gap
        self.__port_speed: float = 0  # P_SPPED

    @property
    def __sync_status(self) -> "enums.SyncStatus":
        return self.port.info.sync_status

    @property
    def __traffic_status(self) -> "enums.TrafficOnOff":
        return self.port.info.traffic_state

    @property
    def __reservation_status(self) -> "enums.ReservedStatus":
        return self.port.info.reservation

    def __await__(self) -> Generator[None, None, "TestResource"]:
        return self.__prepare().__await__()

    async def set_mac_address(self):
        mac = await self.port.net_config.mac_address.get()
        current_port_mac_address = MacAddress(mac.mac_address)
        if self.__get_mac_address_function:
            self.mac_address = self.__get_mac_address_function(self, current_port_mac_address)
        elif not self.__get_mac_address_function:
            self.mac_address = current_port_mac_address
        elif not self.__get_mac_address_function and self.mac_address:
            self.mac_address = current_port_mac_address.partial_replace(self.mac_address)

    async def __prepare(self) -> "TestResource":
        await self.set_mac_address()
        await self.reserve()
        return self

    @property
    def traffic_is_off(self) -> bool:
        return self.__traffic_status == enums.TrafficOnOff.OFF

    @property
    def is_sync(self) -> bool:
        return self.__sync_status == enums.SyncStatus.IN_SYNC

    async def get_used_port_speed(self, frame_size: int = 0) -> Decimal:
        self.__port_speed = self.__port_speed or await self.get_port_speed()

        if self.port_config.port_speed_mode.is_auto:
            port_speed = min(self.port.info.capabilities.max_speed * 1e6, self.__port_speed)
        else:
            port_speed = min(self.port_config.port_speed_mode.to_bps(), self.__port_speed)

        if self.port_config.port_rate_cap_enabled:
            port_cap_rate = port_speed
            if self.port_config.port_rate_cap_profile.is_custom:
                port_cap_rate = self.port_config.port_rate_cap_value * self.port_config.port_rate_cap_unit.to_int
            else:
                factor = (frame_size + self.interframe_gap) / (frame_size * self.port_config.interframe_gap) if frame_size else 1.0
                port_cap_rate = factor * self.port_config.port_rate_cap_value
            port_speed = min(port_cap_rate, port_speed)

        return Decimal(port_speed)

    async def set_peer(self, stream_id: int, tpld_id: int, peer: "TestResource") -> None:
        assert peer.mac_address is not None
        stream = StreamManager(stream_id, tpld_id, self, peer_resource=peer)
        await stream.setup_stream()
        self.streams.append(stream)
        peer.statistics.add_tx_resources(self, stream.tpld_id)
        self.peers.append(peer)

    async def reserve(self) -> None:
        if self.__reservation_status == enums.ReservedStatus.RESERVED_BY_YOU:
            await self.port.reservation.set_release()
        elif self.__reservation_status == enums.ReservedStatus.RESERVED_BY_OTHER:
            await self.port.reservation.set_relinquish()
            while self.__reservation_status != enums.ReservedStatus.RELEASED:
                await self.port.reservation.set_relinquish()
                await sleep_log(INTERVAL_CHECK_PORT_RESERVE)
        await apply(self.port.reservation.set_reserve(), self.port.reset.set())
        await self.port.streams.server_sync()

    async def release(self) -> None:
        await apply(
            # self.port.reset.set(),
            self.port.reservation.set_release(),
        )

    async def mac_learning(self) -> None:
        assert self.mac_address
        logger.debug(self.mac_address)
        dest_mac = "FFFFFFFFFFFF"
        four_f = "FFFF"
        paddings = "00" * 118
        own_mac = self.mac_address.to_hexstring()
        hex_data = f"{dest_mac}{own_mac}{four_f}{paddings}"
        if len(hex_data) // 2 > self.port.info.capabilities.max_xmit_one_packet_length:
            raise exceptions.PacketLengthExceed(len(hex_data) // 2, self.port.info.capabilities.max_xmit_one_packet_length)
        await apply(self.port.tx_single_pkt.send.set(hex_data))  # P_XMITONE
        await sleep_log(DELAY_LEARNING_MAC)

    async def set_tx_config_enable(self, on_off: enums.OnOff) -> None:
        await self.port.tx_config.enable.set(on_off)

    async def set_tx_config_delay(self, delay: int) -> None:
        await self.port.tx_config.delay.set(delay)

    async def get_port_speed(self) -> float:
        return (await self.port.speed.current.get()).port_speed * 1e6

    async def calc_set_packet_limit(self, rate_percent: Decimal, packet_size: int, interframe_gap: int, duration_second: int) -> None:
        coroutines = [res.get_port_speed() for res in self.peers]
        coroutines.append(self.get_port_speed())
        lowest_port_speed = min(await asyncio.gather(*coroutines))
        lowest_port_speed = Decimal(lowest_port_speed)

        stream_rate_percent = rate_percent / len(self.streams)
        stream_rate_bps_l1 = stream_rate_percent * lowest_port_speed / Decimal(100)
        stream_rate_bps_l2 = math.floor(stream_rate_bps_l1 * Decimal(packet_size)) / (Decimal(packet_size) + Decimal(interframe_gap))
        stream_packet_rate = stream_rate_bps_l2 / Decimal(8.0) / Decimal(packet_size)
        total_frames = stream_packet_rate * Decimal(duration_second)
        logger.debug(f"{lowest_port_speed} {stream_rate_bps_l2} {total_frames}")

        coroutines = [stream.packet.limit.set(math.floor(total_frames)) for stream in self.port.streams]
        asyncio.gather(*coroutines)

    async def set_rate_pps(self, pps: int) -> None:
        asyncio.gather(*[stream.rate.pps.set(pps) for stream in self.port.streams])

    async def set_packet_limit(self, limit: int) -> None:
        asyncio.gather(*[stream.packet.limit.set(limit) for stream in self.port.streams])

    async def start_traffic_sync(self, module_ports: List[int]) -> None:
        local_time = (await self.tester.time.get()).local_time
        await self.tester.traffic_sync.set(enums.OnOff.ON, local_time + 2, module_ports)  # add 2 second delay

    async def set_stream_peer_mac_address(self, new_peer_mac_address: "MacAddress") -> None:
        await asyncio.gather(*[stream.set_peer_mac_address(new_peer_mac_address) for stream in self.streams])

    async def set_stream_rate_fraction(self, rate: Decimal):
        await asyncio.gather(*[stream.set_rate_fraction(rate) for stream in self.streams])

    async def set_port_ip_address(self) -> None:
        coroutines = []
        if self.port_config.profile.protocol_version.is_ipv4:
            ipv4_properties = self.port_config.ipv4_properties
            coroutines.append(
                self.port.net_config.ipv4.address.set(
                    ipv4_address=ipv4_properties.address,
                    subnet_mask=ipv4_properties.routing_prefix.to_ipv4(),
                    gateway=ipv4_properties.gateway,
                    wild="0.0.0.0",
                )
            )
        elif self.port_config.profile.protocol_version.is_ipv6:
            ipv6_properties = self.port_config.ipv6_properties
            coroutines.append(
                self.port.net_config.ipv6.address.set(
                    ipv6_address=ipv6_properties.address,
                    gateway=ipv6_properties.gateway,
                    subnet_prefix=ipv6_properties.routing_prefix,
                    wildcard_prefix=128,
                )
            )

        coroutines.extend(
            [
                self.port.net_config.ipv4.arp_reply.set(enums.OnOff.ON),  # P_ARPREPLY
                self.port.net_config.ipv6.arp_reply.set(enums.OnOff.ON),  # P_ARPV6REPLY
                self.port.net_config.ipv4.ping_reply.set(enums.OnOff.ON),  # P_PINGREPLY
                self.port.net_config.ipv6.ping_reply.set(enums.OnOff.ON),  # P_PINGV6REPLY
            ]
        )

        asyncio.gather(*coroutines)

    async def set_port_interframe_gap(self, ifg: int = 0) -> None:
        self.interframe_gap = ifg or self.port_config.interframe_gap
        await self.port.interframe_gap.set(min_byte_count=self.interframe_gap)

    async def set_port_speed_selection(self) -> None:
        speed_mode = self.port_config.port_speed_mode.to_xmp()
        if speed_mode not in self.port.info.port_possible_speed_modes:
            logger.warning(f"port doesn't support speed mode selection ({speed_mode})")
            return None
        await self.port.speed.mode.selection.set(speed_mode)

    async def set_port_autoneg(self) -> None:
        if not self.port_config.auto_neg_enabled:
            return None
        if not self.port.info.capabilities.can_set_autoneg or not isinstance(self.port, AutoNegPorts):
            logger.debug(f"{self.port} not support autoneg")
            return None
        await self.port.autoneg_selection.set(enums.OnOff.ON)

    async def set_port_anlt(self) -> None:
        if not self.port_config.anlt_enabled:
            return None
        if not isinstance(self.port, (PThor400G7S1P_c, PThor400G7S1P_b)):
            logger.debug(f"{self.port} not support anlt")
            return None

        coroutines = []
        if bool(self.port.info.capabilities.can_auto_neg_base_r):
            coroutines.append(
                self.port.pcs_pma.auto_neg.settings.set(
                    enums.AutoNegMode.ANEG_ON,
                    enums.AutoNegTecAbility.DEFAULT_TECH_MODE,
                    enums.AutoNegFECOption.NO_FEC,
                    enums.AutoNegFECOption.NO_FEC,
                    enums.PauseMode.NO_PAUSE,
                )
            )
        else:
            logger.debug(f"{self.port} not support can_auto_neg_base_r")

        if bool(self.port.info.capabilities.can_set_link_train):
            coroutines.append(
                self.port.pcs_pma.link_training.settings.set(
                    enums.LinkTrainingMode.STANDALONE,
                    enums.PAM4FrameSize.P16K_FRAME,
                    enums.LinkTrainingInitCondition.NO_INIT,
                    enums.NRZPreset.NRZ_NO_PRESET,
                    enums.TimeoutMode.DEFAULT,
                )
            )
        else:
            logger.debug(f"{self.port} not support can_auto_neg_base_r")
        asyncio.gather(*coroutines)

    async def set_port_brr(self) -> None:
        if not self.port.info.capabilities:
            logger.debug(f"{self.port} not support brr")
            return None

        if isinstance(self.port, (POdin1G3S6PT1RJ45,)):
            self.port.brr_mode.set(self.port_config.broadr_reach_mode.to_xmp())

    async def set_port_mdi_mdix(self) -> None:
        if not self.port.info.capabilities.can_mdi_mdix:
            logger.debug(f"{self.port} not support mdi_mdix")
            return None

        if isinstance(self.port, MdixPorts):
            self.port.mdix_mode.set(self.port_config.mdi_mdix_mode.to_xmp())

    async def set_port_fec(self) -> None:
        can_fec = self.port.info.capabilities.can_fec
        fec_mode = self.port_config.fec_mode

        bin_str = bin(can_fec)[2:].zfill(32)
        is_mandatory = int(bin_str[-32])
        is_fc_fec_supported = int(bin_str[-3])
        if is_mandatory and fec_mode == FECModeStr.OFF:
            logger.debug(f"{self.port} fec mode required")
        elif fec_mode == FECModeStr.FC_FEC and not is_fc_fec_supported:
            logger.debug(f"{self.port} not support fec.fc_fec")
        elif fec_mode == FECModeStr.ON and bin_str[-2:] in ["00", "11"]:
            logger.debug(f"{self.port} not support fec.on")

    def get_ip_address(self) -> Union[IPv4Address, IPv6Address, None]:
        return self.port_config.ip_properties.address

    async def set_tpld_mode(self, use_micro_tpld: bool) -> None:
        if use_micro_tpld and not bool(self.port.info.capabilities.can_micro_tpld):
            raise exceptions.MicroTPLDNotSupport()
        await self.port.tpld_mode.set(enums.TPLDMode(int(use_micro_tpld)))
