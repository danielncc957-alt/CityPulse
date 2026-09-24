# P1 — Data/Backend Lead

## Your folder: `backend/`

**You own:** Feed adapters, normalizer, SQLite DB, virtual clock, SSE stream, deploy (Dockerfile).

## Files you build

```
backend/
├─ app/
│  ├─ main.py          ← FastAPI app, SSE endpoint, static serving
│  ├─ clock.py         ← LiveClock / VirtualClock (shared with P2)
│  ├─ models.py        ← Pydantic Event, Insight, FeedHealth schemas
│  ├─ db.py            ← SQLite helpers (WAL mode)
│  ├─ geo.py           ← zone_of(lat,lon), H3 helpers
│  ├─ adapters/
│  │  ├─ weather.py    ← Open-Meteo Forecast (real)
│  │  ├─ air.py        ← Open-Meteo Air Quality (real)
│  │  ├─ replay.py       ← loads cached Jaipur CSV/JSON from data/replay/
│  │  ├─ incidents_sim.py  ← P4 builds this; you wire it in
│  │  └─ transit_sim.py    ← P4 builds this; you wire it in
│  └─ normalize.py     ← per-source raw → Event
├─ tests/
└─ requirements.txt
```

## Hour-by-hour targets

- **H0–1:** Spin up FastAPI. Expose mock `/api/state` and `/api/stream` SSE so P3 is unblocked immediately.
- **H1–4:** Weather + AQ adapters live. SQLite with WAL. Normalizer. Feed-health tracking.
- **H4–8:** Virtual clock. Wire in scenario engine from P4. SSE `pulse` events.
- **H8–12:** Feed kill toggles (`POST /api/demo/feed`). Time-warp controls. Late-arrival deduplication.
- **H12–15:** Graceful degradation (weight renormalization when a feed is down). Backend reconnect.
- **H15–18:** Jaipur replay loader. Dockerfile. README. Deploy backup.

## Contract with other roles

- Share `models.py` (Pydantic schemas) — P2 reads events, P3 reads API responses.
- `clock.now()` is used by P2's analyzer; never pass raw `datetime.now()` anywhere.
- Emit SSE events in the shape defined in §10 of the PRD.
- Keep `/api/health` returning `{"status":"ok"}` at all times.

## Key dependency

`clock.py` must be done by H4 so P2 can build the analyzer tick on top of it.
