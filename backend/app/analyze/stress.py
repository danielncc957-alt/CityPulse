"""
stress.py — Per-feed stress scores (0.0 = fine, 1.0 = severe) per zone.
P2 owns this file.

Each function takes the latest aggregated feed values for a zone and returns
a float in [0, 1]. All formulas come directly from PRD §7.1.
"""
from __future__ import annotations
import numpy as np
from typing import Optional


def _clip(x: float) -> float:
    """Clip to [0, 1]."""
    return float(np.clip(x, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Weather stress
# ---------------------------------------------------------------------------

def weather_stress(
    rain_mm_h: Optional[float] = None,
    gust_kmh: Optional[float] = None,
    alert_level: float = 0.0,
) -> Optional[float]:
    """
    stress = max(clip(rain_mm_h/10), clip((gust_kmh-40)/40), alert_level)
    Returns None if all inputs are None (feed unavailable).
    """
    parts: list[float] = [_clip(alert_level)]
    if rain_mm_h is not None:
        parts.append(_clip(rain_mm_h / 10.0))
    if gust_kmh is not None:
        parts.append(_clip((gust_kmh - 40.0) / 40.0))
    if len(parts) == 1 and rain_mm_h is None and gust_kmh is None:
        return None
    return max(parts)


# ---------------------------------------------------------------------------
# Air quality stress
# ---------------------------------------------------------------------------

def air_stress(us_aqi: Optional[float]) -> Optional[float]:
    """
    stress = clip((us_aqi - 50) / 150)
    AQI ≤ 50 → 0.0 (good), AQI 200 → 1.0 (very unhealthy)
    """
    if us_aqi is None:
        return None
    return _clip((us_aqi - 50.0) / 150.0)


# ---------------------------------------------------------------------------
# Incident stress (robust z-score based)
# ---------------------------------------------------------------------------

def incident_stress(
    count_30m: Optional[float],
    history_bins: Optional[np.ndarray],
) -> Optional[float]:
    """
    stress = clip(z+ / 4)
    where z is the robust z-score of count_30m vs history_bins.
    z+ means we only penalise counts ABOVE the median (not below).
    Falls back to 0.0 if not enough history.
    """
    if count_30m is None:
        return None
    if history_bins is None or len(history_bins) < 3:
        # Cold start: normalise against a fixed threshold (10 incidents = stress 1)
        return _clip(count_30m / 10.0)

    med = float(np.median(history_bins))
    mad = float(np.median(np.abs(history_bins - med))) or 1e-6
    z = 0.6745 * (count_30m - med) / mad
    z_pos = max(0.0, z)   # only elevated counts increase stress
    return _clip(z_pos / 4.0)


# ---------------------------------------------------------------------------
# Transit stress
# ---------------------------------------------------------------------------

def transit_stress(
    mean_delay_min: Optional[float],
    share_routes_delayed_gt5: Optional[float],
) -> Optional[float]:
    """
    stress = clip(0.6 * mean_delay_min/15 + 0.4 * share_routes_delayed>5min)
    share_routes_delayed_gt5 is a fraction 0..1.
    """
    if mean_delay_min is None and share_routes_delayed_gt5 is None:
        return None
    delay_term = _clip((mean_delay_min or 0.0) / 15.0) * 0.6
    share_term = _clip(share_routes_delayed_gt5 or 0.0) * 0.4
    return delay_term + share_term
