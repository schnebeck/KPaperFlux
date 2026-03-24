
import os
import json
import re
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QSplitter, QFrame,
    QLineEdit, QPlainTextEdit, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QToolButton, QDialog, QComboBox, QInputDialog,
    QStackedWidget, QButtonGroup
)
from PyQt6.QtCore import Qt, pyqtSignal, QSignalBlocker, QSize, QEvent, QTimer, QSettings
from core.workflow import WorkflowRuleRegistry, WorkflowRule, WorkflowState, WorkflowTransition, WorkflowEngine
from gui.widgets.workflow_graph import WorkflowGraphWidget, StateNode, TransitionEdge
from gui.cockpit import StatCard
from typing import Dict, List, Any, Optional
from core.logger import get_logger
from core.semantic_translator import SemanticTranslator

logger = get_logger("gui.workflow_manager")

class WorkflowRuleFormEditor(QWidget):
    """Structured editor for a single Rule."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.current_rule = None
        self._lock_signals = False

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)

        # ── Left panel: rule metadata ──────────────────────────────────────
        self._left_panel = QFrame()
        self._left_panel.setMinimumWidth(28)
        lp_layout = QVBoxLayout(self._left_panel)
        lp_layout.setContentsMargins(0, 0, 0, 0)
        lp_layout.setSpacing(0)

        lp_hdr = QFrame()
        lp_hdr.setFixedHeight(28)
        lp_hdr.setStyleSheet("background:#e8eaf6; border-bottom:1px solid #c5cae9;")
        lp_hdr_layout = QHBoxLayout(lp_hdr)
        lp_hdr_layout.setContentsMargins(6, 0, 4, 0)
        self.lbl_rule_panel = QLabel()
        self.lbl_rule_panel.setStyleSheet("font-weight:bold; color:#3949ab; font-size:10px;")
        lp_hdr_layout.addWidget(self.lbl_rule_panel)
        lp_hdr_layout.addStretch()
        self._btn_collapse_left = QToolButton()
        self._btn_collapse_left.setFixedSize(20, 20)
        self._btn_collapse_left.clicked.connect(self._toggle_left)
        lp_hdr_layout.addWidget(self._btn_collapse_left)
        lp_layout.addWidget(lp_hdr)

        self._left_content = QWidget()
        lc_layout = QFormLayout(self._left_content)
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
        self._splitter.addWidget(self._left_panel)

        # ── Center: graph widget (no inline detail panel) ──────────────────
        self._graph_widget = WorkflowGraphWidget(mode="edit", inline_detail=False)
        self._graph_widget.rule_changed.connect(self._on_changed)
        self._graph_widget.item_selected.connect(self._on_item_selected)
        self._splitter.addWidget(self._graph_widget)

        # ── Right panel: state/transition properties ───────────────────────
        self._right_panel = QFrame()
        self._right_panel.setMinimumWidth(28)
        rp_layout = QVBoxLayout(self._right_panel)
        rp_layout.setContentsMargins(0, 0, 0, 0)
        rp_layout.setSpacing(0)

        rp_hdr = QFrame()
        rp_hdr.setFixedHeight(28)
        rp_hdr.setStyleSheet("background:#e8eaf6; border-bottom:1px solid #c5cae9;")
        rp_hdr_layout = QHBoxLayout(rp_hdr)
        rp_hdr_layout.setContentsMargins(4, 0, 6, 0)
        self._btn_collapse_right = QToolButton()
        self._btn_collapse_right.setFixedSize(20, 20)
        self._btn_collapse_right.clicked.connect(self._toggle_right)
        rp_hdr_layout.addWidget(self._btn_collapse_right)
        rp_hdr_layout.addStretch()
        self.lbl_props_panel = QLabel()
        self.lbl_props_panel.setStyleSheet("font-weight:bold; color:#3949ab; font-size:10px;")
        rp_hdr_layout.addWidget(self.lbl_props_panel)
        rp_layout.addWidget(rp_hdr)

        self._right_content = QWidget()
        rc_layout = QVBoxLayout(self._right_content)
        rc_layout.setContentsMargins(8, 8, 8, 8)
        rc_layout.setSpacing(6)

        self._detail_hint = QLabel()
        self._detail_hint.setStyleSheet("color:#94a3b8; font-style:italic;")
        self._detail_hint.setWordWrap(True)
        rc_layout.addWidget(self._detail_hint)

        self._detail_form = QFrame()
        self._detail_form_layout = QFormLayout(self._detail_form)
        self._detail_form_layout.setContentsMargins(0, 0, 0, 0)
        self._detail_form_layout.setSpacing(6)
        self._detail_form.hide()
        rc_layout.addWidget(self._detail_form)

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

        QTimer.singleShot(0, self._init_splitter_sizes)
        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        """Updates all UI strings for on-the-fly localization."""
        self.lbl_rule_panel.setText(self.tr("Rule"))
        self.lbl_props_panel.setText(self.tr("Properties"))
        self._detail_hint.setText(self.tr("Select a state or transition to edit its properties."))
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

    def load_rule(self, rule: WorkflowRule):
        self._lock_signals = True
        self.current_rule = rule
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
        return WorkflowRule(id=pb_id, name=name, description=desc, states=states,
                            triggers={"type_tags": triggers}, node_positions=node_positions,
                            transition_anchors=transition_anchors)

    def _init_splitter_sizes(self) -> None:
        settings = QSettings("KPaperFlux", "WorkflowEditor")
        saved = settings.value("splitter_sizes")
        if saved:
            self._splitter.setSizes([int(x) for x in saved])
        else:
            total = self._splitter.width()
            if total > 100:
                center = max(200, total - self._left_saved_w - self._right_saved_w)
                self._splitter.setSizes([self._left_saved_w, center, self._right_saved_w])
        self._splitter.splitterMoved.connect(self._save_splitter_sizes)

    def _save_splitter_sizes(self) -> None:
        settings = QSettings("KPaperFlux", "WorkflowEditor")
        settings.setValue("splitter_sizes", self._splitter.sizes())

    def _update_collapse_buttons(self) -> None:
        if hasattr(self, "_btn_collapse_left"):
            self._btn_collapse_left.setText("◀" if self._left_expanded else "▶")
        if hasattr(self, "_btn_collapse_right"):
            self._btn_collapse_right.setText("▶" if self._right_expanded else "◀")

    def _toggle_left(self) -> None:
        sizes = self._splitter.sizes()
        if self._left_expanded:
            self._left_saved_w = max(sizes[0], 80)
            self._splitter.setSizes([28, sizes[1] + sizes[0] - 28, sizes[2]])
            self._left_content.hide()
            self._left_expanded = False
        else:
            w = self._left_saved_w
            self._splitter.setSizes([w, sizes[1] - w + 28, sizes[2]])
            self._left_content.show()
            self._left_expanded = True
        self._update_collapse_buttons()

    def _toggle_right(self) -> None:
        sizes = self._splitter.sizes()
        if self._right_expanded:
            self._right_saved_w = max(sizes[2], 80)
            self._splitter.setSizes([sizes[0], sizes[1] + sizes[2] - 28, 28])
            self._right_content.hide()
            self._right_expanded = False
        else:
            w = self._right_saved_w
            self._splitter.setSizes([sizes[0], sizes[1] - w + 28, w])
            self._right_content.show()
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
        fl.addRow(self.tr("ID:"), QLabel(node.state_id))
        lbl_edit = QLineEdit(node.state_def.label)
        fl.addRow(self.tr("Label:"), lbl_edit)
        final_chk = QCheckBox()
        final_chk.setChecked(node.state_def.final)
        fl.addRow(self.tr("Final state:"), final_chk)

        def _apply():
            node.state_def.label = lbl_edit.text().strip()
            node.display_label = (
                SemanticTranslator.instance().translate(node.state_def.label)
                or node.state_id
            )
            node.state_def.final = final_chk.isChecked()
            node.update()
            self._graph_widget._rebuild()
            self._on_changed()

        apply_btn = QPushButton(self.tr("Apply"))
        apply_btn.setFixedHeight(26)
        apply_btn.clicked.connect(_apply)
        fl.addRow("", apply_btn)

    def _fill_transition_detail(self, edge: "TransitionEdge", fl) -> None:
        t = edge.transition
        action_edit = QLineEdit(t.action)
        fl.addRow(self.tr("Action:"), action_edit)
        auto_chk = QCheckBox()
        auto_chk.setChecked(t.auto)
        fl.addRow(self.tr("Auto:"), auto_chk)
        req_edit = QLineEdit(", ".join(t.required_fields))
        req_edit.setPlaceholderText("iban, total_gross, …")
        fl.addRow(self.tr("Required Fields:"), req_edit)

        def _apply():
            new_action = action_edit.text().strip().lower()
            if not new_action:
                return
            t.action = new_action
            t.auto = auto_chk.isChecked()
            t.required_fields = [f.strip() for f in req_edit.text().split(",") if f.strip()]
            self._graph_widget._rebuild()
            self._on_changed()

        apply_btn = QPushButton(self.tr("Apply"))
        apply_btn.setFixedHeight(26)
        apply_btn.clicked.connect(_apply)
        fl.addRow("", apply_btn)


class WorkflowDashboardWidget(QWidget):
    """Overview of workflow performance and document distribution."""
    navigation_requested = pyqtSignal(dict)

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(15)

        # 1. Stats Row (Total, Urgent, Pending)
        self.stats_layout = QHBoxLayout()
        self.layout.addLayout(self.stats_layout)

        # 2. Rule List / Summary
        self.rule_summary_lbl = QLabel(self.tr("Active Rule Load:"))
        self.rule_summary_lbl.setStyleSheet("font-weight: bold; margin-top: 20px;")
        self.layout.addWidget(self.rule_summary_lbl)

        self.rules_table = QTableWidget(0, 3)
        self.rules_table.setHorizontalHeaderLabels([self.tr("Workflow Rule"), self.tr("Active Documents"), self.tr("Completion Rate")])
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rules_table.setStyleSheet("background: white; border: 1px solid #e0e0e0; border-radius: 4px;")
        self.layout.addWidget(self.rules_table)

        self.layout.addStretch()
        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.rule_summary_lbl.setText(self.tr("Active Rule Load:"))
        self.rules_table.setHorizontalHeaderLabels([
            self.tr("Workflow Rule"), self.tr("Active Documents"), self.tr("Completion Rate")
        ])
        # Refresh dynamic cards labels
        self.refresh()

    def refresh(self):
        """Fetch fresh data from DB."""
        if not self.db_manager:
            return

        # Clear existing cards
        while self.stats_layout.count():
            item = self.stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 1. Total in Workflow
        total_q = {"field": "workflow_step", "op": "is_not_empty", "value": None}
        total_count = self.db_manager.count_documents_advanced(total_q)
        
        # 2. Urgent
        urgent_q = {"field": "workflow_step", "op": "equals", "value": "URGENT"}
        urgent_count = self.db_manager.count_documents_advanced(urgent_q)

        # 3. New/Inbox
        new_q = {"field": "workflow_step", "op": "equals", "value": "NEW"}
        new_count = self.db_manager.count_documents_advanced(new_q)

        # Create Cards
        c1 = StatCard(self.tr("Total in Pipeline"), total_count, "#3b82f6", total_q, parent=self)
        c2 = StatCard(self.tr("Urgent Actions"), urgent_count, "#ef4444", urgent_q, parent=self)
        c3 = StatCard(self.tr("New Tasks"), new_count, "#10b981", new_q, parent=self)

        for c in [c1, c2, c3]:
            c.clicked.connect(self.navigation_requested.emit)
            self.stats_layout.addWidget(c)

        # 4. Populate Rules Table
        registry = WorkflowRuleRegistry()
        rules = registry.list_rules()
        self.rules_table.setRowCount(len(rules))
        
        for i, rule in enumerate(rules):
            # Count per rule: any doc that has this rule assigned (step is not empty)
            rule_step_field = f"semantic:workflows.{rule.id}.current_step"
            rule_q = {"field": rule_step_field, "op": "is_not_empty", "value": None}
            count = self.db_manager.count_documents_advanced(rule_q)
            if not isinstance(count, (int, float)): count = 0

            # Finished count (docs in a final state for this rule)
            final_states = [sid for sid, s in rule.states.items() if s.final]
            if final_states:
                finished_q = {"field": rule_step_field, "op": "in", "value": final_states}
                finished_count = self.db_manager.count_documents_advanced(finished_q)
                if not isinstance(finished_count, (int, float)): finished_count = 0
            else:
                finished_count = 0
            
            total_history = count + finished_count
            rate = f"{(finished_count / total_history * 100):.1f}%" if total_history > 0 else "0%"

            self.rules_table.setItem(i, 0, QTableWidgetItem(rule.name or rule.id))
            self.rules_table.setItem(i, 1, QTableWidgetItem(str(count)))
            self.rules_table.setItem(i, 2, QTableWidgetItem(rate))

class WorkflowManagerWidget(QWidget):
    """Management console for Rules."""
    workflows_changed = pyqtSignal()
    navigation_requested = pyqtSignal(dict)
    status_message = pyqtSignal(str)

    def __init__(self, parent=None, filter_tree=None):
        super().__init__(parent)
        self.registry = WorkflowRuleRegistry()
        self.filter_tree = filter_tree
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

        button_height = 30
        button_style = f"""
            QToolButton {{ 
                padding: 0px 20px; 
                height: {button_height}px;
                border: 1px solid #ddd; 
                border-radius: 4px;
                background: #f8f9fa;
                color: #555; 
                font-size: 15px; 
                font-weight: 500; 
            }}
            QToolButton:hover {{ background: #eee; }}
            QToolButton:checked {{ 
                background: #1565c0; 
                color: white; 
                border-color: #0d47a1;
                font-weight: bold; 
            }}
        """

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

        # Rule Editor Button
        self.btn_show_editor = QToolButton()
        self.btn_show_editor.setText("⚙️ " + self.tr("Rule Editor"))
        self.btn_show_editor.setCheckable(True)
        self.btn_show_editor.setFixedHeight(button_height)
        self.btn_show_editor.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_show_editor.setStyleSheet(button_style)
        self.btn_show_editor.clicked.connect(lambda: self.main_stack.setCurrentIndex(1))
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
        
        # 1. Dashboard View
        self.dashboard_tab = WorkflowDashboardWidget(self.filter_tree.db_manager if self.filter_tree else None)
        self.dashboard_tab.navigation_requested.connect(self.navigation_requested.emit)
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
        layout.addWidget(self.main_stack, 1)


        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.btn_show_dashboard.setText("📊 " + self.tr("Dashboard"))
        self.btn_show_editor.setText("⚙️ " + self.tr("Rule Editor"))
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
            label = rule.name or rule.id
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
            return

        reg = WorkflowRuleRegistry()
        rule = reg.get_rule(rule_id)
        if rule:
            self.form_editor.load_rule(rule)
            self._clear_dirty()
            self.status_message.emit(self.tr("Editing: %1").replace("%1", rule.name or rule_id))

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

