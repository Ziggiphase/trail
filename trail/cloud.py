"""Sync with the hosted Supabase database as the signed-in user.

Calls the functions in supabase/schema.sql through Supabase's REST API.
Row Level Security on the server makes sure a user only ever touches their own rows.
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

from . import config
from .auth import AuthError, SupabaseAuth

PAGE = 1000          # Supabase returns at most 1000 rows per request


class CloudError(Exception):
    pass


class CloudClient:
    def __init__(self, auth: SupabaseAuth, device: str, url: str = config.SUPABASE_URL,
                 key: str = config.SUPABASE_KEY):
        self.auth, self.device = auth, device
        self.rest = url.rstrip("/") + "/rest/v1"
        self.key = key
        self.ready = True            # same interface as the old storage class

    def init_schema(self) -> None:  # tables are created once in the Supabase dashboard
        pass

    def _rpc(self, fn: str, body: dict, params: dict | None = None, retry: bool = True):
        try:
            token = self.auth.access_token()
            r = requests.post(f"{self.rest}/rpc/{fn}", json=body, params=params, timeout=30,
                              headers={"apikey": self.key, "Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json"})
        except AuthError as exc:
            raise CloudError(str(exc)) from exc
        except requests.RequestException as exc:
            raise CloudError("offline") from exc
        if r.status_code == 401 and retry:
            try:
                self.auth.force_refresh()
            except AuthError as exc:
                raise CloudError(str(exc)) from exc
            return self._rpc(fn, body, params, retry=False)
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", r.text)
            except ValueError:
                msg = r.text
            if "could not find the function" in msg.lower():
                msg = "The database isn't set up yet (run supabase/schema.sql in Supabase)."
            raise CloudError(msg[:300])
        return r.json() if r.content else None

    def push(self, batch: dict[tuple[date, str], int]) -> None:
        rows = [{"device": self.device, "day": d.isoformat(), "app": app, "seconds": int(secs)}
                for (d, app), secs in batch.items() if int(secs) > 0]
        for i in range(0, len(rows), 500):
            self._rpc("add_activity", {"rows": rows[i:i + 500]})

    def daily_app_totals(self, days: int = 400) -> dict[tuple[date, str], int]:
        since = (date.today() - timedelta(days=days)).isoformat()
        out: dict[tuple[date, str], int] = {}
        offset = 0
        while True:
            page = self._rpc("daily_totals", {"since": since},
                             params={"limit": PAGE, "offset": offset}) or []
            for row in page:
                out[(date.fromisoformat(row["day"]), row["app"])] = int(row["seconds"])
            if len(page) < PAGE:
                return out
            offset += PAGE

    def delete_my_data(self) -> None:
        self._rpc("delete_my_data", {})
