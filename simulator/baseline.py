"""
baseline.py — Seed 7 days of synthetic history so rolling baselines exist from startup.
Called once at backend startup before the first analyzer tick.
Updated for Jaipur city districts.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

CITY_JSON = Path(__file__).parent.parent / "city.json"

# Jaipur diurnal pattern — peaks during morning market hours and evening bazaar
DIURNAL = [
    0.15, 0.08, 0.06, 0.05, 0.07, 0.15,   # 0–5
    0.35, 0.65, 0.90, 1.00, 1.00, 1.00,   # 6–11
    0.95, 0.90, 0.85, 0.90, 1.00, 1.10,   # 12–17
    1.20, 1.15, 0.95, 0.75, 0.55, 0.30,   # 18–23
]

# Incident base rates per 5-min bin — Walled City highest (dense old city)
BASE_INCIDENT_RATE = {
    "Walled City":    2.2,
    "C-Scheme":       1.6,
    "Mansarovar":     1.3,
    "Tonk Road":      1.4,
    "Malviya Nagar":  1.1,
    "Vaishali Nagar": 1.0,
    "Sodala":         0.8,
    "Jagatpura":      0.7,
}

BASE_DELAY_MIN = 4.0   # Jaipur city bus baseline delay


def seed_baseline(conn, districts: list[str], days: int = 7) -> None:
    """
    Insert synthetic historical events so the anomaly detector has
    a baseline from second one. Generates realistic diurnal patterns
    for incidents and transit.
    """
    from backend.app.db import insert_event

    rng = np.random.default_rng(seed=2024)
    now = datetime.now(timezone.utc)
    t_start = now - timedelta(days=days)

    inserted = 0
    t = t_start
    while t < now:
        hour = t.hour
        for district in districts:
            # Incidents
            base = BASE_INCIDENT_RATE.get(district, 1.0)
            rate = base * DIURNAL[hour]
            count = int(rng.poisson(rate))
            if count > 0:
                insert_event(conn, {
                    "id": f"baseline:incidents:{district}:{t.isoformat()}",
                    "source": "incidents",
                    "ts_utc": t.isoformat(),
                    "ingested_at": t.isoformat(),
                    "lat": None, "lon": None, "h3": None,
                    "district": district,
                    "kind": "complaint",
                    "value": float(count),
                    "unit": "count",
                    "severity": min(count / 10.0, 1.0),
                    "label": f"Baseline {count} complaints",
                    "is_simulated": 1,
                    "raw_ref": None,
                    "mode": "baseline",
                })
                inserted += 1

            # Transit delay
            delay = float(rng.normal(BASE_DELAY_MIN * DIURNAL[hour], 1.2))
            delay = max(0.0, delay)
            insert_event(conn, {
                "id": f"baseline:transit:{district}:{t.isoformat()}",
                "source": "transit",
                "ts_utc": t.isoformat(),
                "ingested_at": t.isoformat(),
                "lat": None, "lon": None, "h3": None,
                "district": district,
                "kind": "route_delay",
                "value": delay,
                "unit": "min",
                "severity": min(delay / 15.0, 1.0),
                "label": f"Baseline delay {delay:.1f} min",
                "is_simulated": 1,
                "raw_ref": None,
                "mode": "baseline",
            })
            inserted += 1

        t += timedelta(minutes=5)

    log.info("Baseline seeded: %d events across %d days", inserted, days)
