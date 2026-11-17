"""Full-window sign-in screen: Google, email link/code, or continue offline."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLineEdit, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import config, icons, theme
from .widgets import label

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _or_divider() -> QHBoxLayout:
    left, right = QFrame(), QFrame()
    left.setObjectName("Divider")
    right.setObjectName("Divider")
    row = QHBoxLayout()
    row.addWidget(left, 1)
    row.addWidget(label("or use your email", "Faint"))
    row.addWidget(right, 1)
    return row


class SignInScreen(QWidget):
    google = Signal()
    send_email = Signal(str)
    verify_code = Signal(str, str)
    skip = Signal()
    back = Signal()              # only shown when opened from inside the app

    def __init__(self):
        super().__init__()
        self.setObjectName("Content")
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        h = QHBoxLayout()
        h.addStretch(1)

        card = QFrame()
        card.setObjectName("Card")
        card.setFixedWidth(440)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(36, 34, 36, 30)
        lay.setSpacing(12)

        logo = label()
        logo.setPixmap(icons.logo_pixmap(128).scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
        title = label("Welcome to Trail", "PageTitle")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        sub = label("Sign in so your trail is saved safely and follows you to any computer.",
                    "Muted", wrap=True)
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)
        lay.addSpacing(10)

        self.pages = QStackedWidget()
        self.pages.setStyleSheet("QStackedWidget { background: transparent; }")
        self.pages.addWidget(self._start_page())
        self.pages.addWidget(self._sent_page())
        lay.addWidget(self.pages)

        self.error = label("", None, wrap=True)
        self.error.setStyleSheet(f"color: {theme.DANGER};")
        self.error.setAlignment(Qt.AlignCenter)
        self.error.hide()
        lay.addWidget(self.error)
        self.status = label("", "Muted", wrap=True)
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()
        lay.addWidget(self.status)

        lay.addSpacing(6)
        self.btn_skip = QPushButton("Continue without an account")
        self.btn_skip.setObjectName("Link")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        self.btn_skip.clicked.connect(self.skip.emit)
        lay.addWidget(self.btn_skip, 0, Qt.AlignCenter)
        self.btn_back = QPushButton("← Back to Trail")
        self.btn_back.setObjectName("Link")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.back.emit)
        self.btn_back.hide()
        lay.addWidget(self.btn_back, 0, Qt.AlignCenter)

        legal = label(f"By continuing you agree to Trail's "
                      f"<a style='color:{theme.ACCENT_HOVER}' href='{config.PRIVACY_URL}'>privacy policy</a>.",
                      "Faint", wrap=True)
        legal.setAlignment(Qt.AlignCenter)
        legal.setOpenExternalLinks(True)
        lay.addWidget(legal)

        h.addWidget(card)
        h.addStretch(1)
        outer.addLayout(h)
        outer.addStretch(1)

    # ---------------------------------------------------------------- pages
    def _start_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.btn_google = QPushButton("  Continue with Google")
        self.btn_google.setObjectName("Google")
        self.btn_google.setCursor(Qt.PointingHandCursor)
        self.btn_google.setMinimumHeight(42)
        self.btn_google.clicked.connect(self._google)
        lay.addWidget(self.btn_google)
        lay.addLayout(_or_divider())
        self.email = QLineEdit()
        self.email.setPlaceholderText("you@example.com")
        self.email.setMinimumHeight(40)
        self.email.returnPressed.connect(self._send)
        lay.addWidget(self.email)
        self.btn_send = QPushButton("Email me a sign-in link")
        self.btn_send.setObjectName("Primary")
        self.btn_send.setMinimumHeight(40)
        self.btn_send.clicked.connect(self._send)
        lay.addWidget(self.btn_send)
        return w

    def _sent_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.sent_text = label("", None, wrap=True)
        self.sent_text.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.sent_text)
        hint = label("Open the email on <b>this computer</b> and click the link. "
                     "Trail finishes signing you in automatically.", "Muted", wrap=True)
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)
        lay.addSpacing(4)
        lay.addWidget(label("Got a 6-digit code instead? Enter it here:", "Faint"))
        row = QHBoxLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText("123456")
        self.code.setMaxLength(10)
        self.code.setMinimumHeight(38)
        self.code.returnPressed.connect(self._verify)
        self.btn_verify = QPushButton("Verify")
        self.btn_verify.setObjectName("Primary")
        self.btn_verify.setMinimumHeight(38)
        self.btn_verify.clicked.connect(self._verify)
        row.addWidget(self.code, 1)
        row.addWidget(self.btn_verify)
        lay.addLayout(row)
        again = QHBoxLayout()
        b1 = QPushButton("Use a different email")
        b1.setObjectName("Link")
        b1.clicked.connect(self.reset)
        b2 = QPushButton("Send again")
        b2.setObjectName("Link")
        b2.clicked.connect(self._send)
        again.addStretch()
        again.addWidget(b1)
        again.addWidget(label("·", "Faint"))
        again.addWidget(b2)
        again.addStretch()
        lay.addLayout(again)
        return w

    # ---------------------------------------------------------------- actions
    def _google(self) -> None:
        self.show_error("")
        self.set_status("Finish signing in in your browser…")
        self.google.emit()

    def _send(self) -> None:
        email = self.email.text().strip()
        if not EMAIL_RE.match(email):
            self.show_error("Please enter a valid email address.")
            return
        self.show_error("")
        self.set_busy(True, "Sending…")
        self.send_email.emit(email)

    def _verify(self) -> None:
        code = self.code.text().strip()
        if not code.isdigit():
            self.show_error("The code is the number from the email.")
            return
        self.show_error("")
        self.set_busy(True, "Checking…")
        self.verify_code.emit(self.email.text().strip(), code)

    # ---------------------------------------------------------------- called by the app
    def reset(self) -> None:
        self.pages.setCurrentIndex(0)
        self.code.clear()
        self.show_error("")
        self.set_status("")
        self.set_busy(False)

    def show_sent(self, email: str) -> None:
        self.set_busy(False)
        self.sent_text.setText(f"<b>Check your inbox</b><br>We sent a sign-in link to {email}")
        self.pages.setCurrentIndex(1)
        self.set_status("Waiting for you to click the link…")

    def set_busy(self, busy: bool, text: str = "") -> None:
        for b in (self.btn_google, self.btn_send, self.btn_verify):
            b.setEnabled(not busy)
        if text or not busy:
            self.set_status(text)

    def set_status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))
        if text:
            self.set_busy(False)
            self.set_status("")

    def set_mode(self, inside_app: bool) -> None:
        """First launch shows 'Continue without an account'; later, a Back button."""
        self.btn_skip.setVisible(not inside_app)
        self.btn_back.setVisible(inside_app)


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))
