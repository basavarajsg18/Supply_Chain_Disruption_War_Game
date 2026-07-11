"""
Shared world state for the Supply Chain Disruption War Game.

State lives in a SQLite database (see db.py) rather than a bare module
dict, so it survives process restarts and can be read and written from
more than one process at once -- both the neuro-san agent mesh and the
standalone dashboard in dashboard/app.py, as long as they're pointed at
the same WAR_GAME_DB_PATH.

Every CodedTool in this network imports `world_state` and calls its
functions -- get_supplier, get_route, get_warehouse, get_all_retail,
get_retail, list_active_disruptions, inject_disruption,
resolve_disruption, reset_state, get_full_state -- to read or mutate the
game world. Because the state is shared through the DB, a disruption or
stock change made from the dashboard is immediately visible to the agent
mesh's next tool call, and vice versa.

adjust_inventory() lets a warehouse's stock be topped up or drawn down
directly, rather than only being recomputed from demand. It backs both
the AdjustInventoryTool coded tool and the dashboard's "add stock"
control.
"""

import logging
from typing import Any, Dict, List, Optional

from coded_tools.supply_chain_war_game import db

logger = logging.getLogger(__name__)

VALID_EVENT_TYPES = ("port_strike", "supplier_offline", "demand_spike", "resolve_event")


def reset_state() -> Dict[str, Any]:
    """Resets the whole world back to the nominal baseline scenario."""
    db.reset_to_baseline()
    return get_full_state()


def get_full_state() -> Dict[str, Any]:
    """Returns the entire current world state."""
    return {
        "suppliers": _all_suppliers(),
        "routes": _all_routes(),
        "warehouse": get_warehouse(),
        "retail": get_all_retail(),
        "active_disruptions": list_active_disruptions(),
        "event_log": _recent_events(200),
    }


def _all_suppliers() -> Dict[str, Any]:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM suppliers").fetchall()
    return {row["supplier_id"]: _supplier_row_to_dict(row) for row in rows}


def _all_routes() -> Dict[str, Any]:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM routes").fetchall()
    return {row["supplier_id"]: _route_row_to_dict(row) for row in rows}


def _supplier_row_to_dict(row) -> Dict[str, Any]:
    return {
        "display_name": row["display_name"],
        "region": row["region"],
        "base_lead_time_days": row["base_lead_time_days"],
        "lead_time_days": row["lead_time_days"],
        "unit_cost": row["unit_cost"],
        "base_capacity_units_per_week": row["base_capacity_units_per_week"],
        "capacity_units_per_week": row["capacity_units_per_week"],
        "status": row["status"],
    }


def _route_row_to_dict(row) -> Dict[str, Any]:
    return {
        "mode": row["mode"],
        "corridor": row["corridor"],
        "base_cost_per_unit": row["base_cost_per_unit"],
        "cost_per_unit": row["cost_per_unit"],
        "base_transit_days": row["base_transit_days"],
        "transit_days": row["transit_days"],
        "risk_level": row["risk_level"],
    }


def get_supplier(supplier_id: str) -> Optional[Dict[str, Any]]:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM suppliers WHERE supplier_id = ?", (supplier_id,)
        ).fetchone()
    return _supplier_row_to_dict(row) if row else None


def get_route(supplier_id: str) -> Optional[Dict[str, Any]]:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM routes WHERE supplier_id = ?", (supplier_id,)
        ).fetchone()
    return _route_row_to_dict(row) if row else None


def get_warehouse() -> Dict[str, Any]:
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM warehouse WHERE id = 1").fetchone()
    return {
        "location": row["location"],
        "current_inventory_units": row["current_inventory_units"],
        "safety_stock_units": row["safety_stock_units"],
        "capacity_units": row["capacity_units"],
        "base_inbound_units_next_7_days": row["base_inbound_units_next_7_days"],
        "inbound_units_next_7_days": row["inbound_units_next_7_days"],
    }


