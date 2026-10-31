"""BlackWall design system: Aurora (default) and Classic (original) themes."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

from config.constants import (
    ACCENTS,
    ACCENTS_BY_THEME,
    AURORA_COLORS,
    COLORS,
    DEFAULT_ACCENT,
    DEFAULT_THEME,
    FONT_FAMILY,
)


@dataclass
class Theme:
    design: str = DEFAULT_THEME
    accent: str = DEFAULT_ACCENT
    scale: int = 100
    compact: bool = False
    animations: bool = True

    @property
    def is_aurora(self) -> bool:
        return self.design == "aurora"

    # ------------------------------------------------------------------ palette
    @property
    def colors(self) -> dict[str, str]:
        base = AURORA_COLORS if self.is_aurora else COLORS
        palette = dict(base)
        accents = ACCENTS_BY_THEME.get(self.design, ACCENTS)
        fallback = DEFAULT_ACCENT if self.is_aurora else "yellow"
        accent = accents.get(self.accent, accents.get(fallback, next(iter(accents.values()))))
        palette["accent"] = accent["accent"]
        palette["accent_light"] = accent["accent_light"]
        palette["accent_text"] = accent["accent_text"]
        palette["selection"] = accent["selection"]
        palette.setdefault("border_hover", palette["surface"])
        palette.setdefault("text_faint", palette.get("text_dim", "#707070"))
        return palette

    def color(self, name: str) -> str:
        return self.colors.get(name, "#FF00FF")

    # ------------------------------------------------------------------ metrics
    def px(self, value: float) -> int:
        """Scale a pixel metric by the UI scale factor."""
        factor = max(0.75, min(1.75, self.scale / 100.0))
        if self.compact:
            factor *= 0.92
        return max(1, int(round(value * factor)))

    def spacing(self, value: float) -> int:
        return max(0, int(round(value * (0.85 if self.compact else 1.0))))

    def font(self, size: float, weight: int = 400, letter_spacing: float = 0) -> QFont:
        font = QFont(FONT_FAMILY)
        font.setPixelSize(max(9, self.px(size)))
        font.setWeight(QFont.Weight(weight))
        if letter_spacing:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
        return font

    # ------------------------------------------------------------------ stylesheet
    def _ensure_combo_arrow(self) -> str:
        """Render a small chevron PNG for QComboBox and return a QSS url."""
        from config import paths
        from ui import icons

        target = paths.CACHE_DIR / "ui" / (
            f"chevron_{self.design}_{self.accent}.png")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                icons.pixmap("chevron-down", self.color("text_dim"), 14).save(
                    str(target), "PNG")
        except OSError:
            return "none"
        return f"url({target.as_posix()})"

    def stylesheet(self) -> str:
        c = self.colors
        px = self.px
        r = px
        scrollbar = px(10)
        arrow_url = self._ensure_combo_arrow()
        aurora = self.is_aurora
        card_bg = c["card"]
        button_bg = c["surface"]
        primary_bg = c["accent"]
        primary_hover = c["accent_light"]
        aurora_extra = ""
        if aurora:
            card_bg = ("qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                       "stop:0 #181818, stop:1 #111111)")
            button_bg = "#141414"
            primary_bg = ("qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                          f"stop:0 {c['accent']}, stop:1 {c['accent_light']})")
            primary_hover = ("qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                             f"stop:0 {c['accent_light']}, stop:1 {c['accent']})")
            accent = c["accent"]
            accent_light = c["accent_light"]
            selection = c["selection"]
            border = c["border"]
            aurora_extra = (
                f"QFrame#TopBar {{ background: {c['bg']};"
                f" border-bottom: 1px solid #151515; }}"
                f"QFrame#Sidebar {{ background: {c['sidebar']};"
                f" border-right: 1px solid #191919; }}"
                f"QFrame#Card {{ border-radius: {px(18)}px; }}"
                f"QFrame#Surface {{ border-radius: {px(12)}px; }}"
                f"QPushButton#Primary {{ border: 1px solid {accent_light}; }}"
                f"QPushButton#NavButton {{ border-radius: {px(12)}px; }}"
                f"QPushButton#NavButton:checked {{ border-left: 3px solid {accent};"
                f" color: #FFFFFF; }}"
                f"QLabel#Badge {{ background: {selection}; color: #FFFFFF;"
                f" border: 1px solid {accent}; }}"
                f"QComboBox QAbstractItemView {{ background: #141414; }}"
                f"QMenu {{ background: #141414; }}"
                f"QToolTip {{ background: #141414; }}"
                f"QProgressBar::chunk {{ background: {accent}; }}"
                f"QFrame#HeroCard {{ background: qlineargradient(x1:0, y1:0,"
                f" x2:1, y2:1, stop:0 #1A1026, stop:1 #0D0D0D);"
                f" border: 1px solid #302044; }}"
                f"QFrame#HeroOverlay {{ background: qlineargradient(x1:0, y1:0,"
                f" x2:0, y2:1, stop:0 rgba(0,0,0,0),"
                f" stop:0.45 rgba(0,0,0,185), stop:1 rgba(0,0,0,240));"
                f" border: none; }}"
                f"QWidget#SettingsNav {{ background: #0A0A0A;"
                f" border: 1px solid #191919; border-radius: {px(16)}px; }}"
                f"QWidget#SettingsNav QPushButton#NavButton {{ background: transparent;"
                f" border: none; text-align: left; padding: {px(9)}px {px(12)}px;"
                f" color: {c['text_dim']}; }}"
                f"QWidget#SettingsNav QPushButton#NavButton:hover {{"
                f" background: {c['hover']}; color: {c['text']}; }}"
                f"QWidget#SettingsNav QPushButton#NavButton:checked {{"
                f" background: {selection}; color: {c['text']};"
                f" border-left: 3px solid {accent}; }}"
                f"QFrame#MetricCard {{ background: #141414;"
                f" border: 1px solid {c['border']};"
                f" border-radius: {px(16)}px; }}"

            )
        qss = """
