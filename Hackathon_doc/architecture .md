# Architecture — Supply Chain Disruption War Game

## What this project does

A live, multi-agent "war game" simulation of a small end-to-end supply
chain — 2 suppliers → 1 logistics/routing layer → 1 warehouse → 3 retail
demand points. A presenter (or any user) can inject real-world
disruptions live — a port strike, a supplier going dark, a demand spike
— and watch a mesh of LLM agents detect the change, reason about it, and
re-plan, entirely on their own, on the very next turn. A companion live
web dashboard shows the same state visually and lets anyone intervene
outside the chat.

The goal was to demonstrate genuine **agentic behavior**: agents that
independently query shared ground truth, reason about trade-offs (cost
vs. speed vs. risk), and coordinate a response — not a single LLM call
dressed up as "agents."

## Why an agentic system, specifically

A single LLM call can't do this well because the problem is inherently
**distributed and stateful**:

- Each node (supplier, warehouse, retail point) has its own live data and
  its own narrow responsibility, and its own objective that doesn't
  always agree with the others — a warehouse agent is optimizing against
  stockout/overstock risk, a logistics agent against cost and route risk,
  and neither should need to know the other's domain.
- The *interesting* behavior is **cross-agent reasoning**: the Logistics
  agent's routing recommendation only makes sense in light of what the
  Supplier agents and Warehouse agent are currently reporting. A
  Coordinator has to synthesize multiple, sometimes competing specialist
  views into one decision — the same trade-off conversation a real
  supply-chain team would have.
- Disruptions are injected **live, mid-conversation**, and every agent
  has to react to a state it didn't know about a moment ago — this is
  what actually tests whether the system is agentic (perceiving →
  reasoning → acting on fresh information) rather than just retrieving a
  static answer.

## Agent network (built on neuro-san / AAOSA)

```
                        ┌─────────────────────┐
                        │      Coordinator      │
                        │  (front agent, owns    │
                        │  the final decision)   │
                        └──────────┬─────────────┘
              ┌───────────────────┼───────────────────┬──────────────────┐
              ▼                   ▼                    ▼                  ▼
   ┌────────────────┐  ┌────────────────────┐  ┌──────────────────┐  ┌─────────────────┐
   │ SupplierRelations│  │  LogisticsPlanner  │  │ WarehouseOperations│  │ DemandForecasting │
   │    Manager       │  │  (route optimizer)  │  │                    │  │      Unit         │
   └───────┬─────────┘  └──────────┬──────────┘  └─────────┬──────────┘  └─────────┬─────────┘
           ▼                       ▼                        ▼                       ▼
   Supplier_A / Supplier_B    RouteOptimizerTool    WarehouseInventoryTool    DemandForecastAPI
   status tools                                     AdjustInventoryTool
                                                      RunWeeklyReplenishmentTool
```

Each specialist agent has one or more **coded tools** — real Python
functions, not hallucinated numbers — that read and write a shared world
state. The Coordinator delegates to specialists via the AAOSA
(Agents-as-Orchestrated-Sub-Agents) pattern already provided by
`neuro-san-studio`, collects their reports, and produces one synthesized
recommendation. The full network and tool wiring live in
`registries/supply_chain_war_game.hocon`.

A separate **DisruptionControlRoom** exposes `InjectDisruptionTool`,
`ResetSimulationTool`, and `GetSimulationStatusTool` — this is how a live
demo (or the dashboard) perturbs the simulation without touching any
agent's internal logic.

## Shared state: from in-memory to a real database

The original prototype kept all state in a single in-process Python
dict. That's fine for a scripted demo, but breaks the moment you want:

- state to survive a server restart,
- more than one process reading/writing it (e.g. a dashboard alongside
  the agent server), or
- a credible "this behaves like a real backend" story for judges.

**What changed:** `world_state.py` now reads and writes a **SQLite**
database (`db.py`), using WAL mode so two processes (the neuro-san server
and the dashboard) can safely share one `.db` file concurrently.
Critically, **every function's name, arguments, and return shape are
unchanged** — so four of the five original coded tools
(`demand_forecast.py`, `disruption_control.py`, `logistics.py`,
`supplier_status.py`) needed zero changes at all. Only `warehouse.py`
gained two new tools.

This project's database (`war_game.db`, path set via `WAR_GAME_DB_PATH`)
is entirely separate from `neuro-san-studio`'s own `nss_local.db` — the
two are unrelated and don't share any tables or state.

```
Coded Tool (unchanged) ──calls──▶ world_state.py (rewritten) ──calls──▶ db.py (new, SQLite)
        ▲                                                                      ▲
        │                                                                      │
   neuro-san agent mesh                                          dashboard/app.py (Flask)
   (reads/writes)                                                (reads/writes, same DB file)
```

## New capabilities added on top of the original prototype

1. **`AdjustInventoryTool`** — lets the Warehouse agent (or a human, via
   the dashboard) apply a real, audited stock change: "a shipment
   arrived," "units were damaged," a manual count correction. Every
   change is logged to an `inventory_log` table.
2. **`RunWeeklyReplenishmentTool`** — advances the simulation by one
   week: every **online** supplier ships its full weekly capacity into
   the warehouse; an **offline** supplier contributes zero. The total is
   capped at the warehouse's physical capacity, with any overflow
   explicitly reported rather than silently discarded. This is what
   makes a `supplier_offline` disruption have a real, compounding
   consequence over time instead of being a status label.
3. **Live dashboard** (`dashboard/`) — a standalone Flask app plus a
   single dark "control room" HTML/JS page. It imports the same
   `world_state` module the agents use, so it is not a separate mock UI
   — it is a second live view into the exact same simulation. Add stock,
   inject a disruption, or resolve one from the dashboard, and the agent
   mesh sees it on its very next tool call, and vice versa.

## Data flow for one disruption, end to end

1. A disruption is injected (via chat → `InjectDisruptionTool`, or via
   the dashboard's "Inject Disruption" panel — both call the exact same
   `world_state.inject_disruption()` function).
2. `world_state.py` writes the change into SQLite and appends a
   human-readable line to the shared `event_log`.
3. On the next relevant question in chat, each specialist agent calls
   its own read-only tool (`SupplierStatusChecker`, `RouteOptimizer`,
   `WarehouseInventoryChecker`, `DemandForecastAPI`) — each of these
   queries the *same* database, so they all see the disruption
   immediately, with no agent-to-agent message passing required for
   state propagation.
4. The Coordinator synthesizes the specialists' reports into one
   recommendation, weighing whatever priority the user asked for (cost,
   speed, risk).
5. The dashboard, polling every 3 seconds, reflects the same change
   independently, without going through the agent mesh at all.

## Why this design choice (SQLite + shared read/write functions) matters

It's the one architectural decision that makes both "agentic" and "real
product" true at the same time: the agents remain simple, single-purpose
tool callers with no awareness of persistence, while the persistence
layer underneath them can be swapped (e.g. for Postgres, if this needed
to scale to concurrent multiplayer games) without touching a single
agent definition or coded tool signature.
