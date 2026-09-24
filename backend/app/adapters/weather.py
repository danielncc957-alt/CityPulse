"""
weather.py — Open-Meteo Forecast adapter.
Fetches real weather for all districts defined in city.json.
No API key required. CC BY 4.0 attribution required.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://api.open-meteo.com/v1/forecast"

PARAMS = {
    "current": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,weather_code,relative_humidity_2m",
    "minutely_15": "precipitation",
    "timezone": "UTC",
}


async def fetch_weather(lat: float, lon: float) -> Optional[dict]:
    """Fetch current weather for a single lat/lon. Returns raw Open-Meteo JSON or None."""
    params = {**PARAMS, "latitude": lat, "longitude": lon}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        log.warning("Weather fetch failed for (%.4f, %.4f): %s", lat, lon, exc)
        return None


async def fetch_all_districts(districts: list[dict]) -> list[tuple[float, float, dict]]:
    """
    Fetch weather for all districts. Returns list of (lat, lon, raw_json).
    Failed fetches are skipped with a warning.
    """
    import asyncio
    tasks = [fetch_weather(d["lat"], d["lon"]) for d in districts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for d, r in zip(districts, results):
        if isinstance(r, dict):
            out.append((d["lat"], d["lon"], r))
        else:
            log.warning("Skipping weather for %s: %s", d["name"], r)
    return out
