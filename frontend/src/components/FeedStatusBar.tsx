import { useStore } from '../store'
import type { FeedHealth, FeedStatus } from '../types'

const FEED_ICONS: Record<string, string> = {
  weather:   '🌧',
  air:       '🌫',
  incidents: '📣',
  transit:   '🚌',
}

const STATUS_LABEL: Record<FeedStatus, string> = {
  ok:      'Live',
  delayed: 'Delayed',
  down:    'Down',
}

function statusColor(status: FeedStatus): string {
  return { ok: '#2DD4BF', delayed: '#FBBF24', down: '#E11D48' }[status] ?? '#475569'
}

function FeedRow({ feed }: { feed: FeedHealth }) {
  const color = statusColor(feed.status)
  const ago = feed.last_ok_ts ? formatAgo(feed.last_ok_ts) : null

  return (
    <div className="flex items-center gap-2 py-1.5">
      {/* Status dot */}
      <span
        className="w-2 h-2 rounded-full shrink-0"
        style={{ background: color }}
        aria-hidden
      />

      {/* Icon + name */}
      <span className="text-sm flex-1">
        {FEED_ICONS[feed.source] ?? '●'}{' '}
        <span className="font-medium capitalize">{feed.source}</span>
        {feed.is_simulated && (
          <span
            className="ml-1 text-xs font-semibold"
            style={{ color: 'var(--color-sim)' }}
            title="Simulated feed"
          >
            SIM
          </span>
        )}
      </span>

      {/* Status + latency */}
      <div className="text-right">
        <span
          className="text-xs font-semibold"
          style={{ color }}
          aria-label={`${feed.source} status: ${STATUS_LABEL[feed.status]}`}
        >
          {STATUS_LABEL[feed.status]}
        </span>
        {feed.latency_ms != null && feed.status === 'ok' && (
          <span className="text-xs ml-1" style={{ color: 'var(--color-muted)' }}>
            {Math.round(feed.latency_ms)}ms
          </span>
        )}
        {ago && feed.status !== 'ok' && (
          <span className="block text-xs" style={{ color: 'var(--color-muted)' }}>
            last ok {ago}
          </span>
        )}
      </div>
    </div>
  )
}

export function FeedStatusBar() {
  const feeds = useStore((s) => s.feedHealth)

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-1"
      style={{ background: 'var(--color-surface)' }}
      aria-label="Feed health"
    >
      <p
        className="text-xs font-semibold uppercase tracking-widest mb-2"
        style={{ color: 'var(--color-text-2)' }}
      >
        Feed Status
      </p>

      {feeds.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--color-muted)' }}>
          Waiting for feed data…
        </p>
      ) : (
        <div className="divide-y" style={{ borderColor: 'var(--color-muted)' }}>
          {feeds.map((f) => (
            <FeedRow key={f.source} feed={f} />
          ))}
        </div>
      )}
    </div>
  )
}

// ---- helpers ----

function formatAgo(isoTs: string): string {
  const diffMs = Date.now() - new Date(isoTs).getTime()
  const diffMin = Math.floor(diffMs / 60_000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH}h ago`
  return `${Math.floor(diffH / 24)}d ago`
}
