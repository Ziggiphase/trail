"""Auto-update from GitHub Releases.

On startup and every few hours, Trail asks GitHub for the latest release of
the repo. If it's newer than this version and has Trail-Setup.exe attached,
the app offers to install it: it downloads the installer, runs it silently,
and the installer reopens Trail when done. Settings and data are kept.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from . import __version__, config

ASSET = "Trail-Setup.exe"


@dataclass
class Release:
    version: str
    url: str          # download link for Trail-Setup.exe
    notes: str
    page: str         # release page on GitHub


def parse(v: str) -> tuple[int, ...]:
    parts = []
    for p in v.strip().lstrip("vV").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts + [0] * (3 - len(parts)))


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse(candidate) > parse(current)


def can_self_update() -> bool:
    """Only the installed Windows app can replace itself."""
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def check(repo: str = config.GITHUB_REPO, current: str = __version__,
          api: str = "https://api.github.com") -> Release | None:
    r = requests.get(f"{api}/repos/{repo}/releases/latest", timeout=15,
                     headers={"Accept": "application/vnd.github+json",
                              "User-Agent": f"Trail/{current}"})
    if r.status_code == 404:          # no releases yet
        return None
    r.raise_for_status()
    d = r.json()
    tag = d.get("tag_name", "")
    if not tag or not is_newer(tag, current):
        return None
    asset = next((a for a in d.get("assets", []) if a.get("name") == ASSET), None)
    if not asset:                     # release published but installer still building
        return None
    return Release(version=tag.lstrip("vV"), url=asset["browser_download_url"],
                   notes=(d.get("body") or "").strip(), page=d.get("html_url", ""))


def download(rel: Release, progress: Callable[[int], None] | None = None) -> Path:
    dest = Path(tempfile.gettempdir()) / f"Trail-Setup-{rel.version}.exe"
    tmp = dest.with_suffix(".part")
    with requests.get(rel.url, stream=True, timeout=60,
                      headers={"User-Agent": f"Trail/{__version__}"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0)) or None
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(int(done * 100 / total))
    if dest.exists():
        dest.unlink()
    os.replace(tmp, dest)
    return dest


def launch_installer(path: Path) -> None:
    """Start the installer silently and detached; the caller then quits Trail.
    The installer waits for Trail to close, updates it, and starts it again."""
    flags = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                      "/CLOSEAPPLICATIONS", "/SP-"], creationflags=flags, close_fds=True)
