"""Rate limiting.

In-process fixed-window counters. Honest about scope: this protects a
single-host deployment, which is the architecture chosen in ADR-002 (the API
is host-pinned by the per-workspace SQLite volume anyway). It does NOT
coordinate across hosts. If the API is ever scaled horizontally, this must
move to a shared store, and the deployment doc must say so before that
happens.

Deliberately not Redis today: adding a network dependency to protect a
single-host process would be infrastructure for its own sake (mission
section 36 — every production dependency must have a reason).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Window:
    count: int = 0
    reset_at: float = 0.0


@dataclass
class RateLimiter:
    """Fixed-window limiter: `max_attempts` per `window_seconds` per key."""

    max_attempts: int
    window_seconds: int
    _windows: dict[str, _Window] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_sweep: float = 0.0

    def check(self, key: str) -> tuple[bool, int]:
        """Record an attempt against `key`.

        Returns (allowed, retry_after_seconds). retry_after is 0 when allowed.
        """
        now = time.time()
        with self._lock:
            self._sweep(now)
            window = self._windows.get(key)
            if window is None or window.reset_at <= now:
                self._windows[key] = _Window(count=1, reset_at=now + self.window_seconds)
                return True, 0

            if window.count >= self.max_attempts:
                return False, max(1, int(window.reset_at - now))

            window.count += 1
            return True, 0

    def reset(self, key: str) -> None:
        """Clear a key's window — called after a SUCCESSFUL login.

        Without this, a user who mistypes their password four times and then
        succeeds stays near the limit for the rest of the window, and a normal
        person gets locked out for being human.
        """
        with self._lock:
            self._windows.pop(key, None)

    def reset_all(self) -> None:
        """Test hook."""
        with self._lock:
            self._windows.clear()

    def _sweep(self, now: float) -> None:
        """Drop expired windows so the dict cannot grow without bound.

        Caller must hold the lock. Amortised: at most once every 60s, since an
        unbounded dict keyed by attacker-controlled IPs is itself a memory
        exhaustion vector.
        """
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        expired = [key for key, win in self._windows.items() if win.reset_at <= now]
        for key in expired:
            del self._windows[key]


def client_key(ip: str | None, identifier: str | None = None) -> str:
    """Build a limiter key.

    Both dimensions matter: per-IP alone lets a botnet spray one account,
    per-identifier alone lets one IP enumerate many accounts.
    """
    return f"{ip or 'unknown'}|{(identifier or '').lower()}"
