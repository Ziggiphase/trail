"""User settings: which apps count, goal, reminders, database link, startup.

Saved with QSettings (on Windows: HKCU\\Software\\Trail). This is
configuration only; your tracked time lives in the cloud database.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QSettings

from . import config

APP_NAME = "Trail"

DEFAULT_APPS = [
    ("code", "Visual Studio Code"), ("cursor", "Cursor"),
    ("windowsterminal", "Windows Terminal"), ("powershell", "Windows PowerShell"),
    ("cmd", "Command Prompt"), ("docker desktop", "Docker Desktop"),
    ("pycharm64", "PyCharm"), ("jupyter-lab", "JupyterLab"),
]


@dataclass
class TrackedApp:
    process: str
    label: str
    # Empty = always counts. Otherwise only counts when the window title
    # contains one of these (e.g. Chrome only when on "JupyterLab" or "Colab").
    title_keywords: list[str] = field(default_factory=list)
    enabled: bool = True     # switched off = kept in the list but not counted

    def matches(self, title: str) -> bool:
        if not self.enabled:
            return False
        if not self.title_keywords:
            return True
        t = title.lower()
        return any(k.lower() in t for k in self.title_keywords)


@dataclass
class Settings:
    apps: list[TrackedApp]
    database_url: str = ""
    idle_minutes: int = config.IDLE_AFTER_SECONDS // 60
    streak_minutes: int = config.STREAK_MIN_MINUTES
    daily_goal_minutes: int = 240
    device_name: str = config.DEVICE_NAME
    notify_goal: bool = True          # "goal reached" notification
    notify_streak: bool = True        # evening reminder when a streak is at risk
    reminder_hour: int = 20           # 24h clock
    first_run: bool = True

    def rules(self) -> dict[str, TrackedApp]:
        return {a.process: a for a in self.apps}


def _qs() -> QSettings:
    return QSettings(APP_NAME, APP_NAME)


def load() -> Settings:
    raw = _qs().value("settings_json", "")
    if raw:
        try:
            d = json.loads(raw)
            known = Settings.__dataclass_fields__
            d = {k: v for k, v in d.items() if k in known}
            d["apps"] = [TrackedApp(**a) for a in d.get("apps", [])]
            s = Settings(**d)
            if not s.database_url:
                s.database_url = config.DATABASE_URL
            return s
        except (TypeError, ValueError):
            pass
    return Settings(apps=[TrackedApp(p, l) for p, l in DEFAULT_APPS],
                    database_url=config.DATABASE_URL)


def save(s: Settings) -> None:
    s.first_run = False
    q = _qs()
    q.setValue("settings_json", json.dumps(asdict(s)))
    q.sync()


# ---------------------------------------------------------------- start at login
def _launch_command() -> str:
    if getattr(sys, "frozen", False):                       # installed .exe
        return f'"{sys.executable}" --minimized'
    exe = sys.executable
    if sys.platform == "win32" and exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"                     # no console window
    root = Path(__file__).resolve().parent.parent
    return f'"{exe}" "{root / "run_trail.py"}" --minimized'


if sys.platform == "win32":
    import winreg
    _RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def autostart_enabled() -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        except OSError:
            return False

    def set_autostart(on: bool) -> None:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass

elif sys.platform == "darwin":
    _PLIST = Path.home() / "Library/LaunchAgents/com.trail.app.plist"

    def autostart_enabled() -> bool:
        return _PLIST.exists()

    def set_autostart(on: bool) -> None:
        if not on:
            _PLIST.unlink(missing_ok=True)
            return
        import shlex
        args = "".join(f"<string>{a}</string>" for a in shlex.split(_launch_command()))
        _PLIST.parent.mkdir(parents=True, exist_ok=True)
        _PLIST.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
            "<key>Label</key><string>com.trail.app</string>"
            f"<key>ProgramArguments</key><array>{args}</array>"
            "<key>RunAtLoad</key><true/></dict></plist>")

else:
    _DESKTOP = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart/trail.desktop"

    def autostart_enabled() -> bool:
        return _DESKTOP.exists()

    def set_autostart(on: bool) -> None:
        if not on:
            _DESKTOP.unlink(missing_ok=True)
            return
        _DESKTOP.parent.mkdir(parents=True, exist_ok=True)
        _DESKTOP.write_text(f"[Desktop Entry]\nType=Application\nName=Trail\n"
                            f"Exec={_launch_command()}\nX-GNOME-Autostart-enabled=true\n")
