"""Reusable UI pieces: cards, stat tiles, a toggle switch, goal ring and charts."""
from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QPropertyAnimation, QRectF,
                            QSize, Qt)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import icons, theme
from .stats import fmt_duration


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def divider() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    return f


def icon_button(icon_name: str, tooltip: str, color: str = theme.MUTED) -> QPushButton:
    b = QPushButton()
    b.setObjectName("Icon")
    b.setIcon(icons.icon(icon_name, color))
    b.setIconSize(QSize(18, 18))
    b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


class Card(QFrame):
    """Rounded panel with an optional uppercase title and right-side widget."""

    def __init__(self, title: str | None = None, right: QWidget | None = None,
                 icon_name: str | None = None):
        super().__init__()
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(10)
        if title:
            head = QHBoxLayout()
            head.setSpacing(8)
            if icon_name:
                ic = QLabel()
                ic.setPixmap(icons.pixmap(icon_name, theme.MUTED, 15))
                head.addWidget(ic)
            head.addWidget(label(title.upper(), "CardTitle"))
            head.addStretch()
            if right:
                head.addWidget(right)
            self.body.addLayout(head)


class StatCard(Card):
    def __init__(self, title: str, icon_name: str, accent: str = theme.ACCENT):
        super().__init__()
        self.body.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(label(title.upper(), "CardTitle"))
        top.addStretch()
        badge = QLabel()
        badge.setPixmap(icons.pixmap(icon_name, accent, 18))
        top.addWidget(badge)
        self.body.addLayout(top)
        self.value = label("–", "BigNumber")
        self.sub = label("", "Muted")
        self.body.addWidget(self.value)
        self.body.addWidget(self.sub)

    def set(self, value: str, sub: str = "") -> None:
        self.value.setText(value)
        self.sub.setText(sub)


class Toggle(QAbstractButton):
    """iOS / Docker-style switch."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(38, 22)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get(self) -> float:
        return self._pos

    def _set(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def setChecked(self, on: bool) -> None:  # noqa: N802 (Qt naming)
        super().setChecked(on)
        if not getattr(self, "_anim", None) or self._anim.state() != QPropertyAnimation.Running:
            self._pos = 1.0 if on else 0.0
            self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(theme.BORDER_STRONG), QColor(theme.ACCENT)
        t = self._pos
        track = QColor(int(off.red() + (on.red() - off.red()) * t),
                       int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 38, 22), 11, 11)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(3 + t * 16, 3, 16, 16))
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(38, 22)


class GoalRing(QWidget):
    def __init__(self, size: int = 92):
        super().__init__()
        self.setFixedSize(size, size)
        self.progress = 0.0
        self.center = ""

    def set(self, progress: float, center: str) -> None:
        self.progress, self.center = max(0.0, progress), center
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        r = QRectF(6, 6, w - 12, w - 12)
        pen = QPen(QColor(theme.SURFACE_2), 9, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 0, 360 * 16)
        done = self.progress >= 1
        pen.setColor(QColor(theme.SUCCESS if done else theme.ACCENT))
        p.setPen(pen)
        span = int(min(self.progress, 1.0) * 360 * 16)
        if span:
            p.drawArc(r, 90 * 16, -span)
        p.setPen(QColor(theme.TEXT))
        f = QFont(self.font())
        f.setPointSizeF(12.5)
        f.setBold(True)
        p.setFont(f)
        p.drawText(r, Qt.AlignCenter, self.center)
        p.end()


class WeekBars(QWidget):
    """Vertical bars for N days with a dashed goal line."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.values: list[float] = []
        self.labels: list[str] = []
        self.goal = 0.0
        self.highlight = -1

    def set(self, values: list[float], labels: list[str], goal: float, highlight: int = -1) -> None:
        self.values, self.labels, self.goal, self.highlight = values, labels, goal, highlight
        self.update()

    def paintEvent(self, _e) -> None:
        if not self.values:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top, bottom = 22, 24
        chart_h = h - top - bottom
        top_val = max(max(self.values), self.goal, 3600) * 1.1
        n = len(self.values)
        slot = w / n
        bar_w = min(34.0, slot * 0.55)
        small = QFont(self.font())
        small.setPointSizeF(8.5)
        p.setFont(small)
        for i, v in enumerate(self.values):
            x = i * slot + (slot - bar_w) / 2
            bh = chart_h * v / top_val
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.SURFACE_2))
            p.drawRoundedRect(QRectF(x, top, bar_w, chart_h), 5, 5)
            if bh > 0:
                color = theme.SUCCESS if self.goal and v >= self.goal else theme.ACCENT
                c = QColor(color)
                if i != self.highlight and self.highlight >= 0:
                    c.setAlphaF(0.75)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x, top + chart_h - bh, bar_w, max(bh, 3)), 5, 5)
            p.setPen(QColor(theme.TEXT if i == self.highlight else theme.MUTED))
            p.drawText(QRectF(i * slot, h - bottom + 4, slot, 16), Qt.AlignCenter, self.labels[i])
            if v >= 60:
                p.setPen(QColor(theme.MUTED))
                txt = fmt_duration(v, short=True) if v < 10 * 3600 else f"{v / 3600:.0f}h"
                p.drawText(QRectF(i * slot, top + chart_h - bh - 18, slot, 16), Qt.AlignCenter, txt)
        if self.goal:
            y = top + chart_h - chart_h * self.goal / top_val
            pen = QPen(QColor(theme.SUCCESS), 1, Qt.DashLine)
            pen.setDashPattern([4, 4])
            p.setPen(pen)
            p.drawLine(0, int(y), w, int(y))
            p.setPen(QColor(theme.SUCCESS))
            p.drawText(QRectF(w - 90, y - 17, 90, 14), Qt.AlignRight, "daily goal")
        p.end()


