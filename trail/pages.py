"""The four main pages: Dashboard, Activity, Apps and Settings."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox,
                               QGridLayout, QHBoxLayout, QHeaderView, QLineEdit,
                               QPushButton, QScrollArea, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import __version__, activity, config, icons, theme
from .heatmap import HeatmapWidget
from .settings import Settings, TrackedApp
from .signin import open_url
from .stats import (Data, best_streak, by_app, current_streak, fmt_duration,
                    fmt_hours, range_total, week_start)
from .widgets import (AppBars, Card, GoalRing, Pill, StatCard, Toggle, WeekBars,
                      divider, icon_button, label, row)


@dataclass
class View:
    """Everything a page needs to draw itself, rebuilt every few seconds."""
    data: Data                 # {(day, app): seconds}, cloud + not-yet-synced
    days: dict                 # {day: seconds}
    today: date
    settings: Settings
    current_app: str | None
    counting: bool
    paused: bool
    recent: list[str]
    connected: bool

    def label(self, proc: str) -> str:
        rule = self.settings.rules().get(proc)
        return rule.label if rule else activity.KNOWN_LABELS.get(proc, proc)


class Page(QScrollArea):
    title = ""
    subtitle = ""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("Content")
        self.setWidget(inner)
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(28, 22, 28, 28)
        self.lay.setSpacing(16)

    def refresh(self, v: View) -> None:  # pragma: no cover - overridden
        pass


# ======================================================================= Dashboard
class TodayCard(Card):
    def __init__(self):
        super().__init__()
        self.body.setSpacing(4)
        h = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(label("TODAY", "CardTitle"))
        self.value = label("–", "BigNumber")
        self.sub = label("", "Muted")
        col.addWidget(self.value)
        col.addWidget(self.sub)
        col.addStretch()
        h.addLayout(col, 1)
        self.ring = GoalRing(84)
        h.addWidget(self.ring, 0, Qt.AlignVCenter)
        self.body.addLayout(h)

    def set(self, secs: float, goal: float) -> None:
        self.value.setText(fmt_duration(secs))
        pct = secs / goal if goal else 0
        self.ring.set(pct, f"{min(pct, 9.99):.0%}")
        left = goal - secs
        self.sub.setText("Goal reached ✓" if left <= 0 else f"{fmt_duration(left)} to your goal")


class DashboardPage(Page):
    title = "Dashboard"
    subtitle = "Your deep work at a glance"
    go_to = Signal(str)

    def __init__(self):
        super().__init__()
        # setup banner (only while not signed in)
        self.banner = Card()
        self.banner.setStyleSheet(f"QFrame#Card {{ background: {theme.ACCENT_SOFT}; "
                                  f"border-color: #29466f; }}")
        b = QHBoxLayout()
        ic = label()
        ic.setPixmap(icons.pixmap("cloud", theme.ACCENT_HOVER, 22))
        b.addWidget(ic)
        txt = QVBoxLayout()
        txt.addWidget(label("Sign in to save your trail", "SectionTitle"))
        txt.addWidget(label("You're tracking without an account, so your time stays on this PC. "
                            "Sign in to keep it safe and see it on any computer.", "Muted", wrap=True))
        b.addLayout(txt, 1)
        apps_btn = QPushButton("Choose apps")
        apps_btn.clicked.connect(lambda: self.go_to.emit("apps"))
        db_btn = QPushButton("Sign in")
        db_btn.setObjectName("Primary")
        db_btn.clicked.connect(lambda: self.go_to.emit("signin"))
        b.addWidget(apps_btn)
        b.addWidget(db_btn)
        self.banner.body.addLayout(b)
        self.lay.addWidget(self.banner)

        grid = QGridLayout()
        grid.setSpacing(16)
        self.today_card = TodayCard()
        self.week_card = StatCard("This week", "calendar")
        self.streak_card = StatCard("Streak", "flame", theme.WARNING)
        self.month_card = StatCard("Last 30 days", "clock", theme.SUCCESS)
        for i, c in enumerate((self.today_card, self.week_card, self.streak_card, self.month_card)):
            grid.addWidget(c, 0, i)
            grid.setColumnStretch(i, 1)
        self.lay.addLayout(grid)

        mid = QHBoxLayout()
        mid.setSpacing(16)
        self.week_chart_card = Card("Last 7 days", icon_name="activity")
        self.week_bars = WeekBars()
        self.week_chart_card.body.addWidget(self.week_bars)
        self.apps_card = Card("Today by app", icon_name="apps")
        self.today_apps = AppBars("No deep work yet today")
        self.apps_card.body.addWidget(self.today_apps)
        self.apps_card.body.addStretch()
        mid.addWidget(self.week_chart_card, 3)
        mid.addWidget(self.apps_card, 2)
        self.lay.addLayout(mid)

        self.trail_card = Card("Your trail · past year", icon_name="dashboard")
        self.heatmap = HeatmapWidget(cell=12, gap=3)
        self.heatmap.day_clicked.connect(lambda d: self.go_to.emit(f"day:{d.isoformat()}"))
        self.trail_card.body.addWidget(self.heatmap)
        self.lay.addWidget(self.trail_card)
        self.lay.addStretch()

    def refresh(self, v: View) -> None:
        s, t, days = v.settings, v.today, v.days
        self.banner.setVisible(not v.connected)
        goal = s.daily_goal_minutes * 60
        self.today_card.set(days.get(t, 0), goal)

        ws = week_start(t)
        this_w = range_total(days, ws, t)
        last_w = range_total(days, ws - timedelta(days=7), t - timedelta(days=7))
        if last_w:
            change = (this_w - last_w) / last_w
            arrow = "▲" if change >= 0 else "▼"
            sub = f"{arrow} {abs(change):.0%} vs same point last week"
        else:
            sub = "First week on your trail"
        self.week_card.set(fmt_duration(this_w), sub)

        cur = current_streak(days, t, s.streak_minutes)
        best = max(best_streak(days, s.streak_minutes), cur)
        self.streak_card.set(f"{cur} day{'s' if cur != 1 else ''}", f"Best: {best} days")

        m_start = t - timedelta(days=29)
        active = sum(1 for d, x in days.items() if m_start <= d <= t and x >= 60)
        self.month_card.set(fmt_hours(range_total(days, m_start, t)), f"Active on {active} of 30 days")

        last7 = [t - timedelta(days=i) for i in range(6, -1, -1)]
        self.week_bars.set([days.get(d, 0) for d in last7],
                           ["Today" if d == t else d.strftime("%a") for d in last7], goal, 6)
        self.today_apps.set([(v.label(a), x) for a, x in by_app(v.data, t, t).items() if x >= 30])
        self.heatmap.set_data(days, t)


# ======================================================================= Activity
class ActivityPage(Page):
    title = "Activity"
    subtitle = "Your full year, day by day"

    def __init__(self):
        super().__init__()
        grid = QGridLayout()
        grid.setSpacing(16)
        self.c_total = StatCard("Past year", "clock")
        self.c_days = StatCard("Active days", "calendar", theme.SUCCESS)
        self.c_best = StatCard("Best streak", "flame", theme.WARNING)
        self.c_avg = StatCard("Average active day", "target", "#7c6cf2")
        for i, c in enumerate((self.c_total, self.c_days, self.c_best, self.c_avg)):
            grid.addWidget(c, 0, i)
            grid.setColumnStretch(i, 1)
        self.lay.addLayout(grid)

        hm_card = Card("Contribution graph", icon_name="activity")
        self.heatmap = HeatmapWidget(cell=12, gap=3)
        self.heatmap.day_clicked.connect(self.show_day)
        hm_card.body.addWidget(self.heatmap)
        self.lay.addWidget(hm_card)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        self.day_card = Card("Selected day", icon_name="calendar")
        self.day_title = label("", "SectionTitle")
        self.day_total = label("", "Muted")
        self.day_apps = AppBars("No deep work on this day")
        self.day_apps.max_rows = 8
        self.day_card.body.addWidget(self.day_title)
        self.day_card.body.addWidget(self.day_total)
        self.day_card.body.addSpacing(6)
        self.day_card.body.addWidget(self.day_apps)
        self.day_card.body.addStretch()
        self.months_card = Card("Monthly totals", icon_name="calendar")
        self.months = WeekBars()
        self.months_card.body.addWidget(self.months)
        bottom.addWidget(self.day_card, 2)
        bottom.addWidget(self.months_card, 3)
        self.lay.addLayout(bottom)
        self.lay.addStretch()
        self._view: View | None = None
        self._selected: date | None = None

    def show_day(self, d: date) -> None:
        self._selected = d
        self.heatmap.select(d)
        if self._view:
            self._fill_day(self._view)

    def _fill_day(self, v: View) -> None:
        d = self._selected or v.today
        self.heatmap.select(d)
        self.day_title.setText("Today" if d == v.today else d.strftime("%A, %d %B %Y"))
        secs = v.days.get(d, 0)
        self.day_total.setText(f"{fmt_duration(secs)} of deep work" if secs >= 60 else "Rest day")
        self.day_apps.set([(v.label(a), x) for a, x in by_app(v.data, d, d).items() if x >= 30])

    def refresh(self, v: View) -> None:
        self._view = v
        t, days, s = v.today, v.days, v.settings
        start = t - timedelta(days=364)
        year = {d: x for d, x in days.items() if start <= d <= t}
        total = sum(year.values())
        active = [x for x in year.values() if x >= 60]
        self.c_total.set(fmt_hours(total), f"since {start:%d %b %Y}")
        self.c_days.set(str(len(active)), f"{len(active) / 365:.0%} of the year")
        self.c_best.set(f"{best_streak(year, s.streak_minutes)} days",
                        f"current: {current_streak(days, t, s.streak_minutes)} days")
        self.c_avg.set(fmt_duration(total / len(active)) if active else "0m", "on days you worked")
        self.heatmap.set_data(days, t)
        self._fill_day(v)

        months, labels = [], []
        y, m = t.year, t.month
        for _ in range(12):
            first = date(y, m, 1)
            nxt = date(y + (m == 12), m % 12 + 1, 1)
            months.append(range_total(days, first, nxt - timedelta(days=1)))
            labels.append(first.strftime("%b"))
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        self.months.set(months[::-1], labels[::-1], 0, 11)


# ======================================================================= Apps
class AppsPage(Page):
    title = "Tracked apps"
    subtitle = "Choose which apps count as deep work"
    add_requested = Signal()
    edit_requested = Signal(str)
    remove_requested = Signal(str)
    enabled_changed = Signal(str, bool)
    quick_add = Signal(str)

    COLS = ["", "App", "Counts when", "Today", "Last 30 days", "Status", ""]

    def __init__(self):
        super().__init__()
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tracked apps")
        self.search.addAction(icons.icon("search"), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self._filter)
        bar.addWidget(self.search)
        bar.addStretch()
        add = QPushButton("  Add apps")
        add.setObjectName("Primary")
        add.setIcon(icons.icon("plus", "white"))
        add.clicked.connect(self.add_requested.emit)
        bar.addWidget(add)
        self.lay.addLayout(bar)

        card = Card()
        card.body.setContentsMargins(4, 4, 4, 4)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().setDefaultSectionSize(54)
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        modes = [QHeaderView.Fixed, QHeaderView.Stretch, QHeaderView.Stretch,
                 QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
                 QHeaderView.Fixed, QHeaderView.Fixed]
        for i, m in enumerate(modes):
            hh.setSectionResizeMode(i, m)
        self.table.setColumnWidth(0, 64)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(6, 90)
        card.body.addWidget(self.table)
        self.card = card
        self.lay.addWidget(card)
        self.lay.addWidget(label("Switch an app off to pause counting it without removing it. "
                                 "Use Edit to count a browser only on certain pages.", "Faint", wrap=True))

        self.suggest_card = Card("Used recently, not tracked", icon_name="info")
        self.suggest_row = QHBoxLayout()
        self.suggest_row.setSpacing(8)
        self.suggest_card.body.addLayout(self.suggest_row)
        self.lay.addWidget(self.suggest_card)
        self.lay.addStretch()
        self._sig: tuple = ()
        self._pills: dict[str, Pill] = {}
        self._cells: dict[str, tuple[QTableWidgetItem, QTableWidgetItem]] = {}

    def _filter(self, text: str) -> None:
        t = text.lower().strip()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            self.table.setRowHidden(r, bool(t) and t not in item.data(Qt.UserRole))

    def _rebuild(self, apps: list[TrackedApp]) -> None:
        self.table.setRowCount(0)
        self._pills.clear()
        self._cells.clear()
        for app in apps:
            r = self.table.rowCount()
            self.table.insertRow(r)

            tog_wrap = QWidget()
            tl = QHBoxLayout(tog_wrap)
            tl.setContentsMargins(14, 0, 0, 0)
            tog = Toggle(app.enabled)
            tog.setToolTip("Count this app")
            tog.toggled.connect(lambda on, p=app.process: self.enabled_changed.emit(p, on))
            tl.addWidget(tog)
            self.table.setCellWidget(r, 0, tog_wrap)

            name = QTableWidgetItem()
            name.setData(Qt.UserRole, f"{app.label} {app.process}".lower())
            self.table.setItem(r, 1, name)
            name_w = QWidget()
            nl = QVBoxLayout(name_w)
            nl.setContentsMargins(8, 6, 0, 6)
            nl.setSpacing(1)
            nl.addWidget(label(app.label))
            nl.addWidget(label(app.process, "Faint"))
            self.table.setCellWidget(r, 1, name_w)

            rule = ("Title contains: " + ", ".join(app.title_keywords)) if app.title_keywords \
                else "Always, when in front"
            rule_item = QTableWidgetItem(rule)
            rule_item.setForeground(QColor(theme.TEXT if app.title_keywords else theme.MUTED))
            self.table.setItem(r, 2, rule_item)

            today_i, month_i = QTableWidgetItem("–"), QTableWidgetItem("–")
            self.table.setItem(r, 3, today_i)
            self.table.setItem(r, 4, month_i)
            self._cells[app.process] = (today_i, month_i)

            pill_w = QWidget()
            pl = QHBoxLayout(pill_w)
            pl.setContentsMargins(8, 0, 0, 0)
            pill = Pill()
            pl.addWidget(pill)
            pl.addStretch()
            self._pills[app.process] = pill
            self.table.setCellWidget(r, 5, pill_w)

            act = QWidget()
            al = QHBoxLayout(act)
            al.setContentsMargins(0, 0, 8, 0)
            al.setSpacing(2)
            e = icon_button("edit", "Edit name and rule")
            e.clicked.connect(lambda _=False, p=app.process: self.edit_requested.emit(p))
            d = icon_button("trash", "Stop tracking this app", theme.DANGER)
            d.clicked.connect(lambda _=False, p=app.process: self.remove_requested.emit(p))
            al.addWidget(e)
            al.addWidget(d)
            self.table.setCellWidget(r, 6, act)

        h = self.table.horizontalHeader().height() + 54 * max(1, len(apps)) + 6
        self.table.setFixedHeight(h)
        self._filter(self.search.text())

    def _rebuild_suggestions(self, procs: list[str], v: View) -> None:
        while self.suggest_row.count():
            w = self.suggest_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        for p in procs:
            b = QPushButton(f"  {v.label(p)}")
            b.setIcon(icons.icon("plus"))
            b.setToolTip(f"Track {p}")
            b.clicked.connect(lambda _=False, proc=p: self.quick_add.emit(proc))
            self.suggest_row.addWidget(b)
        self.suggest_row.addStretch()
        self.suggest_card.setVisible(bool(procs))

    def refresh(self, v: View) -> None:
        apps = v.settings.apps
        sig = tuple((a.process, a.label, tuple(a.title_keywords), a.enabled) for a in apps)
        if sig != self._sig:
            self._sig = sig
            self._rebuild(apps)
        today = by_app(v.data, v.today, v.today)
        month = by_app(v.data, v.today - timedelta(days=29), v.today)
        for proc, (ti, mi) in self._cells.items():
            ti.setText(fmt_duration(today.get(proc, 0)))
            mi.setText(fmt_duration(month.get(proc, 0)))
        rules = v.settings.rules()
        for proc, pill in self._pills.items():
            if not rules[proc].enabled:
                pill.set("Off", theme.FAINT)
            elif v.paused:
                pill.set("Paused", theme.WARNING)
            elif v.counting and v.current_app == proc:
                pill.set("● Counting now", theme.SUCCESS)
            elif v.current_app == proc:
                pill.set("Open · rule not met", theme.WARNING)
            else:
                pill.set("Ready", theme.MUTED)

        tracked = {a.process for a in apps}
        sugg = [p for p in v.recent if p not in tracked and p not in activity.SELF_NAMES][:5]
        if tuple(sugg) != getattr(self, "_sugg", None):
            self._sugg = tuple(sugg)
            self._rebuild_suggestions(sugg, v)


# ======================================================================= Settings
class SettingsPage(Page):
    title = "Settings"
    subtitle = "Account, goal, reminders and startup"
    changed = Signal(object)                 # new Settings (applied immediately)
    autostart_changed = Signal(bool)
    sign_in_requested = Signal()
    sign_out_requested = Signal()
    delete_requested = Signal()
    device_changed = Signal(str)
    import_requested = Signal(str)           # old Neon database link
    check_updates_requested = Signal()
    export_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, autostart_on: bool, data_folder: str):
        super().__init__()
        self._s: Settings | None = None
        self._loading = False

        # --- account
        ac = self._section("Account", "cloud")
        self.acct_title = label("", "SectionTitle")
        self.acct_sub = label("", "Muted", wrap=True)
        t = QVBoxLayout()
        t.setSpacing(2)
        t.addWidget(self.acct_title)
        t.addWidget(self.acct_sub)
        self.btn_signin = QPushButton("Sign in")
        self.btn_signin.setObjectName("Primary")
        self.btn_signin.clicked.connect(self.sign_in_requested.emit)
        self.btn_signout = QPushButton("Sign out")
        self.btn_signout.clicked.connect(self.sign_out_requested.emit)
        h = QHBoxLayout()
        h.addLayout(t, 1)
        h.addWidget(self.btn_signin, 0, Qt.AlignVCenter)
        h.addWidget(self.btn_signout, 0, Qt.AlignVCenter)
        ac.body.addLayout(h)
        ac._rows = 1
        self.device = QLineEdit()
        self.device.setFixedWidth(220)
        self.device.editingFinished.connect(lambda: self.device_changed.emit(self.device.text().strip()))
        self._row(ac, "This computer's name",
                  "Sign in on several PCs with the same account; totals are combined.", self.device)
        self.legacy_wrap = QWidget()
        lw = QHBoxLayout(self.legacy_wrap)
        lw.setContentsMargins(0, 0, 0, 0)
        self.legacy_url = QLineEdit()
        self.legacy_url.setEchoMode(QLineEdit.Password)
        self.legacy_url.setPlaceholderText("postgresql://… (your old Neon link)")
        self.legacy_url.setMinimumWidth(300)
        self.btn_import = QPushButton("Import")
        self.btn_import.clicked.connect(lambda: self.import_requested.emit(self.legacy_url.text().strip()))
        lw.addWidget(self.legacy_url, 1)
        lw.addWidget(self.btn_import)
        self.legacy_row_title = "Bring over earlier history"
        self._row(ac, self.legacy_row_title,
                  "If you used Trail with your own Neon database before, copy that history into your account.",
                  self.legacy_wrap)

        # --- goal
        goal = self._section("Goal & streak", "target")
        self.goal = QDoubleSpinBox(minimum=0.5, maximum=16, singleStep=0.5, suffix=" h", decimals=1)
        self.goal.setFixedWidth(110)
        self.goal.valueChanged.connect(self._emit)
        self._row(goal, "Daily goal", "How much deep work you aim for each day.", self.goal)
        self.streak = QSpinBox(minimum=1, maximum=600, suffix=" min")
        self.streak.setFixedWidth(110)
        self.streak.valueChanged.connect(self._emit)
        self._row(goal, "A day counts towards your streak at",
                  "Keep it small so busy days don't break the chain.", self.streak)

        # --- tracking
        tr = self._section("Tracking", "clock")
        self.idle = QSpinBox(minimum=1, maximum=60, suffix=" min")
        self.idle.setFixedWidth(110)
        self.idle.valueChanged.connect(self._emit)
        self._row(tr, "Stop counting after no activity for",
                  "Reading code counts; walking away from the keyboard doesn't.", self.idle)
        self.autostart = Toggle(autostart_on)
        self.autostart.toggled.connect(self.autostart_changed.emit)
        self._row(tr, "Start Trail when I sign in",
                  "Runs quietly in the system tray so you never forget to track.", self.autostart)

        # --- notifications
        nt = self._section("Notifications", "bell")
        self.n_goal = Toggle()
        self.n_goal.toggled.connect(self._emit)
        self._row(nt, "When I reach my daily goal", "A small desktop notification.", self.n_goal)
        self.n_streak = Toggle()
        self.n_streak.toggled.connect(self._emit)
        self.rem_hour = QComboBox()
        self.rem_hour.setFixedWidth(110)
        for h in range(12, 24):
            self.rem_hour.addItem(f"{h:02d}:00", h)
        self.rem_hour.currentIndexChanged.connect(self._emit)
        r = QHBoxLayout()
        r.setSpacing(10)
        r.addWidget(self.rem_hour)
        r.addWidget(self.n_streak)
        wrap = QWidget()
        wrap.setLayout(r)
        self._row(nt, "Streak reminder",
                  "If you haven't hit your streak minimum by this time, Trail nudges you.", wrap)

        # --- data & privacy
        dp = self._section("Your data & privacy", "download")
        dp.body.addWidget(label(
            "Trail records only app names and how long you used them, per day. It never "
            "stores window titles, keystrokes, screenshots or what you type. Window titles "
            "are read only to check the rules you set, then discarded.", "Muted", wrap=True))
        ex = QPushButton("  Export to CSV")
        ex.setIcon(icons.icon("download"))
        ex.clicked.connect(self.export_requested.emit)
        of = QPushButton("  Open Trail's folder")
        of.setIcon(icons.icon("folder"))
        of.setToolTip(data_folder)
        of.clicked.connect(self.open_folder_requested.emit)
        self.btn_delete = QPushButton("  Delete my cloud data")
        self.btn_delete.setObjectName("Danger")
        self.btn_delete.setIcon(icons.icon("trash", theme.DANGER))
        self.btn_delete.clicked.connect(self.delete_requested.emit)
        pp = QPushButton("Privacy policy")
        pp.setObjectName("Link")
        pp.clicked.connect(lambda: open_url(config.PRIVACY_URL))
        dp.body.addLayout(row(ex, of, self.btn_delete, None, pp))

        # --- about
        ab = self._section("About", "info")
        self.update_status = label("", "Faint")
        chk = QPushButton("Check for updates")
        chk.clicked.connect(self.check_updates_requested.emit)
        site = QPushButton("Website")
        site.setObjectName("Link")
        site.clicked.connect(lambda: open_url(config.WEBSITE_URL))
        about = QVBoxLayout()
        about.setSpacing(2)
        about.addWidget(label(f"Trail {__version__} · small daily decisions, made visible."))
        about.addWidget(self.update_status)
        h2 = QHBoxLayout()
        h2.addLayout(about, 1)
        h2.addWidget(site)
        h2.addWidget(chk)
        ab.body.addLayout(h2)
        self.lay.addStretch()

    def _section(self, title: str, icon_name: str) -> Card:
        c = Card(title, icon_name=icon_name)
        c.body.setSpacing(14)
        self.lay.addWidget(c)
        c._rows = 0
        return c

    def _row(self, card: Card, title: str, desc: str, control: QWidget) -> None:
        if card._rows:
            card.body.addWidget(divider())
        card._rows += 1
        h = QHBoxLayout()
        t = QVBoxLayout()
        t.setSpacing(2)
        t.addWidget(label(title))
        t.addWidget(label(desc, "Faint", wrap=True))
        h.addLayout(t, 1)
        h.addSpacing(24)
        h.addWidget(control, 0, Qt.AlignVCenter | Qt.AlignRight)
        card.body.addLayout(h)

    def load(self, s: Settings) -> None:
        self._loading = True
        self._s = s
        self.goal.setValue(s.daily_goal_minutes / 60)
        self.streak.setValue(s.streak_minutes)
        self.idle.setValue(s.idle_minutes)
        self.n_goal.setChecked(s.notify_goal)
        self.n_streak.setChecked(s.notify_streak)
        self.rem_hour.setCurrentIndex(max(0, self.rem_hour.findData(s.reminder_hour)))
        self.device.setText(s.device_name)
        if s.database_url and not self.legacy_url.text():
            self.legacy_url.setText(s.database_url)
        self._loading = False

    def set_update_status(self, text: str) -> None:
        self.update_status.setText(text)

    def set_account(self, email: str | None, status: str = "", color: str = theme.MUTED) -> None:
        if email:
            self.acct_title.setText(email)
        else:
            self.acct_title.setText("Not signed in")
            status = status or "Your time is kept on this PC. Sign in to save it and see it everywhere."
        self.acct_sub.setText(status)
        self.acct_sub.setStyleSheet(f"color: {color};")
        self.btn_signin.setVisible(not email)
        self.btn_signout.setVisible(bool(email))
        self.btn_delete.setEnabled(bool(email))
        self.btn_import.setEnabled(bool(email))

    def _emit(self, *_a) -> None:
        if self._loading or not self._s:
            return
        self._s = replace(
            self._s,
            daily_goal_minutes=int(round(self.goal.value() * 60)),
            streak_minutes=self.streak.value(),
            idle_minutes=self.idle.value(),
            notify_goal=self.n_goal.isChecked(),
            notify_streak=self.n_streak.isChecked(),
            reminder_hour=self.rem_hour.currentData(),
        )
        self.changed.emit(self._s)

    def refresh(self, v: View) -> None:
        self._s = v.settings          # always edit the latest settings
