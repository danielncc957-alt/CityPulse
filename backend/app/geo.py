"""
geo.py — H3 spatial helpers.
P1 owns this. P2 uses zone_of() when computing per-zone stress.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Optional

import h3

# ---------------------------------------------------------------------------
# Load city config
# ---------------------------------------------------------------------------

_CITY_JSON = Path(__file__).parent.parent.parent / "city.json"

with open(_CITY_JSON) as f:
    _CITY = json.load(f)

H3_RES: int = _CITY.get("h3_resolution", 8)
_DISTRICTS: list[dict] = _CITY["districts"]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def zone_of(lat: float, lon: float) -> tuple[str, Optional[str]]:
    """
    Return (h3_cell, district_name) for a given lat/lon.
    district_name is the nearest named district centroid from city.json.
    """
    cell = h3.latlng_to_cell(lat, lon, H3_RES)
    nearest = min(
        _DISTRICTS,
        key=lambda d: _haversine(lat, lon, d["lat"], d["lon"]),
    )
    return cell, nearest["name"]


def hex_boundary_geojson(cell: str) -> dict:
    """Return a GeoJSON Polygon for the given H3 cell (for the frontend map)."""
    coords = h3.cell_to_boundary(cell)
    # h3 returns (lat, lon) tuples; GeoJSON wants [lon, lat]
    ring = [[lon, lat] for lat, lon in coords]
    ring.append(ring[0])  # close
    return {"type": "Polygon", "coordinates": [ring]}


def neighbours(cell: str, k: int = 1) -> set[str]:
    """Return the k-ring neighbours of a cell (excludes the cell itself)."""
    disk = h3.grid_disk(cell, k)
    return disk - {cell}


def district_centroid_cell(district_name: str) -> Optional[str]:
    """Return the H3 cell for a named district's centroid."""
    for d in _DISTRICTS:
        if d["name"] == district_name:
            return h3.latlng_to_cell(d["lat"], d["lon"], H3_RES)
    return None


def all_district_names() -> list[str]:
    return [d["name"] for d in _DISTRICTS]
