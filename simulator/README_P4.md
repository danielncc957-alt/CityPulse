# P4 — Simulation / Design / Story

## Your folders: `simulator/` and `design/`

**You own:** Incident + transit simulators, scenario engine, design tokens, copy rules, demo script, QA checklist runs, slides.

## Files you build

```
simulator/
├─ incidents_sim.py    ← Poisson incident generator (messy format: ISO-8601 with tz offset)
├─ transit_sim.py      ← Route delay generator (messy format: epoch seconds)
├─ scenarios.py        ← Storm / Smog / Quiet scripts with multipliers per district
└─ baseline.py         ← 7-day seeded synthetic history warm-up

design/
├─ tokens.json         ← colour, type, spacing tokens
├─ copy_rules.md       ← sentence rules, banned words, tone guide
└─ demo_script.md      ← 3-min narrative, cue-by-cue
```

## Hour-by-hour targets

- **H1–4:** Build both simulators with **deliberately messy formats** (see below). Seed 7-day baseline.
- **H4–8:** Scenario engine (Storm / Smog / Quiet). Tune multipliers so the storm scenario is visually obvious.
- **H8–12:** Design tokens in `tokens.json`. Write `copy_rules.md`. Draft demo script.
- **H12–15:** Run QA checklist (§14 of PRD) at H12. Report bugs. Quiet-state copy ("All quiet. Here's what we're watching.").
- **H15–18:** Run QA checklist at H15. Refine demo script. Prepare slides / backup video.
- **H18–19:** Final QA run. Failure drills (Wi-Fi off, kill each feed, LLM 429, restart backend).

## Simulator specs

### Incident simulator (`incidents_sim.py`)
- **Deliberately messy timestamp format:** ISO-8601 with timezone offset e.g. `"2026-09-24T10:32:11+05:30"` (normalizer must handle this)
- Fields: `report_id` (UUID), `reported_at` (ISO+tz), `category`, `sub_category`, `lat`, `lon`
- Complaint types: Sewer, Water System, Street Condition, Traffic Signal, Damaged Tree, Noise
- Rate: Poisson with `base_rate[district][hour_of_day] × scenario_multiplier`

### Transit simulator (`transit_sim.py`)
- **Deliberately messy timestamp format:** epoch seconds (integer) — no timezone, normalizer must convert
- Fields: `route_id`, `update_epoch` (int), `delay_s` (seconds — normalizer converts to minutes), `status`
- Routes: A C E 1 2 3 4 5 6 7 B D F G J L M N Q R W (mapped to districts via `city.json`)
- Cadence: new batch every 60–90 s

### Scenario multipliers (examples)
| Scenario | Riverside rain boost | Transit delay boost | Air quality boost |
|---|---|---|---|
| Storm | 6× incidents, rain_mm_h=12 | 3× delays | 1× (no change) |
| Smog | 1× incidents | 1× | AQI spike to 180 |
| Quiet | 0.3× incidents | 0.5× delays | AQI 35 |

## Design tokens

```json
{
  "colors": {
    "calm":     "#2DD4BF",
    "watch":    "#FBBF24",
    "strained": "#F97316",
    "alert":    "#E11D48",
    "bg":       "#0F172A",
    "surface":  "#1E293B",
    "muted":    "#475569",
    "text":     "#F1F5F9"
  },
  "fonts": {
    "body":   "Inter",
    "mono":   "JetBrains Mono"
  }
}
```

## Copy rules

- Sentences ≤ 25 words
- No jargon: "anomaly" → "unusual activity", "z-score" → never shown outside Why panel
- Never use: "caused by", "because of", "due to", "is responsible for", "resulted from"
- Use instead: "may be linked to", "coincides with", "possible link"
- Simulated feeds always show a "SIM" badge — say so out loud in the pitch
- Empty state: "All quiet. Here's what we're watching." (not "No data")

## QA checklist (run at H8, H12, H15, H18)

- [ ] Status word + headline readable by non-team member in ≤10 s
- [ ] Killing each feed never crashes UI or backend; shows amber chip
- [ ] All timestamps displayed in city local time (UTC internally)
- [ ] No banned causal words in UI or logs
- [ ] No individual-level data or free text visible
- [ ] Simulated feeds carry SIM badge
- [ ] Scenario "Quiet" → no false alerts over 10 min
- [ ] Replay is deterministic (same result twice)
- [ ] Backend restart → UI recovers without page refresh
- [ ] Works at 1280×720 and phone-width
- [ ] Colour-blind check: status word + icon always present alongside colour
