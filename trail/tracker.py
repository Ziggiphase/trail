"""The tracking core. Pure logic: no UI and no database, so it is easy to test.

Every SAMPLE_SECONDS the app calls `tick()`. If the foreground app is one of
the tracked apps (and its window-title rule matches, if it has one) and the
user is not idle, the elapsed time is added to an in-memory `pending` bucket
keyed by (day, app). The sync layer drains that bucket to the cloud and puts
it back if the upload fails.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import date
from typing import Callable

from . import config
from .settings import TrackedApp

Key = tuple[date, str]


class Tracker:
    def __init__(
        self,
        rules: dict[str, TrackedApp],
        get_window: Callable[[], tuple[str | None, str]] | None = None,
        get_idle: Callable[[], float] | None = None,
        idle_after: float = config.IDLE_AFTER_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ):
        if get_window is None or get_idle is None:
            from . import activity
            get_window = get_window or activity.active_window
            get_idle = get_idle or activity.idle_seconds
        self.rules = rules
        self.idle_after = idle_after
        self._get_window, self._get_idle = get_window, get_idle
        self._clock, self._today = clock, today
        self._last = clock()
        self._lock = threading.Lock()
        self.pending: dict[Key, float] = defaultdict(float)
        self.recent: dict[str, float] = {}     # app -> last seen (for the picker)
        self.paused = False
        self.current_app: str | None = None
        self.is_productive = False

    def set_rules(self, rules: dict[str, TrackedApp], idle_after: float) -> None:
        self.rules, self.idle_after = rules, idle_after

    def tick(self) -> None:
        now = self._clock()
        # Cap the gap so sleep/hibernate is never counted as work.
        elapsed = min(now - self._last, config.SAMPLE_SECONDS * 2)
        self._last = now

        app, title = self._get_window()
        self.current_app = app
        if app:
            self.recent[app] = now
        rule = self.rules.get(app) if app else None
        idle = self._get_idle() >= self.idle_after
        self.is_productive = bool(
            rule and rule.matches(title) and not idle and not self.paused)
        if self.is_productive and elapsed > 0:
            with self._lock:
                self.pending[(self._today(), app)] += elapsed

    def recent_apps(self) -> list[str]:
        return sorted(self.recent, key=self.recent.get, reverse=True)

    def drain(self) -> dict[Key, int]:
        """Take everything pending (whole seconds) for upload."""
        with self._lock:
            out = {k: int(v) for k, v in self.pending.items() if int(v) > 0}
            for k, secs in out.items():
                self.pending[k] -= secs          # keep the fractional remainder
                if self.pending[k] <= 0:
                    del self.pending[k]
        return out

    def restore(self, batch: dict[Key, float]) -> None:
        """Upload failed: put the batch back so nothing is lost."""
        with self._lock:
            for k, secs in batch.items():
                self.pending[k] += secs

    def snapshot(self) -> dict[Key, float]:
        """Copy of time not yet uploaded (for the UI and the crash-safe outbox)."""
        with self._lock:
            return dict(self.pending)
