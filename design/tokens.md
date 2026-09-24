# CityPulse — Design Tokens

## Colours (colour-blind safe; always pair with status word + icon)

| Level | Name | Hex | Usage |
|---|---|---|---|
| Calm | Teal | `#2DD4BF` | Hex fill, header glow, status badge |
| Watch | Yellow | `#FBBF24` | Hex fill, header glow, status badge |
| Strained | Orange | `#F97316` | Hex fill, header glow, status badge |
| Alert | Magenta-red | `#E11D48` | Hex fill, header glow, status badge, alert toast |
| Background | Dark slate | `#0F172A` | Page background |
| Surface | Slate | `#1E293B` | Cards, panels, drawer |
| Muted | Mid-slate | `#475569` | Borders, dividers, ghost text |
| Text primary | Off-white | `#F1F5F9` | Body text, headings |
| Text secondary | Slate-300 | `#CBD5E1` | Subtitles, captions |
| SIM badge | Amber | `#D97706` | "SIM" chip on simulated feeds |

## Typography

| Role | Font | Size / Weight |
|---|---|---|
| Status word | Inter | 2.5rem / 800 |
| Headline sentence | Inter | 1.1rem / 400 |
| District name | Inter | 1rem / 600 |
| Numbers / stats | JetBrains Mono | 1rem / 500 |
| Captions / meta | Inter | 0.8rem / 400 |

## Spacing scale (8-point grid)

`4 8 12 16 24 32 48 64` px

## Pulse level icons (always shown alongside colour)

| Level | Icon | Aria label |
|---|---|---|
| Calm | 🟢 or ✓ | "Calm" |
| Watch | 🟡 or ⚠ | "Watch" |
| Strained | 🟠 or ⚡ | "Strained" |
| Alert | 🔴 or 🚨 | "Alert" |

## Copy rules

- Sentences ≤ 25 words
- No jargon: "anomaly" → "unusual activity", "z-score" → never shown outside Why panel
- **Never use:** "caused by", "because of", "due to", "is responsible for", "resulted from"
- **Use instead:** "may be linked to", "coincides with", "possible link"
- Simulated feeds always show a "SIM" badge
- Empty state: "All quiet. Here's what we're watching." (not "No data")
- "Why we think this" → short, plain, honest: show the evidence, say "possible link, not a confirmed cause"

## Animations

- Heartbeat ECG: calm = 60 bpm steady; watch = 80 bpm; strained = 100 bpm slight irregularity; alert = 130 bpm jagged
- Hex breathe: opacity 0.6–1.0 at rate proportional to stress
- Card entrance: `framer-motion` slide-up, 200 ms
- Respect `prefers-reduced-motion`: disable all animations, use static colour only
- Target ≤ 60 fps

## Basemap

CARTO Dark Matter: `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`
Attribution: © CARTO · © OpenStreetMap contributors
