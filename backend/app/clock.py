"""
clock.py — Virtual clock shared by live, replay and scenario modes.
P1 owns this. P2's analyzer calls clock.now() on every tick.
Never use datetime.now() anywhere else in the codebase — always clock.now().
"""
from __future__ import annotations
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...


class LiveClock(Clock):
    """Returns the real wall-clock time in UTC."""
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class VirtualClock(Clock):
    """
    A clock that can be pinned to a start time and run at an arbitrary speed.
    Used for both Replay mode (start = historical date, speed = warp factor)
    and Scenario mode (start = now, speed = 1|10|60).
    """

    def __init__(self, start: datetime, speed: float = 1.0):
        if start.tzinfo is None:
            raise ValueError("VirtualClock start must be timezone-aware (UTC).")
        self._start = start
        self._speed = speed
        self._anchor = time.monotonic()   # real-time reference point

    def now(self) -> datetime:
        elapsed_real = time.monotonic() - self._anchor
        elapsed_virtual = elapsed_real * self._speed
        return self._start + timedelta(seconds=elapsed_virtual)

    def set_speed(self, new_speed: float) -> None:
        """Re-anchor so the virtual time is continuous across speed changes."""
        current = self.now()
        self._start = current
        self._anchor = time.monotonic()
        self._speed = new_speed

    def seek(self, new_start: datetime) -> None:
        """Jump the clock to a new point (for replay scrubber)."""
        self._start = new_start
        self._anchor = time.monotonic()

    @property
    def speed(self) -> float:
        return self._speed


# ---------------------------------------------------------------------------
# Module-level singleton — replaced by the app on startup
# ---------------------------------------------------------------------------

_clock: Clock = LiveClock()


def get_clock() -> Clock:
    return _clock


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock


def now() -> datetime:
    """Convenience wrapper — call clock.now() via this everywhere."""
    return _clock.now()
