// Shared TypeScript types — mirrors backend Pydantic models

export type PulseLevel = 'Calm' | 'Watch' | 'Strained' | 'Alert'
export type FeedSource = 'weather' | 'air' | 'incidents' | 'transit' | 'outage'
export type FeedStatus = 'ok' | 'delayed' | 'down'
export type ConfidenceTier = 'Weak signal' | 'Moderate signal' | 'Strong signal'

export interface DistrictPulse {
  name: string
  pulse: number
  level: PulseLevel
  components: Record<string, number | null>
}

export interface CityPulse {
  ts: string
  pulse: number
  level: PulseLevel
  districts: DistrictPulse[]
}

export interface FeedHealth {
  source: FeedSource
  status: FeedStatus
  last_ok_ts: string | null
  latency_ms: number | null
  expected_interval_s: number
  is_simulated: boolean
}

export interface InsightLink {
  feeds: FeedSource[]
  signal: ConfidenceTier
  lag_min: number | null
  r_value: number | null
}

export interface Insight {
  id: string
  ts: string
  district: string
  level: PulseLevel
  headline: string
  why_it_matters: string
  link: InsightLink | null
  facts: Record<string, number | string>
  caveats: string[]
  confidence: ConfidenceTier | null
  evidence_json: Record<string, unknown> | null
  method: string
  text_source: 'template' | 'llm'
}

export interface StateResponse {
  ts: string
  city: CityPulse
  feed_health: FeedHealth[]
  insights: Insight[]
}

export interface WeatherReading {
  value: number
  unit: string
}

export interface DistrictWeather {
  district: string
  ts: string
  temperature?: WeatherReading
  wind_speed?: WeatherReading
  gust?: WeatherReading
  rain_rate?: WeatherReading
  humidity?: WeatherReading
}

export interface WeatherResponse {
  districts: DistrictWeather[]
}

export interface TimeseriesPoint {
  ts: string
  value: number
}

export interface TimeseriesResponse {
  district: string
  source: string
  window: string
  bins: TimeseriesPoint[]
}

// SSE event payloads
export type SseEventType = 'pulse' | 'insight' | 'feed_health' | 'event' | 'alert' | 'ping'

export interface SsePulsePayload {
  ts: string
  city: { pulse: number; level: PulseLevel }
  districts: DistrictPulse[]
}

export interface SseFeedHealthPayload {
  feeds: FeedHealth[]
}

export interface SseAlertPayload {
  district: string
  level: PulseLevel
  headline: string
  signal: ConfidenceTier | null
}
