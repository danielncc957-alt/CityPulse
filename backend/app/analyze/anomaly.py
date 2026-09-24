"""
anomaly.py — Robust z-score anomaly detector with hysteresis.
P2 owns this file. Spec from PRD §7.3.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import numpy as np


def robust_z(series: np.ndarray, x: float) -> float:
    """
    Robust z-score: z = 0.6745 * (x - median) / MAD
    MAD floored at 1e-6 to avoid division by zero.
    """
    med = float(np.median(series))
    mad = float(np.median(np.abs(series - med))) or 1e-6
    return 0.6745 * (x - med) / mad


@dataclass
class AnomalyState:
    """Per-(district, feed) rolling state."""
    district: str
    feed: str
    is_flagged: bool = False
    consecutive_high: int = 0
    last_z: float = 0.0
    confidence: str = "normal"   # "normal" | "low" (cold start)


# Module-level state store: (district, feed) → AnomalyState
_states: dict[tuple[str, str], AnomalyState] = {}


def _get_state(district: str, feed: str) -> AnomalyState:
    key = (district, feed)
    if key not in _states:
        _states[key] = AnomalyState(district=district, feed=feed)
    return _states[key]


def check_anomaly(
    district: str,
    feed: str,
    current_value: float,
    history_bins: np.ndarray,
    thresh_flag: float = 3.0,
    thresh_clear: float = 1.5,
    consec_required: int = 2,
) -> AnomalyState:
    """
    Update anomaly state for one (district, feed) pair.

    Args:
        district:        Zone name.
        feed:            Feed name ("weather", "air", "incidents", "transit").
        current_value:   The latest 5-min bin value.
        history_bins:    Array of historical 5-min bin values (trailing 6 h = 72 bins).
        thresh_flag:     z-score threshold to flag (default 3.0).
        thresh_clear:    z-score threshold to clear (default 1.5, hysteresis).
        consec_required: How many consecutive high bins before flagging.

    Returns:
        Updated AnomalyState (also stored in module state).
    """
    state = _get_state(district, feed)

    # Cold start: fewer than 12 bins → low confidence
    if len(history_bins) < 12:
        state.confidence = "low"
        # Fall back to fixed threshold: value > 2× median of what little we have
        if len(history_bins) > 0:
            med = float(np.median(history_bins))
            high = current_value > max(2.0 * med, 1e-3)
        else:
            high = False
    else:
        state.confidence = "normal"
        z = robust_z(history_bins, current_value)
        state.last_z = z
        high = z >= thresh_flag

    if high:
        state.consecutive_high += 1
        if state.consecutive_high >= consec_required:
            state.is_flagged = True
    else:
        state.consecutive_high = 0
        # Hysteresis: only clear if z drops below thresh_clear
        if not high:
            if len(history_bins) >= 12:
                z = robust_z(history_bins, current_value)
                if z < thresh_clear:
                    state.is_flagged = False
            else:
                state.is_flagged = False

    return state


def get_anomalous_feeds(district: str) -> list[str]:
    """Return feeds currently flagged as anomalous for a district."""
    return [
        feed for (d, feed), state in _states.items()
        if d == district and state.is_flagged
    ]


def reset_state(district: str, feed: str) -> None:
    """Clear state for a feed (e.g., when the feed is killed and restored)."""
    key = (district, feed)
    if key in _states:
        del _states[key]
