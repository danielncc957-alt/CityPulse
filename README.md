# CityPulse

> One glance should tell a resident what's really happening in their neighbourhood, and why it matters.

**Track B · AmiHacks · Industry / Open Innovation**

## Team Structure

| Folder | Role | Owner |
|---|---|---|
| `backend/` | P1 — Data/Backend Lead | Adapters, normalizer, SQLite, virtual clock, SSE, deploy |
| `backend/app/analyze/` + `backend/app/insights/` | P2 — Analytics/AI Lead | Stress, pulse, anomaly, correlation, insights, LLM, alerts |
| `frontend/` | P3 — Frontend Lead | Map, hexes, heartbeat, cards, timeline, feed-health UI |
| `simulator/` + `design/` | P4 — Simulation/Design/Story | Simulators, scenarios, design tokens, demo script |

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Add `?demo=1` to the URL for the demo control panel.

## Data Modes

- **LIVE**: real weather + air quality from Open-Meteo; simulated incidents + transit
- **REPLAY**: cached NYC 311 + weather data from 2023-09-29 (real flash-flood event)
- **SCENARIO**: scripted Storm / Smog / Quiet events with time-warp (1×, 10×, 60×)

## API

See `http://localhost:8000/docs` for the auto-generated FastAPI docs.

Key endpoints:
- `GET /api/state` — full city snapshot
- `GET /api/stream` — SSE push stream
- `GET /api/timeseries` — binned history
- `POST /api/demo/scenario` — trigger a scenario
- `POST /api/demo/feed` — kill/restore a feed

## Attribution

- Weather & Air Quality: [Open-Meteo](https://open-meteo.com) (CC BY 4.0)
- Map: MapLibre GL JS + CARTO Dark Matter
- NYC 311 replay data: [NYC Open Data](https://data.cityofnewyork.us/resource/erm2-nwe9.json)
