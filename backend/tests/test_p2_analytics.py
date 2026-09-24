"""
test_p2_analytics.py — Unit tests for P2's analytics modules.
Run with: cd backend && pytest tests/ -v

Tests cover:
  - stress formulas
  - pulse score computation
  - anomaly detector (flag + clear + cold start)
  - correlation engine (whitelisted pairs)
  - validate (banned phrases + number grounding)
  - template builder
"""
from __future__ import annotations
import numpy as np
import pytest
from datetime import datetime, timezone

# --- stress ---
from app.analyze.stress import (
    weather_stress, air_stress, incident_stress, transit_stress
)

# --- pulse ---
from app.analyze.pulse import compute_zone_pulse, compute_city_pulse, _level

# --- anomaly ---
from app.analyze.anomaly import robust_z, check_anomaly, _states

# --- correlate ---
from app.analyze.correlate import check_correlation, run_all_pairs

# --- validate ---
from app.insights.validate import validate_llm_output, contains_banned_phrase

# --- templates ---
from app.insights.templates import build_headline, build_why_it_matters


# ===========================================================================
# Stress tests
# ===========================================================================

class TestWeatherStress:
    def test_calm_conditions(self):
        assert weather_stress(rain_mm_h=0.0, gust_kmh=20.0) == 0.0

    def test_heavy_rain_clips_at_one(self):
        assert weather_stress(rain_mm_h=20.0) == 1.0

    def test_moderate_rain(self):
        s = weather_stress(rain_mm_h=5.0)
        assert 0.4 < s < 0.6

    def test_high_gust(self):
        s = weather_stress(gust_kmh=80.0)
        assert s == 1.0

    def test_none_inputs_return_none(self):
        assert weather_stress() is None


class TestAirStress:
    def test_good_aqi(self):
        assert air_stress(35) == 0.0

    def test_moderate_aqi(self):
        s = air_stress(125)
        assert 0.4 < s < 0.6

    def test_very_unhealthy(self):
        assert air_stress(200) == 1.0

    def test_none_returns_none(self):
        assert air_stress(None) is None


class TestIncidentStress:
    def test_no_history_uses_fixed_threshold(self):
        s = incident_stress(10.0, None)
        assert s == 1.0

    def test_count_above_baseline_raises_stress(self):
        baseline = np.ones(72) * 2.0   # baseline: 2 per bin
        s = incident_stress(15.0, baseline)
        assert s > 0.5

    def test_normal_count_low_stress(self):
        baseline = np.ones(72) * 5.0
        s = incident_stress(5.0, baseline)
        assert s is not None and s < 0.1

    def test_none_returns_none(self):
        assert incident_stress(None, np.ones(10)) is None


class TestTransitStress:
    def test_no_delays(self):
        assert transit_stress(0.0, 0.0) == 0.0

    def test_high_delay(self):
        s = transit_stress(15.0, 0.5)
        assert s > 0.5

    def test_both_none_returns_none(self):
        assert transit_stress(None, None) is None


# ===========================================================================
# Pulse tests
# ===========================================================================

class TestPulse:
    def test_all_calm_gives_high_pulse(self):
        stresses = {"weather": 0.0, "air": 0.0, "incidents": 0.0, "transit": 0.0}
        result = compute_zone_pulse("TestDistrict", stresses)
        assert result.pulse >= 75
        assert result.level == "Calm"

    def test_all_severe_gives_alert(self):
        stresses = {"weather": 1.0, "air": 1.0, "incidents": 1.0, "transit": 1.0}
        result = compute_zone_pulse("TestDistrict2", stresses)
        assert result.pulse < 25
        assert result.level == "Alert"

    def test_one_severe_feed_not_averaged_away(self):
        stresses = {"weather": 1.0, "air": 0.0, "incidents": 0.0, "transit": 0.0}
        result = compute_zone_pulse("TestDistrict3", stresses)
        # Even one severe feed should prevent Calm
        assert result.level != "Calm"

    def test_missing_feed_accepted(self):
        stresses = {"weather": 0.5, "air": None, "incidents": 0.2, "transit": None}
        result = compute_zone_pulse("TestDistrict4", stresses)
        assert 0 <= result.pulse <= 100

    def test_level_thresholds(self):
        assert _level(80) == "Calm"
        assert _level(60) == "Watch"
        assert _level(40) == "Strained"
        assert _level(10) == "Alert"


# ===========================================================================
# Anomaly tests
# ===========================================================================

class TestRobustZ:
    def test_median_value_gives_zero(self):
        series = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert abs(robust_z(series, 3.0)) < 0.01

    def test_extreme_outlier_gives_high_z(self):
        series = np.ones(20) * 2.0
        z = robust_z(series, 20.0)
        assert z > 3.0


