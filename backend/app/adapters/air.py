"""
air.py — Open-Meteo Air Quality adapter.
Fetches real AQI data for all districts. No API key required.
"""
from __future__ import annotations
import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

PARAMS = {
    "current": "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone",
    "timezone": "UTC",
}


async def fetch_air(lat: float, lon: float) -> Optional[dict]:
    """Fetch current air quality for a single lat/lon. Returns raw JSON or None."""
    params = {**PARAMS, "latitude": lat, "longitude": lon}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        log.warning("Air quality fetch failed for (%.4f, %.4f): %s", lat, lon, exc)
        return None


async def fetch_all_districts(districts: list[dict]) -> list[tuple[float, float, dict]]:
    """Fetch air quality for all districts. Returns (lat, lon, raw_json) tuples."""
    import asyncio
    tasks = [fetch_air(d["lat"], d["lon"]) for d in districts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for d, r in zip(districts, results):
        if isinstance(r, dict):
            out.append((d["lat"], d["lon"], r))
        else:
            log.warning("Skipping air for %s: %s", d["name"], r)
    return out