def get_retail(retail_id: str) -> Optional[Dict[str, Any]]:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM retail WHERE retail_id = ?", (retail_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "base_weekly_demand": row["base_weekly_demand"],
        "current_weekly_demand": row["current_weekly_demand"],
    }


def get_all_retail() -> Dict[str, Any]:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM retail").fetchall()
    return {
        row["retail_id"]: {
            "base_weekly_demand": row["base_weekly_demand"],
            "current_weekly_demand": row["current_weekly_demand"],
        }
        for row in rows
    }


def list_active_disruptions() -> List[Dict[str, Any]]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM disruptions ORDER BY injected_at ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def _recent_events(limit: int) -> List[Dict[str, Any]]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT timestamp, message FROM event_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{"timestamp": r["timestamp"], "message": r["message"]} for r in reversed(rows)]


def _log(conn, message: str) -> None:
    conn.execute(
        "INSERT INTO event_log (timestamp, message) VALUES (?, ?)", (db.now(), message)
    )
    # Keep the log from growing unbounded in a long demo session.
    conn.execute(
        "DELETE FROM event_log WHERE id NOT IN "
        "(SELECT id FROM event_log ORDER BY id DESC LIMIT 200)"
    )


# --------------------------------------------------------------------- #
# Stock / inventory control -- new capability
# --------------------------------------------------------------------- #

def adjust_inventory(delta_units: int, reason: str = "") -> Dict[str, Any]:
    """
    Adds (positive delta) or removes (negative delta) units from the
    warehouse's current inventory, clamped to [0, capacity_units].
    Logs the change so there's a real audit trail of every manual stock
    adjustment, e.g. from the live dashboard or a coded tool call.

    :param delta_units: signed integer change to apply
    :param reason: free-text reason, e.g. "manual restock", "damaged goods"
    :return: dict with the updated warehouse state and the applied delta
    """
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM warehouse WHERE id = 1").fetchone()
        capacity = row["capacity_units"]
        new_total = max(0, min(capacity, row["current_inventory_units"] + int(delta_units)))
        actual_delta = new_total - row["current_inventory_units"]
        conn.execute(
            "UPDATE warehouse SET current_inventory_units = ? WHERE id = 1", (new_total,)
        )
        conn.execute(
            "INSERT INTO inventory_log (timestamp, delta, reason, resulting_total) "
            "VALUES (?, ?, ?, ?)",
            (db.now(), actual_delta, reason, new_total),
        )
        verb = "added to" if actual_delta >= 0 else "removed from"
        msg = (
            f"STOCK UPDATE: {abs(actual_delta)} units {verb} warehouse "
            f"(reason: {reason or 'unspecified'}). New total: {new_total} units."
        )
        _log(conn, msg)

    logger.info("Inventory adjusted by %s (%s). New total: %s", actual_delta, reason, new_total)
    return {
        "applied_delta": actual_delta,
        "reason": reason,
        "message": msg,
        "warehouse": get_warehouse(),
    }


