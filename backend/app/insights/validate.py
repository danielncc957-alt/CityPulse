"""
validate.py — Number-grounding + banned-phrase validator for LLM output.
P2 owns this file. Spec from PRD §8.2 and §18.3.

Every number in LLM text must appear in facts. No banned causal phrases.
"""
from __future__ import annotations
import re
from typing import Any

# ---------------------------------------------------------------------------
# Banned causal phrases (PRD §7.5 — enforced in code, not just in copy)
# ---------------------------------------------------------------------------

_BANNED_PATTERN = re.compile(
    r"\b(caused\s+by|because\s+of|due\s+to|is\s+responsible\s+for|resulted\s+from)\b",
    re.IGNORECASE,
)

# Max word count for LLM output (PRD: ≤30 words)
MAX_WORDS = 30

# Numbers that are always acceptable (cardinal counts too small to be fabricated)
_ALWAYS_OK = {"1", "2", "3", "0"}


def _allowed_numbers(facts: dict[str, Any]) -> set[str]:
    """
    Build the set of allowed numeric string representations from facts.
    Rounds to 1 decimal, strips trailing zeros.
    """
    allowed: set[str] = set(_ALWAYS_OK)
    for v in facts.values():
        if isinstance(v, (int, float)):
            # add both raw and rounded forms
            allowed.add(str(int(v)) if float(v) == int(v) else str(v))
            rounded = str(round(v, 1))
            allowed.add(rounded.rstrip("0").rstrip("."))
    return allowed


def validate_llm_output(text: str, facts: dict[str, Any]) -> bool:
    """
    Return True iff the LLM text passes all checks:
      1. No banned causal phrases.
      2. Word count ≤ MAX_WORDS.
      3. Every number in the text appears in facts (or is in _ALWAYS_OK).

    Fail → caller should use the template instead.
    """
    if not text or not text.strip():
        return False

    # Check 1: no banned phrases
    if _BANNED_PATTERN.search(text):
        return False

    # Check 2: word count
    if len(text.split()) > MAX_WORDS:
        return False

    # Check 3: every number is grounded
    allowed = _allowed_numbers(facts)
    nums_in_text = re.findall(r"\d+(?:\.\d+)?", text)
    for n in nums_in_text:
        if n not in allowed:
            return False

    return True


def contains_banned_phrase(text: str) -> bool:
    """Quick check for banned causal phrases — used on template output too."""
    return bool(_BANNED_PATTERN.search(text))
