"""
main.py — FastAPI application entry point.
P1 owns this file.

Responsibilities:
  - Mount all API routes
  - Start the analyzer tick (background task)
  - Serve the built frontend from /dist
  - SSE stream endpoint
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from .db import init_db
from .clock import LiveClock, set_clock
from .models import StateResponse, FeedHealth

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(title="CityPulse API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory SSE subscriber registry
# ---------------------------------------------------------------------------

_subscribers: list[asyncio.Queue] = []

async def _sse_emit(event_type: str, payload: dict) -> None:
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait({"event": event_type, "data": json.dumps(payload)})
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)

# ---------------------------------------------------------------------------
# Feed health state (P1 maintains; P2 reads)
# ---------------------------------------------------------------------------

FEED_HEALTH: dict[str, FeedHealth] = {
    src: FeedHealth(source=src, status="ok", expected_interval_s=interval, is_simulated=sim)
    for src, interval, sim in [
        ("weather",   900,  False),
        ("air",       3600, False),
        ("incidents", 60,   True),
        ("transit",   90,   True),
    ]
}

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    init_db()
    set_clock(LiveClock())
    asyncio.create_task(_analyzer_loop())
    log.info("CityPulse backend started")


async def _analyzer_loop():
    """Background loop: run analytics tick every 5 s (demo) or 30 s (live)."""
    from .analyzer import run_tick
    tick_interval = int(os.getenv("TICK_INTERVAL_S", "5"))
    while True:
        try:
            await run_tick(feed_health=FEED_HEALTH, sse_emit=_sse_emit)
        except Exception as exc:
            log.exception("Analyzer tick failed: %s", exc)
        await asyncio.sleep(tick_interval)

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}

# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

@app.get("/api/state")
async def get_state():
    """Full snapshot — called on load and reconnect."""
    from .analyzer import run_tick
    from .db import get_db
    import sqlite3

    # Return last known pulse snapshot + recent insights
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM pulse_snapshots ORDER BY ts DESC LIMIT 50"
        ).fetchall()
        insights_rows = conn.execute(
            "SELECT * FROM insights ORDER BY ts DESC LIMIT 10"
        ).fetchall()

    # Build a minimal mock response if DB is empty (first call before first tick)
    from .clock import now as clock_now
    t = clock_now()
    return {
        "ts": t.isoformat(),
        "feed_health": [h.model_dump() for h in FEED_HEALTH.values()],
        "pulse_snapshots": [dict(r) for r in rows],
        "insights": [dict(r) for r in insights_rows],
    }

# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

@app.get("/api/stream")
async def stream(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.append(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            if queue in _subscribers:
                _subscribers.remove(queue)

    return EventSourceResponse(event_generator())

# ---------------------------------------------------------------------------
# Timeseries
# ---------------------------------------------------------------------------

@app.get("/api/timeseries")
async def timeseries(district: str, source: str, window: str = "6h"):
    from .db import get_db
    from .clock import now as clock_now
    from datetime import timedelta

    hours = int(window.rstrip("h")) if window.endswith("h") else 6
    t_now = clock_now()
    t_start = t_now - timedelta(hours=hours)

    with get_db() as conn:
        rows = conn.execute(
            "SELECT ts_utc, value FROM events WHERE district=? AND source=? AND ts_utc >= ? ORDER BY ts_utc",
            (district, source, t_start.isoformat()),
        ).fetchall()

    return {
        "district": district,
        "source": source,
        "window": window,
        "bins": [{"ts": r["ts_utc"], "value": r["value"]} for r in rows],
    }

# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

@app.get("/api/insights")
async def get_insights(since: str = None):
    with get_db() as conn:
        if since:
            rows = conn.execute(
                "SELECT * FROM insights WHERE ts >= ? ORDER BY ts DESC LIMIT 50",
                (since,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM insights ORDER BY ts DESC LIMIT 50"
            ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/insights/{insight_id}/explain")
async def explain_insight(insight_id: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM insights WHERE id = ?", (insight_id,)
        ).fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"detail": "not found"})
    data = dict(row)
    # Parse JSON fields
    for field in ("facts_json", "evidence_json", "caveats_json"):
        if data.get(field):
            data[field] = json.loads(data[field])
    return data

# ---------------------------------------------------------------------------
# Demo control (only when DEMO_ENABLED=true)
# ---------------------------------------------------------------------------

@app.post("/api/demo/scenario")
async def set_scenario(body: dict):
    if os.getenv("DEMO_ENABLED", "true").lower() != "true":
        return JSONResponse(status_code=403, content={"detail": "demo not enabled"})
    # P4's scenario engine handles this — stub for now
    name = body.get("name", "quiet")
    speed = body.get("speed", 1)
    from .clock import VirtualClock, set_clock, now as clock_now
    vc = VirtualClock(start=clock_now(), speed=float(speed))
    set_clock(vc)
    log.info("Scenario: %s at %sx", name, speed)
    return {"ok": True, "scenario": name, "speed": speed}


@app.post("/api/demo/feed")
async def set_feed_mode(body: dict):
    if os.getenv("DEMO_ENABLED", "true").lower() != "true":
        return JSONResponse(status_code=403, content={"detail": "demo not enabled"})
    source = body.get("source")
    mode = body.get("mode", "ok")
    if source in FEED_HEALTH:
        FEED_HEALTH[source].status = mode
        await _sse_emit("feed_health", {"feeds": [h.model_dump() for h in FEED_HEALTH.values()]})
    return {"ok": True, "source": source, "mode": mode}


@app.post("/api/replay")
async def start_replay(body: dict):
    dataset = body.get("dataset", "nyc_2023_09_29")
    speed = float(body.get("speed", 60))
    replay_start = datetime(2023, 9, 29, 0, 0, 0, tzinfo=timezone.utc)
    from .clock import VirtualClock, set_clock
    set_clock(VirtualClock(start=replay_start, speed=speed))
    log.info("Replay started: %s at %sx", dataset, speed)
    return {"ok": True, "dataset": dataset, "speed": speed}

# ---------------------------------------------------------------------------
# Serve frontend (built by Vite)
# ---------------------------------------------------------------------------

_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="static")
