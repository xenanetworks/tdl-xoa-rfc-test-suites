import math
import asyncio
from xoa_driver import utils
from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union
from .data_model import ArpRefreshData
from .setup_source_port_rates import setup_source_port_rates
from ..utils import exceptions, constants as const
from ..utils.scheduler import schedule
from ..utils.field import IPv4Address, IPv6Address
from ..utils.packet import ARPPacket, MacAddress, NDPPacket
from loguru import logger

if TYPE_CHECKING:
    from xoa_driver import misc
    from .test_resource import ResourceManager
    from .structure import PortStruct


def get_dest_ip_modifier_addr_range(
    port_struct: "PortStruct",
) -> Optional[range]:
    header_segments = port_struct.port_conf.profile.segments
    for header_segment in header_segments:
        if (not header_segment.type.is_ipv4) or (not header_segment.type.is_ipv6):
            continue

        for field in header_segment.fields:
            if field.name in ("Dest IP Addr", "Dest IPv6 Addr") and (
                modifier := field.hw_modifier
            ):
                return range(
                    modifier.start_value,
                    modifier.stop_value + 1,
                    modifier.step_value,
                )
    return None


def add_address_refresh_entry(
    port_struct: "PortStruct",
    source_ip: Union["IPv4Address", "IPv6Address", None],
    source_mac: Union["MacAddress", None],
) -> None:  # AddAddressRefreshEntry
    """ARP REFRESH STEP 1: generate address_refresh_data_set"""
    # is_ipv4 = port_struct.port_conf.profile.protocol_version.is_ipv4
    addr_range = get_dest_ip_modifier_addr_range(port_struct)
    port_struct.properties.address_refresh_data_set.add(
        ArpRefreshData(source_ip, source_mac, addr_range)
    )


def get_bytes_from_macaddress(dmac: "MacAddress") -> Iterator[str]:
    for i in range(0, len(dmac), 3):
        yield dmac[i : i + 2]


def get_link_local_uci_ipv6address(dmac: "MacAddress") -> str:
    b = get_bytes_from_macaddress(dmac)
    return f"FE80000000000000{int(next(b)) | 2 }{next(b)}{next(b)}FFFE{next(b)}{next(b)}{next(b)}"


def get_address_list(
    source_ip: Union["IPv4Address", "IPv6Address"],
    addr_range: Optional[range],
) -> List[Union["IPv4Address", "IPv6Address"]]:
    if not addr_range:
        return [source_ip]
    source_ip_list = []
    for i in addr_range:
        if isinstance(source_ip, IPv4Address):
            splitter = "."
            typing = IPv4Address
        else:
            splitter = ":"
            typing = IPv6Address

        addr = str(source_ip).split(splitter)
        addr[-1] = str(i)
        addr_str = splitter.join(addr)
        source_ip_list.append(typing(addr_str))

    return source_ip_list


async def get_address_learning_packet(
    port_struct: "PortStruct",
    arp_refresh_data: ArpRefreshData,
    use_gateway=False,
) -> List[str]:  # GetAddressLearningPacket
    """ARP REFRESH STEP 2: generate learning packet according to address_refresh_data_set"""
    dmac = MacAddress("FFFFFFFFFFFF")
    if not port_struct.port_conf.ip_address:
        raise exceptions.IPAddressMissing()
    gateway = port_struct.port_conf.ip_address.gateway
    sender_ip = port_struct.port_conf.ip_address.address
    if use_gateway and not gateway.is_empty:
        gwmac = port_struct.port_conf.ip_gateway_mac_address
        if not gwmac.is_empty:
            dmac = gwmac
    smac = (
        port_struct.properties.native_mac_address
        if not arp_refresh_data.source_mac or arp_refresh_data.source_mac.is_empty
        else arp_refresh_data.source_mac
    )
    source_ip = (
        sender_ip
        if not arp_refresh_data.source_ip or arp_refresh_data.source_ip.is_empty
        else arp_refresh_data.source_ip
    )
    source_ip_list = get_address_list(source_ip, arp_refresh_data.addr_range)
    packet_list = []
    for source_ip in source_ip_list:
        if port_struct.protocol_version.is_ipv4:
            destination_ip = sender_ip if gateway.is_empty else gateway
            packet = ARPPacket(
                smac=smac,
                source_ip=IPv4Address(source_ip),
                destination_ip=IPv4Address(destination_ip),
                dmac=dmac,
            ).make_arp_packet()

        else:
            destination_ip = get_link_local_uci_ipv6address(dmac)
            packet = NDPPacket(
                smac=smac,
                source_ip=IPv6Address(source_ip),
                destination_ip=IPv6Address(destination_ip),
                dmac=dmac,
            ).make_ndp_packet()
        packet_list.append(packet)
    return packet_list


