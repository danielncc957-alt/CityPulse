import { useEffect, useState } from 'react'
import { fetchExplain } from '../api'
import type { Insight } from '../types'

export function WhyPanel({ insight }: { insight: Insight }) {
  const [explain, setExplain] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    fetchExplain(insight.id)
      .then(setExplain)
      .catch(() => {})
  }, [insight.id])

  const evidence = explain?.evidence_json as Record<string, unknown> | undefined
  const corr = evidence?.correlation as Record<string, unknown> | undefined

  return (
    <div className="text-xs flex flex-col gap-3">
      <p className="font-semibold uppercase tracking-widest"
        style={{ color: 'var(--color-text-2)' }}>
        Why we think this
      </p>

      {/* Why it matters */}
      <p style={{ color: 'var(--color-text-2)' }}>{insight.why_it_matters}</p>

      {/* Facts */}
      {Object.keys(insight.facts).length > 0 && (
        <div>
          <p className="font-semibold mb-1">Data points</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(insight.facts).map(([k, v]) => (
              <span
                key={k}
                className="font-mono px-2 py-0.5 rounded"
                style={{ background: 'var(--color-bg)', color: 'var(--color-text)' }}
              >
                {k}: {typeof v === 'number' ? v.toFixed(1) : String(v)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Correlation evidence */}
      {insight.link && (
        <div>
          <p className="font-semibold mb-1">Correlation</p>
          <div className="flex flex-col gap-1" style={{ color: 'var(--color-text-2)' }}>
            <p>Feeds: {insight.link.feeds.join(' → ')}</p>
            {insight.link.lag_min != null && <p>Lag: {insight.link.lag_min} min</p>}
            {insight.link.r_value != null && <p>r = {insight.link.r_value.toFixed(2)}</p>}
            {corr && <p>Checks passed: {String(corr.checks ?? '—')}/4</p>}
          </div>
        </div>
      )}

      {/* Method */}
      <p style={{ color: 'var(--color-muted)' }}>
        Method: {insight.method} · Source: {insight.text_source}
      </p>

      {/* Disclaimer */}
      <p
        className="px-2 py-1 rounded text-xs font-medium"
        style={{ background: 'var(--color-bg)', color: '#FBBF24' }}
      >
        ⚠ Possible link, not a confirmed cause.
      </p>

      {/* Caveats */}
      {insight.caveats.length > 0 && (
        <div>
          {insight.caveats.map((c, i) => (
            <p key={i} style={{ color: 'var(--color-muted)' }}>• {c}</p>
          ))}
        </div>
      )}
    </div>
  )
}