def get_inventory_log(limit: int = 50) -> List[Dict[str, Any]]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT timestamp, delta, reason, resulting_total FROM inventory_log "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def run_weekly_replenishment(notes: str = "") -> Dict[str, Any]:
    """
    Simulates one week passing: every ONLINE supplier ships its full
    capacity_units_per_week into the warehouse; an OFFLINE supplier ships
    nothing. The total is added to warehouse stock, capped at the
    warehouse's capacity_units -- any surplus that can't fit is reported
    as lost/overflow rather than silently discarded.

    :param notes: optional free-text context, e.g. "week 3 of the demo"
    :return: dict with the per-supplier breakdown, total shipped, how much
        actually landed, any overflow, and the updated warehouse state
    """
    with db.get_conn() as conn:
        suppliers = conn.execute("SELECT * FROM suppliers").fetchall()
        breakdown = {}
        total_shipped = 0
        for s in suppliers:
            shipped = s["capacity_units_per_week"] if s["status"] == "online" else 0
            breakdown[s["supplier_id"]] = shipped
            total_shipped += shipped

        row = conn.execute("SELECT * FROM warehouse WHERE id = 1").fetchone()
        capacity = row["capacity_units"]
        new_total = min(capacity, row["current_inventory_units"] + total_shipped)
        actual_added = new_total - row["current_inventory_units"]
        overflow = total_shipped - actual_added

        conn.execute(
            "UPDATE warehouse SET current_inventory_units = ? WHERE id = 1", (new_total,)
        )
        reason = "weekly replenishment" + (f" ({notes})" if notes else "")
        conn.execute(
            "INSERT INTO inventory_log (timestamp, delta, reason, resulting_total) "
            "VALUES (?, ?, ?, ?)",
            (db.now(), actual_added, reason, new_total),
        )

        parts = ", ".join(f"{sid}: {units} units" for sid, units in breakdown.items())
        msg = (
            f"WEEKLY REPLENISHMENT: suppliers shipped {total_shipped} units total ({parts}). "
            f"{actual_added} units received into warehouse. New total: {new_total} units."
        )
        if overflow > 0:
            msg += f" WARNING: {overflow} units could not fit -- warehouse is at capacity ({capacity})."
        _log(conn, msg)

    logger.info(
        "Weekly replenishment: shipped=%s, received=%s, overflow=%s",
        total_shipped, actual_added, overflow,
    )
    return {
        "supplier_breakdown": breakdown,
        "total_shipped": total_shipped,
        "actual_received": actual_added,
        "overflow_lost": overflow,
        "message": msg,
        "warehouse": get_warehouse(),
    }


# --------------------------------------------------------------------- #
# Disruption injection / resolution
# --------------------------------------------------------------------- #