async def setup_address_refresh(
    resources: "ResourceManager",
) -> List[Tuple["misc.Token", bool]]:  # SetupAddressRefresh
    address_refresh_tokens: List[Tuple["misc.Token", bool]] = []
    for port_struct in resources.port_structs:
        arp_data_set = port_struct.properties.address_refresh_data_set
        for arp_data in arp_data_set:
            packet_list = await get_address_learning_packet(
                port_struct,
                arp_data,
                resources.test_conf.use_gateway_mac_as_dmac,
            )
            for packet in packet_list:
                address_refresh_tokens.append(
                    (
                        port_struct.port_ins.tx_single_pkt.send.set(packet),
                        port_struct.port_conf.is_rx_only,
                    )
                )
        await port_struct.set_rx_tables()
    return address_refresh_tokens


async def setup_address_arp_refresh(
    resources: "ResourceManager",
) -> "AddressRefreshHandler":  # SetupAddressArpRefresh
    address_refresh_tokens = await setup_address_refresh(resources)
    return AddressRefreshHandler(
        address_refresh_tokens,
        resources.test_conf.arp_refresh_period_second,
    )


class AddressRefreshHandler:
    """set packet interval and return batch"""

    def __init__(
        self,
        address_refresh_tokens: List[Tuple["misc.Token", bool]],
        refresh_period: float,
    ) -> None:
        self.index = 0
        self.refresh_burst_size = 1
        self.tokens: List["misc.Token"] = []
        self.address_refresh_tokens = address_refresh_tokens
        self.interval = 0.0  # unit: second
        self.refresh_period = refresh_period
        self.state = const.TestState.L3_LEARNING

    def get_batch(self) -> List["misc.Token"]:
        packet_list = []
        if self.index >= len(self.tokens):
            self.index = 0
        for _ in range(self.refresh_burst_size):
            if self.index < len(self.tokens):
                packet_list.append(self.tokens[self.index])
                self.index += 1
        return packet_list

    def _calc_refresh_time_interval(
        self, refresh_tokens: List["misc.Token"]
    ) -> None:  # CalcRefreshTimerInternal
        total_refresh_count = len(refresh_tokens)
        if total_refresh_count > 0:
            self.refresh_burst_size = 1
            interval = math.floor(self.refresh_period / total_refresh_count)
            if interval < const.MIN_REFRESH_TIMER_INTERNAL:
                self.refresh_burst_size = math.ceil(
                    const.MIN_REFRESH_TIMER_INTERNAL / interval
                )
                interval = const.MIN_REFRESH_TIMER_INTERNAL
            self.interval = interval / 1000.0  # ms -> second

    def set_current_state(self, state: "const.TestState") -> "AddressRefreshHandler":
        """
        It will send arp refresh packet in two stage
        1. L3 learning
        2. Testcase running traffic
        """
        self.state = state
        if self.state == const.TestState.L3_LEARNING:
            self.tokens = [
                refresh_token[0] for refresh_token in self.address_refresh_tokens
            ]
        else:
            self.tokens = [
                refresh_token[0]
                for refresh_token in self.address_refresh_tokens
                if refresh_token[1]
            ]
        self._calc_refresh_time_interval(self.tokens)
        return self


async def generate_l3_learning_packets(
    _count: int,
    resources: "ResourceManager",
    address_refresh_handler: "AddressRefreshHandler",
) -> bool:
    tokens = address_refresh_handler.get_batch()
    await utils.apply(*tokens)

    return not resources.test_running()


async def send_l3_learning_packets(
    resources: "ResourceManager",
    address_refresh_handler: "AddressRefreshHandler",
) -> None:
    await schedule(
        address_refresh_handler.interval,
        "s",
        generate_l3_learning_packets,
        resources,
        address_refresh_handler,
    )


