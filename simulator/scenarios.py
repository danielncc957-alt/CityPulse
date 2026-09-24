"""
scenarios.py — Scripted scenario engine for Jaipur demos.

Data strategy (PRD §4.1) mode 3 = SCENARIO: scripted synthetic events for a
guaranteed demo, with time-warp (1x, 10x, 60x).

This module ships the original three scripts (Storm / Smog / Quiet) plus two
Jaipur-specific EXTREME events:
  * "dust_storm"  — Andhi: a hot squall carrying dust across the Pink City.
  * "monsoon"     — sudden cloudburst: intense rain, flash flooding in the
                    Walled City, and gridlock on the arterial roads.
Both extremes deliberately push the weather + air feeds into the tail so the
anomaly detector and alert dispatcher can be exercised end-to-end.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

ScenarioName = Literal[
    "storm", "smog", "quiet", "live", "dust_storm", "monsoon"
]

_DISTRICTS = [
    "Walled City", "Mansarovar", "Vaishali Nagar", "Malviya Nagar",
    "C-Scheme", "Tonk Road", "Sodala", "Jagatpura",
]

@dataclass
class Scenario:
    name: ScenarioName
    incident_multipliers: dict[str, float] = field(default_factory=dict)
    weather_overrides: dict[str, dict] = field(default_factory=dict)
    aqi_override: float | None = None
    transit_multiplier: float = 1.0
    description: str = ""
    # Extreme-event metadata used by the monitoring / alerting path.
    # `is_extreme` lets the demo panel highlight it and lets QA assert that an
    # alert actually fired; `headline` is the short human label surfaced in UI.
    is_extreme: bool = False
    headline: str = ""
    # Per-feed override for the PM2.5 / PM10 components of the air feed so a dust
    # event can throw particulates far above the AQI number alone would suggest.
    particulate_override: dict[str, float] = field(default_factory=dict)


SCENARIOS: dict[ScenarioName, Scenario] = {
    "storm": Scenario(
        name="storm",
        incident_multipliers={
            "Walled City":    6.0, "C-Scheme":       4.0,
            "Tonk Road":      3.5, "Mansarovar":     3.0,
            "Malviya Nagar":  2.5, "Vaishali Nagar": 2.0,
            "Sodala":         1.5, "Jagatpura":      2.0,
        },
        weather_overrides={d: {"rain_mm_h": 18.0, "gust_kmh": 70.0} for d in _DISTRICTS},
        aqi_override=None,
        transit_multiplier=3.5,
        description="Monsoon storm: heavy rain, flooding in old city, transit disruption.",
        headline="Monsoon storm rolling in",
    ),
    "smog": Scenario(
        name="smog",
        incident_multipliers={d: 1.2 for d in _DISTRICTS},
        weather_overrides={},
        aqi_override=210.0,
        transit_multiplier=1.1,
        description="Severe smog event: AQI spike across Jaipur, visibility low.",
        headline="Smog spike",
    ),
    "quiet": Scenario(
        name="quiet",
        incident_multipliers={d: 0.25 for d in _DISTRICTS},
        weather_overrides={d: {"rain_mm_h": 0.0, "gust_kmh": 10.0} for d in _DISTRICTS},
        aqi_override=40.0,
        transit_multiplier=0.5,
        description="Quiet day: low activity, clear air, no alerts expected.",
        headline="Quiet day",
    ),
    "live": Scenario(
        name="live",
        incident_multipliers={d: 1.0 for d in _DISTRICTS},
        weather_overrides={},
        aqi_override=None,
        transit_multiplier=1.0,
        description="Live mode: real weather/AQ from Open-Meteo, simulated incidents/transit.",
        headline="Live",
    ),

    # ---------------------------------------------------------------------
    # Jaipur-specific EXTREME events (for the anomaly / alert drill)
    # ---------------------------------------------------------------------
    "dust_storm": Scenario(
        name="dust_storm",
        # Andhi: visibility collapses, complaints cluster around the old city
        # and the ring road; gust is the dominant physical stressor.
        incident_multipliers={
            "Walled City":    4.5, "C-Scheme":       3.0,
            "Tonk Road":      3.5, "Sodala":         3.0,
            "Vaishali Nagar": 2.5, "Mansarovar":     2.0,
            "Malviya Nagar":  2.0, "Jagatpura":      1.8,
        },
        # Very low rain, very high gusts (km/h) — the dust signature.
        weather_overrides={d: {"rain_mm_h": 0.2, "gust_kmh": 95.0} for d in _DISTRICTS},
        aqi_override=260.0,
        particulate_override={"pm2_5": 180.0, "pm10": 520.0},
        transit_multiplier=4.0,
        description=(
            "Dust storm (Andhi): 95 km/h gusts, near-zero visibility, "
            "particulate surge across the Pink City."
        ),
        is_extreme=True,
        headline="Dust storm (Andhi) warning",
    ),
    "monsoon": Scenario(
        name="monsoon",
        # Sudden cloudburst: Walled City flash flooding dominates, transit jams.
        incident_multipliers={
            "Walled City":    9.0, "Tonk Road":      5.0,
            "Sodala":         4.0, "C-Scheme":       4.5,
            "Mansarovar":     3.0, "Malviya Nagar":  2.5,
            "Vaishali Nagar": 2.5, "Jagatpura":      2.8,
        },
        # Intense convective rain plus strong gusts.
        weather_overrides={d: {"rain_mm_h": 42.0, "gust_kmh": 80.0} for d in _DISTRICTS},
        aqi_override=None,
        transit_multiplier=6.0,
        description=(
            "Sudden monsoon cloudburst: 42 mm/h rain, flash flooding in the "
            "Walled City, arterial gridlock."
        ),
        is_extreme=True,
        headline="Monsoon cloudburst",
    ),
}


# Scenario names that represent an extreme event — used by the demo panel and
# by QA to assert the anomaly/alert path fires.
EXTREME_SCENARIOS: tuple[ScenarioName, ...] = ("dust_storm", "monsoon")

_active: ScenarioName = "live"


def get_active() -> Scenario:
    return SCENARIOS[_active]


def is_extreme(name: ScenarioName) -> bool:
    """True if the named scenario is an injected extreme event."""
    return name in EXTREME_SCENARIOS


def set_active(name: ScenarioName) -> None:
    global _active
    if name not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {name}")
    _active = name


def get_scenario(name: ScenarioName) -> Scenario:
    return SCENARIOS[name]


def all_scenario_names() -> list[str]:
    """Return every scenario name (for the demo panel and QA)."""
    return list(SCENARIOS.keys())
