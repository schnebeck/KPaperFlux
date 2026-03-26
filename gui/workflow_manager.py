
import os
import json
import re
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QSplitter, QFrame,
    QLineEdit, QPlainTextEdit, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QToolButton, QDialog, QComboBox, QInputDialog,
    QStackedWidget, QButtonGroup, QScrollArea, QSizePolicy, QProgressBar,
    QDialogButtonBox, QTabWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSignalBlocker, QSize, QEvent, QTimer, QSettings, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QCursor
from core.workflow import WorkflowRuleRegistry, WorkflowRule, WorkflowState, WorkflowTransition, WorkflowEngine, WorkflowL10nPatch
from gui.widgets.workflow_graph import WorkflowGraphWidget, StateNode, TransitionEdge
from gui.cockpit import CELL_WIDTH, CELL_HEIGHT, SPACING, MARGIN, StatCard
from typing import Dict, List, Any, Optional
from core.logger import get_logger
from core.semantic_translator import SemanticTranslator

logger = get_logger("gui.workflow_manager")

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
        final_chk = QCheckBox()
        final_chk.setChecked(node.state_def.final)
        fl.addRow(self.tr("Final state:"), final_chk)

        def _apply():
            try:
                new_label = lbl_edit.text().strip()
            except RuntimeError:
                return  # stale deferred call — widgets already deleted
            node.state_def.label = new_label
            node.state_def.final = final_chk.isChecked()
            self._graph_widget._rebuild()
            self._on_changed()
            QTimer.singleShot(0, lambda nid=node.state_id: (
                self._graph_widget._nodes.get(nid) and
                self._graph_widget._nodes[nid].setSelected(True)
            ))

        lbl_edit.editingFinished.connect(lambda: QTimer.singleShot(0, _apply))
        final_chk.stateChanged.connect(lambda _: QTimer.singleShot(0, _apply))

    def _fill_transition_detail(self, edge: "TransitionEdge", fl) -> None:
        t = edge.transition
        src_id = edge.src.state_id
        action_id = t.action  # captured now — stable ID for re-select after rebuild
        label_edit = QLineEdit(t.label or t.action)
        fl.addRow(self.tr("Label:"), label_edit)
        auto_chk = QCheckBox()
        auto_chk.setChecked(t.auto)
        fl.addRow(self.tr("Auto:"), auto_chk)
        req_edit = QLineEdit(", ".join(t.required_fields))
        req_edit.setPlaceholderText("iban, total_gross, …")
        fl.addRow(self.tr("Required Fields:"), req_edit)

        def _apply():
            try:
                new_label = label_edit.text().strip()
            except RuntimeError:
                return  # stale deferred call — widgets already deleted
            t.label = new_label
            t.auto = auto_chk.isChecked()
            t.required_fields = [f.strip() for f in req_edit.text().split(",") if f.strip()]
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
        req_edit.editingFinished.connect(lambda: QTimer.singleShot(0, _apply))


