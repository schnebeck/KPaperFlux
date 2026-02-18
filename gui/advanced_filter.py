"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/advanced_filter.py
Version:        2.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    Panel for managing complex search filters and document rules.
------------------------------------------------------------------------------
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QComboBox, QLineEdit, QScrollArea, QFrame,
                             QDateEdit, QDoubleSpinBox, QMessageBox, QInputDialog, QMenu, QCheckBox,
                             QSizePolicy, QProgressDialog, QStackedWidget, QTabWidget, QDialog,
                             QToolButton, QButtonGroup)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QSettings, QPoint, QCoreApplication, QEvent
from PyQt6.QtGui import QAction
import json

# Projekt-Imports
try:
    from gui.filter_manager import FilterManagerDialog
    from core.filter_tree import NodeType, FilterNode
    from core.metadata_normalizer import MetadataNormalizer
    from core.semantic_translator import SemanticTranslator
    from core.query_parser import QueryParser
    from core.models.types import DocType
    from gui.widgets.multi_select_combo import MultiSelectComboBox
    from gui.widgets.date_range_picker import DateRangePicker
    from gui.widgets.tag_input import TagInputWidget
    # NEU: Beide aus separaten Dateien importieren
    from gui.widgets.filter_group import FilterGroupWidget
    from gui.widgets.filter_condition import FilterConditionWidget
    from gui.workers import BatchTaggingWorker
    from core.workflow import WorkflowRuleRegistry
except ImportError as e:
    print(f"Warnung: Importfehler in advanced_filter.py: {e}")
    # --- MOCKS START ---
    # ... (Mocks bleiben zur Sicherheit drin, gekürzt für Übersicht)
    class FilterManagerDialog(QDialog):
        filter_selected = pyqtSignal(object)
        def __init__(self, *args, **kwargs): super().__init__()
    class FilterGroupWidget(QWidget): # Mock
        changed = pyqtSignal()
        def __init__(self, *args, **kwargs): super().__init__()
        def set_query(self, d): pass
        def get_query(self): return {}
        def clear(self): pass
        def update_metadata(self, *args): pass
        def add_condition(self, d=None): pass
    # ... weitere Mocks ...
    # --- MOCKS END ---

try:
    from gui.utils import show_selectable_message_box, show_notification
except ImportError:
    def show_selectable_message_box(parent, title, text, icon=QMessageBox.Icon.Information, buttons=QMessageBox.StandardButton.Ok):
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(icon)
        msg.setStandardButtons(buttons)
        return msg.exec()

# HINWEIS: FilterConditionWidget wurde ausgelagert nach gui/widgets/filter_condition.py

