"""
llm.py — Optional LLM paraphrase layer using Gemini Flash.
P2 owns this file. This is a P1 (hours 15-18) feature.

Design: always fall back to templates if anything goes wrong.
Rate-limited to 1 call per district per minute, top 3 zones only.
Cache key = hash(district, level, rounded facts).
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
import time
from typing import Any, Optional

from .validate import validate_llm_output

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit state (in-memory, per district)
# ---------------------------------------------------------------------------

_last_call: dict[str, float] = {}   # district → last call epoch
_cache: dict[str, str] = {}         # cache_key → text

RATE_LIMIT_S = 60          # max 1 call per district per minute
MAX_ZONES_PER_TICK = 3     # only call LLM for top N stressed zones

# ---------------------------------------------------------------------------
# System prompt (PRD §8.2)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You rewrite structured civic data into ONE plain-English sentence (max 28 words) "
    "for a non-technical resident. Use ONLY the numbers and facts in the JSON. "
    "Never state or imply a confirmed cause; use 'may be linked to' or 'coincides with'. "
    "If caveats exist, mention the most important one briefly. Output the sentence only."
)


def _cache_key(district: str, level: str, facts: dict[str, Any]) -> str:
    # Round floats to 1dp before hashing so minor fluctuations don't bust the cache
    rounded = {k: round(v, 1) if isinstance(v, float) else v for k, v in facts.items()}
    payload = json.dumps({"district": district, "level": level, "facts": rounded}, sort_keys=True)
    return hashlib.md5(payload.encode()).hexdigest()


def paraphrase(
    district: str,
    level: str,
    facts: dict[str, Any],
    caveats: list[str],
    template_fallback: str,
) -> tuple[str, str]:
    """
    Try to get a one-sentence LLM paraphrase.
    Returns (text, source) where source is "llm" or "template".
    Always returns a valid sentence.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return template_fallback, "template"

    # Rate-limit check
    now = time.time()
    if now - _last_call.get(district, 0) < RATE_LIMIT_S:
        return template_fallback, "template"

    # Cache check
    key = _cache_key(district, level, facts)
    if key in _cache:
        return _cache[key], "llm"

    # Build prompt
    user_payload = json.dumps({
        "district": district,
        "level": level,
        "facts": facts,
        "caveats": caveats[:2],   # top 2 caveats max
    })

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=_SYSTEM_PROMPT,
        )
        response = model.generate_content(user_payload)
        text = response.text.strip()

        _last_call[district] = time.time()

        if validate_llm_output(text, facts):
            _cache[key] = text
            return text, "llm"
        else:
            log.warning("LLM output failed validation for %s — using template", district)
            return template_fallback, "template"

    except Exception as exc:
        log.warning("LLM call failed for %s: %s — using template", district, exc)
        return template_fallback, "template"
