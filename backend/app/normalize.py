"""
normalize.py — Per-source raw payload → unified Event schema.
P1 owns this file.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .models import Event
from .geo import zone_of
from .clock import now as clock_now


def _utc(ts: Any) -> datetime:
    """Parse any timestamp format into UTC-aware datetime. Raises on failure."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            raise ValueError(f"Naive datetime rejected: {ts}")
        return ts.astimezone(timezone.utc)
    if isinstance(ts, (int, float)):
        # Epoch seconds
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(ts, str):
        # Handles ISO-8601 with or without timezone offset
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # Open-Meteo returns naive UTC strings when timezone=UTC is requested
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise TypeError(f"Cannot parse timestamp: {ts!r}")


def normalize_weather(raw: dict, lat: float, lon: float) -> list[Event]:
    """Open-Meteo current weather → Events."""
    ingested = clock_now()
    h3_cell, district = zone_of(lat, lon)
    events = []

    current = raw.get("current", {})
    ts = _utc(current.get("time", ingested.isoformat()))

    if (rain := current.get("precipitation")) is not None:
        events.append(Event(
            id=f"weather:rain:{h3_cell}:{ts.isoformat()}",
            source="weather", ts_utc=ts, ingested_at=ingested,
            lat=lat, lon=lon, h3=h3_cell, district=district,
            kind="rain_rate", value=float(rain), unit="mm/h",
            severity=min(float(rain) / 10.0, 1.0),
            label=f"Rain {rain:.1f} mm/h", is_simulated=False,
        ))
    if (temp := current.get("temperature_2m")) is not None:
        events.append(Event(
            id=f"weather:temp:{h3_cell}:{ts.isoformat()}",
            source="weather", ts_utc=ts, ingested_at=ingested,
            lat=lat, lon=lon, h3=h3_cell, district=district,
            kind="temperature", value=float(temp), unit="°C",
            severity=min(max((float(temp) - 35) / 15, 0), 1.0),
            label=f"{temp:.1f}°C", is_simulated=False,
        ))
    if (wind := current.get("wind_speed_10m")) is not None:
        events.append(Event(
            id=f"weather:wind:{h3_cell}:{ts.isoformat()}",
            source="weather", ts_utc=ts, ingested_at=ingested,
            lat=lat, lon=lon, h3=h3_cell, district=district,
            kind="wind_speed", value=float(wind), unit="km/h",
            severity=min(max((float(wind) - 20) / 60, 0), 1.0),
            label=f"Wind {wind:.0f} km/h", is_simulated=False,
        ))
    if (gust := current.get("wind_gusts_10m")) is not None:
        events.append(Event(
            id=f"weather:gust:{h3_cell}:{ts.isoformat()}",
            source="weather", ts_utc=ts, ingested_at=ingested,
            lat=lat, lon=lon, h3=h3_cell, district=district,
            kind="gust", value=float(gust), unit="km/h",
            severity=min(max((float(gust) - 40) / 40, 0), 1.0),
            label=f"Gust {gust:.0f} km/h", is_simulated=False,
        ))
    if (humidity := current.get("relative_humidity_2m")) is not None:
        events.append(Event(
            id=f"weather:humidity:{h3_cell}:{ts.isoformat()}",
            source="weather", ts_utc=ts, ingested_at=ingested,
            lat=lat, lon=lon, h3=h3_cell, district=district,
            kind="humidity", value=float(humidity), unit="%",
            severity=0.0,
            label=f"Humidity {humidity:.0f}%", is_simulated=False,
        ))
    return events


def normalize_air(raw: dict, lat: float, lon: float) -> list[Event]:
    """Open-Meteo air quality → Events."""
    ingested = clock_now()
    h3_cell, district = zone_of(lat, lon)
    current = raw.get("current", {})
    ts = _utc(current.get("time", ingested.isoformat()))
    events = []

    if (aqi := current.get("us_aqi")) is not None:
        events.append(Event(
            id=f"air:aqi:{h3_cell}:{ts.isoformat()}",
            source="air", ts_utc=ts, ingested_at=ingested,
            lat=lat, lon=lon, h3=h3_cell, district=district,
            kind="us_aqi", value=float(aqi), unit="AQI",
            severity=min(max((float(aqi) - 50) / 150, 0), 1.0),
            label=f"AQI {aqi:.0f}", is_simulated=False,
        ))

    # Preserve particulate channels. A Jaipur dust storm can produce a large
    # PM10 surge even when a composite AQI is unavailable or changes slowly.
    for field, kind, unit, alert_above in (
        ("pm2_5", "pm2_5", "µg/m³", 75.0),
        ("pm10", "pm10", "µg/m³", 150.0),
    ):
        if (value := current.get(field)) is not None:
            value = float(value)
            events.append(Event(
                id=f"air:{kind}:{h3_cell}:{ts.isoformat()}",
                source="air", ts_utc=ts, ingested_at=ingested,
                lat=lat, lon=lon, h3=h3_cell, district=district,
                kind=kind, value=value, unit=unit,
                severity=min(max((value - alert_above) / 300.0, 0), 1.0),
                label=f"{kind.upper()} {value:.0f} µg/m³", is_simulated=False,
            ))
    return events


def normalize_incident(raw: dict) -> Event | None:
    """Incident simulator record → Event. Messy format: ISO-8601 with tz offset."""
    ingested = clock_now()
    try:
        ts = _utc(raw["reported_at"])   # e.g. "2026-09-24T10:32:11+05:30"
        lat, lon = float(raw["lat"]), float(raw["lon"])
        h3_cell, district = zone_of(lat, lon)
        uid = raw.get("report_id", hashlib.md5(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:12])
        return Event(
            id=f"incident:{uid}",
            source="incidents", ts_utc=ts, ingested_at=ingested,
            lat=lat, lon=lon, h3=h3_cell, district=district,
            kind=raw.get("category", "complaint").lower().replace(" ", "_"),
            value=1.0, unit="count",
            severity=0.5,
            label=raw.get("category", "Complaint"),
            is_simulated=True,
        )
    except Exception:
        return None


def normalize_transit(raw: dict) -> Event | None:
    """Transit simulator record → Event. Messy format: epoch seconds, delay in seconds."""
    ingested = clock_now()
    try:
        ts = _utc(int(raw["update_epoch"]))   # epoch int → UTC datetime
        delay_s = float(raw.get("delay_s", 0))
        delay_min = delay_s / 60.0            # normalizer converts seconds → minutes
        route = str(raw.get("route_id", "?"))

        # Route → district lookup (from city.json via geo.py is fine for zone_of,
        # but transit has no lat/lon — use the route_zone_map)
        import json as _json
        from pathlib import Path
        city = _json.loads((Path(__file__).parent.parent.parent / "city.json").read_text())
        district = city.get("route_zone_map", {}).get(route)
        if not district:
            return None

        return Event(
            id=f"transit:{route}:{ts.isoformat()}",
            source="transit", ts_utc=ts, ingested_at=ingested,
            lat=None, lon=None, h3=None, district=district,
            kind="route_delay", value=delay_min, unit="min",
            severity=min(delay_min / 15.0, 1.0),
            label=f"Route {route} +{delay_min:.0f} min",
            is_simulated=True,
        )
    except Exception:
        return None