/* ---------- base ---------- */
* { outline: 0; }
QWidget {
    background: transparent;
    color: %(text)s;
    font-family: "%(font)s";
    font-size: %(fs)s px;
}
QMainWindow, QDialog, #AppRoot, #PageRoot, QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: %(bg)s;
}
QWidget#CentralHost { background-color: %(bg)s; }
QToolTip {
    background-color: %(surface)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 6px 8px;
    font-size: %(fs_small)s px;
}

/* ---------- typography ---------- */
QLabel { background: transparent; }
QLabel#H1 { font-size: %(h1)s px; font-weight: 700; color: %(text)s; }
QLabel#H2 { font-size: %(h2)s px; font-weight: 600; color: %(text)s; }
QLabel#H3 { font-size: %(h3)s px; font-weight: 600; color: %(text)s; }
QLabel#Body { font-size: %(fs)s px; color: %(text)s; }
QLabel#Subtitle { font-size: %(h3)s px; color: %(text_dim)s; }
QLabel#Dim { font-size: %(fs)s px; color: %(text_dim)s; }
QLabel#Caption { font-size: %(fs_small)s px; color: %(text_dim)s; }
QLabel#Value { font-size: %(h2)s px; font-weight: 700; color: %(text)s; }
QLabel#Accent { color: %(accent)s; }
QLabel#Error { color: %(error)s; }
QLabel#Success { color: %(success)s; }
QLabel#Mono { font-family: "Consolas"; font-size: %(fs_small)s px; color: %(text_dim)s; }

/* ---------- containers ---------- */
QFrame#Card {
    background: %(card_bg)s;
    border: 1px solid %(border)s;
    border-radius: %(card_radius)s px;
}
QFrame#Card:hover { border-color: %(border_hover)s; }
QFrame#ModeCard {
    background: %(card_bg)s;
    border: 1px solid %(border)s;
    border-radius: %(card_radius)s px;
}
QFrame#ModeCard:hover { border-color: %(border_hover)s; }
QFrame#ModeCard[selected="true"] {
    border: 1px solid %(accent)s;
    background-color: %(selection)s;
}
QFrame#Surface {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: %(radius)s px;
}
QFrame#Sidebar {
    background-color: %(sidebar)s;
    border-right: 1px solid %(border)s;
}
QFrame#TopBar { background-color: %(bg)s; }
QFrame#Divider { background-color: %(border)s; border: none; max-height: 1px; }

