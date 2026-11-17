"""Sign-in with Supabase Auth: Google, or an email link / 6-digit code.

Desktop flow (PKCE): Trail opens the browser; after sign-in Supabase sends the
browser back to a tiny web server Trail runs on 127.0.0.1, with a one-time
code that Trail swaps for a session. The refresh token is kept on disk,
encrypted with Windows DPAPI so only this Windows user can read it.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from . import config


class AuthError(Exception):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status       # HTTP status, or None for network problems


@dataclass
class Session:
    access_token: str
    refresh_token: str
    expires_at: float
    user_id: str
    email: str


# ---------------------------------------------------------------- token storage
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _dpapi(data: bytes, protect: bool) -> bytes:
        src = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                           ctypes.POINTER(ctypes.c_char)))
        out = _Blob()
        fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
        if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
            raise OSError("Windows could not encrypt/decrypt the sign-in token")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)

    def _seal(b: bytes) -> bytes:
        return _dpapi(b, True)

    def _open(b: bytes) -> bytes:
        return _dpapi(b, False)
else:
    def _seal(b: bytes) -> bytes:
        return b

    def _open(b: bytes) -> bytes:
        return b


class TokenStore:
    def __init__(self, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "session.bin"

    def save(self, s: Session | None) -> None:
        if s is None:
            self.path.unlink(missing_ok=True)
            return
        self.path.write_bytes(_seal(json.dumps(asdict(s)).encode()))
        if sys.platform != "win32":
            self.path.chmod(0o600)

    def load(self) -> Session | None:
        try:
            return Session(**json.loads(_open(self.path.read_bytes())))
        except (OSError, ValueError, TypeError):
            return None


# ---------------------------------------------------------------- browser callback
_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Trail</title>
<style>body{{margin:0;height:100vh;display:grid;place-items:center;background:#0f1318;
color:#e7ebf1;font-family:Segoe UI,Inter,Arial,sans-serif}}div{{text-align:center}}
h1{{font-size:22px;margin:0 0 8px}}p{{color:#8e99aa}}</style></head>
<body><div><h1>{title}</h1><p>{text}</p></div></body></html>"""


class CallbackServer:
    """One-shot local web server that receives ?code=… from Supabase."""

    def __init__(self, on_result: Callable[[str | None, str | None], None]):
        self.on_result = on_result
        self.httpd: HTTPServer | None = None

    def start(self) -> None:
        if self.httpd:
            return
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                url = urlparse(self.path)
                if url.path != "/callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                q = parse_qs(url.query)
                code = q.get("code", [None])[0]
                err = q.get("error_description", q.get("error", [None]))[0]
                ok = bool(code) and not err
                body = _PAGE.format(
                    title="You're signed in" if ok else "Sign-in didn't work",
                    text="You can close this tab and go back to Trail." if ok
                    else (err or "Please go back to Trail and try again."))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode())
                outer.on_result(code if ok else None, None if ok else (err or "No code received"))

            def log_message(self, *_a):
                pass

        try:
            self.httpd = HTTPServer(("127.0.0.1", config.AUTH_PORT), Handler)
        except OSError as exc:
            raise AuthError(f"Port {config.AUTH_PORT} is busy; close other apps using it and try again") from exc
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


