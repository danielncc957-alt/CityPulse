import { useEffect } from 'react'
import { connectSSE, fetchState } from './api'
import { useStore } from './store'
import { PulseHeader } from './components/PulseHeader'
import { HexMap } from './components/HexMap'
import { InsightCards } from './components/InsightCards'
import { FeedStatusBar } from './components/FeedStatusBar'
import { WeatherStrip } from './components/WeatherStrip'

export default function App() {
  const setCity = useStore((s) => s.setCity)
  const setFeedHealth = useStore((s) => s.setFeedHealth)
  const setInsights = useStore((s) => s.setInsights)
  const alerts = useStore((s) => s.alerts)
  const dismissAlert = useStore((s) => s.dismissAlert)

  // Bootstrap: load initial state, then open SSE stream
  useEffect(() => {
    fetchState()
      .then((data) => {
        setCity({ ...data.city, ts: data.ts })
        setFeedHealth(data.feed_health)
        setInsights(data.insights)
      })
      .catch(() => {/* backend may not be up yet; SSE will fill in */})

    connectSSE()
  }, [])

  return (
    <div className="flex flex-col min-h-screen" style={{ background: 'var(--color-bg)' }}>
      {/* Top header — pulse ring, ECG, status badge */}
      <PulseHeader />

      {/* Alert toasts */}
      {alerts.length > 0 && (
        <div className="fixed top-16 right-4 z-50 flex flex-col gap-2 w-80">
          {alerts.map((a, i) => (
            <div
              key={i}
              className="rounded-xl px-4 py-3 text-sm flex items-start gap-3 shadow-lg"
              style={{ background: 'var(--color-surface)', borderLeft: `3px solid ${levelColorRaw(a.level)}` }}
              role="alert"
            >
              <span className="shrink-0 text-base" aria-hidden>🚨</span>
              <div className="flex-1">
                <p className="font-semibold">{a.district}</p>
                <p style={{ color: 'var(--color-text-2)' }}>{a.headline}</p>
              </div>
              <button
                onClick={() => dismissAlert(i)}
                className="shrink-0 text-xs"
                style={{ color: 'var(--color-muted)' }}
                aria-label="Dismiss alert"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Weather strip — live temp, wind, rain per district */}
      <div className="px-4 pb-0 pt-2">
        <WeatherStrip />
      </div>

      {/* Main content */}
      <main className="flex flex-col lg:flex-row flex-1 gap-4 p-4 overflow-hidden">
        {/* Left column — map */}
        <section
          className="lg:flex-1 rounded-xl overflow-hidden"
          style={{ minHeight: 360 }}
          aria-label="District map"
        >
          <HexMap />
        </section>

        {/* Right column — insights + feed health */}
        <aside
          className="lg:w-80 xl:w-96 flex flex-col gap-4 overflow-y-auto"
          style={{ maxHeight: 'calc(100vh - 120px)' }}
          aria-label="Insights and feed status"
        >
          <InsightCards />
          <FeedStatusBar />
        </aside>
      </main>
    </div>
  )
}

// Inline helper so we don't import levelColor from store (avoids circular hint)
function levelColorRaw(level: string): string {
  return (
    { Calm: '#2DD4BF', Watch: '#FBBF24', Strained: '#F97316', Alert: '#E11D48' }[level]
    ?? '#2DD4BF'
  )
}
