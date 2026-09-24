"""
transit_sim.py — Synthetic transit delay generator.
P4 owns this file.

DELIBERATELY MESSY FORMAT: epoch seconds (integer), delay in seconds.
The normalizer (P1) must convert epoch→UTC and seconds→minutes.

Usage:
    from simulator.transit_sim import TransitSimulator
    sim = TransitSimulator()
    records = sim.generate(clock_now(), scenario_name="storm")
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Routes (from city.json route_zone_map keys)
# ---------------------------------------------------------------------------

ALL_ROUTES = ["A", "C", "E", "1", "2", "3", "4", "5", "6", "7",
              "B", "D", "F", "G", "J", "L", "M", "N", "Q", "R", "W"]

# Base delay seconds per route (slightly different baseline per route)
BASE_DELAY_S: dict[str, float] = {r: float(30 + i * 5) for i, r in enumerate(ALL_ROUTES)}

# Scenario delay multipliers
SCENARIO_MULTIPLIERS: dict[str, float] = {
    "storm": 3.0,
    "smog":  1.1,
    "quiet": 0.5,
    "live":  1.0,
}


class TransitSimulator:
    def __init__(self, seed: int = 99):
        self._rng = np.random.default_rng(seed)

    def generate(
        self,
        t: datetime,
        scenario_name: str = "live",
        routes: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Generate one batch of transit delay records.
        Returns raw dicts — deliberately messy (epoch int, delay in seconds).
        """
        multiplier = SCENARIO_MULTIPLIERS.get(scenario_name, 1.0)
        target_routes = routes or ALL_ROUTES
        records = []

        epoch = int(t.replace(tzinfo=timezone.utc).timestamp())  # deliberate: no tz info in output

        for route in target_routes:
            base_s = BASE_DELAY_S.get(route, 60.0) * multiplier
            delay_s = max(0.0, float(self._rng.normal(base_s, base_s * 0.3)))
            status = "delayed" if delay_s > 60 else "on_time"
            records.append({
                "route_id":     route,
                "update_epoch": epoch,          # messy: int epoch seconds, no timezone
                "delay_s":      int(delay_s),   # messy: seconds (normalizer converts to min)
                "status":       status,
            })

        return records
