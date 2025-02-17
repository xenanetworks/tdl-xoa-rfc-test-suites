from ..utils.constants import TidAllocationScope
from typing import Iterable


class IDControl:
    def __init__(
        self,
        resource_name: Iterable[str],
        curr_tpld_index: int,
        tid_allocation_scope: TidAllocationScope,
    ) -> None:
        self.curr_tpld_index = self.orginal_tpld_index = curr_tpld_index
        self.curr_stream_id_map = dict.fromkeys(resource_name, 0)
        self.tid_allocation_scope = tid_allocation_scope
        self.resource_name = resource_name
        self.curr_tpld_index_map = dict.fromkeys(resource_name, 0)

    def reset_tpld_index(self) -> None:
        self.curr_tpld_index = self.orginal_tpld_index

    def get_next_stream_id(self, port_name: str) -> int:
        self.curr_stream_id_map[port_name] += 1
        return self.curr_stream_id_map[port_name] - 1

    def allocate_new_tid(self, dest_port_name: str) -> int:
        if self.tid_allocation_scope == TidAllocationScope.RX_PORT_SCOPE:
            next_index = self.curr_tpld_index_map[dest_port_name]
            self.curr_tpld_index_map[dest_port_name] += 1
        elif self.tid_allocation_scope == TidAllocationScope.CONFIGURATION_SCOPE:
            next_index = self.curr_tpld_index
            self.curr_tpld_index += 1
        else:
            return 0
        return next_index

    def get_tid(self, dest_port_name: str) -> int:
        if self.tid_allocation_scope == TidAllocationScope.RX_PORT_SCOPE:
            return self.curr_tpld_index_map[dest_port_name]
        elif self.tid_allocation_scope == TidAllocationScope.CONFIGURATION_SCOPE:
            return self.curr_tpld_index
        else:
            return 0
