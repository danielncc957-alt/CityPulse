"""
incidents_sim.py — Poisson incident generator.
P4 owns this file.

DELIBERATELY MESSY FORMAT: ISO-8601 timestamp WITH timezone offset
e.g. "2026-09-24T10:32:11+05:30" — the normalizer (P1) must handle this.
"""
from __future__ import annotations
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

BASE_RATE: dict[str, float] = {
    "Midtown": 1.8, "Riverside": 1.2, "Downtown": 1.5, "Harlem": 0.8,
    "Brooklyn": 1.0, "Queens": 0.9, "Bronx": 0.7, "Old Town": 0.5,
}

DIURNAL = [
    0.2, 0.1, 0.1, 0.1, 0.1, 0.2,
    0.4, 0.7, 0.9, 1.0, 1.0, 1.0,
    1.0, 1.0, 0.9, 0.9, 1.0, 1.1,
    1.2, 1.1, 0.9, 0.7, 0.5, 0.3,
]

COMPLAINT_TYPES = [
    ("Sewer", "Clogged Drain"),
    ("Water System", "No Running Water"),
    ("Street Condition", "Pothole / Flooding"),
    ("Traffic Signal Condition", "Signal Out"),
    ("Damaged Tree", "Fallen Branch"),
    ("Noise", "Loud Construction"),
]

SCENARIO_MULTIPLIERS: dict[str, dict[str, float]] = {
    "storm": {
        "Riverside": 6.0, "Downtown": 4.0, "Harlem": 3.0,
        "Midtown": 2.5, "Brooklyn": 2.0, "Queens": 1.5,
        "Bronx": 1.5, "Old Town": 2.0,
    },
    "smog":  {d: 1.1 for d in BASE_RATE},
    "quiet": {d: 0.3 for d in BASE_RATE},
    "live":  {d: 1.0 for d in BASE_RATE},
}

_DISTRICTS: dict[str, tuple[float, float]] = {}


def _load_districts(city_json: str = "city.json") -> None:
    path = Path(city_json)
    if not path.exists():
        path = Path(__file__).parent.parent / "city.json"
    data = json.loads(path.read_text())
    for d in data["districts"]:
        _DISTRICTS[d["name"]] = (d["lat"], d["lon"])


class IncidentSimulator:
    def __init__(self, city_json_path: str = "city.json", seed: int = 42):
        _load_districts(city_json_path)
        self._rng = np.random.default_rng(seed)

    def _jitter(self, lat: float, lon: float, r: float = 0.01) -> tuple[float, float]:
        return (
            lat + self._rng.uniform(-r, r),
            lon + self._rng.uniform(-r, r),
        )

    def _tz_offset(self) -> str:
        """Random timezone offset — deliberately messy for the normalizer."""
        return self._rng.choice(["+00:00", "+05:30", "-05:00", "-04:00", "+01:00"])

    def generate(self, t: datetime, scenario_name: str = "live",
                 district: Optional[str] = None) -> list[dict]:
        multipliers = SCENARIO_MULTIPLIERS.get(scenario_name, SCENARIO_MULTIPLIERS["live"])
        hour = t.hour
        targets = [district] if district else list(BASE_RATE.keys())
        events = []

        for d in targets:
            rate = BASE_RATE.get(d, 0.5) * DIURNAL[hour] * multipliers.get(d, 1.0)
            n = int(self._rng.poisson(rate))
            if not n:
                continue
            lat0, lon0 = _DISTRICTS.get(d, (40.71, -74.0))
            for _ in range(n):
                cat, sub = COMPLAINT_TYPES[int(self._rng.integers(len(COMPLAINT_TYPES)))]
                lat, lon = self._jitter(lat0, lon0)
                offset = self._tz_offset()
                ts_str = t.strftime(f"%Y-%m-%dT%H:%M:%S{offset}")
                events.append({
                    "report_id":    str(uuid.uuid4()),
                    "reported_at":  ts_str,    # messy: tz offset varies
                    "category":     cat,
                    "sub_category": sub,
                    "lat":          round(lat, 6),
                    "lon":          round(lon, 6),
                })
        return events
