"""
Coded tool that lets the Logistics agent evaluate both supplier shipping
routes against the shared world state and recommend a routing strategy
under a chosen priority (cost, speed, or risk).
"""

import logging
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.supply_chain_war_game import world_state

logger = logging.getLogger(__name__)

_RISK_SCORE = {"low": 1, "elevated": 2, "high": 3}


class RouteOptimizer(CodedTool):
    """
    CodedTool that compares the live cost/transit-time/risk of both supplier
    shipping routes and recommends how to route/split inbound volume.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        """
        :param args: expects
            "prioritize": optional, one of "cost", "speed", or "risk" (default "cost")
        :param sly_data: unused
        :return: dict with each route's live numbers plus a ranked recommendation
        """
        prioritize = (args or {}).get("prioritize", "cost").lower()
        if prioritize not in ("cost", "speed", "risk"):
            prioritize = "cost"

        routes = {}
        for supplier_id in ("Supplier_A", "Supplier_B"):
            supplier = world_state.get_supplier(supplier_id)
            route = world_state.get_route(supplier_id)
            if supplier is None or route is None:
                continue
            routes[supplier_id] = {
                "supplier_status": supplier["status"],
                "capacity_units_per_week": supplier["capacity_units_per_week"],
                "mode": route["mode"],
                "corridor": route["corridor"],
                "cost_per_unit": route["cost_per_unit"],
                "transit_days": route["transit_days"],
                "risk_level": route["risk_level"],
                "available": supplier["status"] == "online",
            }

        def sort_key(item):
            supplier_id, data = item
            if not data["available"]:
                # Unavailable suppliers sort last regardless of priority.
                return (1, 0)
            if prioritize == "cost":
                metric = data["cost_per_unit"]
            elif prioritize == "speed":
                metric = data["transit_days"]
            else:  # risk
                metric = _RISK_SCORE.get(data["risk_level"], 2)
            return (0, metric)

        ranked = sorted(routes.items(), key=sort_key)
        recommendation_lines = []
        for rank, (supplier_id, data) in enumerate(ranked, start=1):
            status_note = "AVAILABLE" if data["available"] else "OFFLINE - cannot ship"
            recommendation_lines.append(
                f"#{rank} {supplier_id} via {data['corridor']} ({data['mode']}): "
                f"${data['cost_per_unit']}/unit, {data['transit_days']}d transit, "
                f"risk={data['risk_level']} [{status_note}]"
            )

        logger.debug("Route comparison (prioritize=%s): %s", prioritize, routes)
        return {
            "prioritized_on": prioritize,
            "routes": routes,
            "ranked_recommendation": recommendation_lines,
        }

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return self.invoke(args, sly_data)
