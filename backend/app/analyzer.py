"""
analyzer.py — The main analytics tick.
P2 owns this file. Called every 5 s (demo) or 30 s (live) by the scheduler in main.py.

On each tick:
  1. Pull recent events from SQLite (P1's db.py)
  2. Compute per-feed stress per zone
  3. Compute pulse score per zone + city-wide
  4. Detect anomalies
  5. Run correlation engine
  6. Build insight objects (template + optional LLM)
  7. Persist pulse snapshots and insights
  8. Emit SSE events (via a callback supplied by main.py)
  9. Dispatch alerts
"""
from __future__ import annotations
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Coroutine, Optional

import numpy as np

from .clock import now as clock_now
from .db import get_db, query_events, insert_pulse_snapshot, insert_insight
from .geo import all_district_names
from .models import (
    Insight, InsightLink, CityPulse, DistrictPulse, FeedHealth, PulseLevel
)
from .analyze.stress import weather_stress, air_stress, incident_stress, transit_stress
from .analyze.pulse import compute_zone_pulse, compute_city_pulse
from .analyze.anomaly import check_anomaly, get_anomalous_feeds
from .analyze.correlate import run_all_pairs
from .insights.templates import build_headline, build_why_it_matters
from .insights.llm import paraphrase, MAX_ZONES_PER_TICK

log = logging.getLogger(__name__)

# Window for stress computation
STRESS_WINDOW_MIN = 30
# Window for anomaly history (6 h = 72 bins of 5 min)
ANOMALY_WINDOW_H = 6
# Window for correlation (3 h = 36 bins)
CORR_WINDOW_H = 3
BIN_MIN = 5


SseCallback = Callable[[str, dict], Coroutine]   # (event_type, payload) → None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_bins(
    values: list[float],
    timestamps: list[datetime],
    window_h: float,
    bin_min: int = BIN_MIN,
) -> np.ndarray:
    """Resample raw event values into fixed-size bins (simple mean per bin)."""
    if not values:
        return np.array([])

    t_end = clock_now()
    t_start = t_end - timedelta(hours=window_h)
    n_bins = int(window_h * 60 / bin_min)

    bins = np.zeros(n_bins)
    counts = np.zeros(n_bins)

    for v, t in zip(values, timestamps):
        if t < t_start:
            continue
        idx = int((t - t_start).total_seconds() / 60 / bin_min)
        if 0 <= idx < n_bins:
            bins[idx] += v
            counts[idx] += 1

    # Mean where we have data, 0 elsewhere
    mask = counts > 0
    bins[mask] /= counts[mask]
    return bins


def _event_rows_to_bins(rows, value_col: str, window_h: float) -> np.ndarray:
    vals, times = [], []
    for row in rows:
        v = row[value_col]
        if v is None:
            continue
        t = datetime.fromisoformat(row["ts_utc"])
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        vals.append(float(v))
        times.append(t)
    return _to_bins(vals, times, window_h)


# ---------------------------------------------------------------------------
# Main tick
# ---------------------------------------------------------------------------

