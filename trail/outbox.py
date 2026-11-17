"""Crash-safe buffer for time that hasn't reached the cloud yet.

Trail keeps unsynced seconds in memory and uploads them every few minutes.
If the PC loses power or crashes in between, that time would be lost, so the
pending amounts are also written here every minute and removed once uploaded.
It only ever holds a few minutes of totals (or more while you're offline).
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

Key = tuple[date, str]


class Outbox:
    def __init__(self, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "unsynced.json"

    def save(self, pending: dict[Key, float]) -> None:
        rows = [[d.isoformat(), app, round(secs, 1)] for (d, app), secs in pending.items() if secs > 0]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows))
        os.replace(tmp, self.path)          # atomic: never a half-written file

    def load(self) -> dict[Key, float]:
        try:
            rows = json.loads(self.path.read_text())
            return {(date.fromisoformat(d), app): float(s) for d, app, s in rows}
        except (OSError, ValueError, TypeError):
            return {}
