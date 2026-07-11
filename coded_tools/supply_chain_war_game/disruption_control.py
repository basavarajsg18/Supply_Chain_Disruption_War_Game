"""
Coded tools that make up the "control room" of the war game.

These are the tools the presenter uses live, mid-demo, to inject a
disruption event (port strike, supplier going dark, demand spike) and watch
the rest of the agent mesh react and re-plan on the next turn.
"""

import logging
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.supply_chain_war_game import world_state

logger = logging.getLogger(__name__)


class InjectDisruption(CodedTool):
    """
    CodedTool that injects a live disruption event into the shared world
    state so every other agent in the network sees it on their next turn.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        """
        :param args: expects
            "event_type": one of "port_strike", "supplier_offline", "demand_spike", "resolve_event"
            "target": a supplier_id ("Supplier_A"/"Supplier_B") for port_strike/supplier_offline,
                a retail_id ("Retail_North"/"Retail_South"/"Retail_West") for demand_spike,
                or a disruption_id (e.g. "DISR-001") / "all" for resolve_event
            "severity": optional, one of "minor", "moderate", "severe" (default "moderate")
            "multiplier": optional float override, mainly for demand_spike
            "notes": optional free-text color for the scenario
        :param sly_data: unused
        :return: a dict describing what changed in the world, or an "error" key
        """
        event_type = args.get("event_type")
        target = args.get("target")
        severity = args.get("severity", "moderate")
        multiplier = args.get("multiplier")
        notes = args.get("notes", "")

        if not event_type or not target:
            return {"error": "Both 'event_type' and 'target' are required."}

        logger.info("Injecting disruption: %s on %s (severity=%s)", event_type, target, severity)
        result = world_state.inject_disruption(
            event_type=event_type,
            target=target,
            severity=severity,
            multiplier=multiplier,
            notes=notes,
        )
        return result

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return self.invoke(args, sly_data)


class ResetSimulation(CodedTool):
    """
    CodedTool that resets the whole scenario back to its nominal baseline.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        """
        :param args: unused
        :param sly_data: unused
        :return: the freshly reset world state
        """
        logger.info("Resetting supply chain simulation to baseline.")
        return world_state.reset_state()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return self.invoke(args, sly_data)


class GetSimulationStatus(CodedTool):
    """
    CodedTool that returns the full current world state plus a short summary
    of active disruptions and the most recent event log entries.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        """
        :param args: unused
        :param sly_data: unused
        :return: dict with "state", "active_disruptions", and "recent_events"
        """
        state = world_state.get_full_state()
        return {
            "state": state,
            "active_disruptions": state.get("active_disruptions", []),
            "recent_events": state.get("event_log", [])[-10:],
        }

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return self.invoke(args, sly_data)