async def run_tick(
    feed_health: dict[str, FeedHealth],
    sse_emit: Optional[SseCallback] = None,
    llm_zone_limit: int = MAX_ZONES_PER_TICK,
) -> tuple[CityPulse, list[Insight]]:
    """
    Run one full analytics tick. Returns (city_pulse, insights).
    Persists to DB and emits SSE events as a side effect.
    """
    t_now = clock_now()
    t_stress_start = t_now - timedelta(minutes=STRESS_WINDOW_MIN)
    t_anomaly_start = t_now - timedelta(hours=ANOMALY_WINDOW_H)
    t_corr_start = t_now - timedelta(hours=CORR_WINDOW_H)

    districts = all_district_names()
    available_feeds = {
        src for src, h in feed_health.items() if h.status == "ok"
    }

    zone_results = []
    all_insights: list[Insight] = []

    with get_db() as conn:
        for district in districts:
            stresses: dict[str, Optional[float]] = {}

            # ---- Weather stress ----
            if "weather" in available_feeds:
                w_rows = query_events(conn, district, "weather", t_stress_start, t_now)
                rain = next((r["value"] for r in reversed(w_rows) if r["kind"] == "rain_rate"), None)
                gust = next((r["value"] for r in reversed(w_rows) if r["kind"] == "gust"), None)
                stresses["weather"] = weather_stress(rain_mm_h=rain, gust_kmh=gust)
            else:
                stresses["weather"] = None

            # ---- Air quality stress ----
            if "air" in available_feeds:
                a_rows = query_events(conn, district, "air", t_stress_start, t_now)
                aqi = next((r["value"] for r in reversed(a_rows) if r["kind"] == "us_aqi"), None)
                stresses["air"] = air_stress(aqi)
            else:
                stresses["air"] = None

            # ---- Incident stress ----
            if "incidents" in available_feeds:
                i_rows = query_events(conn, district, "incidents", t_stress_start, t_now)
                count_30m = float(len(i_rows))
                hist_rows = query_events(conn, district, "incidents", t_anomaly_start, t_stress_start)
                hist_bins = _event_rows_to_bins(hist_rows, "value", ANOMALY_WINDOW_H)
                stresses["incidents"] = incident_stress(count_30m, hist_bins if len(hist_bins) > 0 else None)
            else:
                stresses["incidents"] = None

            # ---- Transit stress ----
            if "transit" in available_feeds:
                tr_rows = query_events(conn, district, "transit", t_stress_start, t_now)
                delays = [r["value"] for r in tr_rows if r["kind"] == "route_delay" and r["value"] is not None]
                if delays:
                    mean_delay = float(np.mean(delays))
                    share_gt5 = float(sum(1 for d in delays if d > 5) / len(delays))
                else:
                    mean_delay, share_gt5 = 0.0, 0.0
                stresses["transit"] = transit_stress(mean_delay, share_gt5)
            else:
                stresses["transit"] = None

            # ---- Pulse ----
            zone_result = compute_zone_pulse(district, stresses)
            zone_results.append(zone_result)

            # ---- Persist pulse snapshot ----
            insert_pulse_snapshot(conn, {
                "ts": t_now.isoformat(),
                "district": district,
                "pulse": zone_result.pulse,
                "level": zone_result.level,
                "components_json": json.dumps(zone_result.components),
            })

            # ---- Anomaly detection ----
            feed_anomalous: dict[str, bool] = {}
            feed_bins: dict[str, np.ndarray] = {}

            for feed in ["weather", "air", "incidents", "transit"]:
                if feed not in available_feeds:
                    feed_anomalous[feed] = False
                    continue
                hist = query_events(conn, district, feed, t_anomaly_start, t_now)
                bins = _event_rows_to_bins(hist, "value", ANOMALY_WINDOW_H)
                feed_bins[feed] = bins
                if len(bins) > 0:
                    state = check_anomaly(
                        district=district,
                        feed=feed,
                        current_value=float(bins[-1]) if len(bins) > 0 else 0.0,
                        history_bins=bins[:-1] if len(bins) > 1 else bins,
                    )
                    feed_anomalous[feed] = state.is_flagged
                else:
                    feed_anomalous[feed] = False

            # ---- Correlation ----
            corr_results = []
            if len([f for f in available_feeds if f in feed_bins]) >= 2:
                corr_bins = {}
                for feed in available_feeds:
                    hist = query_events(conn, district, feed, t_corr_start, t_now)
                    b = _event_rows_to_bins(hist, "value", CORR_WINDOW_H)
                    if len(b) > 0:
                        corr_bins[feed] = b
                corr_results = run_all_pairs(district, corr_bins, feed_anomalous)

            # ---- Build insight ----
            if zone_result.level != "Calm" or any(feed_anomalous.values()):
                # Gather facts
                facts: dict[str, Any] = {}
                if stresses.get("weather") is not None:
                    w_rows = query_events(conn, district, "weather", t_stress_start, t_now)
                    rain = next((r["value"] for r in reversed(w_rows) if r["kind"] == "rain_rate"), None)
                    gust = next((r["value"] for r in reversed(w_rows) if r["kind"] == "gust"), None)
                    if rain is not None: facts["rain_mm_h"] = round(rain, 1)
                    if gust is not None: facts["gust_kmh"] = round(gust, 1)
                if stresses.get("air") is not None:
                    a_rows = query_events(conn, district, "air", t_stress_start, t_now)
                    aqi = next((r["value"] for r in reversed(a_rows) if r["kind"] == "us_aqi"), None)
                    if aqi is not None: facts["us_aqi"] = round(aqi, 0)
                if stresses.get("incidents") is not None:
                    i_rows = query_events(conn, district, "incidents", t_stress_start, t_now)
                    facts["incidents_30m"] = len(i_rows)
                    facts["baseline_30m"] = 2.0  # TODO: compute from history
                if stresses.get("transit") is not None:
                    if "mean_delay" in dir():
                        facts["mean_delay_min"] = round(mean_delay, 1)

                # Caveats
                caveats: list[str] = []
                for src, h in feed_health.items():
                    if h.status != "ok":
                        caveats.append(f"{src} feed {h.status}.")
                if any(h.is_simulated for h in feed_health.values()):
                    caveats.append("Some feeds are simulated.")

                # Best correlation for this zone
                best_corr = corr_results[0] if corr_results else None
                link = None
                if best_corr and best_corr.checks_passed >= 2:
                    link = InsightLink(
                        feeds=[best_corr.cause_feed, best_corr.effect_feed],
                        signal=best_corr.signal,
                        lag_min=best_corr.best_lag_bins * BIN_MIN,
                        r_value=round(best_corr.best_r, 2),
                    )

                template_text = build_headline(
                    district=district,
                    level=zone_result.level,
                    facts=facts,
                    link_signal=link.signal if link else None,
                    link_feeds=link.feeds if link else None,
                    caveats=caveats,
                )
                why = build_why_it_matters(district, zone_result.level, facts)

                # LLM paraphrase for top stressed zones only (sorted by stress, top N)
                text_source = "template"
                headline = template_text
                if llm_zone_limit > 0:
                    headline, text_source = paraphrase(
                        district=district,
                        level=zone_result.level,
                        facts=facts,
                        caveats=caveats,
                        template_fallback=template_text,
                    )

                insight_id = hashlib.md5(
                    f"{district}{t_now.isoformat()}".encode()
                ).hexdigest()[:16]

                insight = Insight(
                    id=insight_id,
                    ts=t_now,
                    district=district,
                    level=zone_result.level,
                    headline=headline,
                    why_it_matters=why,
                    link=link,
                    facts=facts,
                    caveats=caveats,
                    confidence=link.signal if link else None,
                    evidence_json={
                        "anomalous_feeds": [f for f, a in feed_anomalous.items() if a],
                        "correlation": {
                            "cause": best_corr.cause_feed,
                            "effect": best_corr.effect_feed,
                            "r": best_corr.best_r,
                            "lag_bins": best_corr.best_lag_bins,
                            "checks": best_corr.checks_passed,
                        } if best_corr else None,
                    },
                    method="robust_z",
                    text_source=text_source,
                )

                insert_insight(conn, {
                    "id": insight.id,
                    "ts": insight.ts.isoformat(),
                    "district": insight.district,
                    "level": insight.level,
                    "headline": insight.headline,
                    "why_it_matters": insight.why_it_matters,
                    "facts_json": json.dumps(insight.facts),
                    "evidence_json": json.dumps(insight.evidence_json),
                    "confidence": insight.confidence,
                    "method": insight.method,
                    "text_source": insight.text_source,
                    "caveats_json": json.dumps(insight.caveats),
                })

                all_insights.append(insight)

    # ---- City-wide pulse ----
    city_pulse_val, city_level = compute_city_pulse(zone_results)
    city_pulse = CityPulse(
        ts=t_now,
        pulse=city_pulse_val,
        level=city_level,
        districts=[
            DistrictPulse(
                name=z.district,
                pulse=z.pulse,
                level=z.level,
                components=z.components,
            )
            for z in zone_results
        ],
    )

    # ---- SSE emit ----
    if sse_emit:
        await sse_emit("pulse", city_pulse.model_dump(mode="json"))
        for ins in all_insights:
            await sse_emit("insight", ins.model_dump(mode="json"))

    # ---- Alerts ----
    from .alerts import dispatch as alert_dispatch
    for ins in all_insights:
        try:
            await alert_dispatch(ins)
        except Exception as exc:
            log.warning("Alert dispatch failed: %s", exc)

    return city_pulse, all_insights
