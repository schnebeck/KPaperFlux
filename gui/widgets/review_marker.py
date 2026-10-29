"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/review_marker.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Visual 'needs review' marker for MetadataEditor fields: amber
                border on input widgets, amber background on table items, a
                tooltip with the engine's review reasons and provenance.
------------------------------------------------------------------------------
"""

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QTableWidgetItem, QWidget

from gui.theme import CLR_REVIEW, CLR_REVIEW_LIGHT

#: Dynamic property set on marked widgets (tests and style queries).
PROPERTY_NEEDS_REVIEW: str = "needsReview"
#: Item data role holding True on marked table items.
ROLE_NEEDS_REVIEW: int = int(Qt.ItemDataRole.UserRole) + 21

_ORIGINAL_STYLE = "_reviewOriginalStyle"
_ORIGINAL_TIP = "_reviewOriginalToolTip"
_REVIEW_STYLE = f"border: 2px solid {CLR_REVIEW}; border-radius: 3px;"


def is_marked(widget: QWidget) -> bool:
    """True if the widget currently shows the review marker."""
    return bool(widget.property(PROPERTY_NEEDS_REVIEW))


def mark_widget(widget: QWidget, tooltip: str) -> None:
    """
    Shows the review marker on an input widget (idempotent).

    Args:
        widget: The field widget.
        tooltip: Review reasons and provenance.
    """
    if not is_marked(widget):
        widget.setProperty(_ORIGINAL_STYLE, widget.styleSheet())
        widget.setProperty(_ORIGINAL_TIP, widget.toolTip())
    widget.setProperty(PROPERTY_NEEDS_REVIEW, True)
    original = widget.property(_ORIGINAL_STYLE) or ""
    widget.setStyleSheet(f"{original} {_REVIEW_STYLE}".strip())
    widget.setToolTip(tooltip)


def clear_widget(widget: QWidget) -> None:
    """Removes the review marker and restores the original look."""
    if not is_marked(widget):
        return
    widget.setStyleSheet(widget.property(_ORIGINAL_STYLE) or "")
    widget.setToolTip(widget.property(_ORIGINAL_TIP) or "")
    widget.setProperty(PROPERTY_NEEDS_REVIEW, False)


def mark_item(item: Optional[QTableWidgetItem], tooltip: str) -> None:
    """Shows the review marker on a table item."""
    if item is None:
        return
    item.setBackground(QBrush(QColor(CLR_REVIEW_LIGHT)))
    item.setForeground(QBrush(QColor("#000000")))
    item.setToolTip(tooltip)
    item.setData(ROLE_NEEDS_REVIEW, True)


def clear_item(item: Optional[QTableWidgetItem]) -> None:
    """Removes the review marker from a table item."""
    if item is None or not item.data(ROLE_NEEDS_REVIEW):
        return
    item.setBackground(QBrush())
    item.setForeground(QBrush())
    item.setToolTip("")
    item.setData(ROLE_NEEDS_REVIEW, False)
