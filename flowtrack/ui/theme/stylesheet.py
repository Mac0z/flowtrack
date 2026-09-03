"""Central Qt stylesheet generation."""

from flowtrack.ui.theme.tokens import Theme


def build_stylesheet(theme: Theme) -> str:
    c, s, r, t = theme.colors, theme.spacing, theme.radii, theme.typography
    return f"""
QWidget {{ background: {c.application_background}; color: {c.text_primary}; font-size: {t.body}px; }}
QMainWindow, #contentArea {{ background: {c.application_background}; }}
#sidebar {{ background: {c.sidebar_background}; border-right: 1px solid {c.border_subtle}; }}
QLabel#brand {{ font-size: {t.heading}px; font-weight: {t.weight_semibold}; color: {c.text_primary}; }}
QLabel#eyebrow {{ font-size: {t.small}px; font-weight: {t.weight_semibold}; color: {c.accent}; }}
QLabel#pageTitle {{ font-size: {t.title}px; font-weight: {t.weight_semibold}; }}
QLabel#secondaryText {{ color: {c.text_secondary}; }}
QLabel#mutedText {{ color: {c.text_muted}; }}
QLabel#dangerText {{ color: {c.danger}; }}
QFrame#card {{ background: {c.surface_primary}; border: 1px solid {c.border_subtle}; border-radius: {r.lg}px; }}
QPushButton {{ background: {c.surface_secondary}; border: 1px solid {c.border_subtle}; border-radius: {r.md}px; padding: {s.sm}px {s.md}px; }}
QPushButton:hover {{ background: {c.surface_hover}; }}
QPushButton:pressed {{ background: {c.surface_selected}; }}
QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QDateEdit:focus, QSpinBox:focus, QListWidget:focus, QTableWidget:focus {{
    border: 1px solid {c.focus}; outline: 0;
}}
QPushButton:disabled {{ color: {c.disabled}; }}
QPushButton#navItem {{ text-align: left; border: 0; background: transparent; padding: 10px 12px; }}
QPushButton#navItem:hover {{ background: {c.surface_hover}; }}
QPushButton#navItem:checked {{ background: {c.surface_selected}; color: {c.text_primary}; border-left: 3px solid {c.accent}; }}
QTabWidget::pane {{ background: {c.surface_primary}; border: 1px solid {c.border_subtle}; border-radius: {r.md}px; top: -1px; }}
QTabBar::tab {{ background: {c.surface_secondary}; color: {c.text_secondary}; border: 1px solid {c.border_subtle}; padding: {s.sm}px {s.lg}px; }}
QTabBar::tab:selected {{ background: {c.surface_selected}; color: {c.text_primary}; border-bottom: 2px solid {c.accent}; }}
QTabBar::tab:hover:!selected {{ background: {c.surface_hover}; color: {c.text_primary}; }}
QTabBar::tab:disabled {{ color: {c.disabled}; }}
QLineEdit {{ background: {c.surface_secondary}; border: 1px solid {c.border_subtle}; border-radius: {r.md}px; padding: 9px 12px; selection-background-color: {c.accent}; }}
QDialog {{ background: {c.surface_elevated}; }}
QDialog QLabel {{ background: transparent; }}
QListWidget {{ background: transparent; border: 0; outline: 0; }}
QListWidget::item {{ padding: 10px; border-radius: {r.sm}px; }}
QListWidget::item:hover {{ background: {c.surface_hover}; }}
QListWidget::item:selected {{ background: {c.surface_selected}; }}
QListWidget::item:selected:hover {{ background: {c.surface_selected}; }}
QListWidget::item:focus, QTableWidget::item:focus {{ border: 1px solid {c.focus}; }}
QTableWidget {{ background: {c.surface_primary}; border: 1px solid {c.border_subtle}; gridline-color: {c.divider}; selection-background-color: {c.surface_selected}; }}
QHeaderView::section {{ background: {c.surface_secondary}; color: {c.text_secondary}; border: 0; border-bottom: 1px solid {c.border_subtle}; padding: 7px; }}
QComboBox, QDateEdit, QPlainTextEdit, QSpinBox {{ background: {c.surface_secondary}; border: 1px solid {c.border_subtle}; border-radius: {r.sm}px; padding: 6px; }}
QCalendarWidget {{ background: {c.surface_elevated}; color: {c.text_primary}; border: 1px solid {c.border_subtle}; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {c.surface_secondary}; border-bottom: 1px solid {c.border_subtle}; }}
QCalendarWidget QToolButton {{ background: transparent; color: {c.text_primary}; border: 0; border-radius: {r.sm}px; padding: {s.sm}px; }}
QCalendarWidget QToolButton:hover {{ background: {c.surface_hover}; }}
QCalendarWidget QToolButton:pressed {{ background: {c.surface_selected}; }}
QCalendarWidget QToolButton:focus {{ border: 1px solid {c.focus}; }}
QCalendarWidget QToolButton:disabled {{ color: {c.disabled}; }}
QCalendarWidget QSpinBox#qt_calendar_yearedit {{ background: {c.surface_elevated}; color: {c.text_primary}; selection-background-color: {c.accent}; selection-color: {c.text_primary}; }}
QCalendarWidget QMenu {{ background: {c.surface_elevated}; color: {c.text_primary}; border: 1px solid {c.border_subtle}; }}
QCalendarWidget QMenu::item:selected {{ background: {c.surface_selected}; color: {c.text_primary}; }}
QCalendarWidget QAbstractItemView {{ background: {c.surface_primary}; alternate-background-color: {c.surface_secondary}; color: {c.text_primary}; selection-background-color: {c.accent}; selection-color: {c.text_primary}; outline: 0; }}
QCalendarWidget QAbstractItemView::item:hover {{ background: {c.surface_hover}; color: {c.text_primary}; }}
QCalendarWidget QAbstractItemView::item:focus {{ border: 1px solid {c.focus}; }}
QCalendarWidget QAbstractItemView::item:disabled {{ color: {c.disabled}; }}
QProgressBar {{ border: 1px solid {c.border_subtle}; border-radius: {r.sm}px; background: {c.surface_secondary}; text-align: center; }}
QProgressBar::chunk {{ background: {c.accent}; border-radius: {r.sm}px; }}
QWidget#tagChip {{ background: {c.surface_secondary}; border: 1px solid {c.border_subtle}; border-radius: {r.sm}px; }}
QPushButton#tagChipRemove {{ border: 0; background: transparent; padding: 2px 6px; color: {c.text_secondary}; }}
QPushButton#tagChipRemove:hover {{ color: {c.text_primary}; background: {c.surface_hover}; }}
QWidget#dependencyRow {{ background: {c.surface_secondary}; border: 1px solid {c.border_subtle}; border-radius: {r.sm}px; }}
QLabel#dependencyText {{ color: {c.text_primary}; background: transparent; }}
QPushButton#dependencyRemove {{ border: 0; background: transparent; padding: 3px 7px; color: {c.text_secondary}; }}
QPushButton#dependencyRemove:hover {{ color: {c.danger}; background: {c.surface_hover}; }}
"""
