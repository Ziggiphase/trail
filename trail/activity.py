"""Cross-platform helpers: which window is in front, idle time, and which
apps currently have open windows (for the app picker).

Windows uses ctypes only (no pywin32). macOS uses pyobjc. Linux uses
xprop/xprintidle and works on X11 only (Wayland hides other apps' windows).
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

import psutil

SELF_NAMES = {"trail", "python", "pythonw"}


@dataclass(frozen=True)
class AppInfo:
    process: str          # normalised process name, e.g. "code"
    label: str            # friendly name, e.g. "Visual Studio Code"


def clean(name: str) -> str:
    name = os.path.basename(name).lower().strip()
    return name[:-4] if name.endswith(".exe") else name


KNOWN_LABELS = {
    "code": "Visual Studio Code", "cursor": "Cursor", "windowsterminal": "Windows Terminal",
    "powershell": "Windows PowerShell", "pwsh": "PowerShell 7", "cmd": "Command Prompt",
    "docker desktop": "Docker Desktop", "pycharm64": "PyCharm", "idea64": "IntelliJ IDEA",
    "dbeaver": "DBeaver", "postman": "Postman", "jupyter-lab": "JupyterLab",
    "chrome": "Google Chrome", "msedge": "Microsoft Edge", "firefox": "Firefox",
    "spyder": "Spyder", "rstudio": "RStudio", "datagrip64": "DataGrip",
    "antigravity": "Antigravity", "anaconda-navigator": "Anaconda Navigator",
}


# ---------------------------------------------------------------- Windows
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _version = ctypes.windll.version

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    def _pid_of(hwnd) -> int:
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _title_of(hwnd) -> str:
        n = _user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def _file_description(path: str) -> str | None:
        """Read the 'File description' from an .exe (what Task Manager shows)."""
        try:
            size = _version.GetFileVersionInfoSizeW(path, None)
            if not size:
                return None
            data = ctypes.create_string_buffer(size)
            if not _version.GetFileVersionInfoW(path, 0, size, data):
                return None
            ptr, ln = ctypes.c_void_p(), wintypes.UINT()
            if not _version.VerQueryValueW(data, r"\VarFileInfo\Translation",
                                           ctypes.byref(ptr), ctypes.byref(ln)) or not ln.value:
                return None
            lang, cp = ctypes.cast(ptr, ctypes.POINTER(wintypes.WORD * 2)).contents
            key = rf"\StringFileInfo\{lang:04x}{cp:04x}\FileDescription"
            if _version.VerQueryValueW(data, key, ctypes.byref(ptr), ctypes.byref(ln)) and ln.value:
                return ctypes.wstring_at(ptr.value, ln.value - 1).strip() or None
        except (OSError, ValueError):
            pass
        return None

    def active_window() -> tuple[str | None, str]:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None, ""
        try:
            return clean(psutil.Process(_pid_of(hwnd)).name()), _title_of(hwnd)
        except psutil.Error:
            return None, ""

    def idle_seconds() -> float:
        info = _LASTINPUTINFO(cbSize=ctypes.sizeof(_LASTINPUTINFO))
        _user32.GetLastInputInfo(ctypes.byref(info))
        return ((_kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0

    def _window_pids() -> set[int]:
        pids: set[int] = set()
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            if _user32.IsWindowVisible(hwnd) and _user32.GetWindowTextLengthW(hwnd) > 0:
                pids.add(_pid_of(hwnd))
            return True

        _user32.EnumWindows(proc(cb), 0)
        return pids

    def label_for_path(path: str) -> str:
        return KNOWN_LABELS.get(clean(path)) or _file_description(path) or clean(path)

# ---------------------------------------------------------------- macOS
elif sys.platform == "darwin":
    from AppKit import NSWorkspace
    from Quartz import (CGEventSourceSecondsSinceLastEventType,
                        kCGAnyInputEventType,
                        kCGEventSourceStateCombinedSessionState)

    def active_window() -> tuple[str | None, str]:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return (clean(app.localizedName()) if app else None), ""  # titles need Accessibility

    def idle_seconds() -> float:
        return CGEventSourceSecondsSinceLastEventType(
            kCGEventSourceStateCombinedSessionState, kCGAnyInputEventType)

    def _window_pids() -> set[int]:
        return {a.processIdentifier() for a in NSWorkspace.sharedWorkspace().runningApplications()
                if a.activationPolicy() == 0}

    def label_for_path(path: str) -> str:
        return KNOWN_LABELS.get(clean(path), os.path.basename(path).removesuffix(".app"))

# ---------------------------------------------------------------- Linux (X11)
else:
    def _run(*cmd: str) -> str:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout

    def active_window() -> tuple[str | None, str]:
        try:
            win = _run("xprop", "-root", "_NET_ACTIVE_WINDOW").split()[-1]
            props = _run("xprop", "-id", win, "_NET_WM_PID", "_NET_WM_NAME")
            pid = int(props.split("_NET_WM_PID(CARDINAL) = ")[1].split()[0])
            title = props.split(" = ", 2)[-1].strip().strip('"') if "_NET_WM_NAME" in props else ""
            return clean(psutil.Process(pid).name()), title
        except (OSError, ValueError, IndexError, psutil.Error, subprocess.SubprocessError):
            return None, ""

    def idle_seconds() -> float:
        try:
            return int(_run("xprintidle")) / 1000.0
        except (OSError, ValueError, subprocess.SubprocessError):
            return 0.0

    def _window_pids() -> set[int]:
        pids = set()
        try:
            ids = _run("xprop", "-root", "_NET_CLIENT_LIST").split("#", 1)[1].split(",")
            for w in ids:
                out = _run("xprop", "-id", w.strip(), "_NET_WM_PID")
                if "=" in out:
                    pids.add(int(out.split("=")[1]))
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
        return pids

    def label_for_path(path: str) -> str:
        return KNOWN_LABELS.get(clean(path), clean(path))


def open_window_apps() -> list[AppInfo]:
    """Apps that currently have a visible window, for the picker."""
    seen: dict[str, AppInfo] = {}
    for pid in _window_pids():
        try:
            p = psutil.Process(pid)
            name = clean(p.name())
            if name in seen or name in SELF_NAMES:
                continue
            try:
                exe = p.exe()
            except psutil.Error:
                exe = p.name()
            seen[name] = AppInfo(name, label_for_path(exe))
        except psutil.Error:
            continue
    return sorted(seen.values(), key=lambda a: a.label.lower())