/* ---------- buttons ---------- */
QPushButton {
    background: %(button_bg)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    border-radius: %(radius)s px;
    padding: %(pad_v)s px %(pad_h)s px;
    font-size: %(fs)s px;
}
QPushButton:hover { background: %(hover)s; border-color: %(border_hover)s; }
QPushButton:pressed { background: %(pressed)s; }
QPushButton:disabled { color: %(text_dim)s; background: %(card)s; }

QPushButton#Primary {
    background: %(primary_bg)s;
    color: %(accent_text)s;
    border: 1px solid %(accent)s;
    font-weight: 600;
}
QPushButton#Primary:hover { background: %(primary_hover)s; border-color: %(accent_light)s; }
QPushButton#Primary:pressed { background: %(primary_bg)s; }
QPushButton#Primary:disabled { background-color: %(card)s; color: %(text_dim)s; border-color: %(border)s; }

QPushButton#Ghost {
    background-color: transparent;
    border: 1px solid transparent;
    color: %(text_dim)s;
}
QPushButton#Ghost:hover { color: %(text)s; background-color: %(surface)s; }

QPushButton#Outline {
    background-color: transparent;
    border: 1px solid %(border)s;
    color: %(text)s;
}
QPushButton#Outline:hover { border-color: %(accent)s; color: %(accent)s; background-color: transparent; }

QPushButton#Danger {
    background-color: transparent;
    border: 1px solid %(error)s;
    color: %(error)s;
}
QPushButton#Danger:hover { background-color: %(error)s; color: %(text)s; }

QPushButton#NavButton {
    background-color: transparent;
    border: none;
    border-radius: %(radius)s px;
    color: %(text_dim)s;
    text-align: left;
    padding: %(nav_pad_v)s px %(nav_pad_h)s px;
    font-size: %(fs)s px;
}
QPushButton#NavButton:hover { color: %(text)s; background-color: %(hover)s; }
QPushButton#NavButton:checked {
    color: %(accent)s;
    background-color: %(selection)s;
    font-weight: 600;
}

QPushButton#Chip {
    background-color: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 999px;
    padding: 6px 14px;
    color: %(text_dim)s;
    font-size: %(fs_small)s px;
}
QPushButton#Chip:hover { color: %(text)s; border-color: %(border_hover)s; }
QPushButton#Chip:checked {
    background-color: %(selection)s;
    color: %(accent)s;
    border-color: %(accent)s;
}

QPushButton#IconButton {
    background-color: transparent;
    border: none;
    border-radius: %(radius)s px;
    padding: 6px;
    color: %(text_dim)s;
}
QPushButton#IconButton:hover { background-color: %(hover)s; color: %(text)s; }

QPushButton#LinkButton {
    background: transparent;
    border: none;
    color: %(accent)s;
    padding: 2px 0;
    font-size: %(fs_small)s px;
}
QPushButton#LinkButton:hover { color: %(accent_light)s; }

QPushButton#Segment {
    background-color: transparent;
    border: none;
    border-radius: 7px;
    padding: 6px 14px;
    color: %(text_dim)s;
    font-size: %(fs_small)s px;
}
QPushButton#Segment:hover { color: %(text)s; }
QPushButton#Segment:checked {
    background-color: %(selection)s;
    color: %(accent)s;
    font-weight: 600;
}

QLabel#CardTitle { font-size: %(h3)s px; font-weight: 600; color: %(text)s; }
QLabel#CardMeta { font-size: %(fs_small)s px; color: %(text_dim)s; }
QLabel#StatValue { font-size: %(h1)s px; font-weight: 700; color: %(text)s; }
QLabel#Badge {
    background-color: %(selection)s;
    color: %(accent)s;
    border-radius: 9px;
    padding: 2px 9px;
    font-size: %(fs_tiny)s px;
    font-weight: 600;
}
QLabel#BadgeDim {
    background-color: %(surface)s;
    color: %(text_dim)s;
    border-radius: 9px;
    padding: 2px 9px;
    font-size: %(fs_tiny)s px;
}

