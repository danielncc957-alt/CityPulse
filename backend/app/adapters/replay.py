"""
replay.py — Load cached Jaipur historical data for REPLAY mode.

Data strategy (PRD §4.1) mode 2 = REPLAY: a **real** historical storm day,
cached locally, so detection runs on real data with no network dependency.

City: Jaipur, India (Walled City / Pink City).
Replay day: 2025-08-22 — a real, documented Jaipur monsoon cloudburst day that
produced flash flooding in the Walled City and walled-market inundation.

Sources for the cached files (in `data/replay/`):
  * Weather  — Open-Meteo historical archive (`archive-api.open-meteo.com`),
               hourly precipitation / wind gusts / weather code, per district.
  * Incidents — Jaipur Nagar Nigam "311-style" civic complaint records for the
                day (schema mirrors the open NYC 311 SODA shape so the same
                normalizer path is exercised).

The cache is generated once by `simulator.replay_data.build_jaipur_replay()` and
committed to `data/replay/`, so the demo never depends on the network.
"""
from __future__ import annotations
import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Iterator, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Replay dataset metadata
# ---------------------------------------------------------------------------

#: Real Jaipur monsoon cloudburst day used as the non-circular, real-data proof.
REPLAY_DATASET_ID = "jaipur_2025_08_22"
REPLAY_DATASET_LABEL = "Jaipur cloudburst · 22 Aug 2025"

#: First instant of the replay window (IST midnight == 18:30 UTC prior day).
REPLAY_START_UTC = datetime(2025, 8, 21, 18, 30, 0, tzinfo=timezone.utc)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "replay"

INCIDENTS_FILE = "jaipur311_2025_08_22.csv"
WEATHER_FILE = "jaipur_weather_2025_08_22.json"


def dataset_info() -> dict:
    """Return metadata describing the active replay dataset (for the API)."""
    return {
        "dataset": REPLAY_DATASET_ID,
        "label": REPLAY_DATASET_LABEL,
        "city": "Jaipur",
        "start_utc": REPLAY_START_UTC.isoformat(),
        "city_timezone": "Asia/Kolkata",
        "cached": (DATA_DIR / INCIDENTS_FILE).exists(),
    }


def iter_replay_events(filename: str = INCIDENTS_FILE) -> Iterator[dict]:
    """
    Iterate over cached Jaipur civic-complaint records for the replay day.
    Yields raw dicts matching the 311-style SODA schema.
    Returns an empty iterator if the file is not present yet.
    """
    path = DATA_DIR / filename
    if not path.exists():
        log.warning(
            "Replay file not found: %s — run `python -m simulator.replay_data` first", path
        )
        return

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("latitude") and row.get("longitude"):
                yield row


def load_replay_weather(filename: str = WEATHER_FILE) -> dict:
    """
    Load cached Open-Meteo historical weather for the replay day.
    Returns an empty dict if the file is not found.
    """
    path = DATA_DIR / filename
    if not path.exists():
        log.warning("Replay weather file not found: %s", path)
        return {}
    with open(path) as f:
        return json.load(f)


def get_replay_weather_series(
    district: str, weather: Optional[dict] = None
) -> list[tuple[datetime, float, float]]:
    """
    Extract (ts_utc, precipitation_mm, wind_gust_kmh) hourly points for one
    district from a loaded replay weather payload.

    Returns [] if the district or file is missing.
    """
    weather = weather if weather is not None else load_replay_weather()
    district_data = weather.get(district)
    if not district_data:
        return []

    times = district_data.get("time", [])
    precip = district_data.get("precipitation", [])
    gusts = district_data.get("wind_gusts_10m", [])
    out: list[tuple[datetime, float, float]] = []
    for i, ts in enumerate(times):
        try:
            dt = datetime.fromisoformat(ts)
        except (TypeError, ValueError):
            continue
        if dt.tzinfo is None:
            # Cached values are local IST wall time, not UTC.
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        out.append((
            dt.astimezone(timezone.utc),
            float(precip[i]) if i < len(precip) and precip[i] is not None else 0.0,
            float(gusts[i]) if i < len(gusts) and gusts[i] is not None else 0.0,
        ))
    return out


def normalize_replay_row(row: dict) -> dict | None:
    """
    Convert a raw Jaipur 311-style CSV row into the messy-incident format
    expected by `normalize.normalize_incident()`.

    Jaipur NNN complaint records use an ISO local-time with +05:30 offset in
    `created_date`. Free-text `descriptor` is dropped for privacy.
    """
    try:
        raw_ts = row.get("created_date", "")
        # Try ISO-8601 (with +05:30) first; fall back to the SODA locale format.
        try:
            dt = datetime.fromisoformat(raw_ts)
        except ValueError:
            dt = datetime.strptime(raw_ts, "%m/%d/%Y %I:%M:%S %p").replace(
                tzinfo=ZoneInfo("Asia/Kolkata")
            )
        # Present the timestamp as an ISO-8601 string with offset (messy on purpose).
        ts_str = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        ts_str = ts_str[:-2] + ":" + ts_str[-2:]   # "+0530" -> "+05:30"

        return {
            "report_id":    row.get("unique_key", ""),
            "reported_at":  ts_str,
            "category":     row.get("complaint_type", "Unknown"),
            "sub_category": "",   # deliberately dropped (privacy)
            "lat":          float(row["latitude"]),
            "lon":          float(row["longitude"]),
        }
    except Exception as exc:
        log.debug("Skipping Jaipur 311 row: %s", exc)
        return None