"""
main.py — FastAPI application entry point. Wires all components together.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from .db import init_db, get_db, insert_event, upsert_feed_health
from .clock import LiveClock, VirtualClock, set_clock, now as clock_now
from .models import FeedHealth
from .geo import all_district_names

# ---------------------------------------------------------------------------
# Scenario weather / air helpers
# ---------------------------------------------------------------------------

def _build_scenario_weather_raw(overrides: dict, t: datetime) -> dict:
    """Build an Open-Meteo-shaped current weather dict from scenario overrides."""
    rain = overrides.get("rain_mm_h", 0.0)
    gust = overrides.get("gust_kmh", 10.0)
    # Jaipur weather codes: 95 thunderstorm (monsoon), 61 rain, 0 clear.
    # A high-gust, low-rain event is the dust-storm (Andhi) signature.
    if rain > 20:
        code = 95          # thunderstorm / cloudburst
    elif rain > 1:
        code = 61          # moderate rain
    elif gust >= 60:
        code = 45          # dust / sand haze when dry and gusty
    else:
        code = 0
    return {
        "current": {
            "time": t.isoformat(),
            # Jaipur seasonal baseline (°C): hot pre-monsoon, milder in monsoon.
            "temperature_2m": 33.0 if rain < 1 else 27.0,
            "precipitation": rain,
            "wind_speed_10m": gust * 0.6,
            "wind_gusts_10m": gust,
            "weather_code": code,
            "relative_humidity_2m": 78.0 if rain > 1 else 25.0,
        }
    }


def _build_scenario_air_raw(aqi: float, t: datetime, particulates: dict | None = None) -> dict:
    """Build an Open-Meteo-shaped air quality dict from AQI override."""
    pm2_5 = round(aqi * 0.3, 1)
    pm10 = round(aqi * 0.5, 1)
    if particulates:
        pm2_5 = particulates.get("pm2_5", pm2_5)
        pm10 = particulates.get("pm10", pm10)
    return {
        "current": {
            "time": t.isoformat(),
            "us_aqi": aqi,
            "pm2_5": pm2_5,
            "pm10": pm10,
            "nitrogen_dioxide": round(aqi * 0.1, 1),
            "ozone": round(aqi * 0.2, 1),
        }
    }

# Add project root to path so simulator imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s — %(message)s")

app = FastAPI(title="CityPulse API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------------------------------------------------------------------------
# Load city config
# ---------------------------------------------------------------------------

_CITY_JSON_PATH = Path(__file__).parent.parent.parent / "city.json"
with open(_CITY_JSON_PATH) as f:
    _CITY = json.load(f)

DISTRICTS: list[dict] = _CITY["districts"]

# ---------------------------------------------------------------------------
# SSE subscriber registry
# ---------------------------------------------------------------------------

_subscribers: list[asyncio.Queue] = []

# Active PRD data mode: LIVE | REPLAY | SCENARIO. SCENARIO names are also
# accepted here and set the active scenario; REPLAY is driven by /api/replay.
_DATA_MODE: str = "LIVE"

async def _sse_emit(event_type: str, payload: dict) -> None:
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait({"event": event_type, "data": json.dumps(payload, default=str)})
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)

# ---------------------------------------------------------------------------
# Feed health state
# ---------------------------------------------------------------------------

FEED_HEALTH: dict[str, FeedHealth] = {
    "weather":   FeedHealth(source="weather",   status="ok", expected_interval_s=900,  is_simulated=False),
    "air":       FeedHealth(source="air",        status="ok", expected_interval_s=3600, is_simulated=False),
    "incidents": FeedHealth(source="incidents",  status="ok", expected_interval_s=60,   is_simulated=True),
    "transit":   FeedHealth(source="transit",    status="ok", expected_interval_s=90,   is_simulated=True),
}

def _persist_feed_health(conn):
    for h in FEED_HEALTH.values():
        upsert_feed_health(conn, {
            "source": h.source, "status": h.status,
            "last_ok_ts": h.last_ok_ts.isoformat() if h.last_ok_ts else None,
            "latency_ms": h.latency_ms, "expected_interval_s": h.expected_interval_s,
            "is_simulated": int(h.is_simulated),
        })

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    init_db()
    set_clock(LiveClock())
    global _DATA_MODE
    _DATA_MODE = "LIVE"

    # Seed baseline history (7 days synthetic) so anomaly detector works from tick 1
    log.info("Seeding baseline history…")
    try:
        from simulator.baseline import seed_baseline
        districts = [d["name"] for d in DISTRICTS]
        with get_db() as conn:
            # Only seed if table is empty
            count = conn.execute("SELECT COUNT(*) FROM events WHERE mode='baseline'").fetchone()[0]
            if count == 0:
                seed_baseline(conn, districts, days=7)
            else:
                log.info("Baseline already seeded (%d rows), skipping.", count)
    except Exception as exc:
        log.warning("Baseline seeding failed (non-fatal): %s", exc)

    asyncio.create_task(_feed_loop())
    asyncio.create_task(_analyzer_loop())
    log.info("CityPulse backend started ✓")

# ---------------------------------------------------------------------------
# Feed ingestion loop
# ---------------------------------------------------------------------------

WEATHER_INTERVAL_S  = int(os.getenv("WEATHER_INTERVAL_S", "900"))   # 15 min
AIR_INTERVAL_S      = int(os.getenv("AIR_INTERVAL_S", "3600"))       # 1 hour
SIM_INTERVAL_S      = int(os.getenv("SIM_INTERVAL_S", "60"))         # 1 min

def _load_replay_weather_cached() -> dict:
    """Load the Jaipur replay weather payload once per process."""
    cached = getattr(_load_replay_weather_cached, "_cache", None)
    if cached is None:
        from .adapters.replay import load_replay_weather
        cached = load_replay_weather()
        _load_replay_weather_cached._cache = cached
    return cached


async def _feed_loop():
    """Runs all feed adapters on their respective intervals."""
    weather_last  = 0.0
    air_last      = 0.0
    sim_last      = 0.0

    import time
    from .adapters.weather import fetch_all_districts as fetch_weather
    from .adapters.air import fetch_all_districts as fetch_air
    from .normalize import normalize_weather, normalize_air, normalize_incident, normalize_transit
    from simulator.incidents_sim import IncidentSimulator
    from simulator.transit_sim import TransitSimulator
    from simulator.scenarios import get_active as get_scenario

    inc_sim = IncidentSimulator(city_json_path=str(_CITY_JSON_PATH))
    tr_sim  = TransitSimulator()

    while True:
        now = time.monotonic()
        t   = clock_now()

        # ---- REPLAY: deterministic cached Jaipur historical stream ----
        if _DATA_MODE == "REPLAY":
            try:
                from .adapters.replay import (
                    get_replay_weather_series, iter_replay_events,
                    normalize_replay_row,
                )
                from datetime import timedelta as _td
                from .adapters.replay import REPLAY_START_UTC
                # Select the cached hour at the virtual clock's current position.
                # Re-running the same replay position is idempotent because event
                # IDs are deterministic and inserts use INSERT OR REPLACE.
                replay_hour = int(
                    (clock_now() - REPLAY_START_UTC).total_seconds() // 3600
                )
                slice_start = max(0, min(23, replay_hour))
                slice_end = slice_start + 1

                if replay_hour >= 0 and slice_end > slice_start:
                    replay_weather = _load_replay_weather_cached()
                    with get_db() as conn:
                        for district_cfg in DISTRICTS:
                            series = get_replay_weather_series(
                                district_cfg["name"], replay_weather
                            )
                            for dt, rain, gust in series[slice_start:slice_end]:
                                raw = {
                                    "current": {
                                        "time": dt.isoformat(),
                                        "precipitation": rain,
                                        "wind_gusts_10m": gust,
                                        "weather_code": 95 if rain > 10 else 0,
                                    }
                                }
                                for ev in normalize_weather(
                                    raw, district_cfg["lat"], district_cfg["lon"]
                                ):
                                    insert_event(conn, {
                                        **ev.model_dump(),
                                        "ts_utc": ev.ts_utc.isoformat(),
                                        "ingested_at": ev.ingested_at.isoformat(),
                                        "is_simulated": 0,
                                        "mode": "replay",
                                    })

                        # Inject civic complaint rows whose replay timestamp is in
                        # the current virtual-clock slice.
                        current_t = clock_now()
                        window_start = current_t - _td(hours=1)
                        for row in iter_replay_events():
                            raw = normalize_replay_row(row)
                            if not raw:
                                continue
                            event_t = datetime.fromisoformat(raw["reported_at"])
                            if not (window_start <= event_t <= current_t):
                                continue
                            ev = normalize_incident(raw)
                            if ev:
                                insert_event(conn, {
                                    **ev.model_dump(),
                                    "ts_utc": ev.ts_utc.isoformat(),
                                    "ingested_at": ev.ingested_at.isoformat(),
                                    "is_simulated": 0,
                                    "mode": "replay",
                                })

                FEED_HEALTH["weather"].is_simulated = False
                FEED_HEALTH["weather"].status = "ok"
                FEED_HEALTH["weather"].last_ok_ts = clock_now()
            except Exception as exc:
                log.warning("Replay ingestion error: %s", exc)
                FEED_HEALTH["weather"].status = "delayed"

        # ---- Weather (real; LIVE mode only) ----
        if _DATA_MODE == "LIVE" and FEED_HEALTH["weather"].status != "down" and (now - weather_last) >= WEATHER_INTERVAL_S:
            weather_last = now
            try:
                import time as _time; t0 = _time.monotonic()
                results = await fetch_weather(DISTRICTS)
                latency = (_time.monotonic() - t0) * 1000
                with get_db() as conn:
                    for lat, lon, raw in results:
                        for ev in normalize_weather(raw, lat, lon):
                            insert_event(conn, {**ev.model_dump(), "ts_utc": ev.ts_utc.isoformat(),
                                "ingested_at": ev.ingested_at.isoformat(), "is_simulated": int(ev.is_simulated), "mode": "live"})
                FEED_HEALTH["weather"].status = "ok"
                FEED_HEALTH["weather"].last_ok_ts = clock_now()
                FEED_HEALTH["weather"].latency_ms = latency
                log.info("Weather: fetched %d districts", len(results))
            except Exception as exc:
                log.warning("Weather fetch error: %s", exc)
                FEED_HEALTH["weather"].status = "delayed"

        # ---- Air quality (real; LIVE mode only) ----
        if _DATA_MODE == "LIVE" and FEED_HEALTH["air"].status != "down" and (now - air_last) >= AIR_INTERVAL_S:
            air_last = now
            try:
                import time as _time; t0 = _time.monotonic()
                results = await fetch_air(DISTRICTS)
                latency = (_time.monotonic() - t0) * 1000
                with get_db() as conn:
                    for lat, lon, raw in results:
                        for ev in normalize_air(raw, lat, lon):
                            insert_event(conn, {**ev.model_dump(), "ts_utc": ev.ts_utc.isoformat(),
                                "ingested_at": ev.ingested_at.isoformat(), "is_simulated": int(ev.is_simulated), "mode": "live"})
                FEED_HEALTH["air"].status = "ok"
                FEED_HEALTH["air"].last_ok_ts = clock_now()
                FEED_HEALTH["air"].latency_ms = latency
            except Exception as exc:
                log.warning("Air fetch error: %s", exc)
                FEED_HEALTH["air"].status = "delayed"

        # ---- Scenario weather / air injection (SCENARIO mode only) ----
        scenario = get_scenario()
        if _DATA_MODE == "SCENARIO" and scenario.name != "live":
            if scenario.weather_overrides:
                try:
                    with get_db() as conn:
                        for district_cfg in DISTRICTS:
                            d_name = district_cfg["name"]
                            overrides = scenario.weather_overrides.get(d_name, {})
                            if not overrides:
                                continue
                            raw = _build_scenario_weather_raw(overrides, t)
                            for ev in normalize_weather(raw, district_cfg["lat"], district_cfg["lon"]):
                                ev_dict = {**ev.model_dump(), "ts_utc": ev.ts_utc.isoformat(),
                                           "ingested_at": ev.ingested_at.isoformat(),
                                           "is_simulated": 1, "mode": "scenario"}
                                insert_event(conn, ev_dict)
                    FEED_HEALTH["weather"].is_simulated = True
                    FEED_HEALTH["weather"].status = "ok"
                    FEED_HEALTH["weather"].last_ok_ts = clock_now()
                except Exception as exc:
                    log.warning("Scenario weather injection error: %s", exc)

            if scenario.aqi_override is not None:
                try:
                    with get_db() as conn:
                        for district_cfg in DISTRICTS:
                            raw = _build_scenario_air_raw(
                                scenario.aqi_override, t,
                                particulates=scenario.particulate_override or None,
                            )
                            for ev in normalize_air(raw, district_cfg["lat"], district_cfg["lon"]):
                                ev_dict = {**ev.model_dump(), "ts_utc": ev.ts_utc.isoformat(),
                                           "ingested_at": ev.ingested_at.isoformat(),
                                           "is_simulated": 1, "mode": "scenario"}
                                insert_event(conn, ev_dict)
                    FEED_HEALTH["air"].is_simulated = True
                    FEED_HEALTH["air"].status = "ok"
                    FEED_HEALTH["air"].last_ok_ts = clock_now()
                except Exception as exc:
                    log.warning("Scenario air injection error: %s", exc)
        elif _DATA_MODE == "LIVE":
            # Live mode: reset is_simulated flags for real feeds
            FEED_HEALTH["weather"].is_simulated = False
            FEED_HEALTH["air"].is_simulated = False

        # ---- Simulators (SCENARIO mode only) ----
        if _DATA_MODE == "SCENARIO" and (now - sim_last) >= SIM_INTERVAL_S:
            sim_last = now
            scenario = get_scenario()

            # Incidents
            if FEED_HEALTH["incidents"].status != "down":
                try:
                    raw_incidents = inc_sim.generate(t, scenario_name=scenario.name)
                    with get_db() as conn:
                        for raw in raw_incidents:
                            ev = normalize_incident(raw)
                            if ev:
                                insert_event(conn, {**ev.model_dump(), "ts_utc": ev.ts_utc.isoformat(),
                                    "ingested_at": ev.ingested_at.isoformat(), "is_simulated": int(ev.is_simulated), "mode": "scenario"})
                    FEED_HEALTH["incidents"].status = "ok"
                    FEED_HEALTH["incidents"].last_ok_ts = clock_now()
                except Exception as exc:
                    log.warning("Incident sim error: %s", exc)
                    FEED_HEALTH["incidents"].status = "delayed"

            # Transit
            if FEED_HEALTH["transit"].status != "down":
                try:
                    raw_transit = tr_sim.generate(t, scenario_name=scenario.name)
                    with get_db() as conn:
                        for raw in raw_transit:
                            ev = normalize_transit(raw)
                            if ev:
                                insert_event(conn, {**ev.model_dump(), "ts_utc": ev.ts_utc.isoformat(),
                                    "ingested_at": ev.ingested_at.isoformat(), "is_simulated": int(ev.is_simulated), "mode": "scenario"})
                    FEED_HEALTH["transit"].status = "ok"
                    FEED_HEALTH["transit"].last_ok_ts = clock_now()
                except Exception as exc:
                    log.warning("Transit sim error: %s", exc)
                    FEED_HEALTH["transit"].status = "delayed"

        # Persist feed health snapshot
        with get_db() as conn:
            _persist_feed_health(conn)

        # Emit feed health over SSE
        await _sse_emit("feed_health", {"feeds": [h.model_dump(mode="json") for h in FEED_HEALTH.values()]})

        await asyncio.sleep(5)

# ---------------------------------------------------------------------------
# Analyzer loop
# ---------------------------------------------------------------------------

TICK_INTERVAL_S = int(os.getenv("TICK_INTERVAL_S", "5"))

async def _analyzer_loop():
    from .analyzer import run_tick
    while True:
        try:
            await run_tick(feed_health=FEED_HEALTH, sse_emit=_sse_emit)
        except Exception as exc:
            log.exception("Analyzer tick failed: %s", exc)
        await asyncio.sleep(TICK_INTERVAL_S)

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "ts": clock_now().isoformat()}


@app.get("/api/state")
async def get_state():
    with get_db() as conn:
        # Latest pulse per district
        pulse_rows = conn.execute("""
            SELECT DISTINCT district, pulse, level, components_json, ts
            FROM pulse_snapshots
            WHERE ts = (SELECT MAX(ts) FROM pulse_snapshots p2 WHERE p2.district = pulse_snapshots.district)
            ORDER BY district
        """).fetchall()

        city_pulse_row = conn.execute(
            "SELECT pulse, level, ts FROM pulse_snapshots ORDER BY ts DESC LIMIT 1"
        ).fetchone()

        insight_rows = conn.execute(
            "SELECT * FROM insights ORDER BY ts DESC LIMIT 10"
        ).fetchall()

    t = clock_now()
    districts_out = []
    for row in pulse_rows:
        comp = json.loads(row["components_json"]) if row["components_json"] else {}
        districts_out.append({
            "name": row["district"], "pulse": row["pulse"],
            "level": row["level"], "components": comp,
        })

    return {
        "ts": t.isoformat(),
        "mode": _DATA_MODE,
        "city_name": _CITY["city"],
        "center": _CITY["center"],
        "districts_config": DISTRICTS,
        "city": {
            "pulse": city_pulse_row["pulse"] if city_pulse_row else 75,
            "level": city_pulse_row["level"] if city_pulse_row else "Calm",
            "ts": city_pulse_row["ts"] if city_pulse_row else t.isoformat(),
            "districts": districts_out,
        },
        "feed_health": [h.model_dump(mode="json") for h in FEED_HEALTH.values()],
        "insights": [dict(r) for r in insight_rows],
    }


@app.get("/api/stream")
async def stream(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.append(queue)

    async def generator():
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

    return EventSourceResponse(generator())


@app.get("/api/timeseries")
async def timeseries(district: str, source: str, window: str = "6h"):
    from datetime import timedelta
    hours = int(window.rstrip("h")) if window.endswith("h") else 6
    t_now = clock_now()
    t_start = t_now - timedelta(hours=hours)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT ts_utc, value FROM events WHERE district=? AND source=? AND ts_utc>=? ORDER BY ts_utc",
            (district, source, t_start.isoformat()),
        ).fetchall()
    return {"district": district, "source": source, "window": window,
            "bins": [{"ts": r["ts_utc"], "value": r["value"]} for r in rows]}


@app.get("/api/insights")
async def get_insights(since: str = None):
    with get_db() as conn:
        if since:
            rows = conn.execute(
                "SELECT * FROM insights WHERE ts>=? ORDER BY ts DESC LIMIT 50", (since,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM insights ORDER BY ts DESC LIMIT 50"
            ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/weather")
async def get_weather():
    """Return latest weather readings per district: temperature, wind_speed, gust, rain, humidity."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT district, kind, value, unit, ts_utc
            FROM events
            WHERE source = 'weather'
              AND kind IN ('temperature', 'wind_speed', 'gust', 'rain_rate', 'humidity')
              AND ts_utc = (
                  SELECT MAX(ts_utc) FROM events e2
                  WHERE e2.source = 'weather' AND e2.kind = events.kind
                    AND e2.district = events.district
              )
            ORDER BY district, kind
        """).fetchall()

    # Group by district
    by_district: dict[str, dict] = {}
    for row in rows:
        d = row["district"]
        if d not in by_district:
            by_district[d] = {"district": d, "ts": row["ts_utc"]}
        by_district[d][row["kind"]] = {"value": row["value"], "unit": row["unit"]}

    return {"districts": list(by_district.values())}


@app.get("/api/insights/{insight_id}/explain")
async def explain(insight_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM insights WHERE id=?", (insight_id,)).fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"detail": "not found"})
    data = dict(row)
    for field in ("facts_json", "evidence_json", "caveats_json"):
        if data.get(field):
            try:
                data[field] = json.loads(data[field])
            except Exception:
                pass
    return data


@app.post("/api/demo/scenario")
async def set_scenario(body: dict):
    if os.getenv("DEMO_ENABLED", "true").lower() != "true":
        return JSONResponse(status_code=403, content={"detail": "demo not enabled"})
    from simulator.scenarios import set_active
    name = body.get("name", "live")
    speed = float(body.get("speed", 1.0))
    try:
        set_active(name)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    vc = VirtualClock(start=clock_now(), speed=speed)
    set_clock(vc)
    global _DATA_MODE
    _DATA_MODE = "SCENARIO"
    from simulator.scenarios import is_extreme
    if is_extreme(name):
        await _sse_emit("extreme_event", {
            "scenario": name,
            "city": _CITY["city"],
            "headline": {
                "dust_storm": "Dust storm (Andhi) warning",
                "monsoon": "Monsoon cloudburst",
            }.get(name, "Extreme weather event"),
            "status": "triggered",
            "simulated": True,
            "ts": clock_now().isoformat(),
        })
    log.info("Scenario: %s at %sx", name, speed)
    return {
        "ok": True, "mode": "SCENARIO", "scenario": name,
        "speed": speed, "is_extreme": is_extreme(name),
    }


@app.post("/api/demo/feed")
async def set_feed(body: dict):
    if os.getenv("DEMO_ENABLED", "true").lower() != "true":
        return JSONResponse(status_code=403, content={"detail": "demo not enabled"})
    source = body.get("source")
    mode = body.get("mode", "ok")
    if source not in FEED_HEALTH:
        return JSONResponse(status_code=400, content={"detail": f"unknown source: {source}"})
    FEED_HEALTH[source].status = mode
    await _sse_emit("feed_health", {"feeds": [h.model_dump(mode="json") for h in FEED_HEALTH.values()]})
    return {"ok": True, "source": source, "mode": mode}


@app.post("/api/replay")
async def start_replay(body: dict):
    from .adapters.replay import REPLAY_START_UTC, dataset_info
    speed = float(body.get("speed", 60.0))
    global _DATA_MODE
    from simulator.scenarios import set_active
    set_active("live")
    set_clock(VirtualClock(start=REPLAY_START_UTC, speed=speed))
    _DATA_MODE = "REPLAY"
    log.info("Jaipur replay started at %sx", speed)
    return {"ok": True, "mode": "REPLAY", "speed": speed, **dataset_info()}


@app.get("/api/demo/scenarios")
async def list_scenarios():
    """List available modes, including Jaipur extreme-event drills."""
    from simulator.scenarios import SCENARIOS
    return {
        "mode": _DATA_MODE,
        "scenarios": [
            {
                "name": s.name,
                "description": s.description,
                "headline": s.headline,
                "is_extreme": s.is_extreme,
            }
            for s in SCENARIOS.values()
        ],
    }


# ---------------------------------------------------------------------------
# Serve Vite frontend
# ---------------------------------------------------------------------------

_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="static")
