import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore, levelColor, levelIcon } from '../store'
import { WhyPanel } from './WhyPanel'
import type { Insight } from '../types'

const FEED_ICONS: Record<string, string> = {
  weather: '🌧',
  air: '🌫',
  incidents: '📣',
  transit: '🚌',
  outage: '⚡',
}

export function InsightCards() {
  const insights = useStore((s) => s.insights)
  const [expanded, setExpanded] = useState<string | null>(null)

  // Show top 3 non-Calm zones first, then others
  const sorted = [...(insights ?? [])].sort((a, b) => {
    const order = { Alert: 0, Strained: 1, Watch: 2, Calm: 3 }
    return (order[a.level] ?? 3) - (order[b.level] ?? 3)
  }).slice(0, 3)

  if (sorted.length === 0) {
    return (
      <div
        className="flex flex-col gap-3 p-4 rounded-xl"
        style={{ background: 'var(--color-surface)' }}
      >
        <p className="text-sm font-semibold" style={{ color: 'var(--color-text-2)' }}>
          WHAT'S HAPPENING
        </p>
        <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
          All quiet. Here's what we're watching.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs font-semibold uppercase tracking-widest px-1"
        style={{ color: 'var(--color-text-2)' }}>
        What's Happening
      </p>

      <AnimatePresence>
        {sorted.map((ins) => (
          <InsightCard
            key={ins.id}
            insight={ins}
            expanded={expanded === ins.id}
            onToggle={() => setExpanded(expanded === ins.id ? null : ins.id)}
          />
        ))}
      </AnimatePresence>
    </div>
  )
}

function InsightCard({
  insight, expanded, onToggle,
}: {
  insight: Insight
  expanded: boolean
  onToggle: () => void
}) {
  const color = levelColor(insight.level)
  const icon = levelIcon(insight.level)

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
      className="insight-card"
      style={{ borderColor: expanded ? color : undefined }}
    >
      {/* Header row */}
      <button
        className="w-full text-left"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="font-semibold text-sm">{insight.district}</span>
          <span
            className="text-xs font-bold px-2 py-0.5 rounded-full"
            style={{ background: color, color: '#0F172A' }}
            aria-label={`Level: ${insight.level}`}
          >
            {icon} {insight.level}
          </span>
        </div>

        {/* Feed chips */}
        <div className="flex flex-wrap gap-1 mb-2">
          {insight.link?.feeds.map((f) => (
            <span key={f} className="feed-chip ok">
              {FEED_ICONS[f] ?? '●'} {f}
            </span>
          ))}
          {insight.text_source === 'llm' && (
            <span className="feed-chip" style={{ borderColor: '#818CF8', color: '#818CF8' }}>
              ✨ AI
            </span>
          )}
        </div>

        {/* Headline */}
        <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-2)' }}>
          {insight.headline}
        </p>

        {/* Signal badge */}
        {insight.link && (
          <p className="text-xs mt-1 font-medium" style={{ color }}>
            {insight.link.signal} · possible link ▾
          </p>
        )}
      </button>

      {/* Why panel */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-t mt-3 pt-3" style={{ borderColor: 'var(--color-muted)' }}>
              <WhyPanel insight={insight} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
