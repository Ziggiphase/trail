"""Trail cloud storage on any Postgres (Neon recommended; Supabase also works).

One row per (device, day, app). Uploads are additive upserts, so a retried
batch after a failure is merged in, and several computers can share one DB.
"""
from __future__ import annotations

from datetime import date, timedelta

import psycopg

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_activity (
    device      TEXT        NOT NULL,
    day         DATE        NOT NULL,
    app         TEXT        NOT NULL,
    seconds     INTEGER     NOT NULL DEFAULT 0 CHECK (seconds >= 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (device, day, app)
);
CREATE INDEX IF NOT EXISTS daily_activity_day_idx ON daily_activity (day);
"""

UPSERT = """
INSERT INTO daily_activity (device, day, app, seconds)
VALUES (%s, %s, %s, %s)
ON CONFLICT (device, day, app)
DO UPDATE SET seconds    = daily_activity.seconds + EXCLUDED.seconds,
              updated_at = now();
"""


class CloudStore:
    def __init__(self, url: str = config.DATABASE_URL, device: str = config.DEVICE_NAME):
        if not url:
            raise RuntimeError("DATABASE_URL is not set (see .env.example)")
        self.url, self.device = url, device
        self.ready = False

    def _connect(self) -> psycopg.Connection:
        # Short-lived connections: the app syncs every few minutes, and this
        # lets serverless Postgres (Neon) scale to zero between syncs.
        return psycopg.connect(self.url, connect_timeout=10, autocommit=False)

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(SCHEMA)
        self.ready = True

    def push(self, batch: dict[tuple[date, str], int]) -> None:
        if not batch:
            return
        rows = [(self.device, day, app, secs) for (day, app), secs in batch.items()]
        with self._connect() as conn, conn.cursor() as cur:
            cur.executemany(UPSERT, rows)   # one transaction: all or nothing

    def daily_app_totals(self, days: int = 400) -> dict[tuple[date, str], int]:
        """Seconds per (day, app), summed across all your devices."""
        since = date.today() - timedelta(days=days)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT day, app, SUM(seconds)::int FROM daily_activity "
                "WHERE day >= %s GROUP BY day, app",
                (since,),
            ).fetchall()
        return {(day, app): secs for day, app, secs in rows}

    def devices(self) -> list[str]:
        with self._connect() as conn:
            return [r[0] for r in conn.execute(
                "SELECT DISTINCT device FROM daily_activity ORDER BY 1").fetchall()]
