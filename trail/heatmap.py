"""GitHub-style contribution graph, painted with QPainter. Click a day to select it."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import theme
from .stats import fmt_duration, level

WEEKS = 53
LEFT, TOP, LEGEND = 30, 20, 26


class HeatmapWidget(QWidget):
    day_clicked = Signal(object)    # datetime.date

    def __init__(self, cell: int = 13, gap: int = 3, legend: bool = True):
        super().__init__()
        self.cell, self.gap, self.show_legend = cell, gap, legend
        self.days: dict[date, float] = {}
        self.today = date.today()
        self.selected: date | None = None
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(self._grid_h() + (LEGEND if legend else 4))

    def sizeHint(self) -> QSize:
        return QSize(self._grid_w(), self.height())

    def _step(self) -> int:
        return self.cell + self.gap

    def _grid_w(self) -> int:
        return LEFT + WEEKS * self._step()

    def _grid_h(self) -> int:
        return TOP + 7 * self._step()

    def _x0(self) -> float:
        return max(0, (self.width() - self._grid_w()) / 2)     # centre in the card

    def set_data(self, days: dict[date, float], today: date | None = None) -> None:
        self.days = days
        self.today = today or date.today()
        self.update()

    def select(self, d: date | None) -> None:
        self.selected = d
        self.update()

    # Columns are weeks starting on Sunday; the last column contains today.
    def _start(self) -> date:
        return self.today - timedelta(days=(self.today.weekday() + 1) % 7 + 7 * (WEEKS - 1))

    def _cell_rect(self, col: int, row: int) -> QRectF:
        return QRectF(self._x0() + LEFT + col * self._step(), TOP + row * self._step(),
                      self.cell, self.cell)

    def _date_at(self, pos: QPoint) -> date | None:
        step = self._step()
        col = int((pos.x() - self._x0() - LEFT) // step)
        row = int((pos.y() - TOP) // step)
        if not (0 <= col < WEEKS and 0 <= row < 7):
            return None
        d = self._start() + timedelta(days=col * 7 + row)
        return d if d <= self.today else None

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        small = QFont(self.font())
        small.setPointSizeF(8.5)
        p.setFont(small)
        x0 = self._x0()

        p.setPen(QColor(theme.MUTED))
        for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
            r = self._cell_rect(0, row)
            p.drawText(QRectF(x0, r.top() - 2, LEFT - 6, self.cell + 4),
                       Qt.AlignRight | Qt.AlignVCenter, name)

        start, last_month = self._start(), None
        for col in range(WEEKS):
            week = start + timedelta(days=col * 7)
            if week.month != last_month and col < WEEKS - 2:
                p.setPen(QColor(theme.MUTED))
                p.drawText(QRectF(self._cell_rect(col, 0).left(), 0, 40, TOP - 4),
                           Qt.AlignLeft | Qt.AlignBottom, week.strftime("%b"))
                last_month = week.month
            for row in range(7):
                d = week + timedelta(days=row)
                if d > self.today:
                    continue
                r = self._cell_rect(col, row)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.HEAT[level(self.days.get(d, 0))]))
                p.drawRoundedRect(r, 3, 3)
                if d == self.selected or d == self.today:
                    pen = QPen(QColor(theme.TEXT if d == self.selected else theme.MUTED), 1.4)
                    p.setPen(pen)
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(r.adjusted(-1.5, -1.5, 1.5, 1.5), 4, 4)

        if self.show_legend:
            y = self._grid_h() + 6
            right = x0 + self._grid_w()
            box = 11
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(right - 5 * (box + 3) - 40, y - 1, 34, box + 2),
                       Qt.AlignRight | Qt.AlignVCenter, "Less")
            for i, c in enumerate(theme.HEAT):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(c))
                p.drawRoundedRect(QRectF(right - (5 - i) * (box + 3), y, box, box), 2.5, 2.5)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(right + 4, y - 1, 34, box + 2), Qt.AlignLeft | Qt.AlignVCenter, "More")
            p.drawText(QRectF(x0 + LEFT, y - 1, 400, box + 2), Qt.AlignLeft | Qt.AlignVCenter,
                       "Click a day to see what you worked in")
        p.end()

    def mouseMoveEvent(self, event) -> None:
        d = self._date_at(event.position().toPoint())
        if d is None:
            QToolTip.hideText()
            return
        secs = self.days.get(d, 0)
        text = (f"<b>{fmt_duration(secs)}</b> of deep work<br>{d:%A, %d %B %Y}" if secs >= 60
                else f"No deep work<br>{d:%A, %d %B %Y}")
        QToolTip.showText(event.globalPosition().toPoint(), text, self)

    def mousePressEvent(self, event) -> None:
        d = self._date_at(event.position().toPoint())
        if d is not None:
            self.select(d)
            self.day_clicked.emit(d)
