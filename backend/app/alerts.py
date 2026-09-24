"""
alerts.py — Discord/Telegram webhook dispatcher with cooldown deduplication.
P2 owns this file. P1 wires this into the SSE broadcaster. Spec from PRD §8.4.

Trigger conditions:
  - Zone level drops to "Alert"
  - Any "Strong signal" insight

Guardrails:
  - 10-minute cooldown per zone
  - Dedup key = f"{district}:{level}"
  - Always includes "possible link" wording (never causal)
"""
from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

from .db import get_db, recent_alerts, record_alert
from .models import Insight, PulseLevel

log = logging.getLogger(__name__)

COOLDOWN_S = 600   # 10 minutes


def _should_send(district: str, level: PulseLevel) -> bool:
    key = f"{district}:{level}"
    with get_db() as conn:
        rows = recent_alerts(conn, key, COOLDOWN_S)
        return len(rows) == 0


def _mark_sent(district: str, level: PulseLevel) -> None:
    key = f"{district}:{level}"
    with get_db() as conn:
        record_alert(conn, key, datetime.now(timezone.utc))


def _format_message(insight: Insight) -> str:
    lines = [
        f"🚨 CityPulse Alert — {insight.district} [{insight.level}]",
        "",
        insight.headline,
        "",
        insight.why_it_matters,
    ]
    if insight.link:
        lines.append(f"Signal: {insight.link.signal} (possible link, not a confirmed cause)")
    if insight.caveats:
        lines.append(f"Note: {insight.caveats[0]}")
    return "\n".join(lines)


async def dispatch(insight: Insight) -> None:
    """
    Send an alert for the given insight if it meets the trigger criteria
    and the cooldown has not elapsed.
    """
    should_trigger = (
        insight.level == "Alert"
        or (insight.link is not None and insight.link.signal == "Strong signal")
    )
    if not should_trigger:
        return

    if not _should_send(insight.district, insight.level):
        log.debug("Alert suppressed (cooldown) for %s", insight.district)
        return

    message = _format_message(insight)
    tasks = []

    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if discord_url:
        tasks.append(_send_discord(discord_url, message))

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        tasks.append(_send_telegram(tg_token, tg_chat, message))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                log.warning("Alert delivery failed: %s", r)
        _mark_sent(insight.district, insight.level)
        log.info("Alert sent for %s [%s]", insight.district, insight.level)
    else:
        log.debug("No alert webhooks configured — skipping delivery")


async def _send_discord(webhook_url: str, message: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json={"content": message})
        resp.raise_for_status()


async def _send_telegram(token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        })
        resp.raise_for_status()
