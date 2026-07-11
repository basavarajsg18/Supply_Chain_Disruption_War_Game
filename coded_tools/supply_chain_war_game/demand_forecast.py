"""
Coded tool that lets the Demand Forecast agent report what retail demand
actually looks like right now, across all three retail points, flagging any
that have spiked above their baseline.
"""

import logging
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.supply_chain_war_game import world_state

logger = logging.getLogger(__name__)


class DemandForecastAPI(CodedTool):
    """
    CodedTool reporting current vs. baseline weekly demand at every retail
    point, so the forecast agent can flag which ones have spiked.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        """
        :param args: unused
        :param sly_data: unused
        :return: dict with per-retail-point demand numbers and spike flags
        """
        retail = world_state.get_all_retail()
        report = {}
        for retail_id, data in retail.items():
            baseline = data["base_weekly_demand"]
            current = data["current_weekly_demand"]
            delta_pct = round(100.0 * (current - baseline) / baseline, 1) if baseline else 0.0
            report[retail_id] = {
                "baseline_weekly_demand": baseline,
                "current_weekly_demand": current,
                "delta_pct_vs_baseline": delta_pct,
                "spiking": current > baseline,
            }

        total_current = sum(r["current_weekly_demand"] for r in retail.values())
        total_baseline = sum(r["base_weekly_demand"] for r in retail.values())

        logger.debug("Demand forecast report: %s", report)
        return {
            "by_retail_point": report,
            "total_current_weekly_demand": total_current,
            "total_baseline_weekly_demand": total_baseline,
        }

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return self.invoke(args, sly_data)
