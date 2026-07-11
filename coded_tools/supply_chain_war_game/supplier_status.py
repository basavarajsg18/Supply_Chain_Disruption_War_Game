"""
Coded tools that let each Supplier agent check its own status and shipping
route against the shared world state. Uses the same "base class + hardcoded
constructor argument per subclass" pattern as the smart_home example, so
each supplier agent's tool is a distinct, unambiguous CodedTool class while
sharing all the real logic.
"""

import logging
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.supply_chain_war_game import world_state

logger = logging.getLogger(__name__)


class SupplierStatusChecker(CodedTool):
    """
    Base CodedTool implementation that reports a single supplier's current
    status (capacity, lead time, cost) and its shipping route health.
    """

    def __init__(self, supplier_id: str):
        """
        :param supplier_id: the fixed supplier this instance always reports on,
            e.g. "Supplier_A" or "Supplier_B"
        """
        self.supplier_id = supplier_id

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        """
        :param args: unused -- this tool always reports on its own fixed supplier
        :param sly_data: unused
        :return: dict with "supplier" and "route" status, or an "error" key
        """
        supplier = world_state.get_supplier(self.supplier_id)
        route = world_state.get_route(self.supplier_id)
        if supplier is None:
            return {"error": f"No supplier record found for '{self.supplier_id}'."}

        logger.debug("Reporting status for %s: %s", self.supplier_id, supplier)
        return {"supplier_id": self.supplier_id, "supplier": supplier, "route": route}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return self.invoke(args, sly_data)


class SupplierAStatusAPI(SupplierStatusChecker):
    """CodedTool reporting on Supplier A (Vietnam - electronics sub-assemblies)."""

    def __init__(self):
        super().__init__("Supplier_A")


class SupplierBStatusAPI(SupplierStatusChecker):
    """CodedTool reporting on Supplier B (Mexico - final assembly parts)."""

    def __init__(self):
        super().__init__("Supplier_B")
