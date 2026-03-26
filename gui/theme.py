"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/theme.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Centralised design-token module.

                Import design tokens and stylesheet-generator functions from
                here instead of scattering inline colour/size literals
                throughout the widget code.

                Colour tokens are plain strings.  Size tokens (FONT_*, BTN_*,
                RADIUS_*, …) are _Px instances that evaluate lazily: each time
                a value is needed (f-string, setFixedHeight(), arithmetic) the
                token reads the current QApplication font and screen DPI and
                scales proportionally.  On a standard 96 dpi / 10 pt system
                the nominal values are used unchanged.  A 4 K display at 200 %
                OS scaling yields approximately 2× larger values automatically.

                No init call is required — scaling is applied transparently.

Usage:
    from gui.theme import CLR_PRIMARY, FONT_BASE, btn_primary, progress_bar
------------------------------------------------------------------------------
"""

from __future__ import annotations


# ── HiDPI scaling helper ────────────────────────────────────────────────────

def _scale_factor() -> float:
    """
    Return the ratio of the current system font to the 96 dpi / 10 pt
    design baseline (13 px).  Always returns 1.0 when no QApplication
    exists (headless tests, module-level imports).
    """
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: PLC0415
        app = QApplication.instance()
        if app is None:
            return 1.0
        font = app.font()
        pt = font.pointSize()
        if pt <= 0:
            return 1.0
        screens = app.screens()
        if not screens:
            return 1.0
        dpi: float = screens[0].logicalDotsPerInch()
        # Design baseline: 10 pt at 96 dpi → 13.3 px (our FONT_BASE nominal).
        actual_px = pt * dpi / 72.0
        design_px = 10.0 * 96.0 / 72.0
        return actual_px / design_px
    except Exception:  # pragma: no cover
        return 1.0


class _Px:
    """
    A nominal-pixel size token that scales lazily to the live system font.

    Behaves like an int in all contexts:
    - f"{FONT_BASE}px"          → "13px"  (or "16px" at 125 % scaling)
    - widget.setFixedHeight(BTN_HEIGHT)  → passes an int via __index__
    - PROGRESS_H // 2           → integer division
    - max(1, RADIUS_SM * 2)     → arithmetic works transparently
    """

    __slots__ = ("_nominal",)

    def __init__(self, nominal: int) -> None:
        self._nominal = nominal

    def _v(self) -> int:
        return max(1, round(self._nominal * _scale_factor()))

    # ── Protocol methods ──────────────────────────────────────────────────

    def __format__(self, spec: str) -> str:
        return format(self._v(), spec)

    def __str__(self) -> str:
        return str(self._v())

    def __repr__(self) -> str:
        return f"_Px(nominal={self._nominal!r}, current={self._v()!r})"

    # __index__ enables use in C-level integer slots (setFixedHeight etc.)
    def __index__(self) -> int:
        return self._v()

    def __int__(self) -> int:
        return self._v()

    def __float__(self) -> float:
        return float(self._v())

    # ── Arithmetic ────────────────────────────────────────────────────────

    def __add__(self, other: int) -> int:      return self._v() + int(other)
    def __radd__(self, other: int) -> int:     return int(other) + self._v()
    def __sub__(self, other: int) -> int:      return self._v() - int(other)
    def __rsub__(self, other: int) -> int:     return int(other) - self._v()
    def __mul__(self, other: int) -> int:      return self._v() * int(other)
    def __rmul__(self, other: int) -> int:     return int(other) * self._v()
    def __floordiv__(self, other: int) -> int: return self._v() // int(other)
    def __rfloordiv__(self, other: int) -> int: return int(other) // self._v()

    # ── Comparison ────────────────────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        return self._v() == int(other)  # type: ignore[arg-type]

    def __lt__(self, other: object) -> bool:
        return self._v() < int(other)  # type: ignore[arg-type]

    def __le__(self, other: object) -> bool:
        return self._v() <= int(other)  # type: ignore[arg-type]

    def __gt__(self, other: object) -> bool:
        return self._v() > int(other)  # type: ignore[arg-type]

    def __ge__(self, other: object) -> bool:
        return self._v() >= int(other)  # type: ignore[arg-type]

    def __hash__(self) -> int:
        return hash(self._nominal)


# ── Colour palette ─────────────────────────────────────────────────────────────
# Semantic names only — never reference hex literals directly in widget code.

CLR_PRIMARY        = "#1565c0"   # brand blue (buttons, active states)
CLR_PRIMARY_DARK   = "#0d47a1"   # hover / pressed blue
CLR_PRIMARY_LIGHT  = "#e3f2fd"   # tinted blue bg (checked filter badges)
CLR_PRIMARY_NAV    = "#1976d2"   # slightly lighter blue used in nav chrome

CLR_SUCCESS        = "#2e7d32"   # green (final state, completed, save-success)
CLR_SUCCESS_LIGHT  = "#e8f5e9"
CLR_WARNING        = "#e65100"   # deep-orange (pending, unsaved)
CLR_WARNING_LIGHT  = "#fff3e0"
CLR_DANGER         = "#c62828"   # red (error, destructive action)
CLR_DANGER_LIGHT   = "#ffebee"

# Surfaces
CLR_SURFACE        = "#ffffff"   # main card / panel background
CLR_SURFACE_ROW    = "#f8f9fa"   # subtle row / sub-panel background
CLR_SURFACE_HOVER  = "#f0f4f8"   # hover overlay on white surfaces
CLR_NAV_BG         = "#f5f5f5"   # top-level nav bar background

# Borders
CLR_BORDER         = "#e0e0e0"   # default border
CLR_BORDER_STRONG  = "#bdbdbd"   # focus / hover border

# Text
CLR_TEXT           = "#212121"   # high-emphasis body text
CLR_TEXT_SECONDARY = "#555555"   # medium-emphasis (labels, secondary info)
CLR_TEXT_MUTED     = "#9e9e9e"   # low-emphasis (placeholders, hints, counters)
CLR_TEXT_ON_COLOR  = "#ffffff"   # text placed on a coloured background

# ── Typography ─────────────────────────────────────────────────────────────────
# _Px tokens scale proportionally to the system font at runtime.

FONT_SM     = _Px(11)   # history counters, tiny muted labels
FONT_BASE   = _Px(13)   # body text, buttons, form labels, inputs (baseline)
FONT_LG     = _Px(14)   # sub-labels in cards, nav badges
FONT_METRIC = _Px(28)   # large numeric display in cockpit / dashboard cards
FONT_ICON   = _Px(20)   # emoji icon in stat cards

# ── Sizing ──────────────────────────────────────────────────────────────────────

BTN_HEIGHT    = _Px(28)   # all action buttons (save, apply, export, …)
SUBNAV_HEIGHT = _Px(28)   # sub-navigation toggle buttons
NAV_HEIGHT    = _Px(35)   # main navbar tab-container min-height
PROGRESS_H    = _Px(10)   # progress bars — both list rows and dashboard cards
INPUT_H       = _Px(26)   # QLineEdit / QComboBox inside forms

# ── Border-radius ───────────────────────────────────────────────────────────────

RADIUS_SM   = _Px(4)    # buttons, inputs, small chips
RADIUS_MD   = _Px(8)    # cards (cockpit stat-card, dashboard rule-card, dialogs)
RADIUS_PILL = _Px(12)   # status badge pills


# ── Stylesheet generators ───────────────────────────────────────────────────────
# Each function returns a ready-to-use CSS string for setStyleSheet().
# The _Px tokens inside f-strings are evaluated at call time, so the returned
# CSS always reflects the current DPI/font scale.


def btn_primary() -> str:
    """Filled primary-colour action button (e.g. Apply, Save)."""
    return f"""
        QPushButton, QToolButton {{
            background: {CLR_PRIMARY};
            color: {CLR_TEXT_ON_COLOR};
            border: none;
            border-radius: {RADIUS_SM}px;
            height: {BTN_HEIGHT}px;
            font-size: {FONT_BASE}px;
            font-weight: bold;
            padding: 0px 16px;
        }}
        QPushButton:hover, QToolButton:hover {{ background: {CLR_PRIMARY_DARK}; }}
        QPushButton:disabled, QToolButton:disabled {{
            background: {CLR_SURFACE_ROW};
            color: {CLR_TEXT_MUTED};
        }}
    """


def btn_secondary() -> str:
    """Default outlined action button (neutral secondary action)."""
    return f"""
        QPushButton, QToolButton {{
            background: {CLR_SURFACE};
            color: {CLR_TEXT_SECONDARY};
            border: 1px solid {CLR_BORDER};
            border-radius: {RADIUS_SM}px;
            height: {BTN_HEIGHT}px;
            font-size: {FONT_BASE}px;
            padding: 0px 16px;
        }}
        QPushButton:hover, QToolButton:hover {{
            background: {CLR_SURFACE_ROW};
            border-color: {CLR_BORDER_STRONG};
        }}
        QPushButton:disabled, QToolButton:disabled {{
            background: {CLR_SURFACE_ROW};
            color: {CLR_TEXT_MUTED};
            border-color: {CLR_BORDER};
        }}
    """


def btn_subnav() -> str:
    """Toggle pill buttons inside a sub-navigation bar (Search/Filter/…)."""
    return f"""
        QToolButton {{
            background: {CLR_SURFACE_ROW};
            color: {CLR_TEXT_SECONDARY};
            border: 1px solid {CLR_BORDER};
            border-radius: {RADIUS_SM}px;
            height: {SUBNAV_HEIGHT}px;
            font-size: {FONT_BASE}px;
            font-weight: 500;
            padding: 0px 14px;
        }}
        QToolButton:hover {{
            background: {CLR_SURFACE_HOVER};
            border-color: {CLR_BORDER_STRONG};
        }}
        QToolButton:checked {{
            background: {CLR_PRIMARY};
            color: {CLR_TEXT_ON_COLOR};
            border-color: {CLR_PRIMARY_DARK};
            font-weight: bold;
        }}
        QToolButton:disabled {{
            background: {CLR_SURFACE_ROW};
            color: {CLR_TEXT_MUTED};
            border-color: {CLR_BORDER};
        }}
    """


def status_badge(bg_color: str) -> str:
    """Coloured pill label for a workflow state badge."""
    return (
        f"font-size: {FONT_BASE}px; font-weight: 600; "
        f"color: {CLR_TEXT_ON_COLOR}; background: {bg_color}; "
        f"padding: 2px 12px; border-radius: {RADIUS_PILL}px; min-width: 70px;"
    )


def card() -> str:
    """Full dashboard / cockpit card container."""
    return f"""
        QFrame {{
            background: {CLR_SURFACE};
            border: 1px solid {CLR_BORDER};
            border-radius: {RADIUS_MD}px;
        }}
        QFrame:hover {{ border-color: {CLR_BORDER_STRONG}; }}
    """


def card_row() -> str:
    """Compact list-row card (e.g. workflow summary rows)."""
    return f"""
        QFrame {{
            background: {CLR_SURFACE_ROW};
            border: 1px solid {CLR_BORDER};
            border-radius: {RADIUS_SM}px;
        }}
    """


def progress_bar(chunk_color: str) -> str:
    """Consistent progress bar with height PROGRESS_H, border, rounded ends."""
    r = PROGRESS_H // 2
    return f"""
        QProgressBar {{
            border: 1px solid {CLR_BORDER};
            border-radius: {r}px;
            background: {CLR_BORDER};
        }}
        QProgressBar::chunk {{
            border-radius: {r}px;
            background: {chunk_color};
        }}
    """


def label_heading() -> str:
    return f"font-weight: bold; font-size: {FONT_BASE}px; color: {CLR_TEXT};"


def label_secondary() -> str:
    return f"color: {CLR_TEXT_SECONDARY}; font-size: {FONT_BASE}px;"


def label_muted() -> str:
    return f"color: {CLR_TEXT_MUTED}; font-size: {FONT_SM}px;"


def placeholder_label() -> str:
    return f"color: {CLR_TEXT_MUTED}; font-style: italic; padding: 20px;"
