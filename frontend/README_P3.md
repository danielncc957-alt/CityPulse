# P3 — Frontend Lead

## Your folder: `frontend/`

**You own:** React app — hex map, heartbeat header, insight cards, timeline, feed-health UI, demo panel.

## Setup

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
# Then add dependencies (see requirements below)
npm run dev
```

## Dependencies to install

```bash
npm install \
  react-map-gl maplibre-gl \
  h3-js \
  recharts \
  framer-motion \
  zustand \
  tailwindcss @tailwindcss/vite \
  @types/geojson
```

## Files you build

```
frontend/src/
├─ types.ts            ← mirrors backend Pydantic models (agree with P1 at H0)
├─ api.ts              ← REST calls + SSE EventSource connection
├─ store.ts            ← Zustand store (SSE events push in here)
├─ components/
│  ├─ PulseHeader.tsx  ← ECG heartbeat line + pulse ring + status word + headline
│  ├─ HexMap.tsx       ← MapLibre hex layer, incident dots, click → drawer
│  ├─ InsightCards.tsx ← top 3 zones, feed chips, "Why we think this" expander
│  ├─ WhyPanel.tsx     ← evidence drawer: feeds, window, r-value, lag, badges
│  ├─ Timeline.tsx     ← Recharts lanes per feed, anomaly markers, scrubber
│  ├─ FeedHealth.tsx   ← status chips per feed (ok / delayed / down / SIM)
│  ├─ Ticker.tsx       ← scrolling bottom bar of recent insights
│  └─ DemoPanel.tsx    ← hidden behind ?demo=1 — scenario/speed/kill-feed controls
└─ App.tsx
```

## Hour-by-hour targets

- **H0–1:** Scaffold with Vite + Tailwind. Wire up `api.ts` against P1's mock `/api/state`. Map renders with placeholder hexes.
- **H1–4:** Hex layer coloured by mock pulse. Layout skeleton matching PRD §9.2.
- **H4–8:** Connect to real SSE stream. Heartbeat header animating. Hex colours from real pulse data.
- **H8–12:** Insight cards + WhyPanel. Timeline lanes. Feed health chips.
- **H12–15:** Heartbeat irregularity tied to stress. Ticker. Empty/quiet state. Reduced-motion support. 1280×720 check.
- **H15–18:** Replay scrubber. DemoPanel. Mobile viewport.

## Design tokens (from PRD §9.4)

| Level | Colour | Hex |
|---|---|---|
| Calm | Teal | `#2DD4BF` |
| Watch | Yellow | `#FBBF24` |
| Strained | Orange | `#F97316` |
| Alert | Magenta-red | `#E11D48` |

Background: `#0F172A` (dark slate). Typography: Inter (body) + JetBrains Mono (numbers).

Always pair colour with status word + icon — never rely on colour alone.

## SSE event types to handle

- `pulse` → update city + district pulse in store
- `insight` → prepend to insights list
- `feed_health` → update feed chips
- `event` → add to timeline
- `alert` → show toast notification

## Map notes

- Free basemap: `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`
- Draw hexes as GeoJSON polygons coloured by pulse level
- Show incident dots only for zones with ≥3 reports (privacy rule)
- Click hex → open district detail drawer
- Attribution badge required (MapLibre + CARTO)
