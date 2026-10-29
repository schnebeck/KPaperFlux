"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/body_fields_tab.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Generic MetadataEditor tab for one semantic body (statement,
                correspondence, payslip): a form of editable scalar fields and
                an optional read-only table for the body's list (bookings,
                payslip items). Labels are supplied by the editor via tr().
------------------------------------------------------------------------------
"""

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Set

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QFormLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


def _as_text(value: Any) -> str:
    """Display text of a stored value."""
    if value is None:
        return ""
    if isinstance(value, (float, Decimal)) and not isinstance(value, bool):
        return f"{value:.2f}"  # amounts (stored as JSON numbers)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v is not None)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _is_meaningful(value: Any) -> bool:
    """True for non-empty scalars and containers with meaningful content."""
    if isinstance(value, dict):
        return any(_is_meaningful(v) for v in value.values())
    if isinstance(value, list):
        return any(_is_meaningful(v) for v in value)
    return value is not None and value != ""


class BodyFieldsTab(QScrollArea):
    """Editable form of one semantic body plus an optional table for its list field."""

    #: Emitted with the field key when the user edits a field.
    field_edited = pyqtSignal(str)

    def __init__(self, body_key: str, fields: Sequence[str], multiline: Optional[Set[str]] = None,
                 list_fields: Optional[Set[str]] = None, table_key: Optional[str] = None,
                 table_columns: Sequence[str] = (), parent: Optional[QWidget] = None) -> None:
        """
        Args:
            body_key: Key in semantic_data.bodies, e.g. 'statement_body'.
            fields: Scalar field keys shown as form rows (in this order).
            multiline: Keys edited in a multi-line box.
            list_fields: Keys holding a list of strings (edited comma-separated).
            table_key: Key of the list of rows shown in the table (None: no table).
            table_columns: Row keys shown as table columns.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.body_key = body_key
        self.fields: List[str] = list(fields)
        self.multiline = set(multiline or ())
        self.list_fields = set(list_fields or ())
        self.table_key = table_key
        self.table_columns: List[str] = list(table_columns)
        self._loading = False
        self._edited: Set[str] = set()

        self.setWidgetResizable(True)
        content = QWidget()
        self.setWidget(content)
        layout = QVBoxLayout(content)
        form = QFormLayout()
        layout.addLayout(form)

        self.labels: Dict[str, QLabel] = {}
        self.editors: Dict[str, QWidget] = {}
        for key in self.fields:
            label = QLabel(key)
            editor: QWidget = QPlainTextEdit() if key in self.multiline else QLineEdit()
            if isinstance(editor, QPlainTextEdit):
                editor.setMaximumHeight(90)
                editor.textChanged.connect(lambda k=key: self._on_edit(k))
            else:
                editor.textEdited.connect(lambda _text, k=key: self._on_edit(k))
            self.labels[key] = label
            self.editors[key] = editor
            form.addRow(label, editor)

        self.table_title = QLabel("")
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnCount(len(self.table_columns))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table_title)
        layout.addWidget(self.table)
        self.table_title.setVisible(table_key is not None)
        self.table.setVisible(table_key is not None)
        layout.addStretch()

    # ------------------------------------------------------------------ labels

    def set_labels(self, field_labels: Dict[str, str], table_title: str = "",
                   column_labels: Optional[Dict[str, str]] = None) -> None:
        """
        Applies translated labels.

        Args:
            field_labels: Field key -> label.
            table_title: Heading of the table.
            column_labels: Table column key -> header label.
        """
        for key, label in self.labels.items():
            label.setText(field_labels.get(key, key))
        self.table_title.setText(table_title)
        columns = column_labels or {}
        self.table.setHorizontalHeaderLabels([columns.get(c, c) for c in self.table_columns])

    # ------------------------------------------------------------------ data

    def path_of(self, key: str) -> str:
        """Dotted semantic_data path of a field (as used by the engine's review state)."""
        return f"bodies.{self.body_key}.{key}"

    @staticmethod
    def has_content(body: Any) -> bool:
        """True if the body carries any meaningful value."""
        return _is_meaningful(body)

    def load(self, body: Optional[Dict[str, Any]]) -> None:
        """
        Shows a body (dict) without emitting edit signals.

        Args:
            body: The body as dict, or None to clear.
        """
        body = body or {}
        self._loading = True
        self._edited.clear()
        try:
            for key, editor in self.editors.items():
                text = _as_text(body.get(key))
                if isinstance(editor, QPlainTextEdit):
                    editor.setPlainText(text)
                else:
                    editor.setText(text)
            rows = body.get(self.table_key) if self.table_key else None
            rows = rows if isinstance(rows, list) else []
            self.table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, column in enumerate(self.table_columns):
                    value = row.get(column) if isinstance(row, dict) else None
                    self.table.setItem(r, c, QTableWidgetItem(_as_text(value)))
            self.table.resizeColumnsToContents()
        finally:
            self._loading = False

    def edited_values(self) -> Dict[str, Any]:
        """
        Values of the fields the user edited since load() (others are untouched).

        Returns:
            Field key -> value (None for empty, list for list fields).
        """
        values: Dict[str, Any] = {}
        for key in self._edited:
            editor = self.editors[key]
            text = editor.toPlainText() if isinstance(editor, QPlainTextEdit) else editor.text()
            text = text.strip()
            if key in self.list_fields:
                values[key] = [part.strip() for part in text.split(",") if part.strip()]
            else:
                values[key] = text or None
        return values

    def _on_edit(self, key: str) -> None:
        """Records a user edit."""
        if self._loading:
            return
        self._edited.add(key)
        self.field_edited.emit(key)
