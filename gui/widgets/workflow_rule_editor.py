"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/workflow_rule_editor.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Workflow rule editor widgets: WorkflowLocaleDialog for
                per-locale name/description/state-label overrides, and
                WorkflowRuleFormEditor for structured editing of a single rule.
------------------------------------------------------------------------------
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QTimer, QSettings
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame,
    QLineEdit, QPlainTextEdit, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QToolButton, QDialog, QComboBox,
    QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox, QListWidget,
    QLabel, QPushButton, QMessageBox, QProgressBar, QSizePolicy,
)

from core.logger import get_logger
from core.workflow import (
    WorkflowRule, WorkflowState, WorkflowTransition,
    WorkflowCondition, WorkflowL10nPatch, StateType,
    WORKFLOW_FIELD_CATALOG, WORKFLOW_FIELD_GROUPS,
)
from gui.widgets.workflow_graph import WorkflowGraphWidget, StateNode, TransitionEdge

logger = get_logger("gui.widgets.workflow_rule_editor")


# ---------------------------------------------------------------------------
# WorkflowLocaleDialog
# ---------------------------------------------------------------------------

class WorkflowLocaleDialog(QDialog):
    """Dialog for managing per-locale name/description/state-label overrides.

    The dialog edits a *copy* of the rule's l10n dict and creator_locale.
    Call ``get_result()`` after ``exec()`` returns ``Accepted``.
    """

    _COMMON_LOCALES = [
        ("de", "Deutsch"),
        ("en", "English"),
        ("fr", "Français"),
        ("es", "Español"),
        ("it", "Italiano"),
        ("nl", "Nederlands"),
        ("pl", "Polski"),
        ("pt", "Português"),
    ]

    def __init__(self, rule: WorkflowRule, parent=None):
        super().__init__(parent)
        self._rule = rule
        # Deep-copy so we don't mutate the live rule
        self._l10n: Dict[str, WorkflowL10nPatch] = {
            k: WorkflowL10nPatch(
                name=v.name,
                description=v.description,
                states=dict(v.states),
            )
            for k, v in rule.l10n.items()
        }
        self._creator_locale: str = rule.creator_locale
        self._selected_locale: Optional[str] = None
        self._init_ui()
        # Select first available locale
        if self._l10n:
            first = next(iter(self._l10n))
            self._select_locale(first)

    # ── Construction ──────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        self.setWindowTitle(self.tr("Workflow Localizations"))
        self.setMinimumSize(700, 500)
        root = QHBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Left: locale list ─────────────────────────────────────────────
        from gui.theme import (
            CLR_NAV_BG, CLR_BORDER, CLR_PRIMARY_LIGHT, CLR_PRIMARY,
            CLR_TEXT_MUTED, FONT_BASE, BTN_HEIGHT, placeholder_label,
        )
        left = QFrame()
        left.setFixedWidth(170)
        left.setStyleSheet(
            f"QFrame {{ background:{CLR_NAV_BG}; border-right: 1px solid {CLR_BORDER}; }}"
        )
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        hdr = QLabel(self.tr("Locales"))
        hdr.setStyleSheet(
            f"font-weight:bold; font-size:{FONT_BASE}px; padding:6px 10px; "
            f"background:{CLR_PRIMARY_LIGHT}; border-bottom:1px solid {CLR_BORDER};"
        )
        left_layout.addWidget(hdr)

        self._locale_list = QListWidget()
        self._locale_list.setStyleSheet(f"border:none; background:{CLR_NAV_BG};")
        self._locale_list.currentTextChanged.connect(self._on_locale_list_changed)
        left_layout.addWidget(self._locale_list, 1)

        btn_bar = QWidget()
        btn_bar.setStyleSheet(f"background:{CLR_NAV_BG}; border-top:1px solid {CLR_BORDER};")
        btn_bar_layout = QHBoxLayout(btn_bar)
        btn_bar_layout.setContentsMargins(4, 4, 4, 4)
        btn_bar_layout.setSpacing(4)

        self._btn_add_locale = QPushButton(self.tr("Add"))
        self._btn_add_locale.setFixedHeight(BTN_HEIGHT)
        self._btn_add_locale.clicked.connect(self._add_locale)
        btn_bar_layout.addWidget(self._btn_add_locale)

        self._btn_remove_locale = QPushButton(self.tr("Remove"))
        self._btn_remove_locale.setFixedHeight(BTN_HEIGHT)
        self._btn_remove_locale.setEnabled(False)
        self._btn_remove_locale.clicked.connect(self._remove_locale)
        btn_bar_layout.addWidget(self._btn_remove_locale)

        left_layout.addWidget(btn_bar)
        root.addWidget(left)

        # ── Right: form ───────────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 12, 16, 12)
        right_layout.setSpacing(8)

        self._creator_locale_row = QWidget()
        cl_layout = QHBoxLayout(self._creator_locale_row)
        cl_layout.setContentsMargins(0, 0, 0, 0)
        cl_layout.setSpacing(6)
        cl_lbl = QLabel(self.tr("Creator locale:"))
        cl_lbl.setToolTip(self.tr("ISO 639-1 code of the language used to write the original rule."))
        self._edit_creator_locale = QLineEdit(self._creator_locale)
        self._edit_creator_locale.setPlaceholderText("de")
        self._edit_creator_locale.setFixedWidth(60)
        self._edit_creator_locale.textChanged.connect(self._on_creator_locale_changed)
        cl_layout.addWidget(cl_lbl)
        cl_layout.addWidget(self._edit_creator_locale)
        cl_layout.addStretch()
        right_layout.addWidget(self._creator_locale_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#e0e0e0;")
        right_layout.addWidget(sep)

        self._form_placeholder = QLabel(self.tr("Select a locale from the list, or add one."))
        self._form_placeholder.setStyleSheet(f"color:{CLR_TEXT_MUTED}; font-style:italic; font-size:{FONT_BASE}px; padding:20px 0;")
        self._form_placeholder.setAlignment(Qt.AlignmentFlag.AlignTop)
        right_layout.addWidget(self._form_placeholder)

        self._form_widget = QWidget()
        self._form_widget.hide()
        form_layout = QVBoxLayout(self._form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)

        meta_form = QFormLayout()
        meta_form.setSpacing(6)
        self._edit_locale_name = QLineEdit()
        self._edit_locale_name.setPlaceholderText(self.tr("Translated rule name"))
        self._edit_locale_name.textChanged.connect(self._on_form_changed)
        meta_form.addRow(self.tr("Name:"), self._edit_locale_name)

        self._edit_locale_desc = QPlainTextEdit()
        self._edit_locale_desc.setFixedHeight(60)
        self._edit_locale_desc.setPlaceholderText(self.tr("Translated description"))
        self._edit_locale_desc.textChanged.connect(self._on_form_changed)
        meta_form.addRow(self.tr("Description:"), self._edit_locale_desc)

        form_layout.addLayout(meta_form)

        states_lbl = QLabel(self.tr("State labels:"))
        states_lbl.setStyleSheet("font-weight:bold; margin-top:6px;")
        form_layout.addWidget(states_lbl)

        self._states_table = QTableWidget(0, 2)
        self._states_table.setHorizontalHeaderLabels([self.tr("State ID"), self.tr("Translated label")])
        self._states_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._states_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._states_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked)
        self._states_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._states_table.itemChanged.connect(self._on_state_label_changed)
        self._states_table.setMinimumHeight(120)
        form_layout.addWidget(self._states_table, 1)

        right_layout.addWidget(self._form_widget, 1)

        # ── Button box ────────────────────────────────────────────────────
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._commit_current_and_accept)
        bb.rejected.connect(self.reject)
        right_layout.addWidget(bb)

        root.addWidget(right, 1)
        self._rebuild_locale_list()

    # ── List management ────────────────────────────────────────────────────

    def _rebuild_locale_list(self) -> None:
        self._locale_list.blockSignals(True)
        self._locale_list.clear()
        for code in self._l10n:
            label = self._locale_label(code)
            self._locale_list.addItem(label)
        self._locale_list.blockSignals(False)

    @staticmethod
    def _locale_label(code: str) -> str:
        for c, name in WorkflowLocaleDialog._COMMON_LOCALES:
            if c == code:
                return f"{code} — {name}"
        return code

    def _on_locale_list_changed(self, text: str) -> None:
        # Commit edits of previously selected locale before switching
        if self._selected_locale is not None:
            self._commit_current()
        code = text.split(" — ")[0].strip() if text else None
        if code and code in self._l10n:
            self._select_locale(code)
        else:
            self._selected_locale = None
            self._form_widget.hide()
            self._form_placeholder.show()
            self._btn_remove_locale.setEnabled(False)

    def _select_locale(self, code: str) -> None:
        self._selected_locale = code
        patch = self._l10n[code]

        self._states_table.blockSignals(True)
        self._edit_locale_name.blockSignals(True)
        self._edit_locale_desc.blockSignals(True)

        self._edit_locale_name.setText(patch.name)
        self._edit_locale_desc.setPlainText(patch.description)

        self._states_table.setRowCount(0)
        for state_id, state_def in self._rule.states.items():
            row = self._states_table.rowCount()
            self._states_table.insertRow(row)
            id_item = QTableWidgetItem(state_id)
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            id_item.setForeground(Qt.GlobalColor.gray)
            self._states_table.setItem(row, 0, id_item)
            translated = patch.states.get(state_id, "")
            lbl_item = QTableWidgetItem(translated)
            lbl_item.setToolTip(self.tr("Native label: %s") % (state_def.label or state_id))
            self._states_table.setItem(row, 1, lbl_item)

        self._states_table.blockSignals(False)
        self._edit_locale_name.blockSignals(False)
        self._edit_locale_desc.blockSignals(False)

        self._form_placeholder.hide()
        self._form_widget.show()
        self._btn_remove_locale.setEnabled(True)

        # Sync list selection
        for i in range(self._locale_list.count()):
            if self._locale_list.item(i).text().startswith(code):
                self._locale_list.setCurrentRow(i)
                break

    def _add_locale(self) -> None:
        # Build combo list of codes not yet present
        existing = set(self._l10n.keys())
        available = [(c, n) for c, n in self._COMMON_LOCALES if c not in existing]

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Add Locale"))
        dlg_layout = QVBoxLayout(dlg)
        lbl = QLabel(self.tr("Choose locale to add:"))
        dlg_layout.addWidget(lbl)
        combo = QComboBox()
        combo.setEditable(True)
        for code, name in available:
            combo.addItem(f"{code} — {name}", code)
        dlg_layout.addWidget(combo)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        dlg_layout.addWidget(bb)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        raw = combo.currentText().strip()
        code = raw.split(" — ")[0].strip().lower()
        if not code or code in self._l10n:
            return

        # Pre-fill with creator's native values
        self._l10n[code] = WorkflowL10nPatch(
            name=self._rule.name,
            description=self._rule.description,
            states={sid: sd.label for sid, sd in self._rule.states.items() if sd.label},
        )
        self._rebuild_locale_list()
        self._select_locale(code)

    def _remove_locale(self) -> None:
        if not self._selected_locale:
            return
        reply = QMessageBox.question(
            self,
            self.tr("Remove Locale"),
            self.tr("Remove all translations for locale '%s'?") % self._selected_locale,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self._l10n[self._selected_locale]
            self._selected_locale = None
            self._rebuild_locale_list()
            self._form_widget.hide()
            self._form_placeholder.show()
            self._btn_remove_locale.setEnabled(False)

    # ── Form sync ──────────────────────────────────────────────────────────

    def _on_creator_locale_changed(self, text: str) -> None:
        self._creator_locale = text.strip().lower()

    def _on_form_changed(self) -> None:
        pass  # Changes are read from widgets on commit

    def _on_state_label_changed(self, item: QTableWidgetItem) -> None:
        pass  # Changes are read from table on commit

    def _commit_current(self) -> None:
        if self._selected_locale is None or self._selected_locale not in self._l10n:
            return
        patch = self._l10n[self._selected_locale]
        patch.name = self._edit_locale_name.text().strip()
        patch.description = self._edit_locale_desc.toPlainText().strip()
        for row in range(self._states_table.rowCount()):
            id_item = self._states_table.item(row, 0)
            lbl_item = self._states_table.item(row, 1)
            if id_item and lbl_item:
                state_id = id_item.text()
                label = lbl_item.text().strip()
                if label:
                    patch.states[state_id] = label
                else:
                    patch.states.pop(state_id, None)

    def _commit_current_and_accept(self) -> None:
        self._commit_current()
        self.accept()

    # ── Public API ─────────────────────────────────────────────────────────

    def get_result(self) -> tuple[str, Dict[str, WorkflowL10nPatch]]:
        """Return (creator_locale, l10n_dict) after dialog was accepted."""
        return self._creator_locale, self._l10n


# ---------------------------------------------------------------------------
# WorkflowRuleFormEditor
# ---------------------------------------------------------------------------

class WorkflowRuleFormEditor(QWidget):
    """Structured editor for a single Rule."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.current_rule = None
        self._lock_signals = False
        # Start in the neutral "nothing selected" state
        self.clear()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)

        # ── Left panel: rule metadata ──────────────────────────────────────
        self._left_panel = QFrame()
        self._left_panel.setMinimumWidth(0)
        lp_layout = QVBoxLayout(self._left_panel)
        lp_layout.setContentsMargins(0, 0, 0, 0)
        lp_layout.setSpacing(0)

        from gui.theme import (
            CLR_PRIMARY_LIGHT, CLR_BORDER, CLR_BORDER_STRONG,
            CLR_PRIMARY, CLR_TEXT_MUTED, CLR_TEXT_SECONDARY,
            CLR_SURFACE_ROW, CLR_SURFACE_HOVER,
            FONT_BASE, FONT_SM, FONT_LG, BTN_HEIGHT,
        )
        _hdr_style = f"background:{CLR_PRIMARY_LIGHT}; border-bottom:1px solid {CLR_BORDER};"
        _hdr_lbl_style = f"font-weight:bold; color:{CLR_PRIMARY}; font-size:{FONT_BASE}px;"

        lp_hdr = QFrame()
        lp_hdr.setFixedHeight(BTN_HEIGHT)
        lp_hdr.setStyleSheet(_hdr_style)
        lp_hdr_layout = QHBoxLayout(lp_hdr)
        lp_hdr_layout.setContentsMargins(6, 0, 4, 0)
        self.lbl_rule_panel = QLabel()
        self.lbl_rule_panel.setStyleSheet(_hdr_lbl_style)
        lp_hdr_layout.addWidget(self.lbl_rule_panel)
        lp_hdr_layout.addStretch()
        self._btn_locale = QToolButton()
        self._btn_locale.setText("⚙")
        self._btn_locale.setFixedSize(20, 20)
        self._btn_locale.setStyleSheet(f"QToolButton {{ border:none; font-size:{FONT_BASE}px; }}")
        self._btn_locale.clicked.connect(self._open_locale_dialog)
        lp_hdr_layout.addWidget(self._btn_locale)
        lp_layout.addWidget(lp_hdr)

        self._left_content = QWidget()
        lc_layout = QFormLayout(self._left_content)
        self._lc_layout = lc_layout
        lc_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        lc_layout.setContentsMargins(6, 6, 6, 6)
        lc_layout.setSpacing(4)
        lc_layout.setHorizontalSpacing(6)

        self.edit_name = QLineEdit()
        self.edit_desc = QPlainTextEdit()
        self.edit_desc.setFixedHeight(60)
        self.edit_desc.setPlaceholderText(self.tr("What does this rule do?"))
        self.edit_triggers = QLineEdit()
        self.edit_name.textChanged.connect(self._on_changed)
        self.edit_desc.textChanged.connect(self._on_changed)
        self.edit_triggers.textChanged.connect(self._on_changed)

        self.lbl_name = QLabel()
        self.lbl_desc = QLabel()
        self.lbl_triggers = QLabel()
        lc_layout.addRow(self.lbl_name, self.edit_name)
        lc_layout.addRow(self.lbl_desc, self.edit_desc)
        lc_layout.addRow(self.lbl_triggers, self.edit_triggers)

        lp_layout.addWidget(self._left_content)
        lp_layout.addStretch(1)
        self._splitter.addWidget(self._left_panel)

        # ── Center: graph + edge collapse buttons ─────────────────────────
        # The collapse buttons live on the graph's edges so they remain
        # visible even when the adjacent side panel is fully collapsed.
        _edge_btn_style = f"""
            QToolButton {{
                background: {CLR_SURFACE_ROW};
                color: {CLR_TEXT_SECONDARY};
                border: none;
                font-size: {FONT_LG}px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                background: {CLR_PRIMARY_LIGHT};
                color: {CLR_PRIMARY};
            }}
        """
        _center_frame = QFrame()
        _center_layout = QHBoxLayout(_center_frame)
        _center_layout.setContentsMargins(0, 0, 0, 0)
        _center_layout.setSpacing(0)

        self._btn_collapse_left = QToolButton()
        self._btn_collapse_left.setFixedWidth(18)
        self._btn_collapse_left.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._btn_collapse_left.setStyleSheet(
            _edge_btn_style + f"QToolButton {{ border-right: 1px solid {CLR_BORDER}; }}")
        self._btn_collapse_left.clicked.connect(self._toggle_left)
        _center_layout.addWidget(self._btn_collapse_left)

        self._graph_widget = WorkflowGraphWidget(mode="edit", inline_detail=False)
        self._graph_widget.rule_changed.connect(self._on_changed)
        self._graph_widget.item_selected.connect(self._on_item_selected)
        _center_layout.addWidget(self._graph_widget, 1)

        self._btn_collapse_right = QToolButton()
        self._btn_collapse_right.setFixedWidth(18)
        self._btn_collapse_right.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._btn_collapse_right.setStyleSheet(
            _edge_btn_style + f"QToolButton {{ border-left: 1px solid {CLR_BORDER}; }}")
        self._btn_collapse_right.clicked.connect(self._toggle_right)
        _center_layout.addWidget(self._btn_collapse_right)

        self._splitter.addWidget(_center_frame)

        # ── Right panel: state/transition properties ───────────────────────
        self._right_panel = QFrame()
        self._right_panel.setMinimumWidth(0)
        rp_layout = QVBoxLayout(self._right_panel)
        rp_layout.setContentsMargins(0, 0, 0, 0)
        rp_layout.setSpacing(0)

        rp_hdr = QFrame()
        rp_hdr.setFixedHeight(BTN_HEIGHT)
        rp_hdr.setStyleSheet(_hdr_style)
        rp_hdr_layout = QHBoxLayout(rp_hdr)
        rp_hdr_layout.setContentsMargins(6, 0, 6, 0)
        self.lbl_props_panel = QLabel()
        self.lbl_props_panel.setStyleSheet(_hdr_lbl_style)
        rp_hdr_layout.addWidget(self.lbl_props_panel)
        rp_layout.addWidget(rp_hdr)

        self._right_content = QWidget()
        rc_layout = QVBoxLayout(self._right_content)
        rc_layout.setContentsMargins(8, 8, 8, 8)
        rc_layout.setSpacing(6)

        self._detail_hint = QLabel()
        self._detail_hint.setStyleSheet(f"color:{CLR_TEXT_MUTED}; font-style:italic; font-size:{FONT_BASE}px;")
        self._detail_hint.setWordWrap(True)
        rc_layout.addWidget(self._detail_hint)

        self._detail_form = QFrame()
        self._detail_form_layout = QFormLayout(self._detail_form)
        self._detail_form_layout.setContentsMargins(0, 0, 0, 0)
        self._detail_form_layout.setSpacing(6)
        self._detail_form.hide()
        rc_layout.addWidget(self._detail_form)
        rc_layout.addStretch(1)

        rp_layout.addWidget(self._right_content, 1)
        self._splitter.addWidget(self._right_panel)

        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

        layout.addWidget(self._splitter, 1)

        # Collapse state
        self._left_expanded = True
        self._right_expanded = True
        self._left_saved_w = 220
        self._right_saved_w = 240

        # Drag: freeze expensive graph, update side forms live
        self._drag_restore_timer = QTimer(self)
        self._drag_restore_timer.setSingleShot(True)
        self._drag_restore_timer.setInterval(150)
        self._drag_restore_timer.timeout.connect(self._on_splitter_drag_end)
        self._splitter.splitterMoved.connect(self._on_splitter_dragging)

        QTimer.singleShot(0, self._init_splitter_sizes)
        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        """Updates all UI strings for on-the-fly localization."""
        self.lbl_rule_panel.setText(self.tr("Workflow"))
        self.lbl_props_panel.setText(self.tr("Properties"))
        self._detail_hint.setText(self.tr("Select a state or transition to edit its properties."))
        self._btn_locale.setToolTip(self.tr("Manage localizations"))
        self._update_collapse_buttons()

        self.lbl_name.setText(self.tr("Rule Name:"))
        self.lbl_desc.setText(self.tr("Description:"))
        self.lbl_triggers.setText(self.tr("Tag Triggers:"))
        self.lbl_triggers.setToolTip(self.tr("Comma-separated type_tags that activate this rule (e.g. INVOICE, ORDER_CONFIRMATION). Multiple rules may share the same tag."))

        self.edit_name.setPlaceholderText(self.tr("Enter rule name..."))
        self.edit_desc.setPlaceholderText(self.tr("What does this rule do?"))
        self.edit_triggers.setPlaceholderText(self.tr("INVOICE, ORDER_CONFIRMATION, ..."))

    def _on_changed(self):
        if not self._lock_signals:
            self.changed.emit()

    def clear(self) -> None:
        """Reset to the neutral 'nothing selected' state."""
        self._lock_signals = True
        self.current_rule = None
        self.edit_name.clear()
        self.edit_desc.clear()
        self.edit_triggers.clear()
        for w in (self.edit_name, self.edit_desc, self.edit_triggers,
                  self._btn_locale):
            w.setEnabled(False)
        self._graph_widget._rule = None
        self._graph_widget._rebuild()
        self._lock_signals = False

    def load_rule(self, rule: WorkflowRule):
        self._lock_signals = True
        self.current_rule = rule
        for w in (self.edit_name, self.edit_desc, self.edit_triggers,
                  self._btn_locale):
            w.setEnabled(True)
        self.edit_name.setText(rule.name)
        self.edit_desc.setPlainText(rule.description)
        triggers = rule.triggers.get("type_tags", [])
        self.edit_triggers.setText(", ".join(triggers))
        self._graph_widget.load(rule)
        self._lock_signals = False

    def get_rule(self) -> WorkflowRule:
        pb_id = self.current_rule.id if self.current_rule else "new_rule"
        name = self.edit_name.text().strip()
        desc = self.edit_desc.toPlainText().strip()
        triggers = [t.strip() for t in self.edit_triggers.text().split(",") if t.strip()]
        graph_rule = self._graph_widget.get_rule()
        states = graph_rule.states if graph_rule else {}
        node_positions = graph_rule.node_positions if graph_rule else {}
        transition_anchors = graph_rule.transition_anchors if graph_rule else {}
        transition_bends = graph_rule.transition_bends if graph_rule else {}
        # Preserve l10n data and creator_locale from the live rule
        creator_locale = self.current_rule.creator_locale if self.current_rule else ""
        l10n = dict(self.current_rule.l10n) if self.current_rule else {}
        return WorkflowRule(
            id=pb_id, name=name, description=desc, states=states,
            triggers={"type_tags": triggers}, node_positions=node_positions,
            transition_anchors=transition_anchors,
            transition_bends=transition_bends,
            creator_locale=creator_locale, l10n=l10n,
        )

    def _open_locale_dialog(self) -> None:
        """Open the WorkflowLocaleDialog to manage l10n overrides."""
        rule = self.get_rule()
        dlg = WorkflowLocaleDialog(rule, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            creator_locale, l10n = dlg.get_result()
            if self.current_rule:
                self.current_rule.creator_locale = creator_locale
                self.current_rule.l10n = l10n
            self._on_changed()

    # ── Splitter drag helpers ──────────────────────────────────────────────────

    _WRAP_THRESHOLD = 260   # px — below this width labels move above fields

    def _on_splitter_dragging(self) -> None:
        """Called on every splitterMoved tick: update forms live, debounce fit."""
        self._update_form_wrap()
        self._drag_restore_timer.start()   # restart 150 ms countdown

    def _on_splitter_drag_end(self) -> None:
        """Fit view and persist sizes after drag has settled."""
        QTimer.singleShot(0, self._graph_widget._fit_view)
        self._save_splitter_sizes()   # single write after drag ends, not on every pixel

    def _update_form_wrap(self) -> None:
        """Switch QFormLayout label placement based on current panel widths.

        Guards against redundant setRowWrapPolicy calls to avoid unnecessary
        layout reflows on every splitterMoved event.
        """
        from PyQt6.QtWidgets import QFormLayout  # noqa: PLC0415
        lw = self._left_panel.width()
        want_left = (QFormLayout.RowWrapPolicy.WrapAllRows
                     if lw < self._WRAP_THRESHOLD
                     else QFormLayout.RowWrapPolicy.DontWrapRows)
        if self._lc_layout.rowWrapPolicy() != want_left:
            self._lc_layout.setRowWrapPolicy(want_left)

        rw = self._right_panel.width()
        want_right = (QFormLayout.RowWrapPolicy.WrapAllRows
                      if rw < self._WRAP_THRESHOLD
                      else QFormLayout.RowWrapPolicy.DontWrapRows)
        if self._detail_form_layout.rowWrapPolicy() != want_right:
            self._detail_form_layout.setRowWrapPolicy(want_right)

    def _init_splitter_sizes(self) -> None:
        settings = QSettings("KPaperFlux", "WorkflowEditor")
        saved = settings.value("splitter_sizes")
        if saved:
            sizes = [int(x) for x in saved]
            # Only restore if all three values are positive (no collapsed-panel remnants)
            if len(sizes) == 3 and all(s > 0 for s in sizes):
                self._left_saved_w = sizes[0]
                self._right_saved_w = sizes[2]
                self._splitter.setSizes(sizes)
                self._update_form_wrap()
                return
        total = self._splitter.width()
        if total > 100:
            center = max(200, total - self._left_saved_w - self._right_saved_w)
            self._splitter.setSizes([self._left_saved_w, center, self._right_saved_w])
        self._update_form_wrap()

    def _save_splitter_sizes(self) -> None:
        # Only persist when both panels are visible so restore always starts expanded
        if self._left_expanded and self._right_expanded:
            settings = QSettings("KPaperFlux", "WorkflowEditor")
            settings.setValue("splitter_sizes", self._splitter.sizes())

    def _update_collapse_buttons(self) -> None:
        if hasattr(self, "_btn_collapse_left"):
            self._btn_collapse_left.setText("◀" if self._left_expanded else "▶")
        if hasattr(self, "_btn_collapse_right"):
            self._btn_collapse_right.setText("▶" if self._right_expanded else "◀")

    def _toggle_left(self) -> None:
        if self._left_expanded:
            # Save current width before hiding
            sizes = self._splitter.sizes()
            self._left_saved_w = max(sizes[0], 80)
            self._left_panel.hide()
            self._left_expanded = False
        else:
            self._left_panel.show()
            # Redistribute: give the panel its saved width back
            sizes = self._splitter.sizes()
            # sizes[0] may be the minimum size hint Qt assigned on show()
            # Recalculate: left gets saved_w, center absorbs the difference
            total_lc = sizes[0] + sizes[1]
            center = max(50, total_lc - self._left_saved_w)
            self._splitter.setSizes([self._left_saved_w, center, sizes[2]])
            self._left_expanded = True
        self._update_collapse_buttons()

    def _toggle_right(self) -> None:
        if self._right_expanded:
            sizes = self._splitter.sizes()
            self._right_saved_w = max(sizes[2], 80)
            self._right_panel.hide()
            self._right_expanded = False
        else:
            self._right_panel.show()
            sizes = self._splitter.sizes()
            total_cr = sizes[1] + sizes[2]
            center = max(50, total_cr - self._right_saved_w)
            self._splitter.setSizes([sizes[0], center, self._right_saved_w])
            self._right_expanded = True
        self._update_collapse_buttons()

    def _on_item_selected(self, item) -> None:
        fl = self._detail_form_layout
        while fl.rowCount():
            fl.removeRow(0)
        if item is None:
            self._detail_hint.show()
            self._detail_form.hide()
            return
        self._detail_hint.hide()
        self._detail_form.show()
        if isinstance(item, StateNode):
            self._fill_state_detail(item, fl)
        elif isinstance(item, TransitionEdge):
            self._fill_transition_detail(item, fl)

    def _fill_state_detail(self, node: "StateNode", fl) -> None:
        lbl_edit = QLineEdit(node.state_def.label)
        fl.addRow(self.tr("Label:"), lbl_edit)

        type_combo = QComboBox()
        _type_labels = {
            StateType.START: self.tr("START — Entry point"),
            StateType.NORMAL: self.tr("NORMAL — Intermediate"),
            StateType.END_OK: self.tr("END OK — Positive terminal"),
            StateType.END_NOK: self.tr("END NOK — Negative terminal"),
            StateType.END_NEUTRAL: self.tr("END NEUTRAL — Neutral terminal"),
        }
        for st, label in _type_labels.items():
            type_combo.addItem(label, userData=st)
        current_type = node.state_def.state_type
        idx = list(_type_labels.keys()).index(current_type) if current_type in _type_labels else 1
        type_combo.setCurrentIndex(idx)
        fl.addRow(self.tr("Type:"), type_combo)

        def _apply():
            try:
                new_label = lbl_edit.text().strip()
                chosen_type: StateType = type_combo.currentData()
            except RuntimeError:
                return  # stale deferred call — widgets already deleted
            node.state_def.label = new_label
            node.state_def.state_type = chosen_type
            # Sync legacy flags
            node.state_def.final = chosen_type in (StateType.END_OK, StateType.END_NOK, StateType.END_NEUTRAL)
            # Radio semantics: only one START per rule
            if chosen_type == StateType.START:
                for sdef in self._graph_widget._rule.states.values():
                    if sdef is not node.state_def:
                        sdef.initial = False
                        if sdef.state_type == StateType.START:
                            sdef.state_type = StateType.NORMAL
            node.state_def.initial = (chosen_type == StateType.START)
            self._graph_widget._rebuild()
            self._on_changed()
            QTimer.singleShot(0, lambda nid=node.state_id: (
                self._graph_widget._nodes.get(nid) and
                self._graph_widget._nodes[nid].setSelected(True)
            ))

        lbl_edit.editingFinished.connect(lambda: QTimer.singleShot(0, _apply))
        type_combo.currentIndexChanged.connect(lambda _: QTimer.singleShot(0, _apply))

    def _fill_transition_detail(self, edge: "TransitionEdge", fl) -> None:
        t = edge.transition
        src_id = edge.src.state_id
        action_id = t.action  # captured now — stable ID for re-select after rebuild

        label_edit = QLineEdit(t.label or t.action)
        fl.addRow(self.tr("Label:"), label_edit)

        auto_chk = QCheckBox()
        auto_chk.setChecked(t.auto)
        fl.addRow(self.tr("Auto:"), auto_chk)

        # ── Required-fields picker ────────────────────────────────────────────
        req_tree = QTreeWidget()
        req_tree.setHeaderHidden(True)
        req_tree.setRootIsDecorated(False)
        req_tree.setIndentation(16)
        req_tree.setMinimumHeight(120)
        req_tree.setMaximumHeight(180)

        _field_items: dict[str, QTreeWidgetItem] = {}
        _groups_seen: dict[str, QTreeWidgetItem] = {}
        for group_key, field_key, field_label in WORKFLOW_FIELD_CATALOG:
            if group_key not in _groups_seen:
                grp_item = QTreeWidgetItem(req_tree, [self.tr(WORKFLOW_FIELD_GROUPS[group_key])])
                grp_item.setFlags(grp_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                grp_item.setExpanded(True)
                font = grp_item.font(0)
                font.setBold(True)
                grp_item.setFont(0, font)
                _groups_seen[group_key] = grp_item
            child = QTreeWidgetItem(_groups_seen[group_key], [self.tr(field_label)])
            child.setData(0, Qt.ItemDataRole.UserRole, field_key)
            child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = Qt.CheckState.Checked if field_key in t.required_fields else Qt.CheckState.Unchecked
            child.setCheckState(0, checked)
            _field_items[field_key] = child
        fl.addRow(self.tr("Required Fields:"), req_tree)
        # ── End required-fields picker ────────────────────────────────────────

        # ── Condition editor ──────────────────────────────────────────────────
        cond_container = QWidget()
        cond_vbox = QVBoxLayout(cond_container)
        cond_vbox.setContentsMargins(0, 0, 0, 0)
        cond_vbox.setSpacing(3)

        _OPS = [">", "<", ">=", "<=", "=", "!="]
        _FIELD_KEYS = [fk for _, fk, _ in WORKFLOW_FIELD_CATALOG]

        def _make_field_combo(selected_key: str) -> QComboBox:
            combo = QComboBox()
            for _, fk, fl in WORKFLOW_FIELD_CATALOG:
                combo.addItem(self.tr(fl), userData=fk)
            idx = _FIELD_KEYS.index(selected_key) if selected_key in _FIELD_KEYS else 0
            combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(lambda _: QTimer.singleShot(0, _apply))
            return combo

        cond_table = QTableWidget(0, 3)
        cond_table.setHorizontalHeaderLabels([
            self.tr("Field"), self.tr("Op"), self.tr("Value"),
        ])
        cond_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        cond_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        cond_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        cond_table.setColumnWidth(1, 50)
        cond_table.verticalHeader().setVisible(False)
        cond_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        cond_table.setMinimumHeight(80)
        cond_table.setMaximumHeight(160)

        def _populate_cond_table():
            cond_table.setRowCount(0)
            for cond in t.conditions:
                row = cond_table.rowCount()
                cond_table.insertRow(row)
                cond_table.setCellWidget(row, 0, _make_field_combo(cond.field))
                op_combo = QComboBox()
                for op in _OPS:
                    op_combo.addItem(op)
                if cond.op in _OPS:
                    op_combo.setCurrentIndex(_OPS.index(cond.op))
                op_combo.currentIndexChanged.connect(lambda _: QTimer.singleShot(0, _apply))
                cond_table.setCellWidget(row, 1, op_combo)
                cond_table.setItem(row, 2, QTableWidgetItem(str(cond.value)))
                cond_table.setRowHeight(row, 24)

        _populate_cond_table()
        cond_vbox.addWidget(cond_table)

        btn_row = QWidget()
        btn_hbox = QHBoxLayout(btn_row)
        btn_hbox.setContentsMargins(0, 0, 0, 0)
        btn_hbox.setSpacing(4)
        btn_add = QPushButton(self.tr("+ Condition"))
        btn_add.setFixedHeight(22)
        btn_del = QPushButton(self.tr("− Remove"))
        btn_del.setFixedHeight(22)
        btn_hbox.addWidget(btn_add)
        btn_hbox.addWidget(btn_del)
        btn_hbox.addStretch()
        cond_vbox.addWidget(btn_row)

        fl.addRow(self.tr("Conditions:"), cond_container)

        def _read_conditions() -> list:
            rows = []
            for r in range(cond_table.rowCount()):
                field_widget = cond_table.cellWidget(r, 0)
                op_widget = cond_table.cellWidget(r, 1)
                val_item = cond_table.item(r, 2)
                field = field_widget.currentData() if field_widget else ""
                op = op_widget.currentText() if op_widget else "="
                val_raw = val_item.text().strip() if val_item else ""
                if not field or not val_raw:
                    continue
                try:
                    val: float | str = float(val_raw)
                except ValueError:
                    val = val_raw
                rows.append(WorkflowCondition(field=field, op=op, value=val))
            return rows

        def _on_add_condition():
            row = cond_table.rowCount()
            cond_table.insertRow(row)
            # Default to DAYS_IN_STATE — the most common timed condition
            default_key = "DAYS_IN_STATE"
            cond_table.setCellWidget(row, 0, _make_field_combo(default_key))
            op_combo = QComboBox()
            for op in _OPS:
                op_combo.addItem(op)
            op_combo.currentIndexChanged.connect(lambda _: QTimer.singleShot(0, _apply))
            cond_table.setCellWidget(row, 1, op_combo)
            cond_table.setItem(row, 2, QTableWidgetItem("0"))
            cond_table.setRowHeight(row, 24)
            cond_table.setCurrentCell(row, 2)
            QTimer.singleShot(0, _apply)

        def _on_del_condition():
            rows = sorted({i.row() for i in cond_table.selectedItems()}, reverse=True)
            for r in rows:
                cond_table.removeRow(r)
            QTimer.singleShot(0, _apply)

        btn_add.clicked.connect(_on_add_condition)
        btn_del.clicked.connect(_on_del_condition)
        # ── End condition editor ──────────────────────────────────────────────

        def _read_required_fields() -> list[str]:
            result = []
            for i in range(req_tree.topLevelItemCount()):
                grp = req_tree.topLevelItem(i)
                for j in range(grp.childCount()):
                    child = grp.child(j)
                    if child.checkState(0) == Qt.CheckState.Checked:
                        result.append(child.data(0, Qt.ItemDataRole.UserRole))
            return result

        def _apply():
            try:
                new_label = label_edit.text().strip()
            except RuntimeError:
                return  # stale deferred call — widgets already deleted
            t.label = new_label
            t.auto = auto_chk.isChecked()
            t.required_fields = _read_required_fields()
            t.conditions = _read_conditions()
            self._graph_widget._rebuild()
            self._on_changed()
            def _reselect_edge(sid=src_id, aid=action_id):
                e = next(
                    (e for e in self._graph_widget._edges
                     if e.src.state_id == sid and e.transition.action == aid),
                    None,
                )
                if e:
                    e.setSelected(True)
            QTimer.singleShot(0, _reselect_edge)

        label_edit.editingFinished.connect(lambda: QTimer.singleShot(0, _apply))
        auto_chk.stateChanged.connect(lambda _: QTimer.singleShot(0, _apply))
        req_tree.itemChanged.connect(lambda _: QTimer.singleShot(0, _apply))
        cond_table.itemChanged.connect(lambda _: QTimer.singleShot(0, _apply))
