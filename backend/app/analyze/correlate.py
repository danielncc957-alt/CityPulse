"""
correlate.py — Lagged correlation engine with whitelisted feed pairs.
P2 owns this file. Spec from PRD §7.4.

Only tests domain-plausible pairs (avoids p-hacking-style spurious links).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
from scipy.stats import pearsonr

from ..models import ConfidenceTier

# ---------------------------------------------------------------------------
# Whitelisted cause → effect pairs (PRD §7.4)
# ---------------------------------------------------------------------------

WHITELISTED_PAIRS: list[tuple[str, str]] = [
    ("weather",   "incidents"),   # Heavy rain → flooding/drain complaints
    ("weather",   "transit"),     # Storm → delays
    ("air",       "incidents"),   # Smoke/smog → odor/air complaints
    ("incidents", "transit"),     # Road/signal issues → delays
]

# Min bins for a valid correlation (PRD: n ≥ 24)
MIN_BINS = 24
# Min |r| to count as correlated
MIN_R = 0.6
# Lag range: 0–6 bins (each bin = 5 min → 0–30 min)
MAX_LAG = 6


@dataclass
class CorrelationResult:
    cause_feed: str
    effect_feed: str
    district: str
    signal: ConfidenceTier
    checks_passed: int              # 1..4
    best_lag_bins: int              # lag in bins (5-min units)
    best_r: float
    n_bins: int
    both_anomalous: bool
    same_zone: bool                 # always True for same-district check
    cause_leads: bool               # temporal precedence
    confidence: str = "normal"      # "normal" | "low" (cold start)


def _lagged_pearson(x: np.ndarray, y: np.ndarray, max_lag: int) -> tuple[float, int]:
    """
    Find the lag (0..max_lag bins) that maximises |r| between x (cause) and y (effect).
    Positive lag means x leads y.
    Returns (best_r, best_lag).
    """
    best_r, best_lag = 0.0, 0
    n = len(x)
    for lag in range(0, max_lag + 1):
        if n - lag < MIN_BINS:
            break
        x_slice = x[: n - lag]
        y_slice = y[lag:]
        if np.std(x_slice) < 1e-8 or np.std(y_slice) < 1e-8:
            continue
        r, _ = pearsonr(x_slice, y_slice)
        if abs(r) > abs(best_r):
            best_r, best_lag = r, lag
    return best_r, best_lag


def check_correlation(
    district: str,
    cause_feed: str,
    effect_feed: str,
    cause_bins: np.ndarray,        # 5-min bin values for cause feed (last 3 h → 36 bins)
    effect_bins: np.ndarray,       # same for effect feed
    cause_anomalous: bool,
    effect_anomalous: bool,
    same_zone_or_neighbour: bool = True,
) -> Optional[CorrelationResult]:
    """
    Run all 4 checks for one whitelisted pair in one district.
    Returns None if the minimum evidence threshold (≥8 events implied by n_bins) isn't met.
    """
    n = min(len(cause_bins), len(effect_bins))
    if n < MIN_BINS:
        return None

    cause_bins = cause_bins[-n:]
    effect_bins = effect_bins[-n:]

    checks_passed = 0

    # Check 1: at least one feed is anomalous (or rising), both within ±30 min
    check1 = cause_anomalous or effect_anomalous
    if check1:
        checks_passed += 1

    # Check 2: lagged Pearson |r| ≥ 0.6
    best_r, best_lag = _lagged_pearson(cause_bins, effect_bins, MAX_LAG)
    check2 = abs(best_r) >= MIN_R
    if check2:
        checks_passed += 1

    # Check 3: same zone or neighbouring hex
    check3 = same_zone_or_neighbour
    if check3:
        checks_passed += 1

    # Check 4: temporal precedence — cause leads effect (positive lag)
    check4 = best_lag > 0
    if check4:
        checks_passed += 1

    if checks_passed == 0:
        return None

    # Minimum evidence: require meaningful signal (implied by n ≥ MIN_BINS)
    if n < MIN_BINS:
        return None

    # Map checks to confidence tier
    if checks_passed <= 2:
        signal: ConfidenceTier = "Weak signal"
    elif checks_passed == 3:
        signal = "Moderate signal"
    else:
        signal = "Strong signal"

    return CorrelationResult(
        cause_feed=cause_feed,
        effect_feed=effect_feed,
        district=district,
        signal=signal,
        checks_passed=checks_passed,
        best_lag_bins=best_lag,
        best_r=float(best_r),
        n_bins=n,
        both_anomalous=cause_anomalous and effect_anomalous,
        same_zone=same_zone_or_neighbour,
        cause_leads=check4,
    )


def run_all_pairs(
    district: str,
    feed_bins: dict[str, np.ndarray],       # feed → array of 5-min bins
    feed_anomalous: dict[str, bool],         # feed → is currently anomalous
) -> list[CorrelationResult]:
    """
    Run all whitelisted pairs for a district and return results with at least 1 check passed.
    """
    results = []
    for cause, effect in WHITELISTED_PAIRS:
        if cause not in feed_bins or effect not in feed_bins:
            continue
        result = check_correlation(
            district=district,
            cause_feed=cause,
            effect_feed=effect,
            cause_bins=feed_bins[cause],
            effect_bins=feed_bins[effect],
            cause_anomalous=feed_anomalous.get(cause, False),
            effect_anomalous=feed_anomalous.get(effect, False),
            same_zone_or_neighbour=True,   # always true for same-district check
        )
        if result is not None:
            results.append(result)

    # Sort by checks passed descending
    results.sort(key=lambda r: r.checks_passed, reverse=True)
    return results
