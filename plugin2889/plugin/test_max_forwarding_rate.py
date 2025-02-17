from loguru import logger
from typing import TYPE_CHECKING

from plugin2889.const import PortGroup
from plugin2889.dataset import PortPair
from plugin2889.dataset import MaxForwardingRateConfiguration
from plugin2889.plugin.test_forwarding import ForwardingBase
from plugin2889.plugin.utils import group_by_port_property
if TYPE_CHECKING:
    from plugin2889.plugin.utils import PortPairs


class MaxForwardingRateTest(ForwardingBase[MaxForwardingRateConfiguration]):
    def create_port_pairs(self) -> "PortPairs":
        assert self.test_suit_config.port_role_handler
        group_by_result = group_by_port_property(self.full_test_config.ports_configuration, self.test_suit_config.port_role_handler, self.port_identities)
        logger.debug(group_by_result)
        source_port_uuid = group_by_result.port_role_uuids[PortGroup.SOURCE][0]
        destination_port_uuid = group_by_result.port_role_uuids[PortGroup.DESTINATION][0]
        pairs = (
            PortPair(
                west=group_by_result.uuid_port_name[source_port_uuid],
                east=group_by_result.uuid_port_name[destination_port_uuid],
            ),
        )
        logger.debug(pairs)
        return pairs
