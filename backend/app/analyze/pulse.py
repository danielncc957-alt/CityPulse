"""
pulse.py — Weighted pulse score and level per zone + city-wide aggregation.
P2 owns this file. Formulas from PRD §7.2.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from ..models import PulseLevel

# Base weights from city.json (loaded lazily)
_BASE_WEIGHTS: dict[str, float] = {
    "weather":   0.25,
    "air":       0.20,
    "incidents": 0.35,
    "transit":   0.20,
}

# EWMA state per district — persisted in memory across ticks
_ewma_state: dict[str, float] = {}  # district → last smoothed S


@dataclass
class ZonePulseResult:
    district: str
    pulse: int                              # 0..100
    level: PulseLevel
    raw_score: float                        # 0..1 before inversion
    components: dict[str, Optional[float]]  # feed → stress (None = unavailable)


def _level(pulse: int) -> PulseLevel:
    if pulse >= 75:
        return "Calm"
    if pulse >= 50:
        return "Watch"
    if pulse >= 25:
        return "Strained"
    return "Alert"


def compute_zone_pulse(
    district: str,
    stresses: dict[str, Optional[float]],
    feed_weights: Optional[dict[str, float]] = None,
    alpha: float = 0.3,
) -> ZonePulseResult:
    """
    Compute the pulse score for one zone.

    Args:
        district:     Zone name (used to key EWMA state).
        stresses:     {feed: stress_0_to_1_or_None}. None = feed unavailable.
        feed_weights: Override base weights (e.g. from city.json). None = use defaults.
        alpha:        EWMA smoothing factor.

    Returns:
        ZonePulseResult with pulse (0..100) and level.
    """
    weights = feed_weights or _BASE_WEIGHTS

    # --- renormalise over available feeds only ---
    available = {f: s for f, s in stresses.items() if s is not None}
    if not available:
        # No feeds at all — return last known or flat Watch
        prev = _ewma_state.get(district, 0.5)
        p = round(100 * (1 - prev))
        return ZonePulseResult(district, p, _level(p), prev, dict(stresses))

    total_w = sum(weights.get(f, 0.0) for f in available)
    if total_w == 0:
        total_w = 1.0

    s_mean = sum(weights.get(f, 0.0) * s for f, s in available.items()) / total_w

    # One severe feed must not be averaged away
    max_s = max(available.values())
    s_combined = max(s_mean, 0.85 * max_s)

    # EWMA smoothing to prevent jitter
    prev_s = _ewma_state.get(district, s_combined)
    s_smooth = alpha * s_combined + (1 - alpha) * prev_s
    _ewma_state[district] = s_smooth

    pulse = round(100 * (1 - s_smooth))
    pulse = int(np.clip(pulse, 0, 100))

    return ZonePulseResult(
        district=district,
        pulse=pulse,
        level=_level(pulse),
        raw_score=s_smooth,
        components=dict(stresses),
    )


def compute_city_pulse(zone_results: list[ZonePulseResult]) -> tuple[int, PulseLevel]:
    """
    City-wide pulse = mean of zone pulses, but floored by
    (worst zone level - one step).

    Returns (city_pulse, city_level).
    """
    if not zone_results:
        return 75, "Calm"

    mean_pulse = int(round(np.mean([z.pulse for z in zone_results])))
    worst_pulse = min(z.pulse for z in zone_results)

    # Floor: city can be at most one level above the worst zone
    level_floors = {"Alert": 0, "Strained": 25, "Watch": 50, "Calm": 75}
    worst_level = _level(worst_pulse)
    # One step above worst
    steps = ["Alert", "Strained", "Watch", "Calm"]
    worst_idx = steps.index(worst_level)
    floor_level = steps[max(0, worst_idx - 1)]
    floor_pulse = level_floors[floor_level]

    city_pulse = max(mean_pulse, floor_pulse)
    city_pulse = int(np.clip(city_pulse, 0, 100))
    return city_pulse, _level(city_pulse)
