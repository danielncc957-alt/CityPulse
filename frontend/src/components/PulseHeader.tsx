import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useStore, levelColor, levelIcon } from '../store'
import type { PulseLevel } from '../types'

// Beat interval in ms per level
const BEAT_MS: Record<PulseLevel, number> = {
  Calm:     1000,
  Watch:    750,
  Strained: 580,
  Alert:    420,
}

// ECG path irregularity per level (SVG path segments)
function ecgPath(level: PulseLevel, width = 300, height = 40): string {
  const mid = height / 2
  const irregularity = { Calm: 0, Watch: 2, Strained: 5, Alert: 9 }[level]

  const segments: string[] = [`M 0 ${mid}`]
  const step = 30
  const beats = Math.ceil(width / step)

  for (let i = 0; i < beats; i++) {
    const x = i * step
    const jitter = (Math.random() - 0.5) * irregularity
    if (i % 3 === 1) {
      // QRS complex
      segments.push(
        `L ${x + 5} ${mid + jitter}`,
        `L ${x + 8} ${mid - 14 - irregularity * 1.5}`,
        `L ${x + 11} ${mid + 6 + irregularity}`,
        `L ${x + 14} ${mid + jitter}`,
      )
    } else {
      segments.push(`L ${x + step} ${mid + jitter}`)
    }
  }
  return segments.join(' ')
}

export function PulseHeader() {
  const city = useStore((s) => s.city)
  const connected = useStore((s) => s.connected)
  const insights = useStore((s) => s.insights)

  const level: PulseLevel = city?.level ?? 'Calm'
  const pulse = city?.pulse ?? 75
  const color = levelColor(level)
  const icon = levelIcon(level)
  const beatMs = BEAT_MS[level]

  const topInsight = insights[0]
  const headline = topInsight?.headline ?? 'Monitoring all feeds…'

  const pathRef = useRef<SVGPathElement>(null)
  useEffect(() => {
    if (!pathRef.current) return
    pathRef.current.setAttribute('d', ecgPath(level))
  }, [level])

  return (
    <header
      className="relative flex flex-col gap-1 px-5 py-4"
      style={{ background: 'var(--color-surface)', borderBottom: `2px solid ${color}` }}
    >
      <div className="flex items-center gap-4 flex-wrap">
        {/* Pulse ring */}
        <div className="relative flex items-center justify-center w-10 h-10 shrink-0">
          <div
            className="absolute inset-0 rounded-full pulse-ring"
            style={{
              background: color,
              opacity: 0.25,
              '--beat-interval': `${beatMs}ms`,
            } as React.CSSProperties}
          />
          <span className="text-xl" aria-hidden>♥</span>
        </div>

        {/* Wordmark */}
        <span className="text-lg font-bold tracking-wide" style={{ color }}>CITY PULSE</span>

        {/* ECG line */}
        <svg
          width="200" height="40"
          className="hidden sm:block opacity-70"
          aria-hidden
        >
          <path
            ref={pathRef}
            d={ecgPath(level)}
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>

        {/* Status badge */}
        <div className="flex items-center gap-2 ml-auto">
          <motion.span
            key={level}
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="text-sm font-semibold px-3 py-1 rounded-full"
            style={{ background: color, color: '#0F172A' }}
            aria-label={`Status: ${level}`}
          >
            {icon} {level.toUpperCase()}
          </motion.span>
          <span
            className="font-mono text-2xl font-bold"
            style={{ color }}
            aria-label={`Pulse score: ${pulse}`}
          >
            {pulse}
          </span>
        </div>

        {/* Connection indicator */}
        <div
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: connected ? '#2DD4BF' : '#475569' }}
          title={connected ? 'Live' : 'Reconnecting…'}
          aria-label={connected ? 'Connected' : 'Disconnected'}
        />
      </div>

      {/* Headline */}
      <p className="text-sm mt-1" style={{ color: 'var(--color-text-2)' }}>
        {headline}
      </p>
    </header>
  )
}
