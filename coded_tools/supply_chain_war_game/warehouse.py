"""
Coded tools for the Warehouse agent:
  - WarehouseInventoryChecker: check current inventory position against
    live retail demand, flagging stockout or overstock risk.
  - AdjustInventory: apply a real stock change (restock, damage, manual
    correction, etc.) to the warehouse's current inventory. This is what
    lets the network -- or the live dashboard -- actually change how much
    stock is remaining, instead of only ever recomputing it from demand.
"""

import logging
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.supply_chain_war_game import world_state

logger = logging.getLogger(__name__)


class WarehouseInventoryChecker(CodedTool):
    """
    CodedTool reporting the warehouse's current inventory position, days of
    supply remaining given current total retail demand, and whether that
    trips a stockout or overstock warning.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        """
        :param args: unused
        :param sly_data: unused
        :return: dict with warehouse numbers plus computed days_of_supply and risk flags
        """
        warehouse = world_state.get_warehouse()
        retail = world_state.get_all_retail()

        total_weekly_demand = sum(r["current_weekly_demand"] for r in retail.values())
        daily_demand = total_weekly_demand / 7.0 if total_weekly_demand else 0.0
        days_of_supply = (
            round(warehouse["current_inventory_units"] / daily_demand, 1) if daily_demand else None
        )

        stockout_risk = days_of_supply is not None and days_of_supply < 10
        overstock_risk = warehouse["current_inventory_units"] > 0.9 * warehouse["capacity_units"]

        logger.debug(
            "Warehouse check: inventory=%s, weekly_demand=%s, days_of_supply=%s",
            warehouse["current_inventory_units"],
            total_weekly_demand,
            days_of_supply,
        )

        return {
            "warehouse": warehouse,
            "total_weekly_demand_across_retail": total_weekly_demand,
            "days_of_supply": days_of_supply,
            "stockout_risk": stockout_risk,
            "overstock_risk": overstock_risk,
        }

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return self.invoke(args, sly_data)


class AdjustInventory(CodedTool):
    """
    CodedTool that applies a real, persisted stock change to the warehouse
    -- e.g. "we just received a truck of 2000 units" or "1500 units were
    damaged in transit and written off". Positive units add stock,
    negative units remove it. The result is clamped between 0 and the
    warehouse's capacity_units, and every change is written to an
    inventory audit log.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        """
        :param args: expects
            "units": signed integer/float, e.g. 2000 to add stock, -1500 to remove it
            "reason": optional free-text reason, e.g. "inbound shipment received"
        :param sly_data: unused
        :return: dict with the applied delta, message, and updated warehouse state
        """
        units = args.get("units")
        reason = args.get("reason", "")

        if units is None:
            return {"error": "'units' is required (positive to add stock, negative to remove it)."}
        try:
            units = int(round(float(units)))
        except (TypeError, ValueError):
            return {"error": f"'units' must be a number, got {units!r}."}

        logger.info("Adjusting warehouse inventory by %s units (reason=%s)", units, reason)
        return world_state.adjust_inventory(units, reason)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return self.invoke(args, sly_data)


class RunWeeklyReplenishment(CodedTool):
    """
    CodedTool that advances the simulation by one week: every ONLINE
    supplier ships its full weekly capacity into the warehouse, an
    OFFLINE supplier ships nothing, and the total is added to warehouse
    stock (capped at capacity, with any overflow reported). This is what
    makes a supplier going offline actually starve the warehouse over
    time instead of just being a status label.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        """
        :param args: expects
            "notes": optional free-text context, e.g. "week 3"
        :param sly_data: unused
        :return: dict with per-supplier breakdown, units shipped/received/overflow,
            and the updated warehouse state
        """
        notes = args.get("notes", "")
        logger.info("Running weekly replenishment (notes=%s)", notes)
        return world_state.run_weekly_replenishment(notes)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return self.invoke(args, sly_data)