class WorkflowProcessingWidget(QWidget):
    """Active workflow processing view.

    Left panel — three visually separated sections stacked top-to-bottom:
      1. Navigation bar  (Prev / counter / Next / filename)
      2. Rule context    (rule name + WorkflowStateGraphWidget + Übernehmen)
      3. MetadataEditor  (all metadata tabs, no workflow controls bar)

    Right panel — PDF viewer at full height.
    """

    transition_done = pyqtSignal()

    def __init__(self, pipeline=None, db_manager=None, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.db_manager = db_manager
        self._docs: List[Any] = []
        self._current_index: int = 0
        self._rule_id: Optional[str] = None
        self._init_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        from gui.metadata_editor import MetadataEditorWidget
        from gui.pdf_viewer import PdfViewerWidget
        from gui.widgets.workflow_graph import WorkflowGraphWidget

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.splitterMoved.connect(self._save_splitter)

        # ── LEFT panel ────────────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Section 1 — Navigation bar
        nav_bar = QWidget()
        nav_bar.setFixedHeight(38)
        nav_bar.setStyleSheet(
            "background: #f0f4f8; border-bottom: 2px solid #dce1e8;"
        )
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(10, 0, 10, 0)
        nav_layout.setSpacing(8)

        self._btn_prev = QPushButton("◀ " + self.tr("Prev"))
        self._btn_prev.setFixedHeight(28)
        self._btn_prev.clicked.connect(self._prev)
        nav_layout.addWidget(self._btn_prev)

        self._lbl_nav = QLabel("0 / 0")
        self._lbl_nav.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_nav.setStyleSheet("font-weight: bold; min-width: 60px;")
        nav_layout.addWidget(self._lbl_nav)

        self._btn_next = QPushButton(self.tr("Next") + " ▶")
        self._btn_next.setFixedHeight(28)
        self._btn_next.clicked.connect(self._next)
        nav_layout.addWidget(self._btn_next)

        nav_layout.addStretch()

        self._lbl_title = QLabel()
        self._lbl_title.setStyleSheet("color: #555; font-size: 12px;")
        nav_layout.addWidget(self._lbl_title)

        left_layout.addWidget(nav_bar)

        # Section 2 — Rule context: full WorkflowGraphWidget in run mode
        rule_ctx = QFrame()
        rule_ctx.setStyleSheet("border-bottom: 2px solid #dce1e8;")
        rule_ctx.setMinimumHeight(220)
        rule_ctx_layout = QVBoxLayout(rule_ctx)
        rule_ctx_layout.setContentsMargins(0, 0, 0, 0)
        rule_ctx_layout.setSpacing(0)

        self._state_graph = WorkflowGraphWidget(mode="run")
        self._state_graph.transition_triggered.connect(self._on_transition_triggered)
        rule_ctx_layout.addWidget(self._state_graph)

        left_layout.addWidget(rule_ctx)

        # Section 3 — MetadataEditor (no workflow UI)
        self._metadata_editor = MetadataEditorWidget(
            db_manager=self.db_manager, pipeline=self.pipeline
        )
        self._metadata_editor.set_workflow_ui_visible(False)
        self._metadata_editor.metadata_saved.connect(self.transition_done)
        left_layout.addWidget(self._metadata_editor, 1)

        self._splitter.addWidget(left)

        # ── RIGHT panel — PDF viewer full height ──────────────────────────────
        self._pdf_viewer = PdfViewerWidget(pipeline=self.pipeline)
        self._pdf_viewer.set_toolbar_policy("audit")
        self._splitter.addWidget(self._pdf_viewer)

        # Restore splitter
        saved = QSettings().value("workflow_processing/splitter_state")
        if saved:
            self._splitter.restoreState(saved)
        else:
            self._splitter.setSizes([420, 580])

        outer.addWidget(self._splitter, 1)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_documents(self, docs: List[Any], rule_id: str, label: str) -> None:
        """Load *docs* for processing under *rule_id*."""
        self._docs = docs
        self._rule_id = rule_id
        self._current_index = 0
        self._show_current()

    def set_db_manager(self, db_manager) -> None:
        self.db_manager = db_manager
        if hasattr(self, "_metadata_editor"):
            self._metadata_editor.db_manager = db_manager

    # ── Navigation ────────────────────────────────────────────────────────────

    def _prev(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._show_current()

    def _next(self) -> None:
        if self._current_index < len(self._docs) - 1:
            self._current_index += 1
            self._show_current()

    # ── Display ───────────────────────────────────────────────────────────────

    def _show_current(self) -> None:
        total = len(self._docs)
        if not total:
            self._lbl_nav.setText("0 / 0")
            self._lbl_title.setText("")
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
            self._state_graph.load(None)
            self._metadata_editor.clear()
            return

        idx = self._current_index
        self._lbl_nav.setText(f"{idx + 1} / {total}")
        self._btn_prev.setEnabled(idx > 0)
        self._btn_next.setEnabled(idx < total - 1)

        doc = self._docs[idx]
        self._lbl_title.setText(
            getattr(doc, "original_filename", None) or str(doc.uuid)
        )

        self._pdf_viewer.load_document(doc)
        self._metadata_editor.display_documents([doc])

        # Feed the workflow graph with actual semantic data for condition evaluation.
        # Build a flat dict using the VirtualDocument properties so that transition
        # required_fields (e.g. "iban", "total_gross") resolve correctly.
        registry = WorkflowRuleRegistry()
        rule = registry.get_rule(self._rule_id) if self._rule_id else None
        sd = getattr(doc, "semantic_data", None)
        wi = (sd.workflows.get(self._rule_id)
              if (sd and self._rule_id) else None)
        from datetime import datetime as _dt  # noqa: PLC0415
        now = _dt.now()
        doc_data: dict = {
            "total_gross": getattr(doc, "total_amount", None),
            "iban":        getattr(doc, "iban", None),
            "sender_name": getattr(doc, "sender_name", None),
            "doc_date":    getattr(doc, "doc_date", None),
            "doc_number":  getattr(doc, "doc_number", None),
            "AGE_DAYS":    0,
            "DAYS_IN_STATE": 0,
            "DAYS_UNTIL_DUE": 999,
        }
        try:
            if getattr(doc, "created_at", None):
                doc_data["AGE_DAYS"] = (now - _dt.fromisoformat(doc.created_at)).days
        except Exception as exc:
            logger.debug(f"AGE_DAYS skipped: {exc}")
        if wi and wi.history:
            try:
                last_ts = wi.history[-1].timestamp
                doc_data["DAYS_IN_STATE"] = (now - _dt.fromisoformat(last_ts)).days
            except Exception as exc:
                logger.debug(f"DAYS_IN_STATE skipped: {exc}")
        self._state_graph.load(rule, wi, doc_data)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_transition_triggered(
        self, rule_id: str, action: str, target: str, is_auto: bool
    ) -> None:
        """Apply the clicked transition immediately to the current document."""
        if not self._docs or not self.db_manager:
            return
        doc = self._docs[self._current_index]
        sd = getattr(doc, "semantic_data", None)
        if sd and self._rule_id and self._rule_id in sd.workflows:
            sd.workflows[self._rule_id].apply_transition(action, target, user="USER")
            self.db_manager.update_document_metadata(doc.uuid, {"semantic_data": sd})
        self._show_current()
        self.transition_done.emit()

    def _save_splitter(self) -> None:
        QSettings().setValue(
            "workflow_processing/splitter_state", self._splitter.saveState()
        )


_RULE_CARD_COLORS = [
    "#6366f1", "#f59e0b", "#10b981", "#ec4899",
    "#0ea5e9", "#84cc16", "#f97316", "#14b8a6",
]


class WorkflowRuleCard(QFrame):
    """Card tile for a workflow rule, styled like StatCard."""

    def __init__(self, rule: "WorkflowRule", open_count: int, done_count: int,
                 color: str, parent=None):
        super().__init__(parent)
        self.rule_id = rule.id
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setObjectName("WorkflowRuleCard")
        self.setFixedSize(CELL_WIDTH, CELL_HEIGHT)
        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._pos_anim.setDuration(350)
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutQuint)
        from gui.theme import (
            CLR_BORDER, CLR_TEXT, CLR_TEXT_SECONDARY, CLR_TEXT_MUTED,
            FONT_BASE, FONT_LG, FONT_METRIC, FONT_ICON, PROGRESS_H,
            RADIUS_MD, progress_bar as _progress_bar,
        )
        self.setStyleSheet(f"""
            QFrame#WorkflowRuleCard {{
                background: white;
                border: 1px solid {CLR_BORDER};
                border-radius: {RADIUS_MD}px;
            }}
            QFrame#WorkflowRuleCard:hover {{
                border: 1.5px solid {color};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 12)
        layout.setSpacing(4)

        # Title row
        title_row = QHBoxLayout()
        icon_lbl = QLabel("🔄")
        icon_lbl.setStyleSheet(
            f"font-size: {FONT_ICON}px; background: {color}25; padding: 5px; border-radius: {RADIUS_MD}px;"
        )
        title_row.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)
        name_lbl = QLabel(rule.get_display_name() or rule.id)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(f"color: {CLR_TEXT_SECONDARY}; font-weight: 600; font-size: {FONT_BASE}px;")
        title_row.addWidget(name_lbl, 1, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_row)

        # Open count (big number)
        count_lbl = QLabel(str(open_count))
        count_lbl.setStyleSheet(f"color: {CLR_TEXT}; font-weight: 800; font-size: {FONT_METRIC}px;")
        layout.addWidget(count_lbl)

        open_lbl = QLabel(self.tr("open"))
        open_lbl.setStyleSheet(f"color: {CLR_TEXT_MUTED}; font-size: {FONT_LG}px;")
        layout.addWidget(open_lbl)

        layout.addStretch()

        # Completion rate bar
        total = open_count + done_count
        rate_pct = round(done_count / total * 100) if total > 0 else 0
        rate_row = QHBoxLayout()
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(rate_pct)
        bar.setFixedHeight(PROGRESS_H)
        bar.setTextVisible(False)
        bar.setStyleSheet(_progress_bar(color))
        rate_row.addWidget(bar, 1)
        rate_lbl = QLabel(f"{rate_pct}%")
        rate_lbl.setStyleSheet(f"color: {CLR_TEXT_MUTED}; font-size: {FONT_LG}px; min-width: 32px;")
        rate_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rate_row.addWidget(rate_lbl)
        layout.addLayout(rate_row)

    def move_animated(self, new_pos: "QPoint") -> None:
        if self.pos() == new_pos:
            return
        self._pos_anim.stop()
        self._pos_anim.setEndValue(new_pos)
        self._pos_anim.start()


class _CardBoard(QWidget):
    """Scrollable grid that holds both fixed StatCards and draggable WorkflowRuleCards.

    Row 0 contains the three overview StatCards (not draggable).
    Row 1+ contains WorkflowRuleCards that can be freely rearranged.
    """

    navigate_clicked = pyqtSignal(dict)   # overview card click
    process_clicked = pyqtSignal(str)     # rule card click → rule_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._overview: List["StatCard"] = []
        self._rule_cards: List[WorkflowRuleCard] = []
        self._rule_cfgs: List[Dict[str, Any]] = []
        self._dragging: Optional[WorkflowRuleCard] = None
        self._drag_start_mouse = QPoint()
        self._drag_start_widget = QPoint()
        self._drag_moved = False

    # ── geometry helpers ──────────────────────────────────────────────────────

    def _pos(self, row: int, col: int) -> QPoint:
        return QPoint(
            MARGIN + col * (CELL_WIDTH + SPACING),
            MARGIN + row * (CELL_HEIGHT + SPACING),
        )

    def _cell(self, pos: QPoint):
        col = max(0, int((pos.x() - MARGIN + (CELL_WIDTH + SPACING) // 2) // (CELL_WIDTH + SPACING)))
        row = max(0, int((pos.y() - MARGIN + (CELL_HEIGHT + SPACING) // 2) // (CELL_HEIGHT + SPACING)))
        return row, col

    def _resize(self):
        if self._rule_cfgs:
            max_row = max(c["row"] for c in self._rule_cfgs)
            max_col = max(c["col"] for c in self._rule_cfgs)
        else:
            max_row, max_col = 1, 2
        self.setFixedSize(
            MARGIN * 2 + (max(2, max_col) + 1) * (CELL_WIDTH + SPACING),
            MARGIN * 2 + (max(1, max_row) + 1) * (CELL_HEIGHT + SPACING),
        )

    # ── public API ────────────────────────────────────────────────────────────

    def set_cards(
        self,
        overview: List,
        rule_cards: List[WorkflowRuleCard],
        rule_cfgs: List[Dict[str, Any]],
    ) -> None:
        self._overview = overview
        self._rule_cards = rule_cards
        self._rule_cfgs = rule_cfgs
        self._resize()

    # ── drag handling ─────────────────────────────────────────────────────────

    def _find_card(self, child):
        if isinstance(child, (StatCard, WorkflowRuleCard)):
            return child
        if child and isinstance(child.parent(), (StatCard, WorkflowRuleCard)):
            return child.parent()
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        card = self._find_card(self.childAt(event.position().toPoint()))
        if isinstance(card, StatCard):
            self.navigate_clicked.emit({"query": card.filter_query})
        elif isinstance(card, WorkflowRuleCard):
            self._dragging = card
            self._drag_start_mouse = event.position().toPoint()
            self._drag_start_widget = card.pos()
            self._drag_moved = False
            card.raise_()
            card.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return super().mouseMoveEvent(event)
        delta = event.position().toPoint() - self._drag_start_mouse
        if not self._drag_moved and delta.manhattanLength() > 5:
            self._drag_moved = True
        if self._drag_moved:
            new_pos = self._drag_start_widget + delta
            self._dragging.move(new_pos)
            row, col = self._cell(new_pos)
            row = max(1, row)  # prevent dragging into overview row 0
            self._handle_swap(row, col)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._dragging:
            return super().mouseReleaseEvent(event)
        self._dragging.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if not self._drag_moved:
            self.process_clicked.emit(self._dragging.rule_id)
        else:
            idx = self._rule_cards.index(self._dragging)
            cfg = self._rule_cfgs[idx]
            self._dragging.move_animated(self._pos(cfg["row"], cfg["col"]))
            self._save_order()
        self._dragging = None
        super().mouseReleaseEvent(event)

    def _handle_swap(self, target_row: int, target_col: int):
        drag_idx = self._rule_cards.index(self._dragging)
        orig_row = self._rule_cfgs[drag_idx]["row"]
        orig_col = self._rule_cfgs[drag_idx]["col"]
        if orig_row == target_row and orig_col == target_col:
            return
        for i, cfg in enumerate(self._rule_cfgs):
            if i != drag_idx and cfg["row"] == target_row and cfg["col"] == target_col:
                cfg["row"] = orig_row
                cfg["col"] = orig_col
                self._rule_cards[i].move_animated(self._pos(orig_row, orig_col))
                break
        self._rule_cfgs[drag_idx]["row"] = target_row
        self._rule_cfgs[drag_idx]["col"] = target_col
        self._resize()

    def _save_order(self):
        order = [{"rule_id": c["rule_id"], "row": c["row"], "col": c["col"]}
                 for c in self._rule_cfgs]
        settings = QSettings()
        settings.setValue("workflow_dashboard/rule_order", json.dumps(order))


class WorkflowDashboardWidget(QWidget):
    """Overview of workflow performance and document distribution."""
    navigation_requested = pyqtSignal(dict)
    process_requested = pyqtSignal(list, str, str)  # docs, rule_id, label

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self._rules: List[WorkflowRule] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: #f3f4f6;")

        self._board = _CardBoard()
        self._board.navigate_clicked.connect(self.navigation_requested.emit)
        self._board.process_clicked.connect(self._on_rule_card_clicked)

        scroll.setWidget(self._board)
        layout.addWidget(scroll)

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.refresh()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.refresh()

    def refresh(self):
        """Fetch fresh data from DB and rebuild all cards."""
        if not self.db_manager:
            return

        # Clear previous cards
        for card in self._board._overview + self._board._rule_cards:
            card.deleteLater()

        # ── Overview row (row 0, fixed) ───────────────────────────────────────
        total_q = {"field": "workflow_step", "op": "is_not_empty", "value": None}
        urgent_q = {"field": "workflow_step", "op": "equals", "value": "URGENT"}
        new_q = {"field": "workflow_step", "op": "equals", "value": "NEW"}

        overview_data = [
            (self.tr("Total in Pipeline"), total_q, "#3b82f6"),
            (self.tr("Urgent Actions"), urgent_q, "#ef4444"),
            (self.tr("New Tasks"), new_q, "#10b981"),
        ]
        overview_cards = []
        for col, (title, query, color) in enumerate(overview_data):
            _raw = self.db_manager.count_documents_advanced(query)
            count = int(_raw) if isinstance(_raw, (int, float)) else 0
            card = StatCard(title, count, color, query, parent=self._board)
            card.move(self._board._pos(0, col))
            card.show()
            overview_cards.append(card)

        # ── Rule cards (row 1+, draggable) ────────────────────────────────────
        registry = WorkflowRuleRegistry()
        rules = registry.list_rules()
        self._rules = rules

        # Load saved order
        settings = QSettings()
        try:
            saved_order = json.loads(settings.value("workflow_dashboard/rule_order", "[]"))
        except Exception:
            saved_order = []
        saved_positions = {e["rule_id"]: (e["row"], e["col"]) for e in saved_order if "rule_id" in e}

        rule_cfgs: List[Dict[str, Any]] = []
        used: set = set()

        for i, rule in enumerate(rules):
            if rule.id in saved_positions:
                row, col = saved_positions[rule.id]
                row = max(1, row)
            else:
                # Auto-place: 3 columns starting at row 1
                row = 1 + i // 3
                col = i % 3
            # Resolve conflicts
            while (row, col) in used:
                col += 1
                if col > 5:
                    col = 0
                    row += 1
            used.add((row, col))
            rule_cfgs.append({"rule_id": rule.id, "row": row, "col": col})

        rule_cards: List[WorkflowRuleCard] = []
        for cfg, rule in zip(rule_cfgs, rules):
            field = f"semantic:workflows.{rule.id}.current_step"
            total_q_r = {"field": field, "op": "is_not_empty", "value": None}
            _raw_total = self.db_manager.count_documents_advanced(total_q_r)
            total = int(_raw_total) if isinstance(_raw_total, (int, float)) else 0
            final_states = [sid for sid, s in rule.states.items() if s.final]
            done = 0
            if final_states:
                done_q = {"field": field, "op": "in", "value": final_states}
                _raw_done = self.db_manager.count_documents_advanced(done_q)
                done = int(_raw_done) if isinstance(_raw_done, (int, float)) else 0
            color = _RULE_CARD_COLORS[rules.index(rule) % len(_RULE_CARD_COLORS)]
            card = WorkflowRuleCard(rule, total - done, done, color, parent=self._board)
            card.move(self._board._pos(cfg["row"], cfg["col"]))
            card.show()
            rule_cards.append(card)

        self._board.set_cards(overview_cards, rule_cards, rule_cfgs)

    def _on_rule_card_clicked(self, rule_id: str) -> None:
        rule = next((r for r in self._rules if r.id == rule_id), None)
        if not rule:
            return
        field = f"semantic:workflows.{rule.id}.current_step"
        query = {"field": field, "op": "is_not_empty", "value": None}
        self._open_processing(rule, query)

    def _open_processing(self, rule, query: dict) -> None:
        """Fetch open documents for *rule* and emit process_requested."""
        if not self.db_manager:
            return
        try:
            all_docs = self.db_manager.search_documents_advanced(query)
            # Keep only docs not yet in a final state
            open_docs = [
                doc for doc in all_docs
                if doc.semantic_data
                and rule.id in doc.semantic_data.workflows
                and not (
                    rule.states.get(doc.semantic_data.workflows[rule.id].current_step)
                    and rule.states[doc.semantic_data.workflows[rule.id].current_step].final
                )
            ]
            label = self.tr("Processing: %s") % (rule.get_display_name() or rule.id)
            self.process_requested.emit(open_docs, rule.id, label)
        except Exception as exc:
            logger.warning(f"Failed to load docs for processing: {exc}")


class WorkflowManagerWidget(QWidget):
    """Management console for Rules."""
    workflows_changed = pyqtSignal()
    navigation_requested = pyqtSignal(dict)
    status_message = pyqtSignal(str)

    def __init__(self, parent=None, filter_tree=None, pipeline=None):
        super().__init__(parent)
        self.registry = WorkflowRuleRegistry()
        self.filter_tree = filter_tree
        self.pipeline = pipeline
        self.workflow_dir = "resources/workflows"
        self._is_dirty = False
        self._init_ui()
        self.load_workflows()

    def sizeHint(self) -> QSize:
        return QSize(800, 600)

    def minimumSizeHint(self) -> QSize:
        return QSize(100, 100)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(0)

        # Custom Sub-Navigation Bar
        sub_nav_container = QWidget()
        sub_nav_layout = QHBoxLayout(sub_nav_container)
        sub_nav_layout.setContentsMargins(0, 5, 0, 10)
        sub_nav_layout.setSpacing(8)

        self.sub_mode_group = QButtonGroup(self)
        self.sub_mode_group.setExclusive(True)

        from gui.theme import btn_subnav, SUBNAV_HEIGHT
        button_height = SUBNAV_HEIGHT
        button_style = btn_subnav()

        # Dashboard Button
        self.btn_show_dashboard = QToolButton()
        self.btn_show_dashboard.setText("📊 " + self.tr("Dashboard"))
        self.btn_show_dashboard.setCheckable(True)
        self.btn_show_dashboard.setChecked(True)
        self.btn_show_dashboard.setFixedHeight(button_height)
        self.btn_show_dashboard.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_show_dashboard.setStyleSheet(button_style)
        self.btn_show_dashboard.clicked.connect(lambda: self.main_stack.setCurrentIndex(0))
        self.sub_mode_group.addButton(self.btn_show_dashboard, 0)
        sub_nav_layout.addWidget(self.btn_show_dashboard)

        # Processing Button (only enabled when a processing session is active)
        self.btn_show_processing = QToolButton()
        self.btn_show_processing.setText("▶ " + self.tr("Process"))
        self.btn_show_processing.setCheckable(True)
        self.btn_show_processing.setFixedHeight(button_height)
        self.btn_show_processing.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_show_processing.setStyleSheet(button_style)
        self.btn_show_processing.clicked.connect(lambda: self.main_stack.setCurrentIndex(1))
        self.btn_show_processing.setEnabled(False)
        self.sub_mode_group.addButton(self.btn_show_processing, 2)
        sub_nav_layout.addWidget(self.btn_show_processing)

        # Rule Editor Button
        self.btn_show_editor = QToolButton()
        self.btn_show_editor.setText("⚙️ " + self.tr("Rule Editor"))
        self.btn_show_editor.setCheckable(True)
        self.btn_show_editor.setFixedHeight(button_height)
        self.btn_show_editor.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_show_editor.setStyleSheet(button_style)
        self.btn_show_editor.clicked.connect(lambda: self.main_stack.setCurrentIndex(2))
        self.sub_mode_group.addButton(self.btn_show_editor, 1)
        sub_nav_layout.addWidget(self.btn_show_editor)

        sub_nav_layout.addStretch()
        layout.addWidget(sub_nav_container)

        # Horizontal separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #ddd; max-height: 1px; margin-bottom: 15px;")
        layout.addWidget(line)

        # Main Stack for Content
        self.main_stack = QStackedWidget()
        self.main_stack.currentChanged.connect(self._on_stack_changed)

        db_manager = self.filter_tree.db_manager if self.filter_tree else None

        # 1. Dashboard View
        self.dashboard_tab = WorkflowDashboardWidget(db_manager)
        self.dashboard_tab.navigation_requested.connect(self.navigation_requested.emit)
        self.dashboard_tab.process_requested.connect(self._on_process_requested)
        self.main_stack.addWidget(self.dashboard_tab)
        
        # 2. Rule Editor View
        self.editor_widget = QWidget()
        editor_layout = QVBoxLayout(self.editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        
        # Move previous header/top_bar logic into editor_layout
        self.top_bar_widget = QWidget()
        self.top_bar = QHBoxLayout(self.top_bar_widget)
        self.top_bar.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_select_rule = QLabel(self.tr("Select Rule:"))
        self.top_bar.addWidget(self.lbl_select_rule)
        
        self.combo_rules = QComboBox()
        self.combo_rules.setMinimumWidth(250)
        self.combo_rules.currentIndexChanged.connect(self._on_combo_changed)
        self.top_bar.addWidget(self.combo_rules)

        self.btn_new = QPushButton("✚ " + self.tr("New Rule"))
        self.btn_new.setToolTip(self.tr("Create a new workflow rule"))
        self.btn_new.clicked.connect(self._create_new_rule)
        self.top_bar.addWidget(self.btn_new)

        self.btn_manage = QPushButton("⚙️ " + self.tr("Manage..."))
        self.btn_manage.setToolTip(self.tr("Manage rule files (delete, rename, import)"))
        self.btn_manage.clicked.connect(self._on_manage_clicked)
        self.top_bar.addWidget(self.btn_manage)

        self.btn_show_docs = QPushButton("🔍 " + self.tr("Show documents"))
        self.btn_show_docs.setToolTip(self.tr("Navigate to all documents currently tracked by this workflow"))
        self.btn_show_docs.setEnabled(False)
        self.btn_show_docs.clicked.connect(self._on_show_workflow_docs)
        self.top_bar.addWidget(self.btn_show_docs)

        self.top_bar.addStretch()

        editor_layout.addWidget(self.top_bar_widget)

        # Horizontal separator (inner)
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        line2.setStyleSheet("color: #ddd;")
        editor_layout.addWidget(line2)

        # Form Editor Area — full width, no centering constraint
        self.content_container = QWidget()
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 8, 0, 0)

        self.form_editor = WorkflowRuleFormEditor()
        self.form_editor.changed.connect(self._mark_dirty)
        content_layout.addWidget(self.form_editor, 1)

        editor_layout.addWidget(self.content_container, 1)

        # Inject Revert + Save into the graph widget's header toolbar
        graph_hdr = self.form_editor._graph_widget._hdr_layout
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        graph_hdr.addWidget(sep)

        self.btn_revert = QPushButton("🔄 " + self.tr("Revert"))
        self.btn_revert.setToolTip(self.tr("Discard unsaved changes"))
        self.btn_revert.setEnabled(False)
        self.btn_revert.clicked.connect(self._revert_changes)
        graph_hdr.addWidget(self.btn_revert)

        self.btn_save = QPushButton("💾 " + self.tr("Save Rule"))
        self.btn_save.setEnabled(False)
        self.btn_save.setToolTip(self.tr("Save and activate the current rule"))
        self.btn_save.clicked.connect(self._save_rule)
        graph_hdr.addWidget(self.btn_save)

        self.main_stack.addWidget(self.editor_widget)

        # 3. Processing View
        self.processing_widget = WorkflowProcessingWidget(
            pipeline=self.pipeline,
            db_manager=db_manager,
        )
        self.processing_widget.transition_done.connect(self.dashboard_tab.refresh)
        self.main_stack.addWidget(self.processing_widget)
        # Reorder stack: processing at 1, editor at 2
        self.main_stack.removeWidget(self.processing_widget)
        self.main_stack.insertWidget(1, self.processing_widget)

        layout.addWidget(self.main_stack, 1)

        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.btn_show_dashboard.setText("📊 " + self.tr("Dashboard"))
        self.btn_show_editor.setText("⚙️ " + self.tr("Rule Editor"))
        self.btn_show_processing.setText("▶ " + self.tr("Process"))
        if hasattr(self, 'lbl_select_rule'):
             self.lbl_select_rule.setText(self.tr("Select Rule:"))

        self.btn_new.setText("✚ " + self.tr("New Rule"))
        self.btn_new.setToolTip(self.tr("Create a new workflow rule"))
        self.btn_revert.setText("🔄 " + self.tr("Revert"))
        self.btn_revert.setToolTip(self.tr("Discard unsaved changes"))
        self.btn_save.setText("💾 " + self.tr("Save Rule"))
        self.btn_save.setToolTip(self.tr("Save and activate the current rule"))
        self.btn_manage.setText("⚙️ " + self.tr("Manage..."))
        self.btn_manage.setToolTip(self.tr("Manage rule files (delete, rename, import)"))
        self.btn_show_docs.setText("🔍 " + self.tr("Show documents"))
        self.btn_show_docs.setToolTip(self.tr("Navigate to all documents currently tracked by this workflow"))

    def _on_process_requested(self, docs: List, rule_id: str, label: str) -> None:
        """Switch to the Processing view and load the given documents."""
        db_manager = self.filter_tree.db_manager if self.filter_tree else None
        self.processing_widget.set_db_manager(db_manager)
        self.processing_widget.load_documents(docs, rule_id, label)
        self.btn_show_processing.setEnabled(True)
        self.btn_show_processing.setChecked(True)
        self.main_stack.setCurrentIndex(1)

    def _on_stack_changed(self, index):
        if index == 0:
            self.dashboard_tab.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if self.main_stack.currentIndex() == 0:
            self.dashboard_tab.refresh()

    def _mark_dirty(self):
        self._is_dirty = True
        self.btn_save.setEnabled(True)
        self.btn_revert.setEnabled(True)

    def _clear_dirty(self):
        self._is_dirty = False
        self.btn_save.setEnabled(False)
        self.btn_revert.setEnabled(False)

    def load_workflows(self):
        self.combo_rules.blockSignals(True)
        current_id = self.combo_rules.currentData()
        
        self.combo_rules.clear()
        self.combo_rules.addItem(self.tr("--- Select Rule ---"), None)
        
        if not os.path.exists(self.workflow_dir):
            os.makedirs(self.workflow_dir, exist_ok=True)
            
        registry = WorkflowRuleRegistry()
        registry.load_from_directory(self.workflow_dir)
        
        idx_to_restore = 0
        for i, rule in enumerate(registry.list_rules()):
            label = rule.get_display_name() or rule.id
            self.combo_rules.addItem(label, rule.id)
            if rule.id == current_id:
                idx_to_restore = i + 1 # +1 because of placeholder
            
        self.combo_rules.setCurrentIndex(idx_to_restore)
        self.combo_rules.blockSignals(False)
        
        # If the formerly selected rule is gone, clear the form
        if current_id and idx_to_restore == 0:
            self.form_editor.load_rule(WorkflowRule(id="new", name="", states={}))
            self.status_message.emit(self.tr("Rule deleted."))
            self._clear_dirty()

    def _on_combo_changed(self, index):
        if self._is_dirty:
            reply = QMessageBox.question(
                self, self.tr("Unsaved Changes"),
                self.tr("You have unsaved changes. Discard them?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                # Revert selection
                self.load_workflows() # Quick fix to reset selection
                return

        rule_id = self.combo_rules.currentData()
        self.btn_show_docs.setEnabled(bool(rule_id))
        if not rule_id:
            self.form_editor.clear()
            self._clear_dirty()
            return

        reg = WorkflowRuleRegistry()
        rule = reg.get_rule(rule_id)
        if rule:
            self.form_editor.load_rule(rule)
            self._clear_dirty()
            self.status_message.emit(self.tr("Editing: %1").replace("%1", rule.get_display_name() or rule_id))

    def _create_new_rule(self):
        rule = WorkflowRule(
            id="new_workflow",
            name="New Workflow",
            description="Generated via GUI",
            states={
                "NEW": WorkflowState(label="Start", transitions=[
                    WorkflowTransition(action="verify", target="DONE")
                ]),
                "DONE": WorkflowState(label="Done", final=True)
            },
            triggers={"type_tags": ["NEW_TAG"]}
        )
        self.form_editor.load_rule(rule)
        self.combo_rules.setCurrentIndex(0)
        self._mark_dirty()

    def _save_rule(self):
        try:
            rule = self.form_editor.get_rule()
            # Check for duplicate names (excluding current ID)
            reg = WorkflowRuleRegistry()
            for existing in reg.list_rules():
                if existing.name == rule.name and existing.id != rule.id:
                    QMessageBox.warning(self, self.tr("Duplicate Name"), 
                                        self.tr("A rule with the name '%1' already exists.").replace("%1", rule.name))
                    return

            file_path = os.path.join(self.workflow_dir, f"{rule.id}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(rule.model_dump(), f, indent=2)
                
            QMessageBox.information(self, self.tr("Success"), self.tr("Rule '%1' saved and activated.").replace("%1", rule.name))
            
            self._clear_dirty()
            
            # Reload registry and list
            self.registry.load_from_directory(self.workflow_dir)
            self.load_workflows()
            
            # Select the saved one
            self._select_rule_by_id(rule.id)
            
            self.workflows_changed.emit()
            
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Failed to save rule: %1").replace("%1", str(e)))

    def _revert_changes(self):
        """Cancel changes and reload current rule."""
        rule_id = self.combo_rules.currentData()
        if rule_id:
            reg = WorkflowRuleRegistry()
            rule = reg.get_rule(rule_id)
            if rule:
                self.form_editor.load_rule(rule)
        self._clear_dirty()
        
    def _on_show_workflow_docs(self) -> None:
        """Navigate the document list to all documents tracked by the currently selected workflow."""
        rule_id = self.combo_rules.currentData()
        if not rule_id:
            return
        rule_name = self.combo_rules.currentText()
        query = {"field": f"semantic:workflows.{rule_id}.current_step", "op": "is_not_empty", "value": None}
        payload = {
            "query": query,
            "label": self.tr("Documents in workflow '%1'").replace("%1", rule_name),
        }
        self.navigation_requested.emit(payload)

    def _on_manage_clicked(self):
        """Open a management dialog for rules."""
        dlg = WorkflowRuleManagerDialog(self, filter_tree=self.filter_tree)
        dlg.rule_selected.connect(self._select_rule_by_id)
        dlg.exec()
        self.load_workflows()

    def _select_rule_by_id(self, rule_id: str):
        idx = self.combo_rules.findData(rule_id)
        if idx >= 0:
            self.combo_rules.setCurrentIndex(idx)

class WorkflowRuleManagerDialog(QDialog):
    """Simplified management dialog for Rule files."""
    rule_selected = pyqtSignal(str)

    def __init__(self, parent=None, filter_tree=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage Rules"))
        self.resize(400, 500)
        self.workflow_dir = "resources/workflows"
        self.filter_tree = filter_tree
        self._init_ui()
        self._reload_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list_widget)
        
        btn_row = QHBoxLayout()
        btn_row.setSpacing(5)
        self.btn_new = QPushButton()
        self.btn_new.clicked.connect(self._create_new)
        
        self.btn_rename = QPushButton()
        self.btn_rename.clicked.connect(self._rename_display_name)
        
        self.btn_delete = QPushButton()
        self.btn_delete.clicked.connect(self._delete_selected)
        
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_rename)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_delete)
        layout.addLayout(btn_row)
        
        self.close_btn = QPushButton()
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)

        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.setWindowTitle(self.tr("Manage Rules"))
        self.btn_new.setText("✚ " + self.tr("New..."))
        self.btn_new.setToolTip(self.tr("Create a new rule file"))
        self.btn_rename.setText("✎ " + self.tr("Rename..."))
        self.btn_rename.setToolTip(self.tr("Rename the selected rule's display name"))
        self.btn_delete.setText("🗑 " + self.tr("Delete"))
        self.btn_delete.setToolTip(self.tr("Delete selected rule files (DEL)"))
        self.close_btn.setText(self.tr("Close"))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self._delete_selected()
        else:
            super().keyPressEvent(event)

    def _reload_list(self):
        self.list_widget.clear()
        if os.path.exists(self.workflow_dir):
            for f in sorted(os.listdir(self.workflow_dir)):
                if f.endswith(".json"):
                    file_path = os.path.join(self.workflow_dir, f)
                    try:
                        with open(file_path, "r") as jf:
                            data = json.load(jf)
                            pb_id = data.get("id", f.replace(".json", ""))
                            name = data.get("name", pb_id)
                            item = QListWidgetItem(name)
                            item.setData(Qt.ItemDataRole.UserRole, pb_id)
                            self.list_widget.addItem(item)
                    except (json.JSONDecodeError, OSError):
                        self.list_widget.addItem(f.replace(".json", ""))

    def _create_new(self):
        name, ok = QInputDialog.getText(self, self.tr("New Workflow"), self.tr("Enter display name:"))
        if ok and name:
            name = name.strip()
            # Check for duplicates
            reg = WorkflowRuleRegistry()
            if any(p.name == name for p in reg.list_rules()):
                QMessageBox.warning(self, self.tr("Duplicate Name"), 
                                    self.tr("A workflow with the name '%1' already exists.").replace("%1", name))
                return

            # Generate stable ID from name + timestamp
            clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
            pb_id = f"{clean_name}_{int(time.time())}"
            
            pb = WorkflowRule(
                id=pb_id,
                name=name,
                states={"NEW": WorkflowState(label="Start", final=True)}
            )
            file_path = os.path.join(self.workflow_dir, f"{pb_id}.json")
            with open(file_path, "w") as f:
                json.dump(pb.model_dump(), f, indent=2)
            self._reload_list()
            self.rule_selected.emit(pb_id)

    def _rename_display_name(self):
        item = self.list_widget.currentItem()
        if not item: return
        pb_id = item.data(Qt.ItemDataRole.UserRole)
        
        file_path = os.path.join(self.workflow_dir, f"{pb_id}.json")
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                old_name = data.get("name", pb_id)
                
            new_name, ok = QInputDialog.getText(self, self.tr("Rename Workflow"), self.tr("New display name:"), QLineEdit.EchoMode.Normal, old_name)
            if ok and new_name:
                new_name = new_name.strip()
                if new_name == old_name: return
                
                # Duplicate check
                reg = WorkflowRuleRegistry()
                if any(p.name == new_name for p in reg.list_rules()):
                    QMessageBox.warning(self, self.tr("Duplicate Name"), 
                                        self.tr("A rule with the name '%1' already exists.").replace("%1", new_name))
                    return

                data["name"] = new_name
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=2)
                self._reload_list()
                self.rule_selected.emit(pb_id)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), str(e))

    def _delete_selected(self):
        items = self.list_widget.selectedItems()
        if not items: return
        
        if len(items) == 1:
            title = self.tr("Delete Rule")
            msg = self.tr("Are you sure you want to delete the rule '%1'?").replace("%1", items[0].text())
        else:
            title = self.tr("Delete Rules")
            msg = self.tr("Are you sure you want to delete %n selected rule(s)?", "", len(items))

        # Safety Check: Are any of these in use?
        in_use = []
        for item in items:
            pb_id = item.data(Qt.ItemDataRole.UserRole)
            if self.filter_tree:
                usages = self.filter_tree.find_rule_usages(pb_id)
                if usages:
                    in_use.append(item.text())

        if in_use:
            QMessageBox.critical(
                self, self.tr("Rules in Use"),
                self.tr("The following rules cannot be deleted because they are still in use:\n\n%1").replace("%1", ", ".join(in_use))
            )
            return

        reply = QMessageBox.question(self, title, msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            reg = WorkflowRuleRegistry()
            for item in items:
                pb_id = item.data(Qt.ItemDataRole.UserRole)
                file_path = os.path.join(self.workflow_dir, f"{pb_id}.json")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        if pb_id in reg.rules:
                            del reg.rules[pb_id]
                    except Exception as e:
                        logger.error(f"Failed to delete {file_path}: {e}")

            self._reload_list()

