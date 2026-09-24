# CityPulse — 3-Minute Demo Script

## Setup (before presenting)

1. Open app at `http://localhost:5173` (or deployed URL as backup)
2. Make sure the app is in **Calm / Quiet** state — run `POST /api/demo/scenario {"name":"quiet","speed":1}`
3. Have `?demo=1` URL ready but NOT open yet
4. Phone on the table for the Discord/Telegram alert demo

---

## Script

### 0:00 — Hook
**Say:** "Right now, your neighbourhood's data exists — weather, air quality, transit, complaints — but it lives in six different apps. Residents find out about problems *after* they're already in them."

**Screen:** Static image of siloed data sources (use a slide)

---

### 0:20 — The 10-second glance
**Say:** "Here's CityPulse. I'm going to ask you — can you tell me how the city is doing in the next 10 seconds?"

**Screen:** Open the app in **Calm** state. Heartbeat is slow and steady. Status says "Calm · 84".

*Wait 10 seconds. They'll answer correctly. That's the point.*

---

### 0:40 — Storm scenario (60× time-warp)
**Say:** "Let's watch a storm roll in — at 60× speed."

**Action:** Open `?demo=1`. Click **Storm**. Set speed to **60×**.

**Screen:** Heartbeat quickens. Riverside hexes pulse orange then red. Incident count rises. Transit chips show delays.

**Say (while it runs):** "Rain intensifies. Complaints cluster near Riverside. Transit starts slowing. The city's pulse drops to Strained."

---

### 1:20 — Open the insight card
**Say:** "What makes this useful is *why*. Let's look."

**Action:** Click the Riverside insight card. Open "Why we think this".

**Screen:** Evidence panel shows — feeds involved, lag, correlation, event count. Bottom line: **"Possible link, not a confirmed cause."**

**Say:** "We show the evidence. We show the method. And we're honest: this is a *possible* link, not a confirmed cause. That's enforced in the code — there's a validator that rejects any sentence with causal language."

---

### 1:50 — Real-data proof
**Say:** "But let me show you this works on *real* data, not just a simulation."

**Action:** Click **Replay** → NYC 29 Sep 2023 (flash flood day).

**Screen:** Timeline rewinds. Real weather data from Open-Meteo. Real NYC 311 complaints from that day. Watch the anomaly flag fire *before* the complaint peak.

**Say:** "This is real weather data and real NYC 311 records from a flash-flood event. The detection fires before the peak. That's the honest proof."

---

### 2:20 — Resilience: kill a feed
**Say:** "What if a feed goes down mid-demo?"

**Action:** In demo panel, click **Kill transit feed**.

**Screen:** Transit chip turns amber. Summary says "reduced confidence". The rest of the app keeps working.

**Say:** "The system doesn't crash. It tells you what's missing, reweights the remaining feeds, and keeps going. Graceful degradation by design."

---

### 2:40 — Trust and impact
**Say:** "Two more things judges care about: privacy and trust."

**Screen:** Zoom in on the map — individual dots only appear where ≥3 reports in a zone. No names, no free text.

**Say:** "We aggregate to hex zones. We never show individual reports. And —"

**Action:** Trigger an alert from the demo panel.

**Screen:** Discord/Telegram message arrives on phone.

**Say:** "— when the city hits Alert, residents and staff can get a notification. With the same honest language: possible link, not confirmed cause."

---

### 2:55 — Close
**Say:** "One glance. One sentence. Honest about what we don't know."

**Screen:** Pulse header — slow heartbeat returning to Calm.

---

## Likely judge questions — prep answers

| Question | Answer |
|---|---|
| Is this real data? | Weather and air quality are live from Open-Meteo. Replay uses real NYC 311 data. Live incidents and transit are labelled SIM because free citywide feeds don't exist — the replay proves the method works on real data. |
| Isn't the correlation circular in scenario mode? | Yes, and we say so. That's exactly why the replay exists. |
| How do you avoid false causation? | Whitelisted pairs, minimum evidence (n≥24 bins), tiered wording, banned causal phrases enforced by a regex validator in code, plus an evidence panel on every card. |
| What if the LLM hallucinates? | It only sees a facts JSON. A validator checks every number in the output against the facts. On failure, it falls back to the deterministic template. |
| How would this scale? | The adapter pattern means each real feed is one file. H3 zones scale horizontally. SQLite → Postgres/TimescaleDB, SSE → a message broker. |
