"""Pure helpers that turn {(day, app): seconds} into the numbers the UI shows."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from . import config

Data = dict[tuple[date, str], float]


def level(seconds: float) -> int:
    """0 = empty square, 4 = darkest green."""
    minutes = seconds / 60
    lvl = 0
    for i, threshold in enumerate(config.LEVEL_THRESHOLDS_MIN, start=1):
        if minutes >= threshold:
            lvl = i
    return lvl


def merge(*sources: Data) -> Data:
    out: Data = defaultdict(float)
    for src in sources:
        for k, v in src.items():
            out[k] += v
    return dict(out)


def by_day(data: Data) -> dict[date, float]:
    out: dict[date, float] = defaultdict(float)
    for (d, _), v in data.items():
        out[d] += v
    return dict(out)


def by_app(data: Data, start: date, end: date) -> dict[str, float]:
    """Totals per app for start..end inclusive, biggest first."""
    out: dict[str, float] = defaultdict(float)
    for (d, app), v in data.items():
        if start <= d <= end:
            out[app] += v
    return dict(sorted(out.items(), key=lambda kv: kv[1], reverse=True))


def range_total(days: dict[date, float], start: date, end: date) -> float:
    return sum(v for d, v in days.items() if start <= d <= end)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())        # Monday


def current_streak(days: dict[date, float], today: date | None = None,
                   min_minutes: int = config.STREAK_MIN_MINUTES) -> int:
    """Consecutive qualifying days ending today (or yesterday, if today has
    not qualified yet, so the streak doesn't 'break' at breakfast)."""
    today = today or date.today()
    need = min_minutes * 60
    d = today if days.get(today, 0) >= need else today - timedelta(days=1)
    streak = 0
    while days.get(d, 0) >= need:
        streak += 1
        d -= timedelta(days=1)
    return streak


def best_streak(days: dict[date, float], min_minutes: int = config.STREAK_MIN_MINUTES) -> int:
    need = min_minutes * 60
    good = sorted(d for d, v in days.items() if v >= need)
    best = run = 0
    prev = None
    for d in good:
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    return best


def fmt_duration(seconds: float, short: bool = False) -> str:
    m = int(seconds // 60)
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h" if short and m == 0 else f"{h}h {m:02d}m"


def fmt_hours(seconds: float) -> str:
    h = seconds / 3600
    return f"{h:,.0f}h" if h >= 100 else f"{h:,.1f}h"
