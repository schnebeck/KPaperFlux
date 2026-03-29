"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/workflow_history_widget.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Timeline view of workflow transition history per document.
                Displays WorkflowLog entries as a read-only table, grouped
                by workflow rule.
------------------------------------------------------------------------------
"""
from datetime import datetime
from typing import Dict

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models.semantic import WorkflowInfo
from core.workflow import WorkflowRuleRegistry
from gui.theme import FONT_BASE, placeholder_label


class WorkflowHistoryWidget(QWidget):
    """Timeline view of workflow transition history for a single document."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(10, 10, 10, 10)
        self._content_layout.setSpacing(12)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

    # ── Public API ────────────────────────────────────────────────────────────

    def update_workflows(self, workflows: Dict[str, WorkflowInfo], registry: WorkflowRuleRegistry) -> None:
        """Populate the widget from a dict of WorkflowInfo objects."""
        # Clear all existing children (all but the trailing stretch)
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Check if there is any history at all
        has_history = any(bool(wf.history) for wf in workflows.values())

        if not workflows or not has_history:
            placeholder = QLabel(self.tr("No workflow history yet."))
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet(placeholder_label())
            self._content_layout.insertWidget(0, placeholder)
            return

        insert_pos = 0
        for rule_id, wf_info in workflows.items():
            if not wf_info.history:
                continue

            rule = registry.get_rule(rule_id)
            display_name = rule.get_display_name() if rule else rule_id

            # Section header
            header_label = QLabel(display_name)
            header_label.setStyleSheet(
                f"font-weight: bold; font-size: {FONT_BASE + 1}px; margin-top: 4px;"
            )
            self._content_layout.insertWidget(insert_pos, header_label)
            insert_pos += 1

            # Table
            table = self._build_table(wf_info)
            self._content_layout.insertWidget(insert_pos, table)
            insert_pos += 1

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_table(self, wf_info: WorkflowInfo) -> QTableWidget:
        """Build a read-only QTableWidget for the history of one WorkflowInfo."""
        columns = [
            self.tr("Timestamp"),
            self.tr("Step / Action"),
            self.tr("User"),
            self.tr("Comment"),
        ]
        entries = list(reversed(wf_info.history))

        table = QTableWidget(len(entries), len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        for row, log in enumerate(entries):
            # Timestamp — parse ISO and reformat
            try:
                ts = datetime.fromisoformat(log.timestamp).strftime("%d.%m.%Y %H:%M")
            except (ValueError, TypeError):
                ts = log.timestamp or ""

            # Action — strip "TRANSITION: " prefix for readability
            action = log.action or ""
            if action.startswith("TRANSITION: "):
                action = action[len("TRANSITION: "):]

            user = log.user or ""
            comment = log.comment or ""

            table.setItem(row, 0, QTableWidgetItem(ts))
            table.setItem(row, 1, QTableWidgetItem(action))
            table.setItem(row, 2, QTableWidgetItem(user))
            table.setItem(row, 3, QTableWidgetItem(comment))

        # Adjust table height to fit all rows without internal scroll bar
        table.resizeRowsToContents()
        total_height = table.horizontalHeader().height() + 4
        for r in range(table.rowCount()):
            total_height += table.rowHeight(r)
        table.setFixedHeight(total_height)

        return table
