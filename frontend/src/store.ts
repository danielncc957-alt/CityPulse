import { create } from 'zustand'
import type {
  CityPulse, DistrictPulse, FeedHealth, Insight,
  SseAlertPayload, PulseLevel, DistrictWeather,
} from './types'

interface CityPulseStore {
  // Core state
  city: CityPulse | null
  feedHealth: FeedHealth[]
  insights: Insight[]
  alerts: SseAlertPayload[]
  weather: DistrictWeather[]
  connected: boolean
  lastUpdate: string | null

  // Actions
  setCity: (city: CityPulse) => void
  updateDistricts: (districts: DistrictPulse[]) => void
  setFeedHealth: (feeds: FeedHealth[]) => void
  addInsight: (insight: Insight) => void
  setInsights: (insights: Insight[]) => void
  addAlert: (alert: SseAlertPayload) => void
  dismissAlert: (idx: number) => void
  setWeather: (weather: DistrictWeather[]) => void
  setConnected: (v: boolean) => void
  setLastUpdate: (ts: string) => void
}

export const useStore = create<CityPulseStore>((set) => ({
  city: null,
  feedHealth: [],
  insights: [],
  alerts: [],
  weather: [],
  connected: false,
  lastUpdate: null,

  setCity: (city) => set({ city }),

  updateDistricts: (districts) =>
    set((s) => ({
      city: s.city
        ? { ...s.city, districts }
        : null,
    })),

  setFeedHealth: (feeds) => set({ feedHealth: feeds }),

  addInsight: (insight) =>
    set((s) => ({
      insights: [insight, ...s.insights.filter((i) => i.id !== insight.id)].slice(0, 50),
    })),

  setInsights: (insights) => set({ insights }),

  addAlert: (alert) =>
    set((s) => ({ alerts: [alert, ...s.alerts].slice(0, 5) })),

  dismissAlert: (idx) =>
    set((s) => ({ alerts: s.alerts.filter((_, i) => i !== idx) })),

  setWeather: (weather) => set({ weather }),

  setConnected: (connected) => set({ connected }),

  setLastUpdate: (lastUpdate) => set({ lastUpdate }),
}))

// Derived helpers
export const levelColor = (level: PulseLevel): string => ({
  Calm:     '#2DD4BF',
  Watch:    '#FBBF24',
  Strained: '#F97316',
  Alert:    '#E11D48',
}[level] ?? '#2DD4BF')

export const levelIcon = (level: PulseLevel): string => ({
  Calm:     '✓',
  Watch:    '⚠',
  Strained: '⚡',
  Alert:    '🚨',
}[level] ?? '✓')