# ---------------------------------------------------------------- Supabase Auth client
class SupabaseAuth:
    def __init__(self, store: TokenStore, url: str = config.SUPABASE_URL,
                 key: str = config.SUPABASE_KEY):
        self.base = url.rstrip("/") + "/auth/v1"
        self.key = key
        self.store = store
        self.session: Session | None = store.load()
        self._verifier: str | None = None
        self._lock = threading.Lock()

    # -- helpers
    def _headers(self, token: str | None = None) -> dict:
        h = {"apikey": self.key, "Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def _post(self, path: str, body: dict, params: dict | None = None) -> dict:
        try:
            r = requests.post(self.base + path, params=params, json=body, headers=self._headers(), timeout=20)
        except requests.RequestException as exc:
            raise AuthError("Can't reach the sign-in server. Check your internet connection.") from exc
        if r.status_code >= 400:
            try:
                d = r.json()
                msg = d.get("msg") or d.get("error_description") or d.get("message") or d.get("error")
            except ValueError:
                msg = r.text[:200]
            raise AuthError(_friendly(msg or f"HTTP {r.status_code}"), r.status_code)
        return r.json() if r.content else {}

    def _new_pkce(self) -> str:
        self._verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(self._verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def _set_session(self, d: dict) -> Session:
        user = d.get("user") or {}
        s = Session(access_token=d["access_token"], refresh_token=d["refresh_token"],
                    expires_at=time.time() + int(d.get("expires_in", 3600)),
                    user_id=user.get("id", ""), email=user.get("email", ""))
        self.session = s
        self.store.save(s)
        return s

    # -- sign-in flows
    @property
    def signed_in(self) -> bool:
        return self.session is not None

    def oauth_url(self, provider: str = "google") -> str:
        challenge = self._new_pkce()
        q = urlencode({"provider": provider, "redirect_to": config.AUTH_REDIRECT,
                       "code_challenge": challenge, "code_challenge_method": "s256"})
        return f"{self.base}/authorize?{q}"

    def send_email(self, email: str) -> None:
        """Emails a sign-in link (and a 6-digit code, if the email template shows one)."""
        challenge = self._new_pkce()
        self._post("/otp", {"email": email, "create_user": True,
                            "code_challenge": challenge, "code_challenge_method": "s256"},
                   params={"redirect_to": config.AUTH_REDIRECT})

    def verify_code(self, email: str, code: str) -> Session:
        return self._set_session(self._post("/verify", {"type": "email", "email": email,
                                                        "token": code.strip()}))

    def exchange(self, auth_code: str) -> Session:
        if not self._verifier:
            raise AuthError("This sign-in link was started from another window. Please try again.")
        d = self._post("/token", {"auth_code": auth_code, "code_verifier": self._verifier},
                       params={"grant_type": "pkce"})
        self._verifier = None
        return self._set_session(d)

    # -- keeping the session alive
    def access_token(self) -> str:
        with self._lock:
            if not self.session:
                raise AuthError("Not signed in")
            if time.time() > self.session.expires_at - 120:
                self._refresh()
            return self.session.access_token

    def force_refresh(self) -> None:
        with self._lock:
            self._refresh()

    def _refresh(self) -> None:
        try:
            d = self._post("/token", {"refresh_token": self.session.refresh_token},
                           params={"grant_type": "refresh_token"})
        except AuthError as exc:
            if exc.status not in (400, 401, 403):
                raise                    # offline or server hiccup: keep the session, retry later
            self.session = None          # token revoked or expired: sign in again
            self.store.save(None)
            raise AuthError("Your sign-in expired. Please sign in again.") from exc
        email = self.session.email
        s = self._set_session(d)
        if not s.email:
            s.email = email

    def sign_out(self) -> None:
        if self.session:
            try:
                requests.post(self.base + "/logout", params={"scope": "local"},
                              headers=self._headers(self.session.access_token), timeout=8)
            except requests.RequestException:
                pass
        self.session = None
        self.store.save(None)


def _friendly(msg: str) -> str:
    m = msg.lower()
    if "not authorized" in m or "email_address_not_authorized" in m:
        return ("Email sign-in isn't open to everyone yet (the app's email service is still "
                "being set up). Please use Google for now.")
    if "rate limit" in m:
        return "Too many emails were sent. Please wait a few minutes and try again."
    if "expired or is invalid" in m or "otp" in m:
        return "That code is wrong or has expired. Request a new one."
    if "provider is not enabled" in m or "unsupported provider" in m:
        return "Google sign-in isn't switched on yet. Use email for now."
    return msg
