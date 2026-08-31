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
QPushButton:focus, QLineEdit:focus, QListWidget:focus {{ border: 1px solid {c.focus}; }}
QPushButton:disabled {{ color: {c.disabled}; }}
QPushButton#navItem {{ text-align: left; border: 0; background: transparent; padding: 10px 12px; }}
QPushButton#navItem:hover {{ background: {c.surface_hover}; }}
QPushButton#navItem:checked {{ background: {c.surface_selected}; color: {c.text_primary}; border-left: 3px solid {c.accent}; }}
QLineEdit {{ background: {c.surface_secondary}; border: 1px solid {c.border_subtle}; border-radius: {r.md}px; padding: 9px 12px; selection-background-color: {c.accent}; }}
QDialog {{ background: {c.surface_elevated}; }}
QListWidget {{ background: transparent; border: 0; outline: 0; }}
QListWidget::item {{ padding: 10px; border-radius: {r.sm}px; }}
QListWidget::item:hover {{ background: {c.surface_hover}; }}
QListWidget::item:selected {{ background: {c.surface_selected}; }}
#dashboardTaskRow {{ background: transparent; }}
QTableWidget {{ background: {c.surface_primary}; border: 1px solid {c.border_subtle}; gridline-color: {c.divider}; selection-background-color: {c.surface_selected}; }}
QHeaderView::section {{ background: {c.surface_secondary}; color: {c.text_secondary}; border: 0; border-bottom: 1px solid {c.border_subtle}; padding: 7px; }}
QComboBox, QDateEdit, QPlainTextEdit, QSpinBox {{ background: {c.surface_secondary}; border: 1px solid {c.border_subtle}; border-radius: {r.sm}px; padding: 6px; }}
QProgressBar {{ border: 1px solid {c.border_subtle}; border-radius: {r.sm}px; background: {c.surface_secondary}; text-align: center; }}
QProgressBar::chunk {{ background: {c.accent}; border-radius: {r.sm}px; }}
"""
