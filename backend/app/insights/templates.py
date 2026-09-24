"""
templates.py — Deterministic sentence templates for insight generation.
P2 owns this file. Template output is the safety net — always runs,
never calls external services, never hallucinates.

Spec from PRD §8.1 and §8.2.
"""
from __future__ import annotations
from typing import Optional, Any

from ..models import PulseLevel, ConfidenceTier
from .validate import contains_banned_phrase


# ---------------------------------------------------------------------------
# Main template builder
# ---------------------------------------------------------------------------

def build_headline(
    district: str,
    level: PulseLevel,
    facts: dict[str, Any],
    link_signal: Optional[ConfidenceTier] = None,
    link_feeds: Optional[list[str]] = None,
    caveats: Optional[list[str]] = None,
) -> str:
    """
    Build a short, grounded headline sentence (≤25 words) from facts.

    Facts dict expected keys (all optional):
        rain_mm_h, gust_kmh, us_aqi, pm2_5,
        incidents_30m, baseline_30m,
        mean_delay_min, share_routes_delayed
    """
    parts: list[str] = []

    # --- Weather ---
    rain = facts.get("rain_mm_h")
    gust = facts.get("gust_kmh")
    if rain is not None and rain > 0.5:
        parts.append(f"Heavy rain ({rain:.1f} mm/h)")
    elif gust is not None and gust > 50:
        parts.append(f"Strong gusts ({gust:.0f} km/h)")

    # --- Air quality ---
    aqi = facts.get("us_aqi")
    if aqi is not None and aqi > 100:
        label = "Unhealthy" if aqi > 150 else "Moderate air quality"
        parts.append(f"{label} (AQI {aqi:.0f})")

    # --- Incidents ---
    count = facts.get("incidents_30m")
    baseline = facts.get("baseline_30m")
    if count is not None and count > 0:
        if baseline is not None and baseline > 0:
            parts.append(f"{int(count)} complaints (baseline ~{int(baseline)})")
        else:
            parts.append(f"{int(count)} complaints")

    # --- Transit ---
    delay = facts.get("mean_delay_min")
    if delay is not None and delay > 2:
        parts.append(f"transit delays ~{delay:.0f} min")

    # Assemble base sentence
    if not parts:
        headline = _quiet_headline(district)
    else:
        body = ", ".join(parts)
        headline = f"{body} in {district}."

    # Append possible-link suffix if relevant
    if link_signal and link_feeds and link_signal != "Weak signal":
        feed_str = " and ".join(_feed_label(f) for f in link_feeds[:2])
        headline += f" {feed_str} may be linked."

    # Append first caveat if present
    if caveats:
        headline += f" Note: {caveats[0]}"

    # Safety net: if somehow a banned phrase crept in, strip the sentence down
    if contains_banned_phrase(headline):
        headline = _quiet_headline(district)

    return headline[:200]   # hard cap


def build_why_it_matters(
    district: str,
    level: PulseLevel,
    facts: dict[str, Any],
) -> str:
    """One sentence on resident impact."""
    rain = facts.get("rain_mm_h", 0) or 0
    delay = facts.get("mean_delay_min", 0) or 0
    aqi = facts.get("us_aqi", 0) or 0

    if level == "Calm":
        return f"Conditions in {district} are normal. No action needed."

    if rain > 5 and delay > 5:
        return "Low-lying streets may flood; allow extra travel time and expect transit delays."
    if rain > 5:
        return "Low-lying streets and underpasses may flood; allow extra travel time."
    if delay > 10:
        return "Significant transit delays — consider alternate routes."
    if aqi > 150:
        return "Air quality is unhealthy. Limit outdoor exertion, especially for children and seniors."
    if aqi > 100:
        return "Air quality is moderate. Sensitive groups should reduce prolonged outdoor activity."
    if level == "Alert":
        return f"Multiple stress signals are elevated in {district}. Stay informed and allow extra time."
    return f"Some stress signals are elevated in {district}. Monitor conditions."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feed_label(feed: str) -> str:
    return {
        "weather":   "weather",
        "air":       "air quality",
        "incidents": "incident activity",
        "transit":   "transit delays",
    }.get(feed, feed)


def _quiet_headline(district: str) -> str:
    return f"All quiet in {district}. Here's what we're watching."