class AdvancedFilterWidget(QWidget):
    """
    Widget to build complex query objects.
    """
    filter_changed = pyqtSignal(dict) # Emits Query Object
    trash_mode_changed = pyqtSignal(bool) # New signal for Trash Mode
    request_apply_rule = pyqtSignal(object, str) # rule, scope ("ALL", "FILTERED", "SELECTED")
    search_triggered = pyqtSignal(str) # Emits the raw search text for highlighting

    def __init__(self, parent=None, db_manager=None, filter_tree=None, save_callback=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.filter_tree = filter_tree
        self.save_callback = save_callback
        self.extra_keys = []
        self.available_tags = []
        self.available_system_tags = []
        self.available_workflow_steps = []
        self.loaded_filter_node = None
        self._loading = False
        self.parser = QueryParser() # For smart search

        if self.db_manager:
            self.extra_keys = self.db_manager.get_available_extra_keys()
            if hasattr(self.db_manager, "get_available_tags"):
                self.available_tags = self.db_manager.get_available_tags(system=False)
                self.available_system_tags = self.db_manager.get_available_tags(system=True)

        self._init_ui()
        self.retranslate_ui()
        self.refresh_dynamic_data()
        self.load_known_filters()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)

        # Custom Sub-Navigation Bar
        sub_nav_container = QWidget()
        sub_nav_layout = QHBoxLayout(sub_nav_container)
        sub_nav_layout.setContentsMargins(0, 0, 0, 5)
        sub_nav_layout.setSpacing(5)

        self.sub_mode_group = QButtonGroup(self)
        self.sub_mode_group.setExclusive(False) # Manual toggle logic

        button_height = 30
        button_style = f"""
            QToolButton {{ 
                padding: 0px 5px; 
                height: {button_height}px;
                border: 1px solid #ddd; 
                border-radius: 4px;
                background: #f8f9fa;
                color: #555; 
                font-size: 13px; 
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

        self.sub_mode_buttons = {}
        modes = [
            (0, "🔍", "Search"),
            (1, "🎯", "Filter"),
            (2, "🤖", "Rules")
        ]

        for idx, icon, key in modes:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setFixedHeight(button_height)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setStyleSheet(button_style)
            btn.clicked.connect(lambda checked, i=idx: self._on_sub_mode_clicked(i))
            sub_nav_layout.addWidget(btn)
            self.sub_mode_group.addButton(btn, idx)
            self.sub_mode_buttons[idx] = (btn, icon, key)

        sub_nav_layout.addStretch()
        layout.addWidget(sub_nav_container)
        
        # Consistent vertical spacing (10px gap before content starts)
        self.nav_spacer = QWidget()
        self.nav_spacer.setFixedHeight(10)
        layout.addWidget(self.nav_spacer)

        # Horizontal separator
        self.sep_line = QFrame()
        self.sep_line.setFrameShape(QFrame.Shape.HLine)
        self.sep_line.setFrameShadow(QFrame.Shadow.Sunken)
        self.sep_line.setStyleSheet("background-color: #ddd; max-height: 1px; margin-bottom: 12px;")
        layout.addWidget(self.sep_line)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        
        self._update_stack_visibility()

        # --- TAB 1: Suche ---
        self.search_tab = QWidget()
        search_layout = QVBoxLayout(self.search_tab)

        s_row = QHBoxLayout()
        self.lbl_search_header = QLabel("")
        s_row.addWidget(self.lbl_search_header)
        self.txt_smart_search = QLineEdit()
        self.txt_smart_search.returnPressed.connect(self._on_smart_search)
        s_row.addWidget(self.txt_smart_search)

        self.btn_apply_search = QPushButton("")
        self.btn_apply_search.clicked.connect(self._on_smart_search)
        s_row.addWidget(self.btn_apply_search)
        search_layout.addLayout(s_row)

        # Options & Status Row
        opt_layout = QHBoxLayout()
        self.chk_search_scope = QCheckBox("")
        opt_layout.addWidget(self.chk_search_scope)

        opt_layout.addStretch()

        self.lbl_search_status = QLabel("")
        self.lbl_search_status.setStyleSheet("color: #666; font-style: italic;")
        opt_layout.addWidget(self.lbl_search_status)

        search_layout.addLayout(opt_layout)
        search_layout.addStretch()

        self.stack.addWidget(self.search_tab)

        # --- TAB 2: Ansicht filtern ---
        self.filter_tab = QWidget()
        filter_layout = QVBoxLayout(self.filter_tab)

        # Top Bar (Management)
        top_bar = QHBoxLayout()
        self.lbl_filter_select = QLabel("")
        top_bar.addWidget(self.lbl_filter_select)
        self.combo_filters = QComboBox()
        self.combo_filters.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_filters.setMinimumWidth(150)
        self.combo_filters.currentIndexChanged.connect(self._on_saved_filter_selected)
        top_bar.addWidget(self.combo_filters, 1) # Still stretch 1 to fill available space

        self.btn_revert = QPushButton()
        self.btn_revert.setFixedHeight(30)
        self.btn_revert.setToolTip(self.tr("Revert Changes"))
        self.btn_revert.setEnabled(False)
        self.btn_revert.clicked.connect(self.revert_changes)
        top_bar.addWidget(self.btn_revert)

        self.btn_save = QPushButton()
        self.btn_save.setFixedHeight(30)
        self.btn_save.clicked.connect(self.save_current_filter)
        top_bar.addWidget(self.btn_save)

        self.btn_manage = QPushButton()
        self.btn_manage.setFixedHeight(30)
        self.btn_manage.setToolTip(self.tr("Manage Filters"))
        self.btn_manage.clicked.connect(self.manage_filters)
        top_bar.addWidget(self.btn_manage)

        self.btn_export = QPushButton()
        self.btn_export.setFixedHeight(30)
        self.btn_export.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 4px 16px;")
        self.btn_export.setToolTip(self.tr("Export filter"))
        self.btn_export.clicked.connect(self.export_current_filter)
        top_bar.addWidget(self.btn_export)
        filter_layout.addLayout(top_bar)
        
        # Add Drag & Drop support
        self.setAcceptDrops(True)

        # Conditions Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.root_group = FilterGroupWidget(extra_keys=self.extra_keys,
                                            available_tags=self.available_tags,
                                            available_system_tags=self.available_system_tags,
                                            available_workflow_steps=self.available_workflow_steps,
                                            is_root=True)
        self.root_group.changed.connect(self._set_dirty)
        self.scroll.setWidget(self.root_group)
        filter_layout.addWidget(self.scroll, 1)

        # Bottom Bar
        bottom_bar = QHBoxLayout()
        self.btn_clear = QPushButton("")
        self.btn_clear.setEnabled(False) # Grey out if empty
        self.btn_clear.clicked.connect(lambda: self.clear_all(reset_combo=True))
        bottom_bar.addWidget(self.btn_clear)
        bottom_bar.addStretch()

        self.btn_apply = QPushButton("")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._emit_change)
        bottom_bar.addWidget(self.btn_apply)

        self.chk_active = QCheckBox("")
        self.chk_active.setChecked(True)
        self.chk_active.toggled.connect(self._on_active_toggled)
        bottom_bar.addWidget(self.chk_active)
        filter_layout.addLayout(bottom_bar)

        self.stack.addWidget(self.filter_tab)

        # --- TAB 3: Auto-Tagging Rules ---
        self._init_rules_tab()
        self.stack.addWidget(self.rules_tab)

    def _init_rules_tab(self):
        self.rules_tab = QWidget()
        rules_layout = QVBoxLayout(self.rules_tab)

        # Top Bar (Management) - Harmonized with Filter View
        top_bar = QHBoxLayout()
        self.lbl_rule_select = QLabel("")
        top_bar.addWidget(self.lbl_rule_select)
        self.combo_rules = QComboBox()
        self.combo_rules.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_rules.setMinimumWidth(150)
        self.combo_rules.currentIndexChanged.connect(self._on_saved_rule_selected)
        top_bar.addWidget(self.combo_rules, 1)

        self.btn_revert_rule = QPushButton("")
        self.btn_revert_rule.setFixedHeight(30)
        self.btn_revert_rule.setEnabled(False)
        self.btn_revert_rule.clicked.connect(self.revert_rule_changes)
        top_bar.addWidget(self.btn_revert_rule)

        self.btn_save_rule = QPushButton()
        self.btn_save_rule.setFixedHeight(30)
        self.btn_save_rule.clicked.connect(self._on_save_rule_clicked)
        top_bar.addWidget(self.btn_save_rule)

        self.btn_manage_rules = QPushButton("")
        self.btn_manage_rules.setFixedHeight(30)
        self.btn_manage_rules.clicked.connect(self.manage_rules)
        top_bar.addWidget(self.btn_manage_rules)
        rules_layout.addLayout(top_bar)

        # Metadata / Tagging Row
        meta_row = QHBoxLayout()
        self.lbl_tags_add = QLabel("")
        meta_row.addWidget(self.lbl_tags_add)

        self.edit_tags_add = TagInputWidget()
        self.edit_tags_add.tagsChanged.connect(self._set_rule_dirty)
        meta_row.addWidget(self.edit_tags_add, 1)

        self.lbl_tags_rem = QLabel("")
        meta_row.addWidget(self.lbl_tags_rem)
        self.edit_tags_rem = TagInputWidget()
        self.edit_tags_rem.tagsChanged.connect(self._set_rule_dirty)
        meta_row.addWidget(self.edit_tags_rem, 1)
        rules_layout.addLayout(meta_row)

        # Phase 126: Workflow Assignment Row
        wf_row = QHBoxLayout()
        self.lbl_assign_wf = QLabel("")
        wf_row.addWidget(self.lbl_assign_wf)
        self.combo_assign_wf = QComboBox()
        self.combo_assign_wf.currentIndexChanged.connect(self._set_rule_dirty)
        wf_row.addWidget(self.combo_assign_wf, 1)
        wf_row.addStretch()
        rules_layout.addLayout(wf_row)
        
        self._populate_wf_combo()

        # Conditions Area (Mirrored FilterGroupWidget)
        self.rules_scroll = QScrollArea()
        self.rules_scroll.setWidgetResizable(True)
        self.rules_root_group = FilterGroupWidget(extra_keys=self.extra_keys,
                                                  available_tags=self.available_tags,
                                                  available_workflow_steps=self.available_workflow_steps,
                                                  is_root=True)
        self.rules_root_group.changed.connect(self._set_rule_dirty)
        self.rules_scroll.setWidget(self.rules_root_group)
        rules_layout.addWidget(self.rules_scroll, 1)

        # Bottom Bar (Processing)
        bottom_bar = QHBoxLayout()
        self.btn_clear_rule = QPushButton("")
        self.btn_clear_rule.setEnabled(False)
        self.btn_clear_rule.clicked.connect(self.clear_rule)
        bottom_bar.addWidget(self.btn_clear_rule)

        bottom_bar.addStretch()

        self.btn_create_view = QPushButton("")
        self.btn_create_view.setEnabled(False)
        self.btn_create_view.clicked.connect(self.create_view_filter_from_rule)
        bottom_bar.addWidget(self.btn_create_view)

        self.btn_apply_view = QPushButton("")
        self.btn_apply_view.setEnabled(False)
        self.btn_apply_view.clicked.connect(self._on_apply_rule_to_view)
        bottom_bar.addWidget(self.btn_apply_view)

        self.btn_apply_all = QPushButton("")
        self.btn_apply_all.setStyleSheet("font-weight: bold; background-color: #f1f8e9;")
        self.btn_apply_all.setEnabled(False)
        self.btn_apply_all.clicked.connect(self._on_batch_run_clicked)
        bottom_bar.addWidget(self.btn_apply_all)

        self.chk_rule_enabled = QCheckBox("")
        self.chk_rule_enabled.setChecked(True)
        self.chk_rule_enabled.toggled.connect(self._set_rule_dirty)
        bottom_bar.addWidget(self.chk_rule_enabled)

        self.chk_rule_auto = QCheckBox("")
        self.chk_rule_auto.setChecked(True)
        self.chk_rule_auto.toggled.connect(self._set_rule_dirty)
        bottom_bar.addWidget(self.chk_rule_auto)

        rules_layout.addLayout(bottom_bar)

        # Populate rules combo
        self._load_rules_to_combo()

    def _populate_wf_combo(self):
        """Fill the workflow assignment combo with available playbooks."""
        self.combo_assign_wf.blockSignals(True)
        self.combo_assign_wf.clear()
        self.combo_assign_wf.addItem(self.tr("--- No Change ---"), None)
        
        registry = WorkflowRuleRegistry()
        for pb in registry.list_rules():
            self.combo_assign_wf.addItem(pb.name or pb.id, pb.id)
        self.combo_assign_wf.blockSignals(False)

    def _load_rules_to_combo(self):
        self.combo_rules.blockSignals(True)
        self.combo_rules.clear()
        self.combo_rules.addItem(self.tr("--- Saved Rule ---"), None)

        if not self.filter_tree:
            self.combo_rules.blockSignals(False)
            return

        rules = self.filter_tree.get_active_rules(only_auto=False)

        for rule in rules:
            self.combo_rules.addItem(rule.name, rule)
        self.combo_rules.blockSignals(False)

    def _on_saved_rule_selected(self, index):
        rule = self.combo_rules.currentData()
        if not rule:
            self.clear_rule()
            return

        # Load rule into UI
        self.edit_tags_add.blockSignals(True)
        self.edit_tags_rem.blockSignals(True)
        self.edit_tags_add.setText(", ".join(rule.tags_to_add))
        self.edit_tags_rem.setText(", ".join(rule.tags_to_remove))
        self.edit_tags_add.blockSignals(False)
        self.edit_tags_rem.blockSignals(False)

        self.chk_rule_enabled.blockSignals(True)
        self.chk_rule_auto.blockSignals(True)
        self.chk_rule_enabled.setChecked(rule.is_enabled)
        self.chk_rule_auto.setChecked(rule.auto_apply)
        self.chk_rule_enabled.blockSignals(False)
        self.chk_rule_auto.blockSignals(False)

        self.rules_root_group.blockSignals(True)
        self.rules_root_group.set_query(rule.data)
        self.rules_root_group.blockSignals(False)

        # Load Workflow assignment
        self.combo_assign_wf.blockSignals(True)
        if rule.assign_workflow:
            idx = self.combo_assign_wf.findData(rule.assign_workflow)
            self.combo_assign_wf.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.combo_assign_wf.setCurrentIndex(0)
        self.combo_assign_wf.blockSignals(False)

        self._reset_rule_dirty()

    def _set_rule_dirty(self):
        """Enable buttons when rule has unsaved changes."""
        self.btn_revert_rule.setEnabled(True)
        self.btn_apply_view.setEnabled(True)
        self.btn_apply_all.setEnabled(True)
        self.btn_clear_rule.setEnabled(True)

        has_tags = bool(self.edit_tags_add.text().strip())
        self.btn_create_view.setEnabled(has_tags)

        self.btn_save_rule.setStyleSheet("font-weight: bold; color: blue;")

    def _reset_rule_dirty(self):
        """Disable buttons after save/load. Harmonized with Filter View."""
        self.btn_revert_rule.setEnabled(False)
        self.btn_apply_view.setEnabled(False)
        self.btn_apply_all.setEnabled(False)

        query = self.rules_root_group.get_query()
        has_query = bool(query and query.get("conditions"))

        self.btn_revert_rule.setEnabled(False)
        self.btn_clear_rule.setEnabled(has_query)

        has_tags = bool(self.edit_tags_add.text().strip())
        self.btn_create_view.setEnabled(has_tags)

        self.btn_save_rule.setStyleSheet("")

    def revert_rule_changes(self):
        self._on_saved_rule_selected(self.combo_rules.currentIndex())

    def clear_rule(self):
        self._on_new_rule_clicked()

    def _on_new_rule_clicked(self):
        self.combo_rules.blockSignals(True)
        self.combo_rules.setCurrentIndex(0)
        self.combo_rules.blockSignals(False)
        self.edit_tags_add.clear()
        self.edit_tags_rem.clear()
        self.chk_rule_enabled.setChecked(True)
        self.chk_rule_auto.setChecked(True)
        self.rules_root_group.clear()
        self.combo_assign_wf.setCurrentIndex(0)
        self._reset_rule_dirty()

    def manage_rules(self):
        # Find "Tags" folder for focus
        start_node = None
        for child in self.filter_tree.root.children:
            if child.name == "Tags":
                start_node = child
                break

        dlg = FilterManagerDialog(self.filter_tree, db_manager=self.db_manager, parent=self, start_node=start_node)
        dlg.exec()
        self._load_rules_to_combo()

    def _on_apply_rule_to_view(self):
        """Apply ONLY the condition part of the rule to the list view."""
        query = self.rules_root_group.get_query()
        if query:
            self.request_apply_filter.emit(query)

    def create_view_filter_from_rule(self):
        """Transforms the tagging result of this rule into a view filter."""
        tags = [t.strip() for t in self.edit_tags_add.text().split(",") if t.strip()]
        if not tags:
            show_selectable_message_box(self, self.tr("Create View-filter"), self.tr("No 'Add Tags' defined. Cannot create a filter for nothing."), icon=QMessageBox.Icon.Information)
            return

        name = self.combo_rules.currentText()
        if self.combo_rules.currentIndex() <= 0:
            name = "New Filter"

        name, ok = QInputDialog.getText(self, self.tr("Create View-filter"),
                                        self.tr("Filter Name:"), QLineEdit.EchoMode.Normal, f"View: {name}")
        if not ok or not name:
            return

        # Create filter query: matches docs having ALL of these tags
        query = {
            "operator": "AND",
            "conditions": [
                {
                    "field": "tags",
                    "op": "contains",
                    "value": tags,
                    "negate": False
                }
            ]
        }

        # Find/Ensure "Views" folder
        parent = self.filter_tree.root
        for child in self.filter_tree.root.children:
            if child.name == "Views":
                parent = child
                break

        self.filter_tree.add_filter(parent, name, query)
        if self.save_callback:
            self.save_callback()

        show_notification(self, self.tr("Filter Created"),
                          self.tr("A new view filter '%s' has been created in the 'Views' folder.") % name)
        self.load_known_filters() # Refresh filters tab combo

    def _on_save_rule_clicked(self):
        current_node = self.combo_rules.currentData() # FilterNode object

        name = ""
        if current_node:
            name = current_node.name

        name, ok = QInputDialog.getText(self, self.tr("Save Rule"), self.tr("Rule Name:"), QLineEdit.EchoMode.Normal, name)
        if not ok or not name:
            return

        tags_add = [t.strip() for t in self.edit_tags_add.text().split(",") if t.strip()]
        tags_rem = [t.strip() for t in self.edit_tags_rem.text().split(",") if t.strip()]

        query = self.rules_root_group.get_query()

        if current_node:
            # Update existing node
            current_node.name = name
            current_node.data = query
            current_node.tags_to_add = tags_add
            current_node.tags_to_remove = tags_rem
            current_node.assign_workflow = self.combo_assign_wf.currentData()
            current_node.is_enabled = self.chk_rule_enabled.isChecked()
            current_node.auto_apply = self.chk_rule_auto.isChecked()
        else:
            # Add to "Tags" folder if exists, else root
            parent = self.filter_tree.root
            for child in self.filter_tree.root.children:
                if child.name == "Tags":
                    parent = child
                    break

            new_node = self.filter_tree.add_filter(parent, name, query)
            new_node.tags_to_add = tags_add
            new_node.tags_to_remove = tags_rem
            new_node.assign_workflow = self.combo_assign_wf.currentData()
            new_node.is_enabled = self.chk_rule_enabled.isChecked()
            new_node.auto_apply = self.chk_rule_auto.isChecked()

        # Trigger persistence via MainWindow
        if self.save_callback:
            self.save_callback()

        self._load_rules_to_combo()
        # Reselect
        idx = self.combo_rules.findText(name)
        if idx >= 0:
             self.combo_rules.setCurrentIndex(idx)

        self._reset_rule_dirty()

    def _on_delete_rule_clicked(self):
        node = self.combo_rules.currentData()
        if not node or not node.parent: return

        if show_selectable_message_box(self, self.tr("Delete Rule"),
                                        self.tr("Are you sure you want to delete this rule?"),
                                        icon=QMessageBox.Icon.Question,
                                        buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            node.parent.remove_child(node)
            if self.save_callback:
                self.save_callback()
            self._load_rules_to_combo()
            self._on_new_rule_clicked()

    def _on_batch_run_clicked(self):
        node = self.combo_rules.currentData()

        tags_add = [t.strip() for t in self.edit_tags_add.text().split(",") if t.strip()]
        tags_rem = [t.strip() for t in self.edit_tags_rem.text().split(",") if t.strip()]

        # Create a temporary node for execution if it's not a saved one
        rule = FilterNode(
            name=self.combo_rules.currentText() if node else "Unsaved Rule",
            node_type=NodeType.FILTER,
            data=self.rules_root_group.get_query()
        )
        rule.tags_to_add = tags_add
        rule.tags_to_remove = tags_rem
        rule.is_enabled = True
        rule.auto_apply = self.chk_rule_auto.isChecked()

        menu = QMenu(self)

        act_all = QAction(self.tr("Apply to ALL documents"), self)
        act_all.triggered.connect(lambda: self.request_apply_rule.emit(rule, "ALL"))
        menu.addAction(act_all)

        act_filtered = QAction(self.tr("Apply to current List View (Filtered)"), self)
        act_filtered.triggered.connect(lambda: self.request_apply_rule.emit(rule, "FILTERED"))
        menu.addAction(act_filtered)

        act_selected = QAction(self.tr("Apply to SELECTED documents only"), self)
        act_selected.triggered.connect(lambda: self.request_apply_rule.emit(rule, "SELECTED"))
        menu.addAction(act_selected)

        # Show menu below button
        btn = self.sender() # The button
        if btn:
            menu.exec(btn.mapToGlobal(QPoint(0, btn.height())))
        else:
            menu.exec(self.mapToGlobal(QPoint(100, 100)))

    def run_batch_tagging(self, rule, uuids=None):
        """Called by MainWindow with resolved UUIDs to start the actual processing."""
        scope_text = self.tr("all documents") if uuids is None else self.tr("%d selected/filtered documents") % len(uuids)

        reply = show_selectable_message_box(self, self.tr("Apply Rule"),
                                     self.tr("Apply rule '%s' to %s? This cannot be undone automatically.") % (rule.name, scope_text),
                                     icon=QMessageBox.Icon.Question,
                                     buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            progress = QProgressDialog(self.tr("Applying rule..."), self.tr("Cancel"), 0, 100, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)

            self.worker = BatchTaggingWorker(self.db_manager, self.filter_tree, rules=rule, uuids=uuids)
            self.worker.progress.connect(lambda c, t: progress.setValue(c) or progress.setMaximum(t))
            self.worker.finished.connect(lambda count: self._on_batch_finished(progress, count))

            progress.canceled.connect(self.worker.cancel)
            self.worker.start()
            progress.show()

    def _on_batch_finished(self, progress, count):
        progress.close()
        show_notification(self, self.tr("Complete"),
                          self.tr("Rule applied. %d documents modified.") % count)
        # Refresh UI? Better to emit a signal so MainWindow can refresh list.
        self.refresh_dynamic_data()

    def _on_sub_mode_clicked(self, index):
        btn = self.sub_mode_group.button(index)
        
        # If we clicked the already checked button -> uncheck all
        if not btn.isChecked():
            # This happens if clicking a checked button with non-exclusive group?
            # Actually, with non-exclusive, clicking toggles normally.
            pass

        # Since we want "one or none", if checking one, uncheck others
        if btn.isChecked():
            for other in self.sub_mode_group.buttons():
                if other != btn:
                    other.setChecked(False)
            self.stack.setCurrentIndex(index)
        
        self._update_stack_visibility()
    def _update_stack_visibility(self):
        has_selection = any(b.isChecked() for b in self.sub_mode_group.buttons())
        self.stack.setVisible(has_selection)
        self.sep_line.setVisible(has_selection)
        if hasattr(self, 'nav_spacer'):
            self.nav_spacer.setVisible(has_selection)
        
        # KEEP TOP MARGIN STABLE at 10 to avoid jumping!
        # Bottom margin is 10 when open, 5 when closed for a tiny breathing room
        self.layout().setContentsMargins(10, 10, 10, 10 if has_selection else 5)
        
        if not has_selection:
            # Fixed height to avoid any redistribution of space in Splitter
            # 10 (top) + 30 (button) + 5 (internal layout bottom) + 3 (new bottom margin) = 48
            self.setFixedHeight(48) 
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.setFixedHeight(16777215) 
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self.updateGeometry() # Force parent splitter to reconsider

    def _on_smart_search(self):
        text = self.txt_smart_search.text().strip()
        print(f"[Search-Debug] Raw Input: '{text}'")

        # 1. Validation
        if len(text) < 3:
            self.lbl_search_status.setText(self.tr("Search string too short (min 3 chars)"))
            self.lbl_search_status.setStyleSheet("color: red;")
            return

        self.lbl_search_status.setText(self.tr("Searching..."))
        self.lbl_search_status.setStyleSheet("color: black;")
        # Process UI updates immediately
        QCoreApplication.processEvents()

        criteria = self.parser.parse(text)
        print(f"[Search-Debug] Parser Output criteria: {criteria}")

        # Fix: Normalize Parser Keys to Internal filter keys
        if "text_search" in criteria:
            criteria["fulltext"] = criteria.pop("text_search")

        if "type" in criteria:
             # Convert single type to list "types"
             criteria["types"] = [criteria.pop("type")]

        print(f"[Search-Debug] Normalized criteria: {criteria}")

        # Phase 106: Deep Search for fulltext using Raw Data if available
        if criteria.get("fulltext") and self.db_manager:
             print(f"[Search-Debug] Performing Deep Search for text: '{criteria['fulltext']}'")
             # Find UUIDs that match the text in RAW or CACHE
             deep_uuids = self.db_manager.get_virtual_uuids_with_text_content(criteria["fulltext"])
             criteria["deep_uuids"] = deep_uuids
             print(f"[Search-Debug] Deep Search found {len(deep_uuids)} UUIDs")
             if len(deep_uuids) > 0:
                 print(f"[Search-Debug] Sample UUIDs: {deep_uuids[:3]}")

        # 2. Build Text Query
        text_query = self._criteria_to_query(criteria)

        # 3. Handle Scope
        final_query = text_query
        scope_msg = self.tr("in all documents")

        if self.chk_search_scope.isChecked():
            # Merge with "Filter View"
            current_filter = self.root_group.get_query()
            if current_filter and current_filter.get("conditions"):
                final_query = {
                    "operator": "AND",
                    "conditions": [current_filter, text_query]
                }
                scope_msg = self.tr("in current view")

        print(f"[Search-Debug] Final Query: {json.dumps(final_query)}")

        # 4. Count & Feedback
        count = 0
        if self.db_manager:
            try:
                count = self.db_manager.count_documents_advanced(final_query)
            except Exception as e:
                print(f"[Search] Count failed: {e}")

        print(f"[Search-Debug] Count Result: {count}")
        self.lbl_search_status.setText(self.tr(f"{count} Documents found ({scope_msg})"))
        self.lbl_search_status.setStyleSheet("color: green;" if count > 0 else "color: red;")

        # Inject debug meta info for MainWindow
        final_query["_meta_fulltext"] = text

        self.filter_changed.emit(final_query)
        self.search_triggered.emit(text)

    def _criteria_to_query(self, criteria: dict) -> dict:
        # Simple translation for now
        # { 'fulltext': '...', 'tags': [...], 'types': [...] }
        conditions = []

        # Handle Deep Search Results
        if "deep_uuids" in criteria:
            found = criteria["deep_uuids"]
            if found:
                conditions.append({"field": "uuid", "op": "in", "value": found})
            else:
                # Nothing found in Deep Search -> Force empty result
                conditions.append({"field": "uuid", "op": "equals", "value": "__NO_MATCH__"})
        elif criteria.get("fulltext"):
            # Fallback (legacy or no DB access)
            conditions.append({"field": "cached_full_text", "op": "contains", "value": criteria["fulltext"]})

        if criteria.get("tags"):
            conditions.append({"field": "type_tags", "op": "contains", "value": criteria["tags"]})
        if criteria.get("types"):
            conditions.append({"field": "classification", "op": "in", "value": criteria["types"]})

        return {"operator": "AND", "conditions": conditions}

    def add_condition(self, data=None):
        # Delegate to root group
        self.root_group.add_condition(data)

    def refresh_dynamic_data(self):
        """Re-fetch extra keys and tags from DB and refresh UI components."""
        if not self.db_manager: return

        print("[DEBUG] AdvancedFilter: Refreshing dynamic metadata (Stamps/Tags)...")
        self.extra_keys = self.db_manager.get_available_extra_keys()
        if self.db_manager:
            self.available_tags = self.db_manager.get_available_tags(system=False)
            self.available_system_tags = self.db_manager.get_available_tags(system=True)
            
            # 113: Collect available workflow steps from rules
            registry = WorkflowRuleRegistry()
            self.available_workflow_steps = registry.get_all_steps()

        if self.root_group:
            self.root_group.update_metadata(self.extra_keys, self.available_tags, 
                                            self.available_system_tags, self.available_workflow_steps)

    def remove_condition(self, row):
        # Handled internally by groups
        pass

    def clear_all(self, reset_combo=True):
        self._reset_dirty_indicator()
        if reset_combo and isinstance(reset_combo, bool):
            self.combo_filters.setCurrentIndex(0)

        self.root_group.clear()
        self._set_dirty()
        # Auto-apply to update view immediately (UX feedback)
        self._emit_change()

    def get_query(self):
        """Returns the current query from the UI."""
        return self.get_query_object()

    def load_from_node(self, node: FilterNode):
        self._loading = True
        self.loaded_filter_node = node

        # Clear UI
        self.root_group.clear()

        # Load Data
        data = node.data
        if data:
            self.root_group.set_query(data)

        self._loading = False
        self._reset_dirty_indicator()
        self.btn_apply.setEnabled(False)
        self.btn_revert.setEnabled(False)
        self.chk_active.setChecked(True) # Assume active upon load

        # Auto-Apply on Load? Usually yes for saved filters.
        self._emit_change()


    def _set_dirty(self):
        if getattr(self, '_loading', False):
            return

        if self.btn_apply:
            self.btn_apply.setEnabled(True)

        if self.btn_clear:
            self.btn_clear.setEnabled(True)

        if self.btn_revert and self.loaded_filter_node:
             self.btn_revert.setEnabled(True)

        # Ignore Trash Node
        if self.loaded_filter_node and hasattr(self.loaded_filter_node, "node_type") and self.loaded_filter_node.node_type == NodeType.TRASH:
            return

        if self.loaded_filter_node:
            idx = self.combo_filters.findData(self.loaded_filter_node)
            if idx >= 0:
                current_text = self.combo_filters.itemText(idx)
                if not current_text.endswith(" *"):
                     self.combo_filters.setItemText(idx, current_text + " *")

    def _reset_dirty_indicator(self):
        """Removes the * from the currently loaded filter in the combo."""
        if self.btn_revert:
            self.btn_revert.setEnabled(False)

        # Update Clear All button based on content
        query = self.get_query_object()
        has_query = bool(query and query.get("conditions"))
        if self.btn_clear:
            self.btn_clear.setEnabled(has_query)

        if self.loaded_filter_node:
            idx = self.combo_filters.findData(self.loaded_filter_node)
            if idx >= 0:
                current_text = self.combo_filters.itemText(idx)
                if current_text.endswith(" *"):
                     self.combo_filters.setItemText(idx, current_text[:-2])

    def _on_active_toggled(self, checked):
        # Toggling active state applied immediately
        self._emit_change()

    def _emit_change(self):
        query = self.get_query_object()

        if self.btn_apply:
            self.btn_apply.setEnabled(False) # Clean state

        if not self.chk_active.isChecked():
            # If disabled, emit empty query (all docs)
            # But we keep the query object internally in UI
            self.filter_changed.emit({})
            return

        print(f"[DEBUG] AdvancedFilter Emitting: {json.dumps(query, default=str)}")
        self.filter_changed.emit(query)

    def get_query_object(self):
        # Delegate to root group
        if self.root_group:
            return self.root_group.get_query()
        return {}

    # --- Persistence ---
    def load_known_filters(self):
        self.combo_filters.blockSignals(True)
        self.combo_filters.clear()
        self.combo_filters.addItem(self.tr("--- Saved Filter ---"), None)

        if self.filter_tree:
            # Add Favorites (by UUID -> lookup)
            # For MVP, populate from all known filters or just favorites?
            # Let's populate from Root Children that are Filters for now?
            # Or traverse favorites.
            # Tree API has 'favorites' list of IDs.
            # But we don't have easy ID lookup in Tree.
            # Recursively add all filters to combo logic
            def add_nodes(node, path_prefix=""):
                for child in node.children:
                     if child.node_type == NodeType.FILTER:
                         display = f"{path_prefix}{child.name}" if path_prefix else child.name
                         self.combo_filters.addItem(display, child)
                     elif child.node_type == NodeType.TRASH:
                         # Always show Trash at top level or appropriate usage
                         display = f"[ {child.name} ]"
                         self.combo_filters.addItem(display, child)
                     elif child.node_type == NodeType.FOLDER:
                         new_prefix = f"{path_prefix}{child.name} / " if path_prefix else f"{child.name} / "
                         add_nodes(child, new_prefix)

            add_nodes(self.filter_tree.root)

            # Separator
            self.combo_filters.insertSeparator(self.combo_filters.count())
            self.combo_filters.addItem(self.tr("Browse All..."), "BROWSE_ALL")

        self.combo_filters.blockSignals(False)


    def _on_saved_filter_selected(self, index):
        data = self.combo_filters.currentData()
        if not data:
            self.loaded_filter_node = None
            return

        if data == "BROWSE_ALL":
            self.combo_filters.blockSignals(True)
            self.combo_filters.setCurrentIndex(0)
            self.combo_filters.blockSignals(False)
            self.open_filter_manager()
            return

        # Check if it is a FilterNode Object (which has node_type)
        if hasattr(data, "node_type") and data.node_type == NodeType.TRASH:
             self.loaded_filter_node = data
             # Standardize Trash as a normal filter Query
             # This ensures verify logic in DocumentList.apply_advanced_filter works.
             # Must be a Group structure since set_query expects 'conditions' list.
             trash_query = {
                 "operator": "AND",
                 "conditions": [
                     {"field": "deleted", "op": "equals", "value": True}
                 ]
             }
             self.load_from_object(trash_query)
             self._emit_change()
             return

        # It's a FilterNode or saved dict (legacy)
        # We stored FilterNode object in addItem

        # Ensure we exit trash mode
        self.trash_mode_changed.emit(False)

        if hasattr(data, "data"):
             self.load_from_object(data.data)
             self.loaded_filter_node = data # Set loaded reference
             self._emit_change()

    def open_filter_manager(self):
        if not self.filter_tree:
             return
        dlg = FilterManagerDialog(self.filter_tree, db_manager=self.db_manager, parent=self)
        dlg.filter_selected.connect(self._on_manager_selected)
        dlg.exec()

        # Reload combo in case favorites changed or items renamed
        self.load_known_filters()

        # Trigger Save
        if self.save_callback:
            self.save_callback()

        # Restore selection if a filter is loaded (it might be cleared by load_known_filters)
        if self.loaded_filter_node:
             self._sync_combo_selection(self.loaded_filter_node)

    def _on_manager_selected(self, node):
        if not node: return

        if node.node_type == NodeType.TRASH:
            # Special Trash Handling
            self.loaded_filter_node = node
            self.trash_mode_changed.emit(True)
            self._sync_combo_selection(node)
            return

        # Normal Filter
        self.trash_mode_changed.emit(False) # Exit trash mode

        if node.data is not None:
            self.load_from_object(node.data)
            self.loaded_filter_node = node
            self._emit_change()

            self._sync_combo_selection(node)

    def _sync_combo_selection(self, node):
            # Sync Combo
            idx = self.combo_filters.findData(node)
            if idx >= 0:
                self.combo_filters.setCurrentIndex(idx)
            else:
                display_name = f"{node.name} (Folder: {node.parent.name if node.parent else 'Root'})"
                self.combo_filters.insertItem(1, display_name, node)
                self.combo_filters.setCurrentIndex(1)

    def revert_changes(self):
        if self.loaded_filter_node and self.loaded_filter_node.data:
            self.load_from_object(self.loaded_filter_node.data)
            self._emit_change() # Emit clean state
            # _reset_dirty_indicator is called inside load_from_object
            if self.btn_apply:
                self.btn_apply.setEnabled(False) # Clean

    def load_from_object(self, query):
        self._reset_dirty_indicator() # Clear previous *

        self._loading = True
        try:
            self.clear_all(reset_combo=False)
            if not query:
                return

            self.chk_active.blockSignals(True)
            self.chk_active.setChecked(True)
            self.chk_active.blockSignals(False)

            # Use root_group to load nested query
            self.root_group.set_query(query)

        finally:
            self._loading = False
            self.btn_apply.setEnabled(False) # Loaded state is clean
            self.btn_revert.setEnabled(False)
            self._loading = False

    def apply_advanced_filter(self):
        """Public method to force application of current filter."""
        self._emit_change()

    def save_current_filter(self):
        if not self.root_group.children_widgets:
            show_selectable_message_box(self, self.tr("Save Filter"), self.tr("No conditions to save."), icon=QMessageBox.Icon.Warning)
            return

        if not self.filter_tree:
            return

        default_name = self.loaded_filter_node.name if self.loaded_filter_node else ""
        name, ok = QInputDialog.getText(self, self.tr("Save Filter"), self.tr("Filter Name:"), QLineEdit.EchoMode.Normal, default_name)

        if ok and name:
            query = self.get_query_object()

            # Check if we should update existing node (either by reference or name)
            existing_node = None
            if self.loaded_filter_node and self.loaded_filter_node.name == name:
                existing_node = self.loaded_filter_node
            else:
                # Search by name in tree
                all_filters = self.filter_tree.get_all_filters()
                for node in all_filters:
                    if node.name == name:
                        existing_node = node
                        break

            target_node = None
            if existing_node:
                # Update existing
                existing_node.data = query
                self._reset_dirty_indicator()
                target_node = existing_node
            else:
                # Add new to "Views" folder
                parent = self.filter_tree.root
                for child in self.filter_tree.root.children:
                    if child.name == "Views":
                        parent = child
                        break
                target_node = self.filter_tree.add_filter(parent, name, query)

            if self.save_callback:
                self.save_callback()

            self.load_known_filters() # Refresh

            # Select the node
            if target_node:
                idx = self.combo_filters.findData(target_node)
                if idx >= 0:
                    self.combo_filters.setCurrentIndex(idx)
                    self.loaded_filter_node = target_node

    def export_current_filter(self):
        """Exports the current filter to a standalone .kpfx file."""
        query = self.get_query_object()
        if not query or not query.get("conditions"):
             QMessageBox.warning(self, self.tr("Export Filter"), self.tr("No conditions to export."))
             return
             
        from core.exchange import ExchangeService
        name = self.loaded_filter_node.name if self.loaded_filter_node else "CustomFilter"
        
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export Filter"), f"{name}.kpfx", "KPaperFlux Exchange (*.kpfx *.json)")
        if path:
            try:
                # We export it as a smart_list type
                ExchangeService.save_to_file("smart_list", {"name": name, "query": query}, path)
                show_notification(self, self.tr("Export Successful"), self.tr("Filter exported to %s") % os.path.basename(path))
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error"), f"Failed to export filter: {e}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
               return
               
        path = urls[0].toLocalFile()
        if not os.path.exists(path):
               return
               
        from core.exchange import ExchangeService
        payload = ExchangeService.load_from_file(path)
                 
        if payload and payload.type == "smart_list":
             data = payload.payload
             name = data.get("name", "Imported Filter")
             query = data.get("query", {})
             if query:
                  self.load_from_object(query)
                  show_notification(self, self.tr("Filter Imported"), self.tr("Loaded filter: %s") % name)
                  # If we have a filter tree, we could auto-save it, but let's just load it for now
        elif payload:
             QMessageBox.warning(self, self.tr("Import Failed"), self.tr("File is of type '%s', expected 'smart_list'.") % payload.type)

    def manage_filters(self):
        self.open_filter_manager()

    def _show_combo_context(self, pos):
        # MVP: Right click on the collapsed box deletes the currently selected item.
        data = self.combo_filters.currentData()
        idx = self.combo_filters.currentIndex()
        if idx <= 0 or data == "BROWSE_ALL":
             return

        # It's a filter node
        node_name = self.combo_filters.currentText()

        menu = QMenu(self)
        del_action = QAction(f"Delete '{node_name}'", self)
        del_action.triggered.connect(lambda: self._delete_node(data)) # data is the Node or dict
        menu.addAction(del_action)
        menu.exec(self.combo_filters.mapToGlobal(pos))

    def _delete_node(self, node):
        if not self.filter_tree:
            return

        # Check if node is real node
        if hasattr(node, "parent") and node.parent:
            confirm = show_selectable_message_box(
                self, self.tr("Delete Filter"),
                self.tr("Are you sure you want to delete '%s'?") % node.name,
                icon=QMessageBox.Icon.Question,
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                node.parent.remove_child(node)
                if self.save_callback:
                    self.save_callback()
                self.load_known_filters() # Refresh
                self.clear_all(reset_combo=True)

    def _persist(self):
        # Tree persistence managed by MainWindow for now
        pass

    def changeEvent(self, event):
        """Handle language change events."""
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        """Updates all UI strings for on-the-fly localization."""
        # Modes
        for idx, (btn, icon, key) in self.sub_mode_buttons.items():
             btn.setText(f"{icon} {self.tr(key)}")
        
        # Search Tab
        self.lbl_search_header.setText(self.tr("Search:"))
        self.txt_smart_search.setPlaceholderText(self.tr("e.g. Amazon 2024 Invoice..."))
        self.btn_apply_search.setText(self.tr("Go"))
        self.chk_search_scope.setText(self.tr("Search in current view only"))
        self.chk_search_scope.setToolTip(self.tr("If checked, combines the search with the active filters from 'Filter View'."))
        
        # Filter Tab
        self.lbl_filter_select.setText(self.tr("Select:"))
        self.btn_revert.setText(self.tr("Discard"))
        self.btn_revert.setToolTip(self.tr("Revert Changes"))
        self.btn_save.setText(self.tr("Save"))
        self.btn_export.setText("📤 " + self.tr("Export"))
        self.btn_export.setToolTip(self.tr("Export filter"))
        self.btn_manage.setText("⚙️ " + self.tr("Manage"))
        self.btn_manage.setToolTip(self.tr("Manage Filters"))
        self.btn_clear.setText(self.tr("Clear All"))
        self.btn_apply.setText(self.tr("Apply Changes"))
        self.chk_active.setText(self.tr("Filter Active"))

        # Rules Tab
        self.lbl_rule_select.setText(self.tr("Select:"))
        self.btn_revert_rule.setText(self.tr("Revert"))
        self.btn_save_rule.setText(self.tr("Save..."))
        self.btn_manage_rules.setText(self.tr("Manage"))
        self.lbl_tags_add.setText(self.tr("Add Tags:"))
        self.lbl_tags_rem.setText(self.tr("Remove Tags:"))
        self.edit_tags_add.setToolTip(self.tr("Enter tags to add. Press comma or Enter to confirm (e.g. INVOICE, TELEKOM)"))
        self.edit_tags_rem.setToolTip(self.tr("Enter tags to remove. Press comma or Enter to confirm (e.g. DRAFT, REVIEW)"))
        self.lbl_assign_wf.setText(self.tr("Assign Workflow:"))
        self.btn_clear_rule.setText(self.tr("Clear All"))
        self.btn_create_view.setText(self.tr("Create View-filter"))
        self.btn_create_view.setToolTip(self.tr("Create a search-view that filters for the tags this rule adds"))
        self.btn_apply_view.setText(self.tr("Apply to View"))
        self.btn_apply_all.setText(self.tr("Apply to all"))
        self.chk_rule_enabled.setText(self.tr("Active"))
        self.chk_rule_auto.setText(self.tr("Run on Import"))
        self.chk_rule_auto.setToolTip(self.tr("Automatically apply this rule to new documents during import/analysis"))

        # Re-populate combos that have static "Select" headers
        self.load_known_filters()
        self._load_rules_to_combo()
        self._populate_wf_combo()
