"""
Live dashboard backend for the Supply Chain Disruption War Game.

This is a small, standalone Flask app -- it is NOT a neuro-san agent. It
imports the exact same coded_tools.supply_chain_war_game.world_state /
db modules that the agent mesh uses, so as long as this process and your
neuro-san server point at the same WAR_GAME_DB_PATH, they are looking at
the same live data. Change something here (add stock, inject a
disruption) and the agents will see it on their very next tool call --
and vice versa.

Run from the repo root (the directory that contains coded_tools/):

    pip install flask
    export WAR_GAME_DB_PATH=$(pwd)/coded_tools/supply_chain_war_game/war_game.db
    python dashboard/app.py

Then open http://localhost:5050
"""

import os
import sys

# Make sure the repo root (parent of this dashboard/ folder) is importable
# so "coded_tools.supply_chain_war_game.*" resolves the same way it does
# inside neuro-san.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

from coded_tools.supply_chain_war_game import world_state  # noqa: E402

app = Flask(__name__, static_folder="static", static_url_path="")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/state")
def api_state():
    state = world_state.get_full_state()
    retail = state["retail"]
    total_current = sum(r["current_weekly_demand"] for r in retail.values())
    daily_demand = total_current / 7.0 if total_current else 0.0
    warehouse = state["warehouse"]
    days_of_supply = (
        round(warehouse["current_inventory_units"] / daily_demand, 1) if daily_demand else None
    )
    state["computed"] = {
        "total_weekly_demand": total_current,
        "days_of_supply": days_of_supply,
        "stockout_risk": days_of_supply is not None and days_of_supply < 10,
        "overstock_risk": warehouse["current_inventory_units"] > 0.9 * warehouse["capacity_units"],
    }
    return jsonify(state)


@app.get("/api/inventory-log")
def api_inventory_log():
    return jsonify(world_state.get_inventory_log(50))


@app.post("/api/warehouse/adjust")
def api_adjust_stock():
    body = request.get_json(force=True) or {}
    try:
        units = int(round(float(body.get("units"))))
    except (TypeError, ValueError):
        return jsonify({"error": "units must be a number"}), 400
    reason = body.get("reason", "") or "manual dashboard adjustment"
    result = world_state.adjust_inventory(units, reason)
    return jsonify(result)


@app.post("/api/disruption/inject")
def api_inject():
    body = request.get_json(force=True) or {}
    event_type = body.get("event_type")
    target = body.get("target")
    if not event_type or not target:
        return jsonify({"error": "event_type and target are required"}), 400
    result = world_state.inject_disruption(
        event_type=event_type,
        target=target,
        severity=body.get("severity", "moderate"),
        multiplier=body.get("multiplier"),
        notes=body.get("notes", ""),
    )
    return jsonify(result)


@app.post("/api/disruption/resolve")
def api_resolve():
    body = request.get_json(force=True) or {}
    target = body.get("target")
    if not target:
        return jsonify({"error": "target (a disruption id, or 'all') is required"}), 400
    result = world_state.resolve_disruption(target)
    return jsonify(result)


@app.post("/api/warehouse/replenish")
def api_replenish():
    body = request.get_json(force=True) or {}
    result = world_state.run_weekly_replenishment(body.get("notes", ""))
    return jsonify(result)


@app.post("/api/reset")
def api_reset():
    return jsonify(world_state.reset_state())


if __name__ == "__main__":
    port = int(os.environ.get("DASHBOARD_PORT", "5050"))
    print(f"Supply Chain War Game dashboard: http://localhost:{port}")
    print(f"Using DB: {os.environ.get('WAR_GAME_DB_PATH', '(default, next to world_state.py)')}")
    app.run(host="0.0.0.0", port=port, debug=True)