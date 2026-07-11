"""
SQLite-backed persistence for the Supply Chain Disruption War Game.

Using SQLite here (instead of just keeping everything in memory) means
game state survives a neuro-san server restart, and it also means the
DB can be shared across processes -- specifically the neuro-san agent
server and the standalone dashboard in dashboard/app.py -- as long as
they're both pointed at the same file.

If you care where the .db file ends up, set WAR_GAME_DB_PATH to an
absolute path. This matters if the dashboard and neuro-san get started
from different working directories -- just make sure they're both
pointed at the same absolute path, or they'll end up writing to two
different databases. If you don't set it, it defaults to a file
sitting next to this module.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

_LOCK = threading.RLock()

DB_PATH = os.environ.get(
    "WAR_GAME_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "war_game.db"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    region TEXT NOT NULL,
    base_lead_time_days INTEGER NOT NULL,
    lead_time_days INTEGER,
    unit_cost REAL NOT NULL,
    base_capacity_units_per_week INTEGER NOT NULL,
    capacity_units_per_week INTEGER NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routes (
    supplier_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    corridor TEXT NOT NULL,
    base_cost_per_unit REAL NOT NULL,
    cost_per_unit REAL NOT NULL,
    base_transit_days INTEGER NOT NULL,
    transit_days INTEGER NOT NULL,
    risk_level TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouse (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    location TEXT NOT NULL,
    current_inventory_units INTEGER NOT NULL,
    safety_stock_units INTEGER NOT NULL,
    capacity_units INTEGER NOT NULL,
    base_inbound_units_next_7_days INTEGER NOT NULL,
    inbound_units_next_7_days INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS retail (
    retail_id TEXT PRIMARY KEY,
    base_weekly_demand INTEGER NOT NULL,
    current_weekly_demand INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS disruptions (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    target TEXT NOT NULL,
    severity TEXT NOT NULL,
    notes TEXT,
    description TEXT,
    injected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT,
    resulting_total INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """
    Yields a SQLite connection configured for safe multi-process access
    (WAL mode + a busy timeout so the dashboard and neuro-san don't step on
    each other), with sqlite3.Row so results behave like dicts.
    """
    with _LOCK:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _baseline_rows():
    """Returns the nominal 'everything is fine' baseline as row tuples."""
    suppliers = [
        ("Supplier_A", "Supplier A (Vietnam - electronics sub-assemblies)", "Vietnam",
         12, 12, 8.50, 5000, 5000, "online"),
        ("Supplier_B", "Supplier B (Mexico - final assembly parts)", "Mexico",
         6, 6, 9.75, 3000, 3000, "online"),
    ]
    routes = [
        ("Supplier_A", "Ocean Freight", "Port of Long Beach", 1.20, 1.20, 18, 18, "low"),
        ("Supplier_B", "Land Freight", "Laredo Crossing", 0.60, 0.60, 4, 4, "low"),
    ]
    warehouse = (1, "Central Distribution Center (Ohio)", 18000, 8000, 30000, 4000, 4000)
    retail = [
        ("Retail_North", 4000, 4000),
        ("Retail_South", 3500, 3500),
        ("Retail_West", 5000, 5000),
    ]
    return suppliers, routes, warehouse, retail


def reset_to_baseline() -> None:
    """Wipes and reseeds the whole database back to the nominal baseline."""
    suppliers, routes, warehouse, retail = _baseline_rows()
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        conn.execute("DELETE FROM suppliers")
        conn.execute("DELETE FROM routes")
        conn.execute("DELETE FROM warehouse")
        conn.execute("DELETE FROM retail")
        conn.execute("DELETE FROM disruptions")
        conn.executemany(
            "INSERT INTO suppliers VALUES (?,?,?,?,?,?,?,?,?)", suppliers
        )
        conn.executemany(
            "INSERT INTO routes VALUES (?,?,?,?,?,?,?,?)", routes
        )
        conn.execute(
            "INSERT INTO warehouse VALUES (?,?,?,?,?,?,?)", warehouse
        )
        conn.executemany(
            "INSERT INTO retail VALUES (?,?,?)", retail
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('disruption_seq', '0')"
        )
        conn.execute(
            "INSERT INTO event_log (timestamp, message) VALUES (?, ?)",
            (now(), "Simulation initialized. All nodes nominal."),
        )


def ensure_initialized() -> None:
    """Creates the schema and seeds baseline data on first run only."""
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        row = conn.execute("SELECT COUNT(*) AS n FROM warehouse").fetchone()
        already_seeded = row["n"] > 0
    if not already_seeded:
        reset_to_baseline()


def next_disruption_id(conn: sqlite3.Connection) -> str:
    """
    Allocates the next disruption id using the CALLER's already-open
    connection/transaction (rather than opening a second one), since a
    second writer connection mid-transaction would deadlock against the
    first under SQLite's WAL locking.
    """
    row = conn.execute("SELECT value FROM meta WHERE key = 'disruption_seq'").fetchone()
    seq = int(row["value"]) + 1 if row else 1
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('disruption_seq', ?)",
        (str(seq),),
    )
    return f"DISR-{seq:03d}"


ensure_initialized()