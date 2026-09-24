import { useEffect } from 'react'
import { useStore } from '../store'
import { fetchWeather } from '../api'
import type { DistrictWeather } from '../types'

// Refresh live weather every 10 minutes
const REFRESH_MS = 10 * 60 * 1000

function fmt(val: number | undefined, decimals = 1): string {
  return val !== undefined ? val.toFixed(decimals) : '—'
}

function WeatherCard({ d }: { d: DistrictWeather }) {
  const temp = d.temperature?.value
  const wind = d.wind_speed?.value
  const gust = d.gust?.value
  const rain = d.rain_rate?.value
  const hum  = d.humidity?.value

  // Colour temperature reading
  const tempColor =
    temp === undefined ? 'var(--color-muted)'
    : temp >= 40 ? '#E11D48'
    : temp >= 35 ? '#F97316'
    : temp >= 28 ? '#FBBF24'
    : '#2DD4BF'

  return (
    <div
      className="rounded-xl p-3 flex flex-col gap-1 min-w-[140px] shrink-0"
      style={{ background: 'var(--color-surface)' }}
    >
      {/* District name */}
      <p
        className="text-xs font-semibold truncate"
        style={{ color: 'var(--color-text-2)' }}
        title={d.district}
      >
        {d.district}
      </p>

      {/* Temperature — hero number */}
      <p
        className="text-2xl font-bold leading-none"
        style={{ color: tempColor }}
        aria-label={`Temperature ${fmt(temp)}°C`}
      >
        {fmt(temp, 1)}<span className="text-sm font-normal ml-0.5">°C</span>
      </p>

      {/* Wind + gust */}
      <p className="text-xs" style={{ color: 'var(--color-text-2)' }}>
        <span title="Wind speed">💨 {fmt(wind, 0)} km/h</span>
        {gust !== undefined && (
          <span className="ml-1" style={{ color: 'var(--color-muted)' }} title="Gust">
            ↑{fmt(gust, 0)}
          </span>
        )}
      </p>

      {/* Rain */}
      <p className="text-xs" style={{ color: rain && rain > 0 ? '#60A5FA' : 'var(--color-muted)' }}>
        🌧 {rain !== undefined ? `${fmt(rain, 1)} mm/h` : '—'}
      </p>

      {/* Humidity */}
      <p className="text-xs" style={{ color: 'var(--color-muted)' }}>
        💧 {hum !== undefined ? `${fmt(hum, 0)}%` : '—'}
      </p>
    </div>
  )
}

export function WeatherStrip() {
  const weather = useStore((s) => s.weather)
  const setWeather = useStore((s) => s.setWeather)

  useEffect(() => {
    const load = () =>
      fetchWeather()
        .then((r) => setWeather(r.districts))
        .catch(() => {/* non-fatal — backend may not have data yet */})

    load()
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [setWeather])

  if (weather.length === 0) {
    return (
      <div
        className="rounded-xl p-4 text-xs"
        style={{ background: 'var(--color-surface)', color: 'var(--color-muted)' }}
      >
        🌤 Weather data loading… (fetched from Open-Meteo every 15 min)
      </div>
    )
  }

  return (
    <div>
      <p
        className="text-xs font-semibold uppercase tracking-widest mb-2"
        style={{ color: 'var(--color-text-2)' }}
      >
        Live Weather · Jaipur
        <span className="ml-2 font-normal normal-case" style={{ color: 'var(--color-muted)' }}>
          via Open-Meteo
        </span>
      </p>
      {/* Horizontal scroll on narrow viewports */}
      <div className="flex gap-3 overflow-x-auto pb-1" role="list" aria-label="District weather">
        {weather.map((d) => (
          <div key={d.district} role="listitem">
            <WeatherCard d={d} />
          </div>
        ))}
      </div>
    </div>
  )
}