async def schedule_arp_refresh(
    resources: "ResourceManager",
    address_refresh_handler: Optional["AddressRefreshHandler"],
    state: const.TestState = const.TestState.RUNNING_TEST,
) -> None:
    # arp refresh jobs
    if address_refresh_handler:
        address_refresh_handler.set_current_state(state)
        if address_refresh_handler.tokens:
            await send_l3_learning_packets(resources, address_refresh_handler)


async def add_L2L3_learning_preamble_steps(
    resources: "ResourceManager",
    current_packet_size: float,
    address_refresh_handler: Optional["AddressRefreshHandler"] = None,
) -> None:  # AddL3LearningPreambleSteps
    """ set time limit and learning rate, then run traffic to warm up """
    resources.set_rate_percent(resources.test_conf.learning_rate_pct)
    await setup_source_port_rates(resources, current_packet_size)
    await resources.set_tx_time_limit(
        resources.test_conf.learning_duration_second * 1000
    )

    await resources.start_traffic()
    if address_refresh_handler:
        address_refresh_handler.set_current_state(const.TestState.L3_LEARNING)
        await asyncio.gather(*address_refresh_handler.tokens)
        await schedule_arp_refresh(
            resources, address_refresh_handler, const.TestState.L3_LEARNING
        )
    while resources.test_running():
        await resources.query_traffic_status()
        await asyncio.sleep(const.INTERVAL_CHECK_LEARNING_TRAFFIC)
    await resources.set_tx_time_limit(0)


async def add_flow_based_learning_preamble_steps(
    resources: "ResourceManager",
    current_packet_size: float,
) -> None:  # AddFlowBasedLearningPreambleSteps
    """ set frame limit and learning rate and run traffic """
    if (
        not resources.test_conf.use_flow_based_learning_preamble
    ):
        return
    resources.set_rate_percent(resources.test_conf.learning_rate_pct)
    await setup_source_port_rates(resources, current_packet_size)
    await resources.set_frame_limit(
        resources.test_conf.flow_based_learning_frame_count
    )
    await resources.start_traffic()
    while resources.test_running():
        await resources.query_traffic_status()
        await asyncio.sleep(const.INTERVAL_CHECK_LEARNING_TRAFFIC)
    await asyncio.sleep(resources.test_conf.delay_after_flow_based_learning_ms / 1000)
    await resources.set_frame_limit(0)  # clear packet limit


def make_mac_token(
    send_struct: "PortStruct", hex_data: str
) -> "misc.Token":
    # logger.debug(send_struct.port_identity.name)
    packet = hex_data
    max_cap = send_struct.capabilities.max_xmit_one_packet_length
    cur_length = len(hex_data) // 2
    if cur_length > max_cap:
        raise exceptions.PacketLengthExceed(cur_length, max_cap)
    return send_struct.send_packet(packet)  # P_XMITONE


async def add_mac_learning_steps(
    resources: "ResourceManager",
    require_mode: "const.MACLearningMode",
) -> None:
    """ send raw packet for mac learning """
    if (
        require_mode
        != resources.test_conf.mac_learning_mode
    ):
        return

    mac_learning_frame_count = (
        resources.test_conf.mac_learning_frame_count
    )
    none_mac = "FFFFFFFFFFFF"
    four_f = "FFFF"
    paddings = "00" * 118
    tasks = []
    done_struct = []
    for port_struct in resources.port_structs:
        for stream_struct in port_struct.stream_structs:
            src_hex_data = f"{none_mac}{stream_struct._addr_coll.smac.to_hexstring()}{four_f}{paddings}"
            if port_struct.port_identity.name not in done_struct:
                tokens = make_mac_token(
                    port_struct, src_hex_data
                )
                tasks.append(tokens)
                done_struct.append(port_struct.port_identity.name)
            for dest_port_struct in stream_struct._rx_ports:
                dest_hex_data = f"{none_mac}{stream_struct._addr_coll.dmac.to_hexstring()}{four_f}{paddings}"
                if dest_port_struct.port_identity.name in done_struct:
                    continue
                tokens = make_mac_token(
                    dest_port_struct, dest_hex_data
                )
                done_struct.append(dest_port_struct.port_identity.name)
                tasks.append(tokens)
    for _ in range(mac_learning_frame_count):
        await asyncio.gather(*tasks)
        await asyncio.sleep(const.DELAY_LEARNING_MAC)
