from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

SYSTEM_THEME = "system"
LIGHT_THEME = "light"
DARK_THEME = "dark"

THEME_LABELS = {
    SYSTEM_THEME: "System",
    LIGHT_THEME: "Light",
    DARK_THEME: "Dark",
}


def resolved_theme(theme_name: str) -> str:
    if theme_name != SYSTEM_THEME:
        return theme_name
    try:
        color_scheme = QGuiApplication.styleHints().colorScheme()
    except RuntimeError:
        return LIGHT_THEME
    return DARK_THEME if color_scheme == Qt.ColorScheme.Dark else LIGHT_THEME


def stylesheet_for_theme(theme_name: str) -> str:
    colors = _palette(resolved_theme(theme_name))
    return f"""
QMainWindow, QWidget {{
    background-color: {colors["app_bg"]};
    color: {colors["text"]};
    font-size: 12px;
}}
QMenuBar {{
    background-color: {colors["chrome_bg"]};
    color: {colors["text"]};
    border-bottom: 1px solid {colors["border"]};
}}
QMenuBar::item {{
    padding: 6px 10px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background-color: {colors["hover"]};
}}
QMenu {{
    background-color: {colors["panel_bg"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
}}
QMenu::item {{
    padding: 6px 28px 6px 14px;
}}
QMenu::item:selected {{
    background-color: {colors["accent"]};
    color: #ffffff;
}}
QToolBar {{
    background-color: {colors["chrome_bg"]};
    border: 0;
    border-bottom: 1px solid {colors["border"]};
    spacing: 6px;
    padding: 6px;
}}
QLabel {{
    color: {colors["text"]};
}}
QLineEdit, QComboBox, QPlainTextEdit {{
    background-color: {colors["control_bg"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {colors["accent"]};
}}
QComboBox::drop-down {{
    border: 0;
    width: 22px;
}}
QPushButton, QToolButton {{
    background-color: {colors["button_bg"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 4px;
    padding: 6px 10px;
}}
QPushButton:hover, QToolButton:hover {{
    background-color: {colors["button_hover"]};
    border-color: {colors["accent"]};
}}
QPushButton:pressed, QToolButton:pressed {{
    background-color: {colors["accent"]};
    color: #ffffff;
}}
QPushButton:disabled, QToolButton:disabled {{
    background-color: {colors["disabled_bg"]};
    color: {colors["disabled_text"]};
    border-color: {colors["border"]};
}}
QPushButton[buttonRole="primary"] {{
    background-color: {colors["primary"]};
    border-color: {colors["primary"]};
    color: #ffffff;
}}
QPushButton[buttonRole="primary"]:hover {{
    background-color: {colors["primary_hover"]};
    border-color: {colors["primary_hover"]};
}}
QPushButton[buttonRole="primary"]:pressed {{
    background-color: {colors["primary_pressed"]};
}}
QPushButton[buttonRole="neutral"], QPushButton[buttonRole="secondary"] {{
    background-color: {colors["neutral_bg"]};
    border-color: {colors["neutral_border"]};
    color: {colors["text"]};
}}
QPushButton[buttonRole="neutral"]:hover, QPushButton[buttonRole="secondary"]:hover {{
    background-color: {colors["neutral_hover"]};
    border-color: {colors["accent"]};
}}
QPushButton[buttonRole="warning"], QPushButton[buttonRole="success"] {{
    background-color: {colors["warning"]};
    border-color: {colors["warning"]};
    color: #ffffff;
}}
QPushButton[buttonRole="warning"]:hover, QPushButton[buttonRole="success"]:hover {{
    background-color: {colors["warning_hover"]};
    border-color: {colors["warning_hover"]};
}}
QPushButton[buttonRole="warning"]:pressed, QPushButton[buttonRole="success"]:pressed {{
    background-color: {colors["warning_pressed"]};
}}
QPushButton[buttonRole="loading"] {{
    background-color: {colors["loading"]};
    border-color: {colors["loading"]};
    color: #ffffff;
}}
QPushButton[buttonRole="danger"] {{
    background-color: {colors["danger"]};
    border-color: {colors["danger"]};
    color: #ffffff;
}}
QPushButton[buttonRole="danger"]:hover {{
    background-color: {colors["danger_hover"]};
    border-color: {colors["danger_hover"]};
}}
QPushButton[buttonRole="danger"]:pressed {{
    background-color: {colors["danger_pressed"]};
}}
QToolButton#pathButton {{
    padding: 0px;
}}
QTableWidget, QTableView {{
    background-color: {colors["table_bg"]};
    alternate-background-color: {colors["panel_bg"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    gridline-color: {colors["grid"]};
    selection-background-color: {colors["accent"]};
    selection-color: #ffffff;
}}
QTableWidget::item, QTableView::item {{
    padding: 5px 8px;
    border: 0;
}}
QTableWidget::item:hover, QTableView::item:hover,
QTableWidget::item:selected, QTableView::item:selected {{
    background: transparent;
}}
QHeaderView::section {{
    background-color: {colors["header_bg"]};
    color: {colors["muted"]};
    border: 0;
    border-right: 1px solid {colors["border"]};
    border-bottom: 1px solid {colors["border"]};
    padding: 6px 8px;
    font-weight: 600;
}}
QSplitter::handle {{
    background-color: {colors["border"]};
}}
QStatusBar {{
    background-color: {colors["chrome_bg"]};
    color: {colors["muted"]};
    border-top: 1px solid {colors["border"]};
}}
"""


