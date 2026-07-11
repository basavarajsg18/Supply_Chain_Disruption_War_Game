# Supply Chain Disruption War Game

A live, multi-agent supply chain simulation built on
[`neuro-san-studio`](https://github.com/cognizant-ai-lab/neuro-san-studio),
backed by a real SQLite shared state and a live web dashboard. Inject a
disruption — a port strike, a supplier going offline, a demand spike —
and watch a mesh of specialist AI agents detect it and re-plan, live, in
chat. Watch and operate the same simulation visually from the dashboard,
in real time, from a second process reading the same state.

See [`architecture.md`](./architecture.md) for how the agent network and
data layer are put together, and [`summary.md`](./summary.md) for the
full project write-up.

## Project layout

This project is built to sit **inside a `neuro-san-studio` checkout**, so
a full clone also contains that framework's own scaffolding
(`config/`, `mcp/`, `logs/`, its base `aaosa*.hocon` example registries,
`nss_local.db`, `server_log.txt`, `.env`). The files and folders below are
what this project actually adds:

```
.
├── coded_tools/
│   └── supply_chain_war_game/
│       ├── __init__.py
│       ├── db.py                 # SQLite persistence layer
│       ├── world_state.py        # shared state API used by every agent tool
│       ├── warehouse.py          # WarehouseInventoryChecker, AdjustInventory, RunWeeklyReplenishment
│       ├── demand_forecast.py    # DemandForecastAPI
│       ├── disruption_control.py # InjectDisruption, ResetSimulation, GetSimulationStatus
│       ├── logistics.py          # RouteOptimizer
│       ├── supplier_status.py    # SupplierAStatusAPI, SupplierBStatusAPI
│       └── war_game.db           # SQLite database file (created/reseeded at runtime)
├── dashboard/
│   ├── app.py                    # Flask API, reuses world_state.py directly
│   └── static/
│       └── index.html            # live dashboard UI
├── registries/
│   ├── manifest.hocon
│   └── supply_chain_war_game.hocon   # agent network + tool definitions
├── requirements.txt
├── architecture.md
├── summary.md
└── README.md

# Provided by the neuro-san-studio base install (not part of this project):
# config/, mcp/, logs/, registries/aaosa*.hocon, registries/generated/,
# nss_local.db, server_log.txt, .env
```

## Prerequisites

- Python 3.10+
- A working `neuro-san-studio` installation ([setup guide](https://github.com/cognizant-ai-lab/neuro-san-studio))
- An LLM API key configured the way your `neuro-san-studio` install expects
  (e.g. `OPENAI_API_KEY`) — this project doesn't add any new LLM
  dependency beyond what `neuro-san-studio` already requires

## Setup

1. **Clone this repo into (or alongside) your `neuro-san-studio` checkout**
   so the folder layout above matches — `coded_tools/`, `registries/`, and
   `dashboard/` should all sit at the repo root, next to `neuro-san-studio`'s
   own `config/`, `mcp/`, and base registries.

2. **Create and activate a virtual environment, then install dependencies:**
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Point both processes at the same database file.** SQLite is
   file-based — the neuro-san server and the dashboard need to agree on
   exactly one path so they're reading/writing the same simulation state.
   This is separate from `neuro-san-studio`'s own `nss_local.db`, which
   is unrelated to this project.

   Windows (cmd):
   ```cmd
   set WAR_GAME_DB_PATH=%cd%\coded_tools\supply_chain_war_game\war_game.db
   ```
   Windows (PowerShell):
   ```powershell
   $env:WAR_GAME_DB_PATH = "$PWD\coded_tools\supply_chain_war_game\war_game.db"
   ```
   macOS/Linux:
   ```bash
   export WAR_GAME_DB_PATH="$(pwd)/coded_tools/supply_chain_war_game/war_game.db"
   ```
   Set this in **every terminal window** you use to run either process —
   it does not persist across new terminal sessions.

4. **Start the neuro-san agent server** (in a terminal with the env var
   set from step 3):
   ```bash
   python -m neuro_san_studio run
   ```
   Chat UI: `http://localhost:4173` — select `supply_chain_war_game`.

5. **Start the live dashboard**, in a second terminal (same venv, same
   `WAR_GAME_DB_PATH` exported):
   ```bash
   python dashboard/app.py
   ```
   Dashboard: `http://localhost:5050`

## Quick test

In the chat UI, try:
```
There's been a port strike at Supplier A's port, severity severe.
```
then switch to the dashboard tab — Supplier A's route should show
elevated/high risk within a few seconds, confirming both processes are
reading the same live state.

## Resetting

- From the dashboard: click **Reset to baseline**.
- From chat: say *"reset the simulation."*
- From scratch: stop both processes and delete
  `coded_tools/supply_chain_war_game/war_game.db` (and its `-wal`/`-shm`
  siblings, if present) — it will be reseeded automatically on next
  startup.