/* ---------- inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: %(radius)s px;
    padding: %(input_pad)s px %(pad_h)s px;
    color: %(text)s;
    selection-background-color: %(accent)s;
    selection-color: %(accent_text)s;
    font-size: %(fs)s px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: %(accent)s; }
QLineEdit:disabled { color: %(text_dim)s; }

QComboBox {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: %(radius)s px;
    padding: %(input_pad)s px %(pad_h)s px;
    color: %(text)s;
    font-size: %(fs)s px;
    min-height: %(combo_h)s px;
}
QComboBox:hover { border-color: %(border_hover)s; }
QComboBox:focus { border-color: %(accent)s; }
QComboBox::drop-down { border: none; width: %(combo_arrow_w)s px; }
QComboBox::down-arrow {
    image: %(combo_arrow)s;
    width: %(arrow_size)s px;
    height: %(arrow_size)s px;
}
QComboBox { padding-right: %(combo_arrow_pad)s px; }
QComboBox QAbstractItemView {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    color: %(text)s;
    selection-background-color: %(selection)s;
    selection-color: %(accent)s;
    padding: 4px;
    outline: 0;
}

QSpinBox, QDoubleSpinBox {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: %(radius)s px;
    padding: %(input_pad)s px %(pad_h)s px;
    color: %(text)s;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: %(accent)s; }

QCheckBox, QRadioButton {
    color: %(text)s;
    font-size: %(fs)s px;
    spacing: 8px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px; height: 18px;
    border-radius: 5px;
    border: 1px solid %(border)s;
    background-color: %(surface)s;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: %(accent)s;
    border-color: %(accent)s;
}
QRadioButton::indicator { border-radius: 9px; }

/* ---------- sliders ---------- */
QSlider::groove:horizontal {
    height: 4px;
    background: %(border)s;
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
QSlider::handle:horizontal {
    background: %(accent)s;
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover { background: %(accent_light)s; }

/* ---------- progress ---------- */
QProgressBar {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    height: %(progress_h)s px;
    text-align: center;
    color: %(text_dim)s;
    font-size: %(fs_small)s px;
}
QProgressBar::chunk { background-color: %(accent)s; border-radius: 5px; }

/* ---------- scroll areas ---------- */
QScrollArea { border: none; }
QScrollBar:vertical {
    background: transparent;
    width: %(scrollbar)s px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: %(border)s;
    border-radius: %(scrollbar_handle)s px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: %(scrollbar_hover)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
    background: transparent;
    height: %(scrollbar)s px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: %(border)s;
    border-radius: %(scrollbar_handle)s px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover { background: %(scrollbar_hover)s; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ---------- menus ---------- */
QMenu {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
    padding: 6px;
    color: %(text)s;
}
QMenu::item { padding: 7px 22px 7px 12px; border-radius: 6px; font-size: %(fs_small)s px; }
QMenu::item:selected { background-color: %(selection)s; color: %(accent)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 6px 8px; }

/* ---------- tabs ---------- */
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: transparent;
    color: %(text_dim)s;
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: %(fs)s px;
}
QTabBar::tab:selected { color: %(accent)s; border-bottom: 2px solid %(accent)s; }
QTabBar::tab:hover { color: %(text)s; }

/* ---------- lists ---------- */
QListWidget, QListView, QTreeWidget, QTableWidget {
    background: transparent;
    border: none;
    color: %(text)s;
    font-size: %(fs)s px;
    outline: 0;
}
QListWidget::item, QTreeWidget::item { padding: 6px; border-radius: 6px; }
QListWidget::item:selected, QTreeWidget::item:selected {
    background: %(selection)s;
    color: %(accent)s;
}

/* ---------- misc ---------- */
QStatusBar { background: %(sidebar)s; color: %(text_dim)s; }
QSplitter::handle { background: %(border)s; }
%(aurora_extra)s
""" % {
            "font": FONT_FAMILY,
            "bg": c["bg"],
            "sidebar": c["sidebar"],
            "card": c["card"],
            "card_bg": card_bg,
            "button_bg": button_bg,
            "primary_bg": primary_bg,
            "primary_hover": primary_hover,
            "aurora_extra": aurora_extra,
            "surface": c["surface"],
            "hover": c["hover"],
            "pressed": c["pressed"],
            "border": c["border"],
            "border_hover": c.get("border_hover") or c["surface"],
            "accent": c["accent"],
            "accent_light": c["accent_light"],
            "accent_text": c["accent_text"],
            "selection": c["selection"],
            "text": c["text"],
            "text_dim": c["text_dim"],
            "error": c["error"],
            "success": c["success"],
            "fs": px(13),
            "fs_small": px(12),
            "fs_tiny": px(11),
            "h1": px(30 if aurora else 26),
            "h2": px(21 if aurora else 19),
            "h3": px(15),
            "card_radius": px(18 if aurora else 14),
            "radius": px(12 if aurora else 10),
            "pad_v": px(9 if aurora else 8),
            "pad_h": px(16 if aurora else 14),
            "nav_pad_v": px(11 if aurora else 10),
            "nav_pad_h": px(14 if aurora else 12),
            "input_pad": px(7),
            "combo_h": px(22),
            "combo_arrow_w": px(22),
            "combo_arrow": arrow_url,
            "combo_arrow_pad": px(26),
            "arrow_size": px(12),
            "progress_h": px(8),
            "scrollbar": px(10),
            "scrollbar_handle": px(4),
            "scrollbar_hover": c["text_dim"],
        }
        # QSS requires the unit to be attached to the number ("13px").
        return re.sub(r"(\d+)\s+px\b", r"\1px", qss)

    def apply(self, app: QApplication) -> None:
        app.setStyle("Fusion")
        app.setFont(self.font(13))
        app.setStyleSheet(self.stylesheet())

    def qcolor(self, name: str):
        from PySide6.QtGui import QColor

        return QColor(self.color(name))


def normalize_appearance(settings) -> tuple[str, str]:
    """Migrate old settings to Aurora and remember accents per theme."""
    before = (
        str(settings.get("appearance.theme", "") or ""),
        str(settings.get("appearance.accent", "") or ""),
        str(settings.get("appearance.aurora_accent", "") or ""),
        str(settings.get("appearance.classic_accent", "") or ""),
    )
    raw = str(settings.get("appearance.theme", "") or "")
    if raw in ACCENTS_BY_THEME:
        design = raw
    elif raw in ("dark", "premium", "default", ""):
        design = DEFAULT_THEME
    else:
        design = DEFAULT_THEME
    current = str(settings.get("appearance.accent", "") or "")
    classic = set(ACCENTS)
    aurora = set(ACCENTS_BY_THEME["aurora"])
    if current in classic:
        settings.set("appearance.classic_accent", current, save=False)
    if design == "aurora":
        saved = str(settings.get("appearance.aurora_accent", "") or "")
        if current not in aurora:
            current = saved if saved in aurora else DEFAULT_ACCENT
    else:
        saved = str(settings.get("appearance.classic_accent", "") or "")
        if current not in classic:
            current = saved if saved in classic else "yellow"
    settings.set("appearance.theme", design, save=False)
    settings.set("appearance.accent", current, save=False)
    settings.set(f"appearance.{design}_accent", current, save=False)
    after = (
        str(settings.get("appearance.theme", "") or ""),
        str(settings.get("appearance.accent", "") or ""),
        str(settings.get("appearance.aurora_accent", "") or ""),
        str(settings.get("appearance.classic_accent", "") or ""),
    )
    if after != before:
        settings.save()
    return design, current


def apply_theme(app: QApplication, settings) -> Theme:
    design, accent = normalize_appearance(settings)
    theme = Theme(
        design=design,
        accent=accent,
        scale=int(settings.get("appearance.ui_scale", 100) or 100),
        compact=bool(settings.get("appearance.compact", False)),
        animations=bool(settings.get("appearance.animations", True)),
    )
    theme.apply(app)
    app.setProperty("bw_theme", theme)
    return theme


def current_theme() -> Theme:
    app = QApplication.instance()
    theme = app.property("bw_theme") if app is not None else None
    if not isinstance(theme, Theme):
        theme = Theme()
        if app is not None:
            app.setProperty("bw_theme", theme)
    return theme


def refresh_widgets(widget: QWidget) -> None:
    """Re-polish a whole widget tree after a theme change."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    for child in widget.findChildren(QWidget):
        child.style().unpolish(child)
        child.style().polish(child)
    widget.update()

