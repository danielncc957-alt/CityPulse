import type {
  StateResponse, TimeseriesResponse,
  Insight, SseEventType, WeatherResponse,
} from './types'
import { useStore } from './store'

const BASE = '/api'

// ---------------------------------------------------------------------------
// REST
// ---------------------------------------------------------------------------

export async function fetchState(): Promise<StateResponse> {
  const res = await fetch(`${BASE}/state`)
  if (!res.ok) throw new Error(`/api/state ${res.status}`)
  return res.json()
}

export async function fetchInsights(since?: string): Promise<Insight[]> {
  const url = since ? `${BASE}/insights?since=${encodeURIComponent(since)}` : `${BASE}/insights`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`/api/insights ${res.status}`)
  return res.json()
}

export async function fetchExplain(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/insights/${id}/explain`)
  if (!res.ok) throw new Error(`/api/insights/${id}/explain ${res.status}`)
  return res.json()
}

export async function fetchTimeseries(
  district: string, source: string, window = '6h'
): Promise<TimeseriesResponse> {
  const res = await fetch(
    `${BASE}/timeseries?district=${encodeURIComponent(district)}&source=${source}&window=${window}`
  )
  if (!res.ok) throw new Error(`/api/timeseries ${res.status}`)
  return res.json()
}

export async function postScenario(name: string, speed: number) {
  await fetch(`${BASE}/demo/scenario`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, speed }),
  })
}

export async function postFeedMode(source: string, mode: string) {
  await fetch(`${BASE}/demo/feed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, mode }),
  })
}

export async function fetchWeather(): Promise<WeatherResponse> {
  const res = await fetch(`${BASE}/weather`)
  if (!res.ok) throw new Error(`/api/weather ${res.status}`)
  return res.json()
}

export async function postReplay(speed = 60) {
  await fetch(`${BASE}/replay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset: 'jaipur_2025_08_22', speed }),
  })
}

// ---------------------------------------------------------------------------
// SSE
// ---------------------------------------------------------------------------

let _es: EventSource | null = null

export function connectSSE(): void {
  if (_es) return
  const { setCity, updateDistricts, setFeedHealth, addInsight, addAlert, setConnected, setLastUpdate } = useStore.getState()

  const connect = () => {
    _es = new EventSource(`${BASE}/stream`)

    _es.onopen = () => {
      setConnected(true)
    }

    _es.onerror = () => {
      setConnected(false)
      _es?.close()
      _es = null
      // Auto-reconnect after 3 s
      setTimeout(connect, 3000)
    }

    const handle = (type: SseEventType, data: string) => {
      try {
        const payload = JSON.parse(data)
        switch (type) {
          case 'pulse':
            setLastUpdate(payload.ts)
            if (payload.city) setCity({ ...payload.city, ts: payload.ts })
            if (payload.districts) updateDistricts(payload.districts)
            break
          case 'insight':
            addInsight(payload)
            break
          case 'feed_health':
            if (payload.feeds) setFeedHealth(payload.feeds)
            break
          case 'alert':
            addAlert(payload)
            break
          default:
            break
        }
      } catch (_) {}
    }

    for (const t of ['pulse', 'insight', 'feed_health', 'alert'] as SseEventType[]) {
      _es.addEventListener(t, (e: MessageEvent) => handle(t, e.data))
    }
  }

  connect()
}
