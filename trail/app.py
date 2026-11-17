"""Trail main window: sidebar navigation, pages, top bar, status bar and tray."""
from __future__ import annotations

import csv
import getpass
import logging
import os
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

from . import __version__, config, icons, theme, updater
from . import settings as settings_mod
from .auth import AuthError, CallbackServer, SupabaseAuth, TokenStore
from .cloud import CloudClient, CloudError
from .dialogs import AddAppsDialog, EditAppDialog
from .outbox import Outbox
from .pages import ActivityPage, AppsPage, DashboardPage, SettingsPage, View
from .signin import SignInScreen, open_url
from .stats import by_day, current_streak, fmt_duration, merge
from .tracker import Tracker
from .widgets import Dot, Pill, label

log = logging.getLogger("trail")


def data_folder() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))


class Bridge(QObject):
    """Carries results from background threads to the UI thread."""
    synced = Signal(object, str)        # cloud data (or None), status text
    email_sent = Signal(str)
    auth_error = Signal(str)
    signed_in = Signal(object)          # Session
    callback = Signal(object, object)   # code, error  (from the browser)
    done = Signal(str, object)          # task name, error text or None
    update_found = Signal(object)       # updater.Release
    update_progress = Signal(int)
    update_ready = Signal(object)       # installer path
    update_failed = Signal(str)


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
        self.auth = SupabaseAuth(TokenStore(data_folder()))
        self.cloud: dict = {}
        self.store = None
        self.quitting = False
        self.pause_until: datetime | None = None
        self.notified: dict[str, date] = {}
        self.sync_ok: bool | None = None
        self.sync_text = ""
        self._ticks = 0
        self._sync_lock = threading.Lock()
        self.release: updater.Release | None = None
        self._update_notified: str | None = None
        self.bridge = Bridge()
        self.bridge.synced.connect(self._on_synced)
        self.bridge.email_sent.connect(self._on_email_sent)
        self.bridge.auth_error.connect(self._on_auth_error)
        self.bridge.signed_in.connect(self._on_signed_in)
        self.bridge.callback.connect(self._on_callback)
        self.bridge.done.connect(self._on_task_done)
        self.bridge.update_found.connect(self._on_update_found)
        self.bridge.update_progress.connect(
            lambda pct: self.btn_update.setText(f"  Downloading… {pct}%"))
        self.bridge.update_ready.connect(self._install_update)
        self.bridge.update_failed.connect(self._on_update_failed)
        self.callback_server = CallbackServer(lambda code, err: self.bridge.callback.emit(code, err))

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
        s.sign_in_requested.connect(lambda: self.show_signin(inside_app=True))
        s.sign_out_requested.connect(self.sign_out)
        s.delete_requested.connect(self.delete_cloud_data)
        s.device_changed.connect(self.set_device_name)
        s.import_requested.connect(self.import_legacy)
        s.check_updates_requested.connect(lambda: self.check_updates(manual=True))
        s.export_requested.connect(self.export_csv)
        s.open_folder_requested.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_folder()))))
        s.load(self.settings)

        self._build_ui()
        self._build_tray()
        self._apply_account()
        self.go_to("dashboard")
        if not self.auth.signed_in and not self.settings.offline_mode:
            self.show_signin(inside_app=False)

        self.sample_timer = QTimer(self, interval=config.SAMPLE_SECONDS * 1000)
        self.sample_timer.timeout.connect(self._on_sample)
        self.sample_timer.start()
        self.sync_timer = QTimer(self, interval=config.SYNC_MINUTES * 60 * 1000)
        self.sync_timer.timeout.connect(self.sync)
        self.sync_timer.start()
        self.sync()

        self.update_timer = QTimer(self, interval=config.UPDATE_CHECK_HOURS * 3600 * 1000)
        self.update_timer.timeout.connect(self.check_updates)
        self.update_timer.start()
        QTimer.singleShot(15_000, self.check_updates)

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

        self.signin = SignInScreen()
        self.signin.google.connect(self.sign_in_google)
        self.signin.send_email.connect(self.sign_in_email)
        self.signin.verify_code.connect(self.verify_email_code)
        self.signin.skip.connect(self.continue_offline)
        self.signin.back.connect(self.show_shell)
        self.root_stack = QStackedWidget()
        self.root_stack.addWidget(self.signin)
        self.root_stack.addWidget(root)
        self.shell = root
        self.root_stack.setCurrentWidget(root)
        self.setCentralWidget(self.root_stack)

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
        self.btn_update = QPushButton()
        self.btn_update.setObjectName("Update")
        self.btn_update.setIcon(icons.icon("download", "#7ee2a0", 15))
        self.btn_update.clicked.connect(self.offer_update)
        self.btn_update.hide()
        lay.addWidget(self.btn_update)
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
        if key == "signin":
            self.show_signin(inside_app=True)
            return
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

    def show_signin(self, inside_app: bool) -> None:
        self.signin.reset()
        self.signin.set_mode(inside_app)
        self.root_stack.setCurrentWidget(self.signin)
        self.show_window()

    def show_shell(self) -> None:
        self.callback_server.stop()
        self.root_stack.setCurrentWidget(self.shell)
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
                    connected=self.auth.signed_in)

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

        if not self.auth.signed_in:
            self.dot_cloud.set_color(theme.WARNING)
            self.lbl_cloud.setText("Not signed in · time is kept on this PC")
        else:
            self.dot_cloud.set_color({True: theme.SUCCESS, False: theme.DANGER}.get(self.sync_ok, theme.FAINT))
            self.lbl_cloud.setText(f"{self.auth.session.email}   ·   {self.sync_text or 'Connecting…'}")
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

    # ================================================================ account
    def _apply_account(self) -> None:
        if self.auth.signed_in:
            self.store = CloudClient(self.auth, self.settings.device_name)
            self.sync_ok, self.sync_text = None, "Connecting…"
            self.pages["settings"].set_account(self.auth.session.email, "Signed in · syncing every 10 minutes")
        else:
            self.store = None
            self.pages["settings"].set_account(None)

    def _bg(self, fn, *args) -> None:
        threading.Thread(target=fn, args=args, daemon=True).start()

    def sign_in_google(self) -> None:
        try:
            self.callback_server.start()
        except AuthError as exc:
            self.signin.show_error(str(exc))
            return
        open_url(self.auth.oauth_url("google"))

    def sign_in_email(self, email: str) -> None:
        try:
            self.callback_server.start()       # the email link comes back here
        except AuthError as exc:
            self.signin.show_error(str(exc))
            return

        def work():
            try:
                self.auth.send_email(email)
                self.bridge.email_sent.emit(email)
            except AuthError as exc:
                self.bridge.auth_error.emit(str(exc))
        self._bg(work)

    def verify_email_code(self, email: str, code: str) -> None:
        def work():
            try:
                self.bridge.signed_in.emit(self.auth.verify_code(email, code))
            except AuthError as exc:
                self.bridge.auth_error.emit(str(exc))
        self._bg(work)

    def _on_callback(self, code, err) -> None:
        if err or not code:
            self.signin.show_error(f"Sign-in didn't finish: {err}")
            return
        self.signin.set_busy(True, "Finishing sign-in…")

        def work():
            try:
                self.bridge.signed_in.emit(self.auth.exchange(code))
            except AuthError as exc:
                self.bridge.auth_error.emit(str(exc))
        self._bg(work)

    def _on_email_sent(self, email: str) -> None:
        self.signin.show_sent(email)

    def _on_auth_error(self, msg: str) -> None:
        self.signin.show_error(msg)

    def _on_signed_in(self, session) -> None:
        self.callback_server.stop()
        self.cloud = {}
        self._save(replace(self.settings, offline_mode=False))
        self._apply_account()
        self.show_shell()
        self.show_window()
        self.notify("Signed in to Trail", f"Your trail now syncs to {session.email}.")
        self.sync()

    def continue_offline(self) -> None:
        self._save(replace(self.settings, offline_mode=True))
        self.show_shell()

    def sign_out(self) -> None:
        if QMessageBox.question(self, "Sign out", "Sign out of Trail on this computer?\n\n"
                                "Your saved history stays in your account.") != QMessageBox.Yes:
            return
        self._sync_blocking()                 # send the last minutes first
        self.auth.sign_out()
        self.cloud = {}
        self._apply_account()
        self.show_signin(inside_app=False)

    def set_device_name(self, name: str) -> None:
        name = name or config.DEVICE_NAME
        if name != self.settings.device_name:
            self._save(replace(self.settings, device_name=name))
            if isinstance(self.store, CloudClient):
                self.store.device = name

    def delete_cloud_data(self) -> None:
        if not isinstance(self.store, CloudClient):
            return
        box = QMessageBox(self)
        box.setWindowTitle("Delete cloud data")
        box.setText("Delete all your Trail history from the cloud?")
        box.setInformativeText("This removes every day of tracked time from your account, on all "
                               "your computers. It can't be undone. Export to CSV first if you want a copy.")
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        box.button(QMessageBox.Yes).setText("Delete everything")
        if box.exec() != QMessageBox.Yes:
            return
        store = self.store

        def work():
            try:
                store.delete_my_data()
                self.bridge.done.emit("delete", None)
            except CloudError as exc:
                self.bridge.done.emit("delete", str(exc))
        self._bg(work)

    def import_legacy(self, url: str) -> None:
        if not isinstance(self.store, CloudClient) or not url:
            return
        if self.settings.legacy_imported:
            QMessageBox.information(self, "Trail", "Your earlier history was already imported.")
            return
        self.pages["settings"].set_account(self.auth.session.email, "Importing earlier history…")
        store = self.store

        def work():
            try:
                from .storage import CloudStore
                old = CloudStore(url).daily_app_totals(days=36500)
                store.push(old)
                self.bridge.done.emit("import", None)
            except Exception as exc:
                self.bridge.done.emit("import", str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__)
        self._bg(work)

    def _on_task_done(self, task: str, err) -> None:
        email = self.auth.session.email if self.auth.session else None
        if task == "delete":
            if err:
                self.pages["settings"].set_account(email, f"Couldn't delete: {err}", theme.DANGER)
            else:
                self.cloud = {}
                self.pages["settings"].set_account(email, "All cloud data deleted.", theme.SUCCESS)
        elif task == "import":
            if err:
                self.pages["settings"].set_account(email, f"Import failed: {err}", theme.DANGER)
            else:
                self._save(replace(self.settings, legacy_imported=True, database_url=""))
                self.pages["settings"].set_account(email, "✓ Earlier history imported.", theme.SUCCESS)
                self.sync()
        self.refresh()

    # ================================================================ updates
    def check_updates(self, manual: bool = False) -> None:
        api = os.getenv("TRAIL_GITHUB_API", "https://api.github.com")

        def work():
            try:
                rel = updater.check(api=api)
                if rel:
                    self.bridge.update_found.emit(rel)
                elif manual:
                    self.bridge.update_failed.emit(f"You're on the latest version ({__version__}).")
            except Exception as exc:
                log.info("update check failed: %s", exc)
                if manual:
                    self.bridge.update_failed.emit("Couldn't check for updates. Are you online?")
        self._bg(work)

    def _on_update_found(self, rel) -> None:
        self.release = rel
        self.btn_update.setText(f"  Update to {rel.version}")
        self.btn_update.setEnabled(True)
        self.btn_update.show()
        self.pages["settings"].set_update_status(f"Version {rel.version} is available.")
        if self._update_notified != rel.version:
            self._update_notified = rel.version
            self.notify("A Trail update is ready", f"Version {rel.version} is available. "
                                                   "Click Update in the top bar to install.")

    def _on_update_failed(self, msg: str) -> None:
        self.pages["settings"].set_update_status(msg)
        if self.release:
            self.btn_update.setEnabled(True)
            self.btn_update.setText(f"  Update to {self.release.version}")

    def offer_update(self) -> None:
        rel = self.release
        if not rel:
            return
        if not updater.can_self_update():
            open_url(rel.page or config.WEBSITE_URL)
            return
        box = QMessageBox(self)
        box.setWindowTitle("Update Trail")
        box.setText(f"Trail {rel.version} is ready to install.")
        notes = rel.notes[:800] + ("…" if len(rel.notes) > 800 else "")
        box.setInformativeText((notes + "\n\n" if notes else "") +
                               "Trail will close for a few seconds and reopen by itself. "
                               "Your settings and history are kept.")
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        box.button(QMessageBox.Yes).setText("Install && restart")
        box.button(QMessageBox.Cancel).setText("Later")
        if box.exec() != QMessageBox.Yes:
            return
        self.btn_update.setEnabled(False)
        self.btn_update.setText("  Downloading…")

        def work():
            try:
                path = updater.download(rel, self.bridge.update_progress.emit)
                self.bridge.update_ready.emit(path)
            except Exception as exc:
                log.warning("update download failed: %s", exc)
                self.bridge.update_failed.emit("Download failed. Please try again.")
        self._bg(work)

    def _install_update(self, path) -> None:
        self.btn_update.setText("  Installing…")
        self.quitting = True
        self.sample_timer.stop()
        self._sync_blocking()
        self._save_outbox()
        try:
            updater.launch_installer(path)
        except OSError as exc:
            self.quitting = False
            self.sample_timer.start()
            self._on_update_failed(f"Couldn't start the installer: {exc}")
            return
        self.tray.hide()
        QApplication.quit()

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
        except Exception as exc:     # offline, signed out elsewhere, server problem…
            self.tracker.restore(batch)
            log.warning("sync failed: %s", exc)
            msg = str(exc)
            text = ("Offline · will retry, nothing is lost" if msg in ("offline", "") or "internet" in msg
                    else msg)
            self.bridge.synced.emit(None, text)
        finally:
            self._sync_lock.release()
            self._save_outbox()

    def sync(self) -> None:
        threading.Thread(target=self._sync_blocking, daemon=True).start()

    def _on_synced(self, data, text: str) -> None:
        self.sync_ok = data is not None
        self.sync_text = text
        if not self.auth.signed_in:          # the session expired or was revoked
            if isinstance(self.store, CloudClient):
                self._apply_account()
                self.notify("Please sign in again", "Your Trail sign-in expired. Your time is "
                                                    "kept on this PC until you sign in.")
            self.refresh()
            return
        email = self.auth.session.email
        if data is not None:
            self.cloud = data
            self.pages["settings"].set_account(email, f"✓ Synced at {datetime.now():%H:%M}", theme.SUCCESS)
        else:
            self.pages["settings"].set_account(email, text, theme.DANGER)
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
        self.callback_server.stop()
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
    if "--updated" in sys.argv:
        QTimer.singleShot(1500, lambda: win.notify("Trail was updated",
                                                   f"You're now on version {__version__}."))
    log.info("Trail %s started", __version__)
    sys.exit(app.exec())
