"""
db.py — SQLite helpers (WAL mode).
P1 owns this. P2 reads events and writes pulse_snapshots, insights, alerts_sent.
"""
from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

DB_PATH = Path(__file__).parent.parent.parent / "citypulse.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id          TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            ts_utc      TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            lat         REAL,
            lon         REAL,
            h3          TEXT,
            district    TEXT,
            kind        TEXT NOT NULL,
            value       REAL,
            unit        TEXT,
            severity    REAL NOT NULL,
            label       TEXT NOT NULL,
            is_simulated INTEGER NOT NULL DEFAULT 0,
            raw_ref     TEXT,
            mode        TEXT DEFAULT 'live'
        );
        CREATE INDEX IF NOT EXISTS idx_events_district_ts ON events(district, ts_utc);
        CREATE INDEX IF NOT EXISTS idx_events_source_ts   ON events(source, ts_utc);

        CREATE TABLE IF NOT EXISTS feed_health (
            source              TEXT PRIMARY KEY,
            status              TEXT NOT NULL DEFAULT 'ok',
            last_ok_ts          TEXT,
            latency_ms          REAL,
            expected_interval_s INTEGER NOT NULL,
            is_simulated        INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pulse_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT NOT NULL,
            district        TEXT NOT NULL,
            pulse           INTEGER NOT NULL,
            level           TEXT NOT NULL,
            components_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pulse_district_ts ON pulse_snapshots(district, ts);

        CREATE TABLE IF NOT EXISTS insights (
            id              TEXT PRIMARY KEY,
            ts              TEXT NOT NULL,
            district        TEXT NOT NULL,
            level           TEXT NOT NULL,
            headline        TEXT NOT NULL,
            why_it_matters  TEXT,
            facts_json      TEXT,
            evidence_json   TEXT,
            confidence      TEXT,
            method          TEXT,
            text_source     TEXT DEFAULT 'template',
            caveats_json    TEXT
        );

        CREATE TABLE IF NOT EXISTS alerts_sent (
            key         TEXT NOT NULL,
            ts          TEXT NOT NULL,
            PRIMARY KEY (key, ts)
        );
        """)


def insert_event(conn: sqlite3.Connection, event: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO events
          (id, source, ts_utc, ingested_at, lat, lon, h3, district,
           kind, value, unit, severity, label, is_simulated, raw_ref, mode)
        VALUES
          (:id, :source, :ts_utc, :ingested_at, :lat, :lon, :h3, :district,
           :kind, :value, :unit, :severity, :label, :is_simulated, :raw_ref, :mode)
        """,
        event,
    )


def query_events(
    conn: sqlite3.Connection,
    district: str,
    source: str,
    since: datetime,
    until: datetime,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM events
        WHERE district = ? AND source = ?
          AND ts_utc BETWEEN ? AND ?
        ORDER BY ts_utc ASC
        """,
        (district, source, since.isoformat(), until.isoformat()),
    ).fetchall()


def upsert_feed_health(conn: sqlite3.Connection, health: dict) -> None:
    conn.execute(
        """
        INSERT INTO feed_health (source, status, last_ok_ts, latency_ms,
                                  expected_interval_s, is_simulated)
        VALUES (:source, :status, :last_ok_ts, :latency_ms,
                :expected_interval_s, :is_simulated)
        ON CONFLICT(source) DO UPDATE SET
            status              = excluded.status,
            last_ok_ts          = excluded.last_ok_ts,
            latency_ms          = excluded.latency_ms,
            expected_interval_s = excluded.expected_interval_s,
            is_simulated        = excluded.is_simulated
        """,
        health,
    )


def insert_pulse_snapshot(conn: sqlite3.Connection, snap: dict) -> None:
    conn.execute(
        """
        INSERT INTO pulse_snapshots (ts, district, pulse, level, components_json)
        VALUES (:ts, :district, :pulse, :level, :components_json)
        """,
        snap,
    )


def insert_insight(conn: sqlite3.Connection, insight: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO insights
          (id, ts, district, level, headline, why_it_matters,
           facts_json, evidence_json, confidence, method, text_source, caveats_json)
        VALUES
          (:id, :ts, :district, :level, :headline, :why_it_matters,
           :facts_json, :evidence_json, :confidence, :method, :text_source, :caveats_json)
        """,
        insight,
    )


def recent_alerts(conn: sqlite3.Connection, key: str, window_s: int) -> list[sqlite3.Row]:
    """Check cooldown: return alerts sent for this key in the last window_s seconds."""
    from datetime import timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_s)).isoformat()
    return conn.execute(
        "SELECT * FROM alerts_sent WHERE key = ? AND ts > ?",
        (key, cutoff),
    ).fetchall()


def record_alert(conn: sqlite3.Connection, key: str, ts: datetime) -> None:
    conn.execute(
        "INSERT INTO alerts_sent (key, ts) VALUES (?, ?)",
        (key, ts.isoformat()),
    )
