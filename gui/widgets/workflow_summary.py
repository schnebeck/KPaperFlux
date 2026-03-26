"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/workflow_summary.py
Version:        1.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Compact read-only workflow progress summary widget used in
                MetadataEditor Tab 8.  Shows one row per active workflow with
                rule name, current-state badge, progress bar and percentage.
------------------------------------------------------------------------------
"""
from typing import Dict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QScrollArea,
    QVBoxLayout, QWidget,
)
from PyQt6.QtGui import QCursor

from core.workflow import WorkflowRuleRegistry, completion_percent
from gui.theme import (
    CLR_PRIMARY, CLR_SUCCESS, FONT_BASE, FONT_SM,
    PROGRESS_H, card_row, placeholder_label, progress_bar, status_badge,
)


class _ClickableRow(QFrame):
    """QFrame that emits clicked(rule_id) when the user clicks anywhere in the row."""
    clicked = pyqtSignal(str)

    def __init__(self, rule_id: str, parent=None):
        super().__init__(parent)
        self._rule_id = rule_id

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._rule_id)
        super().mousePressEvent(event)


class WorkflowSummaryWidget(QWidget):
    """Read-only list of workflow progress rows for a single document."""

    workflow_clicked = pyqtSignal(str)   # emits rule_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(10, 10, 10, 10)
        self._content_layout.setSpacing(6)
        self._content_layout.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll)

    # ── Public API ────────────────────────────────────────────────────────────

    def update_workflows(self, workflows: Dict, registry: WorkflowRuleRegistry) -> None:
        """Rebuild rows from *workflows* dict (rule_id → WorkflowInfo)."""
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not workflows:
            placeholder = QLabel(self.tr("No active workflows"))
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet(placeholder_label())
            self._content_layout.insertWidget(0, placeholder)
            return

        for i, (rule_id, wf_info) in enumerate(workflows.items()):
            rule = registry.get_rule(rule_id)
            row = self._build_row(rule_id, wf_info, rule)
            self._content_layout.insertWidget(i, row)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_row(self, rule_id: str, wf_info, rule) -> QFrame:
        frame = _ClickableRow(rule_id)
        frame.clicked.connect(self.workflow_clicked)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(card_row())
        frame.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        frame.setToolTip(self.tr("Click to open this workflow in the Process view"))

        row_layout = QHBoxLayout(frame)
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(12)

        display_name = rule.get_display_name() if rule else rule_id
        name_lbl = QLabel(display_name)
        name_lbl.setStyleSheet(f"font-weight: bold; font-size: {FONT_BASE}px;")
        name_lbl.setMinimumWidth(140)
        row_layout.addWidget(name_lbl)

        if rule:
            state_def = rule.states.get(wf_info.current_step)
            state_label = rule.get_state_label(wf_info.current_step)
            is_final = state_def is not None and state_def.final
        else:
            state_label = wf_info.current_step
            is_final = False

        badge_color = CLR_SUCCESS if is_final else CLR_PRIMARY
        badge = QLabel(state_label)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(status_badge(badge_color))
        row_layout.addWidget(badge)
        row_layout.addStretch()

        # Progress bar
        pct = completion_percent(wf_info, rule) if rule else 0
        chunk_color = CLR_SUCCESS if is_final else CLR_PRIMARY
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(pct)
        bar.setFixedWidth(120)
        bar.setFixedHeight(PROGRESS_H)
        bar.setTextVisible(False)
        bar.setStyleSheet(progress_bar(chunk_color))
        row_layout.addWidget(bar)

        pct_lbl = QLabel(f"{pct} %")
        pct_lbl.setStyleSheet(f"color: #555555; font-size: {FONT_BASE}px;")
        pct_lbl.setFixedWidth(42)
        pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(pct_lbl)

        # History count
        hist_count = len(wf_info.history)
        if hist_count:
            hist_lbl = QLabel(self.tr("%n step(s)", "", hist_count))
            hist_lbl.setStyleSheet(f"color: #9e9e9e; font-size: {FONT_SM}px;")
            hist_lbl.setMinimumWidth(60)
            row_layout.addWidget(hist_lbl)

        return frame
