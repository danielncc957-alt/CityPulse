# P2 — Analytics/AI Lead

## Your folder: `backend/app/analyze/` and `backend/app/insights/`

**You own:** Stress formulas, pulse score, anomaly detection, correlation engine, insight generation, LLM summaries, validator, alerts.

## Files you build

```
backend/app/
├─ analyze/
│  ├─ stress.py        ← per-feed stress(0..1) per zone
│  ├─ pulse.py         ← weighted pulse score + level (Calm/Watch/Strained/Alert)
│  ├─ anomaly.py       ← robust z-score detector
│  └─ correlate.py     ← lagged correlation + confidence tiers
├─ insights/
│  ├─ templates.py     ← deterministic sentence templates
│  ├─ llm.py           ← Gemini Flash paraphrase (P1 feature, optional)
│  └─ validate.py      ← number-grounding + banned-phrase validator
└─ alerts.py           ← Discord/Telegram webhook with cooldown
```

## Hour-by-hour targets

- **H1–4:** Stress formulas + rolling-bin utilities with unit tests.
- **H4–8:** Pulse score, anomaly detector, feed into SSE `pulse` events.
- **H8–12:** Correlation engine, insight objects, template summaries, `/api/insights/{id}/explain`.
- **H12–15:** Banned-phrase validator, privacy thresholds, empty/quiet-state logic.
- **H15–18:** LLM layer + cache + rate-limit + fallback. Alert webhook. IsolationForest (P2, if time).

## Key interfaces

- Read from SQLite `events` table (via `db.py` from P1).
- Use `clock.now()` for all time references — never `datetime.now()`.
- Write to `pulse_snapshots`, `insights`, `alerts_sent` tables.
- P3 reads your insights via `GET /api/insights` and `/explain`.

## Analytics specs (from PRD §7)

### Stress formulas
| Feed | Formula |
|---|---|
| Weather | `max(clip(rain_mm_h/10), clip((gust_kmh−40)/40), alert_level)` |
| Air | `clip((us_aqi−50)/150)` |
| Incidents | `clip(z⁺/4)` robust z-score of 30-min complaint count vs hour-of-week baseline |
| Transit | `clip(0.6·mean_delay_min/15 + 0.4·share_routes_delayed>5min)` |

### Pulse score
```
S_mean = Σ(w_f · stress_f) / Σ(w_f)       # over available feeds only
S      = max(S_mean, 0.85 · max_f stress_f) # one bad feed can't be averaged away
pulse  = round(100 · (1 − EWMA(S, α=0.3)))
level  = Calm ≥75 · Watch 50–74 · Strained 25–49 · Alert <25
```

### Anomaly detection
- Robust z-score: `z = 0.6745 · (x − median) / MAD` over trailing 6h of 5-min bins
- Flag when z ≥ 3 for ≥2 consecutive bins; clear when z < 1.5
- Cold start (<12 bins): fixed thresholds, mark confidence "low"

### Correlation (whitelisted pairs only)
1. Both feeds anomalous within ±30 min
2. Lagged Pearson |r| ≥ 0.6, lags 0–6 bins, n ≥ 24
3. Same zone or neighbour hex
4. Cause-side leads effect-side

Confidence: `Weak` (1–2 checks) → `Moderate` (3) → `Strong` (all 4). Always "possible link, not a confirmed cause."

### Epistemic honesty (enforced in code)
Banned phrases: "caused by", "because of", "due to", "is responsible for", "resulted from"
→ regex validator; violation → use template instead.
