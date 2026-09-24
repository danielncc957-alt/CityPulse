"""Build the cached Jaipur REPLAY dataset.

The fixture represents the 22 Aug 2025 Jaipur monsoon cloudburst. Weather
values are shaped like Open-Meteo historical data; civic incidents follow the
Jal Rajasthan Urban Services / 311-style complaint schema. Generate once and
commit the files under data/replay/ so replay never needs a network call.

Run: python -m simulator.replay_data
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "replay"
CITY = json.loads((ROOT / "city.json").read_text(encoding="utf-8"))
DISTRICTS = CITY["districts"]

# Local IST wall time; the replay adapter converts it to UTC.
START_IST = datetime(2025, 8, 22, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
WEATHER_FILE = DATA_DIR / "jaipur_weather_2025_08_22.json"
INCIDENTS_FILE = DATA_DIR / "jaipur311_2025_08_22.csv"

# Cloudburst shape: dry overnight, build from 14:00, peak 17:00–19:00 IST.
PRECIP_MM = (
    [0.0] * 12
    + [0.2, 0.5, 1.2, 3.5, 8.0, 18.0, 34.0, 48.0, 41.0, 26.0, 14.0, 6.0]
)
GUSTS_KMH = (
    [12.0] * 12
    + [18.0, 25.0, 38.0, 52.0, 66.0, 74.0, 82.0, 78.0, 63.0, 49.0, 36.0, 25.0]
)
WEATHER_CODE = (
    [0] * 12
    + [61, 61, 63, 65, 80, 95, 95, 95, 95, 80, 65, 63]
)

COMPLAINT_TYPES = [
    ("Waterlogging", "Water enters homes"),
    ("Sewer", "Blocked drain"),
    ("Road Damage", "Pothole / washed-out road"),
    ("Traffic Signal", "Signal not working"),
    ("Solid Waste", "Debris blocking road"),
    ("Streetlight", "No power after flooding"),
]
# Walled City and Tonk Road are the flood hotspots in this fixture.
HOTSPOTS = {
    "Walled City": 3.5,
    "Tonk Road": 2.2,
    "Sodala": 1.8,
    "C-Scheme": 1.7,
    "Mansarovar": 1.3,
    "Jagatpura": 1.2,
    "Vaishali Nagar": 1.1,
    "Malviya Nagar": 1.0,
}


def _weather_payload() -> dict:
    payload: dict[str, dict] = {}
    for idx, district in enumerate(DISTRICTS):
        # Small deterministic spatial variation: western districts get +12% rain.
        spatial = 1.12 if district["lon"] < 75.80 else 0.94
        times: list[str] = []
        precipitation: list[float] = []
        gusts: list[float] = []
        codes: list[int] = []
        for hour in range(24):
            local = START_IST + timedelta(hours=hour)
            times.append(local.strftime("%Y-%m-%dT%H:%M"))
            rain = round(PRECIP_MM[hour] * spatial, 1)
            # Slight deterministic peak lag across districts.
            phase = min(23, max(0, hour + (idx % 3 - 1)))
            precipitation.append(round(PRECIP_MM[phase] * spatial, 1))
            gusts.append(round(GUSTS_KMH[phase] * (1.0 + 0.02 * (idx % 4)), 1))
            codes.append(WEATHER_CODE[phase])
            # Keep rain present even when shifted (the storm is broad).
            if rain > 0 and precipitation[-1] == 0:
                precipitation[-1] = rain
        payload[district["name"]] = {
            "latitude": district["lat"],
            "longitude": district["lon"],
            "timezone": "Asia/Kolkata",
            "time": times,
            "precipitation": precipitation,
            "wind_gusts_10m": gusts,
            "weather_code": codes,
        }
    return payload


def _incident_rows(seed: int = 2205) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    key = 0
    for district in DISTRICTS:
        name = district["name"]
        boost = HOTSPOTS[name]
        for hour in range(24):
            # Complaint rise begins at 16:00 and peaks at 18:00.
            shape = max(0.05, 1.7 ** (max(0, hour - 14) / 1.5)) if hour >= 14 else 0.12
            count = int(rng.poisson(0.55 * boost * shape))
            for _ in range(count):
                key += 1
                category, descriptor = COMPLAINT_TYPES[
                    int(rng.integers(len(COMPLAINT_TYPES)))
                ]
                local_ts = START_IST + timedelta(
                    hours=hour,
                    minutes=int(rng.integers(0, 60)),
                    seconds=int(rng.integers(0, 60)),
                )
                rows.append({
                    "unique_key": f"JNJ-20250822-{key:06d}",
                    "created_date": local_ts.isoformat(),
                    "complaint_type": category,
                    "descriptor": descriptor,
                    "district": name,
                    "latitude": f"{district['lat'] + float(rng.uniform(-0.008, 0.008)):.6f}",
                    "longitude": f"{district['lon'] + float(rng.uniform(-0.008, 0.008)):.6f}",
                })
    # Stable chronological replay order.
    rows.sort(key=lambda r: (r["created_date"], r["unique_key"]))
    return rows


def build_jaipur_replay() -> tuple[Path, Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEATHER_FILE.write_text(
        json.dumps(_weather_payload(), indent=2), encoding="utf-8"
    )
    rows = _incident_rows()
    with INCIDENTS_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return WEATHER_FILE, INCIDENTS_FILE


if __name__ == "__main__":
    weather_path, incident_path = build_jaipur_replay()
    print(f"Wrote {weather_path}")
    print(f"Wrote {incident_path}")
