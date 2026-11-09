"""Rate limits for the assistant: per visitor, and a daily ceiling for everyone together.

Counts are kept in memory, per API process. Behind several processes, each one counts on
its own, so put the same limit in the reverse proxy too. A visitor is their IP address, as
uvicorn reports it (run it with --proxy-headers behind nginx so it is the real one).
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

DAY = 86_400
MINUTE = 60
MAX_VISITORS = 50_000
"""Beyond this many visitors in memory, the ones idle longest are forgotten first."""


@dataclass(frozen=True)
class Refusal:
    reason: str
    """"visitor" (this visitor asked too much) or "budget" (the day's ceiling is reached)."""
    retry_after: int


class Limiter:
    def __init__(
        self,
        per_minute: int,
        per_day: int,
        daily_budget: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self.daily_budget = daily_budget
        self.clock = clock
        self._lock = threading.Lock()
        self._asked: dict[str, deque[float]] = {}
        self._day = -1
        self._spent = 0

    def take(self, visitor: str) -> Refusal | None:
        """Count one question from `visitor`, or say why not and for how long."""
        now = self.clock()
        with self._lock:
            day = int(now // DAY)
            if day != self._day:
                self._day, self._spent = day, 0
            asked = self._asked.setdefault(visitor, deque())
            while asked and asked[0] <= now - DAY:
                asked.popleft()
            if len(asked) >= self.per_day:
                return Refusal("visitor", math.ceil(asked[0] + DAY - now))
            last_minute = [t for t in asked if t > now - MINUTE]
            if len(last_minute) >= self.per_minute:
                return Refusal("visitor", math.ceil(last_minute[0] + MINUTE - now))
            if self._spent >= self.daily_budget:
                return Refusal("budget", math.ceil((day + 1) * DAY - now))
            asked.append(now)
            self._spent += 1
            if len(self._asked) > MAX_VISITORS:
                self._forget(now)
            return None

    def _forget(self, now: float) -> None:
        for visitor in [
            v for v, asked in self._asked.items() if not asked or asked[-1] <= now - DAY
        ]:
            del self._asked[visitor]
        while len(self._asked) > MAX_VISITORS:
            idle = min(self._asked, key=lambda v: self._asked[v][-1] if self._asked[v] else 0.0)
            del self._asked[idle]