class AppBars(QWidget):
    """Horizontal ranked bars: label, bar, duration."""

    ROW = 34

    def __init__(self, empty_text: str = "Nothing tracked yet"):
        super().__init__()
        self.rows: list[tuple[str, float]] = []
        self.empty_text = empty_text
        self.max_rows = 6
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumHeight(self.ROW * 2)

    def set(self, rows: list[tuple[str, float]]) -> None:
        self.rows = rows[: self.max_rows]
        self.setMinimumHeight(max(2, len(self.rows)) * self.ROW)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        if not self.rows:
            p.setPen(QColor(theme.FAINT))
            p.drawText(self.rect(), Qt.AlignCenter, self.empty_text)
            return
        top = max(v for _, v in self.rows) or 1
        total = sum(v for _, v in self.rows) or 1
        palette = [theme.ACCENT, "#7c6cf2", "#2ea8a0", "#e3a33b", "#d16bb2", "#6b8afd"]
        for i, (name, v) in enumerate(self.rows):
            y = i * self.ROW
            p.setPen(QColor(theme.TEXT))
            p.drawText(QRectF(0, y, w * 0.62, 16), Qt.AlignLeft | Qt.AlignVCenter, name)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(0, y, w, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"{fmt_duration(v)}  ·  {v / total:.0%}")
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.SURFACE_2))
            p.drawRoundedRect(QRectF(0, y + 20, w, 6), 3, 3)
            p.setBrush(QColor(palette[i % len(palette)]))
            p.drawRoundedRect(QRectF(0, y + 20, max(6.0, w * v / top), 6), 3, 3)
        p.end()


class Dot(QWidget):
    """Small coloured status dot."""

    def __init__(self, color: str = theme.FAINT, size: int = 8):
        super().__init__()
        self.color = color
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self.color = color
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(self.rect())
        p.end()


class Pill(QLabel):
    """Rounded status chip, e.g. 'Counting now'."""

    def __init__(self, text: str = "", color: str = theme.MUTED):
        super().__init__(text)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setAlignment(Qt.AlignCenter)
        self.set(text, color)

    def set(self, text: str, color: str) -> None:
        self.setText(text)
        c = QColor(color)
        self.setStyleSheet(
            f"color: {color}; background: rgba({c.red()},{c.green()},{c.blue()},0.13);"
            f"border-radius: 12px; padding: 0px 11px; font-size: 12px; font-weight: 600;")
        self.setVisible(bool(text))


def row(*widgets, spacing: int = 12, stretch_last: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        elif w is None:
            lay.addStretch()
        else:
            lay.addWidget(w)
    if stretch_last:
        lay.addStretch()
    return lay