def hover_color_for_theme(theme_name: str) -> str:
    return _palette(resolved_theme(theme_name))["hover"]


def selected_color_for_theme(theme_name: str) -> str:
    return _palette(resolved_theme(theme_name))["selected"]


def _palette(theme_name: str) -> dict[str, str]:
    if theme_name == DARK_THEME:
        return {
            "app_bg": "#111827",
            "chrome_bg": "#0b1220",
            "panel_bg": "#141c2b",
            "control_bg": "#0f172a",
            "table_bg": "#0f172a",
            "header_bg": "#111827",
            "button_bg": "#172033",
            "button_hover": "#1f2a44",
            "disabled_bg": "#1f2937",
            "disabled_text": "#6b7280",
            "primary": "#2563eb",
            "primary_hover": "#1d4ed8",
            "primary_pressed": "#1e40af",
            "warning": "#d97706",
            "warning_hover": "#b45309",
            "warning_pressed": "#92400e",
            "loading": "#0891b2",
            "danger": "#dc2626",
            "danger_hover": "#b91c1c",
            "danger_pressed": "#991b1b",
            "neutral_bg": "#172033",
            "neutral_border": "#3b475c",
            "neutral_hover": "#1f2a44",
            "hover": "#243244",
            "selected": "#1d4ed8",
            "accent": "#2563eb",
            "text": "#e5e7eb",
            "muted": "#9ca3af",
            "border": "#2b3648",
            "grid": "#1f2937",
        }
    return {
        "app_bg": "#f5f7fb",
        "chrome_bg": "#ffffff",
        "panel_bg": "#ffffff",
        "control_bg": "#ffffff",
        "table_bg": "#ffffff",
        "header_bg": "#eef2f7",
        "button_bg": "#ffffff",
        "button_hover": "#eef4ff",
        "disabled_bg": "#e5e7eb",
        "disabled_text": "#94a3b8",
        "primary": "#2563eb",
        "primary_hover": "#1d4ed8",
        "primary_pressed": "#1e40af",
        "warning": "#d97706",
        "warning_hover": "#b45309",
        "warning_pressed": "#92400e",
        "loading": "#0891b2",
        "danger": "#dc2626",
        "danger_hover": "#b91c1c",
        "danger_pressed": "#991b1b",
        "neutral_bg": "#ffffff",
        "neutral_border": "#cbd5e1",
        "neutral_hover": "#eef4ff",
        "hover": "#dbeafe",
        "selected": "#bfdbfe",
        "accent": "#2563eb",
        "text": "#1f2937",
        "muted": "#64748b",
        "border": "#d8dee8",
        "grid": "#e5e7eb",
    }
