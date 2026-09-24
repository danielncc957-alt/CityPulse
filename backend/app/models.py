"""
models.py — Shared Pydantic schemas for CityPulse.
P1 owns this file. P2 reads Event; P3's types.ts mirrors these.
"""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Core event schema — every feed is normalized into this
# ---------------------------------------------------------------------------

class Event(BaseModel):
    id: str                         # "{source}:{native_id_or_hash}"
    source: Literal["weather", "air", "incident", "transit", "outage"]
    ts_utc: datetime                # always UTC, timezone-aware
    ingested_at: datetime           # for latency / staleness tracking
    lat: Optional[float] = None
    lon: Optional[float] = None
    h3: Optional[str] = None        # res-8 H3 cell; None only for feed-level data
    district: Optional[str] = None
    kind: str                       # e.g. "rain_rate", "us_aqi", "sewer", "route_delay"
    value: Optional[float] = None   # normalized numeric
    unit: Optional[str] = None
    severity: float = Field(ge=0.0, le=1.0)   # 0..1 raw feed-native severity
    label: str                      # short human label — NO free text from users
    is_simulated: bool = False
    raw_ref: Optional[str] = None   # pointer to raw payload — never shown in UI


# ---------------------------------------------------------------------------
# Feed health
# ---------------------------------------------------------------------------

FeedStatus = Literal["ok", "delayed", "down"]

class FeedHealth(BaseModel):
    source: str
    status: FeedStatus
    last_ok_ts: Optional[datetime] = None
    latency_ms: Optional[float] = None
    expected_interval_s: int
    is_simulated: bool = False


# ---------------------------------------------------------------------------
# Pulse snapshot (per district + city-wide)
# ---------------------------------------------------------------------------

PulseLevel = Literal["Calm", "Watch", "Strained", "Alert"]

class DistrictPulse(BaseModel):
    name: str
    pulse: int                      # 0..100
    level: PulseLevel
    components: dict[str, Optional[float]]  # feed → stress 0..1, None = unavailable

class CityPulse(BaseModel):
    ts: datetime
    pulse: int
    level: PulseLevel
    districts: list[DistrictPulse]


# ---------------------------------------------------------------------------
# Insight
# ---------------------------------------------------------------------------

ConfidenceTier = Literal["Weak signal", "Moderate signal", "Strong signal"]
TextSource = Literal["template", "llm"]

class InsightLink(BaseModel):
    feeds: list[str]
    signal: ConfidenceTier
    lag_min: Optional[int] = None
    r_value: Optional[float] = None

class Insight(BaseModel):
    id: str
    ts: datetime
    district: str
    level: PulseLevel
    headline: str
    why_it_matters: str
    link: Optional[InsightLink] = None
    facts: dict                     # the grounding JSON sent to / checked against LLM
    caveats: list[str] = Field(default_factory=list)
    confidence: Optional[ConfidenceTier] = None
    evidence_json: Optional[dict] = None
    method: str = "robust_z"
    text_source: TextSource = "template"


# ---------------------------------------------------------------------------
# SSE payloads
# ---------------------------------------------------------------------------

class PulseEvent(BaseModel):
    ts: datetime
    city: dict
    districts: list[dict]

class FeedHealthEvent(BaseModel):
    feeds: list[FeedHealth]

class AlertPayload(BaseModel):
    district: str
    level: PulseLevel
    headline: str
    signal: Optional[ConfidenceTier] = None


# ---------------------------------------------------------------------------
# API response wrappers
# ---------------------------------------------------------------------------

class StateResponse(BaseModel):
    ts: datetime
    city: CityPulse
    feed_health: list[FeedHealth]
    insights: list[Insight]         # top 3 active insights

class TimeseriesPoint(BaseModel):
    ts: datetime
    value: float

class TimeseriesResponse(BaseModel):
    district: str
    source: str
    window: str
    bins: list[TimeseriesPoint]
