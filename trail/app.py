"""Trail main window: sidebar navigation, pages, top bar, status bar and tray."""
from __future__ import annotations

import csv
import getpass
import logging
import sys
import threading
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, QSize, QStandardPaths, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFileDialog, QFrame,
                               QHBoxLayout, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QStackedWidget, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

from . import __version__, config, icons, theme
from . import settings as settings_mod
from .dialogs import AddAppsDialog, EditAppDialog
from .outbox import Outbox
from .pages import ActivityPage, AppsPage, DashboardPage, SettingsPage, View
from .stats import by_day, current_streak, fmt_duration, merge
from .tracker import Tracker
from .widgets import Dot, Pill, label

log = logging.getLogger("trail")


def data_folder() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))


class Bridge(QObject):
    """Carries results from background threads to the UI thread."""
    synced = Signal(object, str)        # cloud data (or None), status text
    tested = Signal(object)             # None = ok, else error text


class GoalLine(QWidget):
    """Thin progress bar for the sidebar."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(6)
        self.value = 0.0

    def set(self, v: float) -> None:
        self.value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.SURFACE_2))
        p.drawRoundedRect(self.rect(), 3, 3)
        if self.value:
            p.setBrush(QColor(theme.SUCCESS if self.value >= 1 else theme.ACCENT))
            r = self.rect()
            r.setWidth(max(6, int(r.width() * self.value)))
            p.drawRoundedRect(r, 3, 3)
        p.end()


def nav_icon(name: str) -> QIcon:
    ic = QIcon()
    ic.addPixmap(icons.pixmap(name, theme.MUTED, 18), QIcon.Normal, QIcon.Off)
    ic.addPixmap(icons.pixmap(name, theme.ACCENT_HOVER, 18), QIcon.Normal, QIcon.On)
    return ic


class MainWindow(QMainWindow):
    def __init__(self, settings: settings_mod.Settings, tracker: Tracker | None = None):
        super().__init__()
        self.settings = settings
        self.tracker = tracker or Tracker(settings.rules(), idle_after=settings.idle_minutes * 60)
        self.outbox = Outbox(data_folder())
        self.tracker.restore(self.outbox.load())        # time saved before a crash/shutdown
        self.cloud: dict = {}
        self.store = None
        self.quitting = False
        self.pause_until: datetime | None = None
        self.notified: dict[str, date] = {}
        self.sync_ok: bool | None = None
        self.sync_text = ""
        self._ticks = 0
        self._sync_lock = threading.Lock()
        self.bridge = Bridge()
        self.bridge.synced.connect(self._on_synced)
        self.bridge.tested.connect(self._on_tested)

        self.setWindowTitle("Trail")
        self.setWindowIcon(icons.logo_icon())
        self.resize(1260, 820)
        self.setMinimumSize(1120, 700)

        # ---- pages
        self.pages = {
            "dashboard": DashboardPage(),
            "activity": ActivityPage(),
            "apps": AppsPage(),
            "settings": SettingsPage(self._autostart_on(), str(data_folder())),
        }
        p = self.pages
        p["dashboard"].go_to.connect(self.go_to)
        p["apps"].add_requested.connect(self.add_apps)
        p["apps"].edit_requested.connect(self.edit_app)
        p["apps"].remove_requested.connect(self.remove_app)
        p["apps"].enabled_changed.connect(self.set_app_enabled)
        p["apps"].quick_add.connect(self.quick_add)
        s = p["settings"]
        s.changed.connect(self.apply_settings)
        s.autostart_changed.connect(self.set_autostart)
        s.connect_requested.connect(self.connect_database)
        s.test_requested.connect(self.test_database)
        s.export_requested.connect(self.export_csv)
        s.open_folder_requested.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_folder()))))
        s.load(self.settings)

        self._build_ui()
        self._build_tray()
        self._apply_database()
        self.go_to("dashboard")

        self.sample_timer = QTimer(self, interval=config.SAMPLE_SECONDS * 1000)
        self.sample_timer.timeout.connect(self._on_sample)
        self.sample_timer.start()
        self.sync_timer = QTimer(self, interval=config.SYNC_MINUTES * 60 * 1000)
        self.sync_timer.timeout.connect(self.sync)
        self.sync_timer.start()
        self.sync()

    # ================================================================ layout
    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        right = QVBoxLayout()
        right.setSpacing(0)
        right.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        for page in self.pages.values():
            self.stack.addWidget(page)
        right.addWidget(self.stack, 1)
        body.addLayout(right, 1)
        outer.addLayout(body, 1)
        outer.addWidget(self._build_statusbar())
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(220)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 18, 14, 16)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        logo = label()
        logo.setPixmap(icons.logo_pixmap(64).scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(logo)
        brand.addSpacing(4)
        brand.addWidget(label("Trail", "Brand"))
        brand.addStretch()
        lay.addLayout(brand)
        lay.addSpacing(20)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, text, ic in (("dashboard", "Dashboard", "dashboard"),
                              ("activity", "Activity", "activity"),
                              ("apps", "Tracked apps", "apps"),
                              ("settings", "Settings", "settings")):
            b = QPushButton(f"   {text}")
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setIcon(nav_icon(ic))
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.go_to(k))
            self.nav.addButton(b)
            self.nav_buttons[key] = b
            lay.addWidget(b)
        lay.addStretch()

        goal_box = QFrame()
        goal_box.setObjectName("Card")
        gl = QVBoxLayout(goal_box)
        gl.setContentsMargins(14, 12, 14, 14)
        gl.setSpacing(6)
        gl.addWidget(label("TODAY'S GOAL", "CardTitle"))
        self.side_goal_text = label("", None)
        gl.addWidget(self.side_goal_text)
        self.side_goal = GoalLine()
        gl.addWidget(self.side_goal)
        self.side_streak = label("", "Faint")
        gl.addWidget(self.side_streak)
        lay.addWidget(goal_box)
        return side

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(76)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(28, 12, 22, 12)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.page_title = label("", "PageTitle")
        self.page_sub = label("", "Muted")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_sub)
        lay.addLayout(titles)
        lay.addStretch()

        self.state_pill = Pill()
        lay.addWidget(self.state_pill, 0, Qt.AlignVCenter)
        lay.addSpacing(8)

        self.pause_menu = QMenu(self)
        for text, minutes in (("Pause for 30 minutes", 30), ("Pause for 1 hour", 60),
                              ("Pause for 2 hours", 120), ("Pause until tomorrow", -1),
                              ("Pause until I resume", 0)):
            self.pause_menu.addAction(text, lambda m=minutes: self.pause(m))
        self.btn_pause = QPushButton("  Pause")
        self.btn_pause.setIcon(icons.icon("pause", theme.TEXT, 14))
        self.btn_pause.setMenu(self.pause_menu)
        self.btn_resume = QPushButton("  Resume tracking")
        self.btn_resume.setObjectName("Primary")
        self.btn_resume.setIcon(icons.icon("play", "white", 14))
        self.btn_resume.clicked.connect(self.resume)
        self.btn_resume.hide()
        sync_btn = QPushButton("  Sync now")
        sync_btn.setIcon(icons.icon("sync", theme.TEXT, 15))
        sync_btn.clicked.connect(self.sync)
        for b in (self.btn_pause, self.btn_resume, sync_btn):
            lay.addWidget(b)
        return bar

    def _build_statusbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(7)
        self.dot_track = Dot()
        self.lbl_track = label("")
        self.dot_cloud = Dot()
        self.lbl_cloud = label("")
        lay.addWidget(self.dot_track)
        lay.addWidget(self.lbl_track)
        lay.addStretch()
        lay.addWidget(self.dot_cloud)
        lay.addWidget(self.lbl_cloud)
        lay.addSpacing(10)
        self.lbl_device = label("")
        lay.addWidget(self.lbl_device)
        return bar

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(icons.logo_icon(), self)
        menu = QMenu()
        menu.addAction("Open Trail", self.show_window)
        menu.addSeparator()
        tray_pause = menu.addMenu("Pause tracking")
        for a in self.pause_menu.actions():
            tray_pause.addAction(a)
        self.act_resume = menu.addAction("Resume tracking", self.resume)
        menu.addAction("Sync now", self.sync)
        menu.addSeparator()
        menu.addAction("Quit Trail", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.show_window() if r in (QSystemTrayIcon.Trigger,
                                                  QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()

    # ================================================================ navigation
    def go_to(self, key: str) -> None:
        if key.startswith("day:"):
            self.go_to("activity")
            self.pages["activity"].show_day(date.fromisoformat(key[4:]))
            return
        page = self.pages[key]
        self.current = key
        self.stack.setCurrentWidget(page)
        self.nav_buttons[key].setChecked(True)
        self.page_title.setText(page.title)
        self.page_sub.setText(page.subtitle)
        self.refresh()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ================================================================ view model
    def view(self) -> View:
        data = merge(self.cloud, self.tracker.snapshot())
        return View(data=data, days=by_day(data), today=date.today(), settings=self.settings,
                    current_app=self.tracker.current_app, counting=self.tracker.is_productive,
                    paused=self.is_paused(), recent=self.tracker.recent_apps(),
                    connected=bool(self.settings.database_url))

    def refresh(self) -> None:
        v = self.view()
        self.pages[getattr(self, "current", "dashboard")].refresh(v)
        self._refresh_chrome(v)

    def _refresh_chrome(self, v: View) -> None:
        today = v.days.get(v.today, 0)
        goal = self.settings.daily_goal_minutes * 60
        self.side_goal_text.setText(f"{fmt_duration(today)} <span style='color:{theme.MUTED}'>"
                                    f"of {fmt_duration(goal, short=True)}</span>")
        self.side_goal.set(today / goal if goal else 0)
        streak = current_streak(v.days, v.today, self.settings.streak_minutes)
        self.side_streak.setText(f"🔥 {streak}-day streak" if streak else "Start a streak today")

        name = v.label(v.current_app) if v.current_app else "—"
        if v.paused:
            until = ("until you resume" if self.pause_until == datetime.max
                     else f"until {self.pause_until:%H:%M}" if self.pause_until.date() == v.today
                     else "until tomorrow")
            self.state_pill.set(f"Paused {until}", theme.WARNING)
            self.dot_track.set_color(theme.WARNING)
            self.lbl_track.setText(f"Tracking paused {until}")
        elif v.counting:
            self.state_pill.set("● Counting", theme.SUCCESS)
            self.dot_track.set_color(theme.SUCCESS)
            self.lbl_track.setText(f"Counting deep work · {name}")
        else:
            idle = v.current_app in self.settings.rules()
            self.state_pill.set("Idle" if idle else "Not counting", theme.MUTED)
            self.dot_track.set_color(theme.FAINT)
            self.lbl_track.setText(f"Not counting · {name}" + (" (idle)" if idle else ""))
        self.btn_pause.setVisible(not v.paused)
        self.btn_resume.setVisible(v.paused)
        self.act_resume.setVisible(v.paused)

        if not self.settings.database_url:
            self.dot_cloud.set_color(theme.WARNING)
            self.lbl_cloud.setText("Not connected · time is kept on this PC until you connect")
        else:
            self.dot_cloud.set_color({True: theme.SUCCESS, False: theme.DANGER}.get(self.sync_ok, theme.FAINT))
            self.lbl_cloud.setText(self.sync_text or "Connecting…")
        self.lbl_device.setText(f"·   {self.settings.device_name}   ·   v{__version__}")
        self.tray.setToolTip(f"Trail · {fmt_duration(today)} today"
                             + (" (paused)" if v.paused else ""))
        self.tray.setIcon(icons.logo_icon(muted=v.paused))

    # ================================================================ tracking
    def is_paused(self) -> bool:
        return self.pause_until is not None and datetime.now() < self.pause_until

    def pause(self, minutes: int) -> None:
        now = datetime.now()
        if minutes == 0:
            self.pause_until = datetime.max
        elif minutes < 0:
            self.pause_until = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        else:
            self.pause_until = now + timedelta(minutes=minutes)
        self.tracker.paused = True
        self.refresh()

    def resume(self) -> None:
        self.pause_until = None
        self.tracker.paused = False
        self.refresh()

    def _on_sample(self) -> None:
        if self.pause_until is not None and not self.is_paused():
            self.resume()
        self.tracker.paused = self.is_paused()
        self.tracker.tick()
        self._ticks += 1
        if self._ticks % 12 == 0:              # about once a minute
            self._save_outbox()
            self._check_notifications()
        self.refresh()

    def _save_outbox(self) -> None:
        try:
            self.outbox.save(self.tracker.snapshot())
        except OSError as exc:
            log.warning("outbox save failed: %s", exc)

    def _check_notifications(self) -> None:
        v = self.view()
        s, t = self.settings, v.today
        today = v.days.get(t, 0)
        if s.notify_goal and today >= s.daily_goal_minutes * 60 and self.notified.get("goal") != t:
            self.notified["goal"] = t
            self.notify("Daily goal reached 🎯",
                        f"{fmt_duration(today)} of deep work today. Another step on your trail.")
        streak_before = current_streak(v.days, t - timedelta(days=1), s.streak_minutes)
        if (s.notify_streak and datetime.now().hour >= s.reminder_hour and streak_before > 0
                and today < s.streak_minutes * 60 and self.notified.get("streak") != t):
            self.notified["streak"] = t
            self.notify(f"Keep your {streak_before}-day streak alive",
                        f"{s.streak_minutes} minutes of deep work today keeps it going.")

    def notify(self, title: str, text: str) -> None:
        self.tray.showMessage(title, text, icons.logo_icon(), 6000)

    # ================================================================ apps
    def _save(self, new: settings_mod.Settings) -> None:
        self.settings = new
        settings_mod.save(new)
        self.tracker.set_rules(new.rules(), idle_after=new.idle_minutes * 60)
        self.refresh()

    def apply_settings(self, new: settings_mod.Settings) -> None:
        self._save(new)

    def add_apps(self) -> None:
        dlg = AddAppsDialog({a.process for a in self.settings.apps}, self.tracker.recent_apps(), self)
        if dlg.exec():
            chosen = dlg.chosen()
            if chosen:
                apps = self.settings.apps + [a for a in chosen
                                             if a.process not in self.settings.rules()]
                self._save(replace(self.settings, apps=sorted(apps, key=lambda a: a.label.lower())))

    def quick_add(self, proc: str) -> None:
        from .activity import KNOWN_LABELS
        from .settings import TrackedApp
        if proc not in self.settings.rules():
            apps = self.settings.apps + [TrackedApp(proc, KNOWN_LABELS.get(proc, proc))]
            self._save(replace(self.settings, apps=sorted(apps, key=lambda a: a.label.lower())))

    def edit_app(self, proc: str) -> None:
        app = self.settings.rules().get(proc)
        if not app:
            return
        dlg = EditAppDialog(app, self)
        if dlg.exec():
            new = dlg.result_app()
            self._save(replace(self.settings, apps=[new if a.process == proc else a
                                                    for a in self.settings.apps]))

    def remove_app(self, proc: str) -> None:
        app = self.settings.rules().get(proc)
        if not app:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Stop tracking")
        box.setText(f"Stop tracking {app.label}?")
        box.setInformativeText("Time already recorded stays in your history. "
                               "Tip: use the switch to pause an app without removing it.")
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        box.button(QMessageBox.Yes).setText("Stop tracking")
        if box.exec() == QMessageBox.Yes:
            self._save(replace(self.settings, apps=[a for a in self.settings.apps if a.process != proc]))

    def set_app_enabled(self, proc: str, on: bool) -> None:
        self._save(replace(self.settings, apps=[replace(a, enabled=on) if a.process == proc else a
                                                for a in self.settings.apps]))

    # ================================================================ settings actions
    @staticmethod
    def _autostart_on() -> bool:
        try:
            return settings_mod.autostart_enabled()
        except OSError:
            return False

    def set_autostart(self, on: bool) -> None:
        try:
            settings_mod.set_autostart(on)
        except OSError as exc:
            log.warning("autostart failed: %s", exc)
            QMessageBox.warning(self, "Trail", f"Couldn't change the startup setting:\n{exc}")

    def connect_database(self, url: str, device: str) -> None:
        if self.settings.database_url and url != self.settings.database_url:
            self._sync_blocking()          # send pending time to the old database first
        self.cloud = {}
        self._save(replace(self.settings, database_url=url,
                           device_name=device or config.DEVICE_NAME))
        self._apply_database()
        self.pages["settings"].set_cloud_status("Connecting…")
        self.sync()

    def test_database(self, url: str) -> None:
        if not url:
            self.pages["settings"].set_cloud_status("Paste a connection string first.", theme.WARNING)
            return
        self.pages["settings"].set_cloud_status("Testing…")

        def work():
            try:
                from .storage import CloudStore
                CloudStore(url).init_schema()
                self.bridge.tested.emit(None)
            except Exception as exc:
                msg = str(exc).strip().splitlines()[0][:180] if str(exc).strip() else type(exc).__name__
                self.bridge.tested.emit(msg)

        threading.Thread(target=work, daemon=True).start()

    def _on_tested(self, err) -> None:
        if err is None:
            self.pages["settings"].set_cloud_status("✓ Connection works. Click Save & connect.", theme.SUCCESS)
        else:
            self.pages["settings"].set_cloud_status(f"✗ {err}", theme.DANGER)

    def export_csv(self) -> None:
        default = str(Path.home() / f"trail-export-{date.today():%Y-%m-%d}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export your Trail data", default, "CSV (*.csv)")
        if not path:
            return
        v = self.view()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "app", "program", "minutes"])
            for (d, app), secs in sorted(v.data.items()):
                w.writerow([d.isoformat(), v.label(app), app, round(secs / 60, 1)])
        self.notify("Export complete", f"Saved {Path(path).name}")

    # ================================================================ cloud sync
    def _apply_database(self) -> None:
        if not self.settings.database_url:
            self.store = None
            return
        from .storage import CloudStore
        self.store = CloudStore(self.settings.database_url, device=self.settings.device_name)
        self.sync_ok, self.sync_text = None, "Connecting…"

    def _sync_blocking(self) -> None:
        store = self.store
        if store is None or not self._sync_lock.acquire(blocking=False):
            return
        batch = self.tracker.drain()
        try:
            if not store.ready:
                store.init_schema()
            store.push(batch)
            data = store.daily_app_totals()
            self.bridge.synced.emit(data, f"Synced {datetime.now():%H:%M}")
        except Exception as exc:     # offline, database asleep, wrong link…
            self.tracker.restore(batch)
            log.warning("sync failed: %s", exc)
            self.bridge.synced.emit(None, "Offline · will retry, nothing is lost")
        finally:
            self._sync_lock.release()
            self._save_outbox()

    def sync(self) -> None:
        threading.Thread(target=self._sync_blocking, daemon=True).start()

    def _on_synced(self, data, text: str) -> None:
        self.sync_ok = data is not None
        self.sync_text = text
        if data is not None:
            self.cloud = data
            self.pages["settings"].set_cloud_status(f"✓ Connected · last sync {datetime.now():%H:%M}",
                                                    theme.SUCCESS)
        else:
            self.pages["settings"].set_cloud_status("✗ Can't reach the database right now. "
                                                    "Check the link and your internet.", theme.DANGER)
        self.refresh()

    # ================================================================ lifecycle
    def closeEvent(self, event) -> None:
        if self.quitting:
            event.accept()
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.quit_app()
            return
        event.ignore()
        self.hide()
        if not getattr(self, "_told_tray", False):
            self._told_tray = True
            self.notify("Trail is still tracking",
                        "It keeps running in the system tray. Right-click the icon to quit.")

    def quit_app(self) -> None:
        self.quitting = True
        self.sample_timer.stop()
        self._sync_blocking()
        self._save_outbox()
        self.tray.hide()
        QApplication.quit()


# ==================================================================== startup
def _already_running(name: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Trail")
    app.setApplicationDisplayName("Trail")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(theme.QSS)
    app.setWindowIcon(icons.logo_icon())

    folder = data_folder()
    folder.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=folder / "trail.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    # Only one copy may run, otherwise time would be counted twice.
    name = f"trail-{getpass.getuser()}"
    if _already_running(name):
        return
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)

    s = settings_mod.load()
    if s.first_run:
        settings_mod.save(s)            # remembers the default app list
    win = MainWindow(s)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.show_window()))
    if "--minimized" not in sys.argv:
        win.show()
    log.info("Trail %s started", __version__)
    sys.exit(app.exec())
