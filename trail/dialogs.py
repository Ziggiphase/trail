"""Dialogs: add apps to track, and edit one tracked app."""
from __future__ import annotations

import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

from . import activity, icons, theme
from .settings import TrackedApp
from .widgets import label

ROLE_PROC, ROLE_LABEL = Qt.UserRole, Qt.UserRole + 1


class _Base(QDialog):
    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 22, 24, 20)
        self.lay.setSpacing(12)
        self.lay.addWidget(label(title, "SectionTitle"))
        self.lay.addWidget(label(subtitle, "Muted", wrap=True))

    def _buttons(self, ok_text: str) -> QPushButton:
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton(ok_text)
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        ok.setAutoDefault(False)
        cancel.setAutoDefault(False)
        row.addWidget(cancel)
        row.addWidget(ok)
        self.lay.addLayout(row)
        return ok

    def keyPressEvent(self, event) -> None:
        # Enter inside a text box shouldn't close the dialog.
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and \
                not isinstance(self.focusWidget(), QPushButton):
            return
        super().keyPressEvent(event)


class AddAppsDialog(_Base):
    """Pick apps from 'open now' + 'used recently', type a name, or browse for an .exe."""

    def __init__(self, tracked: set[str], recent: list[str], parent=None):
        super().__init__("Add apps to track",
                         "Tick the apps that count as deep work. The list shows apps that are "
                         "open right now and apps you've used recently.", parent)
        self.resize(520, 560)
        self.tracked = tracked
        self.extra: dict[str, str] = {}     # typed / browsed apps

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search, or type a program name and press Enter")
        self.search.addAction(icons.icon("search"), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._add_typed)
        self.lay.addWidget(self.search)

        self.list = QListWidget()
        self.list.setIconSize(QSize(16, 16))
        self.list.setStyleSheet(f"QListWidget {{ border: 1px solid {theme.BORDER}; border-radius: 10px; padding: 4px; }}")
        self.list.itemClicked.connect(self._toggle_item)
        self.lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        browse = QPushButton("  Browse for a program…")
        browse.setIcon(icons.icon("folder"))
        browse.setAutoDefault(False)
        browse.clicked.connect(self._browse)
        refresh = QPushButton("  Refresh")
        refresh.setIcon(icons.icon("sync"))
        refresh.setAutoDefault(False)
        refresh.clicked.connect(self._populate)
        row.addWidget(browse)
        row.addWidget(refresh)
        row.addStretch()
        self.lay.addLayout(row)
        self.ok = self._buttons("Add selected")
        self._recent = recent
        self._populate()

    def _populate(self) -> None:
        checked = {self.list.item(i).data(ROLE_PROC) for i in range(self.list.count())
                   if self.list.item(i).checkState() == Qt.Checked}
        try:
            open_apps = {a.process: a.label for a in activity.open_window_apps()}
        except Exception:
            open_apps = {}
        entries: dict[str, tuple[str, str]] = {}
        for proc, lbl in self.extra.items():
            entries[proc] = (lbl, "added by you")
        for proc in self._recent:
            if proc not in activity.SELF_NAMES and proc not in entries:
                entries[proc] = (open_apps.get(proc) or activity.KNOWN_LABELS.get(proc, proc),
                                 "used recently")
        for proc, lbl in open_apps.items():
            entries.setdefault(proc, (lbl, "open now"))

        self.list.clear()
        for proc, (lbl, why) in entries.items():
            if proc in self.tracked:
                continue
            shown = lbl if lbl.lower() == proc else f"{lbl}   ({proc})"
            item = QListWidgetItem(f"{shown}      · {why}")
            item.setData(ROLE_PROC, proc)
            item.setData(ROLE_LABEL, lbl)
            # not ItemIsUserCheckable: a click anywhere on the row toggles it (see _toggle_item)
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if proc in checked or proc in self.extra else Qt.Unchecked)
            self.list.addItem(item)
        if not self.list.count():
            self.list.addItem(QListWidgetItem("No other apps found. Open the app you want, "
                                              "then click Refresh, or type its name above."))
        self._filter(self.search.text())

    def _toggle_item(self, item: QListWidgetItem) -> None:
        if item.data(ROLE_PROC):
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def _filter(self, text: str) -> None:
        t = text.lower().strip()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def _add_typed(self) -> None:
        text = self.search.text().strip()
        visible = [self.list.item(i) for i in range(self.list.count())
                   if not self.list.item(i).isHidden() and self.list.item(i).data(ROLE_PROC)]
        if len(visible) == 1:
            visible[0].setCheckState(Qt.Checked)
        elif text:
            proc = activity.clean(text)
            self.extra[proc] = activity.KNOWN_LABELS.get(proc, text)
            self._populate()
        self.search.clear()

    def _browse(self) -> None:
        filt = "Programs (*.exe)" if sys.platform == "win32" else "All files (*)"
        path, _ = QFileDialog.getOpenFileName(self, "Choose a program", "", filt)
        if path:
            self.extra[activity.clean(path)] = activity.label_for_path(path)
            self._populate()

    def chosen(self) -> list[TrackedApp]:
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(ROLE_PROC) and it.checkState() == Qt.Checked:
                out.append(TrackedApp(it.data(ROLE_PROC), it.data(ROLE_LABEL)))
        return out


class EditAppDialog(_Base):
    def __init__(self, app: TrackedApp, parent=None):
        super().__init__(f"Edit {app.label}", f"Program name: {app.process}", parent)
        self.resize(480, 300)
        self.app = app
        self.lay.addSpacing(4)
        self.lay.addWidget(label("Display name"))
        self.name = QLineEdit(app.label)
        self.lay.addWidget(self.name)
        self.lay.addSpacing(4)
        self.lay.addWidget(label("Only count when the window title contains"))
        self.kw = QLineEdit(", ".join(app.title_keywords))
        self.kw.setPlaceholderText("Leave empty to always count, e.g. JupyterLab, Colab")
        self.lay.addWidget(self.kw)
        self.lay.addWidget(label("Handy for browsers: track Chrome only while it shows a "
                                 "notebook. Separate words with commas.", "Faint", wrap=True))
        self.lay.addStretch()
        self._buttons("Save")

    def result_app(self) -> TrackedApp:
        return TrackedApp(
            process=self.app.process,
            label=self.name.text().strip() or self.app.label,
            title_keywords=[k.strip() for k in self.kw.text().split(",") if k.strip()],
            enabled=self.app.enabled,
        )
