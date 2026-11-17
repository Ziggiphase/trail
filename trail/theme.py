"""Colours, fonts and the Qt stylesheet for Trail's dark desktop look."""

# Surfaces
BG = "#0f1318"          # window background
SIDEBAR = "#141920"
SURFACE = "#19202a"     # cards
SURFACE_2 = "#202834"   # inputs, hover
BORDER = "#28313e"
BORDER_STRONG = "#36404f"

# Text
TEXT = "#e7ebf1"
MUTED = "#8e99aa"
FAINT = "#5d6878"

# Accents
ACCENT = "#3d8bfd"
ACCENT_HOVER = "#5a9dff"
ACCENT_SOFT = "#1a2d4a"
SUCCESS = "#3fb950"
WARNING = "#e3a33b"
DANGER = "#f2555a"

# Heatmap scale (empty → most)
HEAT = ["#1d242e", "#0e4429", "#006d32", "#26a641", "#39d353"]

FONT_FAMILY = "Segoe UI Variable Text, Segoe UI, Inter, Helvetica Neue, Arial"

QSS = f"""
* {{ font-family: {FONT_FAMILY}; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog, QMessageBox, QWidget#Content {{ background: {BG}; }}
QStackedWidget, QScrollArea > QWidget > QWidget {{ background: {BG}; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Faint {{ color: {FAINT}; font-size: 12px; }}
QLabel#PageTitle {{ font-size: 22px; font-weight: 600; }}
QLabel#SectionTitle {{ font-size: 16px; font-weight: 600; color: {TEXT}; }}
QLabel#CardTitle {{ color: {MUTED}; font-size: 12px; font-weight: 600;
                    letter-spacing: 0.4px; }}
QLabel#BigNumber {{ font-size: 28px; font-weight: 600; }}
QLabel#Brand {{ font-size: 17px; font-weight: 700; }}

/* ---- sidebar ---- */
QFrame#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QPushButton#Nav {{ text-align: left; padding: 9px 12px; border: none; border-radius: 8px;
                   color: {MUTED}; font-size: 13.5px; background: transparent; }}
QPushButton#Nav:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#Nav:checked {{ background: {ACCENT_SOFT}; color: {TEXT}; font-weight: 600; }}

/* ---- top bar & status bar ---- */
QFrame#TopBar {{ background: {BG}; border-bottom: 1px solid {BORDER}; }}
QFrame#StatusBar {{ background: {SIDEBAR}; border-top: 1px solid {BORDER}; }}
QFrame#StatusBar QLabel {{ color: {MUTED}; font-size: 12px; }}

/* ---- cards ---- */
QFrame#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#Divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; }}

/* ---- buttons ---- */
QPushButton {{ background: {SURFACE_2}; border: 1px solid {BORDER_STRONG}; border-radius: 7px;
               padding: 7px 14px; }}
QPushButton:hover {{ background: #2a3442; }}
QPushButton:pressed {{ background: #232c38; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {BORDER}; }}
QPushButton#Primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: white;
                       font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Danger {{ color: {DANGER}; }}
QPushButton#Icon {{ padding: 6px; border-radius: 7px; background: transparent; border: none; }}
QPushButton#Icon:hover {{ background: {SURFACE_2}; }}
QPushButton#Google {{ background: #ffffff; color: #1f2328; border: 1px solid #ffffff;
                      font-weight: 600; font-size: 14px; }}
QPushButton#Google:hover {{ background: #eef1f5; }}
QPushButton#Google:disabled {{ background: #9aa3ae; color: #3a4048; }}
QPushButton#Link {{ background: transparent; border: none; color: {ACCENT_HOVER}; padding: 2px 4px; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
QPushButton#Update {{ background: #12361f; border: 1px solid #2ea043; color: #7ee2a0; font-weight: 600; }}
QPushButton#Update:hover {{ background: #174628; }}
QPushButton::menu-indicator {{ image: none; width: 0; }}

/* ---- inputs ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTimeEdit {{ background: {SURFACE_2}; border: 1px solid {BORDER_STRONG};
               border-radius: 7px; padding: 6px 9px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTimeEdit:focus {{ border-color: {ACCENT}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QTimeEdit::up-button, QTimeEdit::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER_STRONG};
               selection-background-color: {ACCENT_SOFT}; outline: 0; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER_STRONG};
               border-radius: 4px; background: {SURFACE_2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ---- tables & lists ---- */
QTableWidget, QListWidget {{ background: {SURFACE}; border: none; gridline-color: transparent;
               outline: 0; }}
QTableWidget::item {{ border-bottom: 1px solid {BORDER}; padding: 0 8px; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: {ACCENT_SOFT}; }}
QListWidget::item {{ padding: 8px; border-radius: 6px; }}
QListWidget::indicator {{ width: 16px; height: 16px; border: 1px solid {MUTED};
               border-radius: 4px; background: {SURFACE_2}; }}
QListWidget::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QListWidget::item:hover {{ background: {SURFACE_2}; }}
QHeaderView::section {{ background: {SURFACE}; color: {MUTED}; border: none;
               border-bottom: 1px solid {BORDER}; padding: 10px 8px; font-size: 12px;
               font-weight: 600; text-align: left; }}

/* ---- scrollbars ---- */
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 2px; border: none; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border: none; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- menus & tooltips ---- */
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 4px; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
            padding: 6px 8px; border-radius: 6px; }}
"""
