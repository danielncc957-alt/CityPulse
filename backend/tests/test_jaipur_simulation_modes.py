"""Tests for Jaipur LIVE / REPLAY / SCENARIO simulation modes."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from simulator.scenarios import SCENARIOS, is_extreme
from simulator.incidents_sim import IncidentSimulator
from simulator.transit_sim import TransitSimulator
from backend.app.adapters.replay import (
    REPLAY_DATASET_ID,
    get_replay_weather_series,
    iter_replay_events,
    normalize_replay_row,
)


ROOT = Path(__file__).parent.parent.parent


def test_city_configuration_targets_jaipur_pink_city() -> None:
    import json

    city = json.loads((ROOT / "city.json").read_text(encoding="utf-8"))
    assert city["city"] == "Jaipur"
    assert city["timezone"] == "Asia/Kolkata"
    assert 26.80 <= city["center"]["lat"] <= 27.00
    assert 75.70 <= city["center"]["lon"] <= 75.90
    assert "Walled City" in {d["name"] for d in city["districts"]}


def test_all_three_data_modes_are_available() -> None:
    assert {"live", "storm", "smog", "quiet"}.issubset(SCENARIOS)
    assert REPLAY_DATASET_ID == "jaipur_2025_08_22"


@pytest.mark.parametrize("name", ["dust_storm", "monsoon"])
def test_jaipur_extreme_events_push_signals_into_alert_tail(name: str) -> None:
    scenario = SCENARIOS[name]
    assert scenario.is_extreme and is_extreme(name)
    assert scenario.weather_overrides
    assert max(
        values["gust_kmh"] for values in scenario.weather_overrides.values()
    ) >= 80
    assert scenario.transit_multiplier >= 4.0
    assert max(scenario.incident_multipliers.values()) >= 4.0


def test_dust_storm_injects_particulate_surge() -> None:
    dust = SCENARIOS["dust_storm"]
    assert dust.aqi_override is not None and dust.aqi_override >= 250
    assert dust.particulate_override["pm10"] >= 500


def test_extreme_incident_streams_use_jaipur_coordinates() -> None:
    t = datetime(2025, 8, 22, 18, 0, tzinfo=timezone.utc)
    sim = IncidentSimulator(city_json_path=str(ROOT / "city.json"), seed=7)
    rows = sim.generate(t, scenario_name="monsoon")
    assert rows
    for row in rows:
        assert 26.7 <= row["lat"] <= 27.1
        assert 75.6 <= row["lon"] <= 75.95
        assert row["reported_at"].endswith(("+05:30", "+00:00"))


def test_extreme_transit_stream_is_messy_epoch_format() -> None:
    t = datetime(2025, 8, 22, 18, 0, tzinfo=timezone.utc)
    rows = TransitSimulator(seed=9).generate(t, scenario_name="monsoon")
    assert rows
    assert all(isinstance(r["update_epoch"], int) for r in rows)
    assert all(r["delay_s"] >= 60 for r in rows)


def test_jaipur_replay_cache_is_present_and_ist_to_utc_aware() -> None:
    assert list(iter_replay_events())
    weather = __import__(
        "backend.app.adapters.replay", fromlist=["load_replay_weather"]
    ).load_replay_weather()
    series = get_replay_weather_series("Walled City", weather)
    assert len(series) == 24
    assert series[0][0].utcoffset().total_seconds() == 0
    # Local 00:00 IST converts to 18:30 UTC on the previous day.
    assert series[0][0].hour == 18
    assert series[0][0].minute == 30
    assert max(point[1] for point in series) >= 45


def test_replay_rows_normalize_to_jaipur_coordinates() -> None:
    row = next(iter_replay_events())
    event = normalize_replay_row(row)
    assert event is not None
    assert event["reported_at"].endswith("+05:30")
    assert 26.7 <= event["lat"] <= 27.1
    assert 75.6 <= event["lon"] <= 75.95