class TestAnomalyDetector:
    def setup_method(self):
        _states.clear()

    def test_flags_after_consecutive_high(self):
        history = np.ones(72) * 2.0
        # First high bin — should not flag yet (need 2 consecutive)
        state = check_anomaly("D", "incidents", 20.0, history)
        assert not state.is_flagged
        # Second high bin — should flag
        state = check_anomaly("D", "incidents", 20.0, history)
        assert state.is_flagged

    def test_clears_on_low_z(self):
        history = np.ones(72) * 2.0
        # Flag it
        check_anomaly("D2", "incidents", 20.0, history)
        check_anomaly("D2", "incidents", 20.0, history)
        # Clear it
        state = check_anomaly("D2", "incidents", 2.0, history)
        assert not state.is_flagged

    def test_cold_start_low_confidence(self):
        history = np.ones(5) * 2.0  # < 12 bins
        state = check_anomaly("D3", "incidents", 5.0, history)
        assert state.confidence == "low"


# ===========================================================================
# Correlation tests
# ===========================================================================

class TestCorrelation:
    def _make_bins(self, n=36, base=1.0, spike_at: int = None, spike_val: float = 10.0):
        bins = np.ones(n) * base
        if spike_at is not None:
            bins[spike_at] = spike_val
        return bins

    def test_correlated_pair_detected(self):
        cause = np.sin(np.linspace(0, 4 * np.pi, 36)) + 2
        effect = np.roll(cause, 2)   # effect lags cause by 2 bins
        result = check_correlation(
            "TestZone", "weather", "incidents",
            cause_bins=cause, effect_bins=effect,
            cause_anomalous=True, effect_anomalous=True,
        )
        assert result is not None
        assert result.checks_passed >= 2

    def test_uncorrelated_pair_low_checks(self):
        rng = np.random.default_rng(42)
        cause = rng.random(36)
        effect = rng.random(36)
        result = check_correlation(
            "TestZone2", "weather", "transit",
            cause_bins=cause, effect_bins=effect,
            cause_anomalous=False, effect_anomalous=False,
        )
        # Should either be None or low checks
        if result:
            assert result.checks_passed <= 2

    def test_run_all_pairs_returns_list(self):
        feed_bins = {
            "weather": np.ones(36),
            "incidents": np.ones(36),
            "air": np.ones(36),
            "transit": np.ones(36),
        }
        results = run_all_pairs("TestZone3", feed_bins, {f: False for f in feed_bins})
        assert isinstance(results, list)


# ===========================================================================
# Validator tests
# ===========================================================================

class TestValidator:
    def test_valid_text_passes(self):
        facts = {"rain_mm_h": 8.2, "incidents_30m": 14}
        text = "Heavy rain of 8.2 mm/h coincides with 14 complaints in Riverside."
        assert validate_llm_output(text, facts)

    def test_banned_phrase_fails(self):
        facts = {"rain_mm_h": 8.2}
        text = "Flooding caused by heavy rain of 8.2 mm/h."
        assert not validate_llm_output(text, facts)

    def test_hallucinated_number_fails(self):
        facts = {"rain_mm_h": 8.2}
        text = "Rain of 42.0 mm/h detected."
        assert not validate_llm_output(text, facts)

    def test_too_long_fails(self):
        facts = {"rain_mm_h": 8.2}
        text = " ".join(["word"] * 35)
        assert not validate_llm_output(text, facts)

    def test_empty_text_fails(self):
        assert not validate_llm_output("", {})

    def test_contains_banned_phrase(self):
        assert contains_banned_phrase("The flood was due to heavy rain.")
        assert not contains_banned_phrase("Rain may be linked to flooding.")


# ===========================================================================
# Template tests
# ===========================================================================

class TestTemplates:
    def test_headline_not_empty(self):
        facts = {"rain_mm_h": 8.2, "incidents_30m": 14, "baseline_30m": 2}
        h = build_headline("Riverside", "Strained", facts)
        assert len(h) > 10

    def test_headline_no_banned_phrases(self):
        facts = {"rain_mm_h": 5.0, "us_aqi": 120}
        h = build_headline("Downtown", "Watch", facts)
        assert not contains_banned_phrase(h)

    def test_quiet_state_headline(self):
        h = build_headline("Old Town", "Calm", {})
        assert "quiet" in h.lower() or "watching" in h.lower()

    def test_why_it_matters_calm(self):
        w = build_why_it_matters("Midtown", "Calm", {})
        assert "normal" in w.lower() or "calm" in w.lower() or "no action" in w.lower()

    def test_why_it_matters_rain_and_delay(self):
        w = build_why_it_matters("Riverside", "Alert", {"rain_mm_h": 8.0, "mean_delay_min": 12.0})
        assert "flood" in w.lower() or "transit" in w.lower()