def inject_disruption(
    event_type: str,
    target: str,
    severity: str = "moderate",
    multiplier: Optional[float] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Applies a live disruption event to the shared world state.
    Same contract as before: same args, same return shape.
    """
    if event_type not in VALID_EVENT_TYPES:
        return {"error": f"Unknown event_type '{event_type}'. Valid types: {VALID_EVENT_TYPES}"}

    if event_type == "resolve_event":
        return resolve_disruption(target)

    severity_scale = {"minor": 1, "moderate": 2, "severe": 3}.get(severity, 2)

    with db.get_conn() as conn:
        if event_type == "port_strike":
            row = conn.execute(
                "SELECT * FROM routes WHERE supplier_id = ?", (target,)
            ).fetchone()
            if row is None:
                return {"error": f"No shipping route found for supplier '{target}'."}
            new_transit = row["base_transit_days"] * (1 + severity_scale)
            new_cost = round(row["base_cost_per_unit"] * (1 + 0.4 * severity_scale), 2)
            new_risk = "high" if severity_scale >= 2 else "elevated"
            conn.execute(
                "UPDATE routes SET transit_days = ?, cost_per_unit = ?, risk_level = ? "
                "WHERE supplier_id = ?",
                (new_transit, new_cost, new_risk, target),
            )
            msg = (
                f"PORT STRIKE at {row['corridor']} ({row['mode']}, {target}): "
                f"transit time now {new_transit}d, cost now ${new_cost}/unit, risk={new_risk}."
            )

        elif event_type == "supplier_offline":
            row = conn.execute(
                "SELECT * FROM suppliers WHERE supplier_id = ?", (target,)
            ).fetchone()
            if row is None:
                return {"error": f"No supplier found with id '{target}'."}
            conn.execute(
                "UPDATE suppliers SET status = 'offline', capacity_units_per_week = 0, "
                "lead_time_days = NULL WHERE supplier_id = ?",
                (target,),
            )
            msg = f"SUPPLIER OFFLINE: {row['display_name']} ({target}) has gone dark. 0 capacity."

        elif event_type == "demand_spike":
            row = conn.execute(
                "SELECT * FROM retail WHERE retail_id = ?", (target,)
            ).fetchone()
            if row is None:
                return {"error": f"No retail demand point found with id '{target}'."}
            spike_multiplier = multiplier if multiplier else (1.0 + 0.5 * severity_scale)
            new_demand = int(round(row["base_weekly_demand"] * spike_multiplier))
            conn.execute(
                "UPDATE retail SET current_weekly_demand = ? WHERE retail_id = ?",
                (new_demand, target),
            )
            msg = (
                f"DEMAND SPIKE at {target}: weekly demand jumped from "
                f"{row['base_weekly_demand']} to {new_demand} units ({spike_multiplier}x baseline)."
            )

        else:  # pragma: no cover - guarded above
            return {"error": f"Unhandled event_type '{event_type}'."}

        disruption_id = db.next_disruption_id(conn)
        record = {
            "id": disruption_id,
            "event_type": event_type,
            "target": target,
            "severity": severity,
            "notes": notes,
            "description": msg,
            "injected_at": db.now(),
        }
        conn.execute(
            "INSERT INTO disruptions (id, event_type, target, severity, notes, description, injected_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                disruption_id, event_type, target, severity, notes, msg, record["injected_at"],
            ),
        )
        _log(conn, msg)

    logger.info("Injected disruption: %s on %s (severity=%s)", event_type, target, severity)
    return {"disruption": record, "message": msg}


def resolve_disruption(disruption_id: str) -> Dict[str, Any]:
    """
    Resolves (reverts) a previously injected disruption by id, or "all" to
    clear every active disruption and restore full baseline for
    suppliers/routes/retail (warehouse stock is left untouched).
    """
    with db.get_conn() as conn:
        if disruption_id == "all":
            cleared = [r["id"] for r in conn.execute("SELECT id FROM disruptions").fetchall()]
            suppliers, routes, _warehouse, retail = db._baseline_rows()
            conn.execute("DELETE FROM suppliers")
            conn.execute("DELETE FROM routes")
            conn.execute("DELETE FROM retail")
            conn.executemany("INSERT INTO suppliers VALUES (?,?,?,?,?,?,?,?,?)", suppliers)
            conn.executemany("INSERT INTO routes VALUES (?,?,?,?,?,?,?,?)", routes)
            conn.executemany("INSERT INTO retail VALUES (?,?,?)", retail)
            conn.execute("DELETE FROM disruptions")
            _log(conn, "All active disruptions resolved. Network restored to baseline.")
            return {"resolved": cleared, "message": "All disruptions resolved."}

        match = conn.execute(
            "SELECT * FROM disruptions WHERE id = ?", (disruption_id,)
        ).fetchone()
        if match is None:
            return {"error": f"No active disruption found with id '{disruption_id}'."}

        event_type, target = match["event_type"], match["target"]
        if event_type == "port_strike":
            base = conn.execute(
                "SELECT base_cost_per_unit, base_transit_days FROM routes WHERE supplier_id = ?",
                (target,),
            ).fetchone()
            conn.execute(
                "UPDATE routes SET transit_days = ?, cost_per_unit = ?, risk_level = 'low' "
                "WHERE supplier_id = ?",
                (base["base_transit_days"], base["base_cost_per_unit"], target),
            )
        elif event_type == "supplier_offline":
            base = conn.execute(
                "SELECT base_capacity_units_per_week, base_lead_time_days FROM suppliers "
                "WHERE supplier_id = ?",
                (target,),
            ).fetchone()
            conn.execute(
                "UPDATE suppliers SET status = 'online', capacity_units_per_week = ?, "
                "lead_time_days = ? WHERE supplier_id = ?",
                (base["base_capacity_units_per_week"], base["base_lead_time_days"], target),
            )
        elif event_type == "demand_spike":
            base = conn.execute(
                "SELECT base_weekly_demand FROM retail WHERE retail_id = ?", (target,)
            ).fetchone()
            conn.execute(
                "UPDATE retail SET current_weekly_demand = ? WHERE retail_id = ?",
                (base["base_weekly_demand"], target),
            )

        conn.execute("DELETE FROM disruptions WHERE id = ?", (disruption_id,))
        msg = f"Resolved {disruption_id} ({event_type} on {target}). That factor is back to baseline."
        _log(conn, msg)

    return {"resolved": [disruption_id], "message": msg}