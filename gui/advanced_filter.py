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
                             QToolButton, QButtonGroup, QLayout)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QSettings, QPoint, QCoreApplication, QEvent
from PyQt6.QtGui import QAction
import json
from core.logger import get_logger
logger = get_logger("gui.advanced_filter")

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
    logger.warning(f"Import error in advanced_filter.py: {e}")
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

from core.exchange import ExchangeService

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
    archive_mode_changed = pyqtSignal(bool) # [NEW] Signal for Archive Mode
    request_apply_rule = pyqtSignal(object, str) # rule, scope ("ALL", "FILTERED", "SELECTED")
    search_triggered = pyqtSignal(str) # Emits the raw search text for highlighting
    filter_active_changed = pyqtSignal(bool) # [NEW] Signal for active toggle
    size_changed = pyqtSignal() # [NEW] Signal for splitter notification
    next_hit_requested = pyqtSignal()
    prev_hit_requested = pyqtSignal()

    def __init__(self, parent=None, db_manager=None, filter_tree=None, save_callback=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
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
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)
        self.setMinimumHeight(0)

        # Custom Sub-Navigation Bar
        sub_nav_container = QWidget()
        sub_nav_layout = QHBoxLayout(sub_nav_container)
        sub_nav_layout.setContentsMargins(0, 0, 0, 5)
        sub_nav_layout.setSpacing(5)

        self.sub_mode_group = QButtonGroup(self)
        self.sub_mode_group.setExclusive(False) # Manual toggle logic

        from gui.theme import btn_subnav, SUBNAV_HEIGHT
        button_height = SUBNAV_HEIGHT
        button_style = btn_subnav()

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
            
            # Store buttons explicitly for easier access and reliable l10n
            if idx == 0: self.btn_mode_search = btn
            elif idx == 1: self.btn_mode_filter = btn
            elif idx == 2: self.btn_mode_rules = btn

        sub_nav_layout.addStretch()
        layout.addWidget(sub_nav_container)
        
        # Consistent vertical spacing (5px gap before content starts)
        self.nav_spacer = QWidget()
        self.nav_spacer.setFixedHeight(5)
        layout.addWidget(self.nav_spacer)

        # Horizontal separator
        self.sep_line = QFrame()
        self.sep_line.setFrameShape(QFrame.Shape.HLine)
        self.sep_line.setFrameShadow(QFrame.Shadow.Sunken)
        from gui.theme import CLR_BORDER
        self.sep_line.setStyleSheet(f"background-color: {CLR_BORDER}; max-height: 1px; margin-bottom: 0px;")
        layout.addWidget(self.sep_line)

        self.stack = QStackedWidget()
        if self.stack.layout():
            self.stack.layout().setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout.addWidget(self.stack)
        layout.addStretch(1) # [REF] Ensure items are pushed to TOP, giving space back to DocumentList
        
        self._update_stack_visibility()

        # --- TAB 1: Suche ---
        self.search_tab = QWidget()
        self.search_tab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        search_layout = QVBoxLayout(self.search_tab)
        search_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        search_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        search_layout.setContentsMargins(0, 5, 0, 5)
        search_layout.setSpacing(8)

        s_row = QHBoxLayout()
        self.lbl_search_header = QLabel("")
        self.lbl_search_header.setFixedWidth(110)
        s_row.addWidget(self.lbl_search_header)
        self.txt_smart_search = QLineEdit()
        self.txt_smart_search.setClearButtonEnabled(True)
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

        self.btn_hit_prev = QPushButton("▲")
        self.btn_hit_prev.setFixedSize(24, 24)
        self.btn_hit_prev.setVisible(False)
        self.btn_hit_prev.clicked.connect(self.prev_hit_requested.emit)
        opt_layout.addWidget(self.btn_hit_prev)

        self.lbl_hits = QLabel("")
        self.lbl_hits.setStyleSheet("font-weight: bold; margin: 0 4px;")
        self.lbl_hits.setVisible(False)
        opt_layout.addWidget(self.lbl_hits)

        self.btn_hit_next = QPushButton("▼")
        self.btn_hit_next.setFixedSize(24, 24)
        self.btn_hit_next.setVisible(False)
        self.btn_hit_next.clicked.connect(self.next_hit_requested.emit)
        opt_layout.addWidget(self.btn_hit_next)

        opt_spacer = QWidget()
        opt_spacer.setFixedWidth(10)
        opt_layout.addWidget(opt_spacer)

        self.lbl_search_status = QLabel("")
        from gui.theme import CLR_TEXT_SECONDARY
        self.lbl_search_status.setStyleSheet(f"color: {CLR_TEXT_SECONDARY}; font-style: italic;")
        opt_layout.addWidget(self.lbl_search_status)

        search_layout.addLayout(opt_layout)
        # Removed search_layout.addStretch() to avoid red box area

        self.stack.addWidget(self.search_tab)

        # --- TAB 2: Ansicht filtern ---
        self.filter_tab = QWidget()
        self.filter_tab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        filter_layout = QVBoxLayout(self.filter_tab)
        filter_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        filter_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        filter_layout.setContentsMargins(0, 5, 0, 5)
        filter_layout.setSpacing(8)

        # Top Bar (Management)
        top_bar = QHBoxLayout()
        self.lbl_filter_select = QLabel("")
        self.lbl_filter_select.setFixedWidth(110)
        top_bar.addWidget(self.lbl_filter_select)
        self.combo_filters = QComboBox()
        self.combo_filters.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_filters.setMinimumWidth(150)
        # currentIndexChanged is now restricted (only commands), manual "Laden" required for filters
        self.combo_filters.currentIndexChanged.connect(self._on_combo_filter_selected)
        top_bar.addWidget(self.combo_filters, 1)

        self.btn_load = QPushButton("")
        self.btn_load.setFixedHeight(30)
        self.btn_load.setEnabled(False) # [NEW] Disabled until selection
        self.btn_load.clicked.connect(self._on_load_filter_clicked)
        top_bar.addWidget(self.btn_load)

        self.btn_new = QPushButton("")
        self.btn_new.setFixedHeight(30)
        self.btn_new.clicked.connect(self._on_new_filter_clicked)
        top_bar.addWidget(self.btn_new)

        self.btn_manage = QPushButton()
        self.btn_manage.setFixedHeight(30)
        self.btn_manage.clicked.connect(self.manage_filters)
        top_bar.addWidget(self.btn_manage)

        self.chk_active = QCheckBox("")
        self.chk_active.setChecked(False)
        self.chk_active.setEnabled(False)
        self.chk_active.toggled.connect(self._on_active_toggled)
        top_bar.addWidget(self.chk_active)

        self.btn_export = QPushButton()
        self.btn_export.setFixedHeight(30)
        from gui.theme import CLR_SUCCESS, CLR_TEXT_ON_COLOR
        self.btn_export.setStyleSheet(f"background-color: {CLR_SUCCESS}; color: {CLR_TEXT_ON_COLOR}; font-weight: bold; padding: 4px 16px;")
        self.btn_export.clicked.connect(self.export_current_filter)
        top_bar.addWidget(self.btn_export)

        # Toggle Editor Button
        self.btn_toggle_editor = QPushButton("🔽")
        self.btn_toggle_editor.setFixedWidth(30)
        self.btn_toggle_editor.setFixedHeight(30)
        from gui.theme import CLR_WARNING, FONT_BASE
        self.btn_toggle_editor.setStyleSheet(f"color: {CLR_WARNING}; font-weight: bold; border: none; background: transparent; font-size: {FONT_BASE}px;")
        self.btn_toggle_editor.setToolTip(self.tr("Show/Hide Editor"))
        self.btn_toggle_editor.setVisible(False) # Hide by default
        self.btn_toggle_editor.clicked.connect(self._toggle_editor_visibility)
        top_bar.addWidget(self.btn_toggle_editor)

        filter_layout.addLayout(top_bar)
        
        # Add Drag & Drop support
        self.setAcceptDrops(True)

        # Conditions Area
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame) # Remove outer frame
        self.scroll.setWidgetResizable(True)
        self.scroll.setVisible(False) # [PHASE 131] Hide until Load/New
        self.root_group = FilterGroupWidget(extra_keys=self.extra_keys,
                                            available_tags=self.available_tags,
                                            available_system_tags=self.available_system_tags,
                                            available_workflow_steps=self.available_workflow_steps,
                                            is_root=True)
        self.root_group.changed.connect(self._set_dirty)
        self.scroll.setWidget(self.root_group)
        filter_layout.addWidget(self.scroll)

        # Bottom Bar
        bottom_bar = QHBoxLayout()
        self.btn_clear = QPushButton("")
        self.btn_clear.setEnabled(False) # Grey out if empty
        self.btn_clear.clicked.connect(lambda: self.clear_all(reset_combo=True))
        bottom_bar.addWidget(self.btn_clear)
        bottom_bar.addStretch()

        self.lbl_changes = QLabel("")
        from gui.theme import CLR_TEXT_SECONDARY
        self.lbl_changes.setStyleSheet(f"color: {CLR_TEXT_SECONDARY}; margin-right: 5px;")
        bottom_bar.addWidget(self.lbl_changes)

        self.btn_revert = QPushButton()
        self.btn_revert.setFixedHeight(30)
        self.btn_revert.setEnabled(False)
        self.btn_revert.clicked.connect(self.revert_changes)
        bottom_bar.addWidget(self.btn_revert)

        self.btn_apply = QPushButton("")
        self.btn_apply.setFixedHeight(30)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._emit_change)
        bottom_bar.addWidget(self.btn_apply)

        self.btn_save = QPushButton()
        self.btn_save.setFixedHeight(30)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self.save_current_filter)
        bottom_bar.addWidget(self.btn_save)
        filter_layout.addLayout(bottom_bar)

        self.stack.addWidget(self.filter_tab)

        # --- TAB 3: Auto-Tagging Rules ---
        self._init_rules_tab()
        self.stack.addWidget(self.rules_tab)

    def _init_rules_tab(self):
        self.rules_tab = QWidget()
        self.rules_tab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        rules_layout = QVBoxLayout(self.rules_tab)
        rules_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        rules_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        rules_layout.setContentsMargins(0, 5, 0, 5)
        rules_layout.setSpacing(8)

        # Top Bar (Management) - Harmonized with Filter View
        top_bar = QHBoxLayout()
        self.lbl_rule_select = QLabel("")
        self.lbl_rule_select.setFixedWidth(110)
        top_bar.addWidget(self.lbl_rule_select)
        self.combo_rules = QComboBox()
        self.combo_rules.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_rules.setMinimumWidth(150)
        self.combo_rules.currentIndexChanged.connect(self._on_combo_rule_selected)
        top_bar.addWidget(self.combo_rules, 1)

        self.btn_load_rule = QPushButton("")
        self.btn_load_rule.setFixedHeight(30)
        self.btn_load_rule.setEnabled(False) 
        self.btn_load_rule.clicked.connect(self._on_load_rule_clicked)
        top_bar.addWidget(self.btn_load_rule)

        self.btn_new_rule = QPushButton("")
        self.btn_new_rule.setFixedHeight(30)
        self.btn_new_rule.clicked.connect(self._on_new_rule_clicked)
        top_bar.addWidget(self.btn_new_rule)

        self.btn_manage_rules = QPushButton("")
        self.btn_manage_rules.setFixedHeight(30)
        self.btn_manage_rules.clicked.connect(self.manage_rules)
        top_bar.addWidget(self.btn_manage_rules)

        self.chk_rule_enabled = QCheckBox("")
        self.chk_rule_enabled.setChecked(False)
        self.chk_rule_enabled.setEnabled(False)
        self.chk_rule_enabled.toggled.connect(self._set_rule_dirty)
        top_bar.addWidget(self.chk_rule_enabled)

        # Toggle Rules Button
        self.btn_toggle_rules = QPushButton("🔽")
        self.btn_toggle_rules.setFixedWidth(30)
        self.btn_toggle_rules.setFixedHeight(30)
        from gui.theme import CLR_WARNING, FONT_BASE
        self.btn_toggle_rules.setStyleSheet(f"color: {CLR_WARNING}; font-weight: bold; border: none; background: transparent; font-size: {FONT_BASE}px;")
        self.btn_toggle_rules.setToolTip(self.tr("Show/Hide Editor"))
        self.btn_toggle_rules.setVisible(False) 
        self.btn_toggle_rules.clicked.connect(self._toggle_rules_visibility)
        top_bar.addWidget(self.btn_toggle_rules)

        rules_layout.addLayout(top_bar)

        # Combined Editor Container (Tags + Workflow + Conditions)
        self.rules_editor_widget = QWidget()
        self.rules_editor_widget.setVisible(False)
        editor_layout = QVBoxLayout(self.rules_editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)

        # Metadata / Tagging Row
        meta_row = QHBoxLayout()
        self.lbl_tags_add = QLabel("")
        self.lbl_tags_add.setFixedWidth(110) # Align with top bar
        meta_row.addWidget(self.lbl_tags_add)

        self.edit_tags_add = TagInputWidget()
        self.edit_tags_add.tagsChanged.connect(self._set_rule_dirty)
        meta_row.addWidget(self.edit_tags_add, 1)

        self.lbl_tags_rem = QLabel("")
        self.lbl_tags_rem.setFixedWidth(110)
        meta_row.addWidget(self.lbl_tags_rem)
        self.edit_tags_rem = TagInputWidget()
        self.edit_tags_rem.tagsChanged.connect(self._set_rule_dirty)
        meta_row.addWidget(self.edit_tags_rem, 1)
        editor_layout.addLayout(meta_row)

        wf_row = QHBoxLayout()
        self.lbl_assign_wf = QLabel("")
        self.lbl_assign_wf.setFixedWidth(110)
        wf_row.addWidget(self.lbl_assign_wf)
        self.combo_assign_wf = QComboBox()
        self.combo_assign_wf.currentIndexChanged.connect(self._set_rule_dirty)
        wf_row.addWidget(self.combo_assign_wf, 1)
        wf_row.addStretch()
        editor_layout.addLayout(wf_row)
        
        self._populate_wf_combo()

        # Conditions Area (Mirrored FilterGroupWidget)
        self.rules_root_group = FilterGroupWidget(extra_keys=self.extra_keys,
                                                  available_tags=self.available_tags,
                                                  available_workflow_steps=self.available_workflow_steps,
                                                  is_root=True)
        self.rules_root_group.changed.connect(self._set_rule_dirty)
        editor_layout.addWidget(self.rules_root_group, 1)

        # Rules Scroll Area (Wraps the combined editor)
        self.rules_scroll = QScrollArea()
        self.rules_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rules_scroll.setWidgetResizable(True)
        self.rules_scroll.setWidget(self.rules_editor_widget)
        self.rules_scroll.setVisible(False)
        rules_layout.addWidget(self.rules_scroll)

        # Bottom Bar (Processing)
        bottom_bar = QHBoxLayout()
        self.btn_clear_rule = QPushButton("")
        self.btn_clear_rule.setEnabled(False)
        self.btn_clear_rule.clicked.connect(self.clear_rule)
        bottom_bar.addWidget(self.btn_clear_rule)

        self.btn_create_view = QPushButton("")
        self.btn_create_view.setFixedHeight(30)
        self.btn_create_view.setEnabled(False)
        self.btn_create_view.clicked.connect(self.create_view_filter_from_rule)
        bottom_bar.addWidget(self.btn_create_view)

        bottom_bar.addStretch()

        self.lbl_changes_rule = QLabel("")
        from gui.theme import CLR_TEXT_SECONDARY
        self.lbl_changes_rule.setStyleSheet(f"color: {CLR_TEXT_SECONDARY}; margin-right: 5px;")
        bottom_bar.addWidget(self.lbl_changes_rule)

        self.btn_revert_rule = QPushButton("")
        self.btn_revert_rule.setFixedHeight(30)
        self.btn_revert_rule.setEnabled(False)
        self.btn_revert_rule.clicked.connect(self.revert_rule_changes)
        bottom_bar.addWidget(self.btn_revert_rule)

        self.btn_apply_view = QPushButton("")
        self.btn_apply_view.setFixedHeight(30)
        self.btn_apply_view.setEnabled(False)
        self.btn_apply_view.clicked.connect(self._on_apply_rule_to_view)
        bottom_bar.addWidget(self.btn_apply_view)

        self.btn_save_rule = QPushButton()
        self.btn_save_rule.setFixedHeight(30)
        self.btn_save_rule.setEnabled(False)
        self.btn_save_rule.clicked.connect(self._on_save_rule_clicked)
        bottom_bar.addWidget(self.btn_save_rule)

        self.btn_apply_all = QPushButton("")
        from gui.theme import CLR_SUCCESS_LIGHT
        self.btn_apply_all.setStyleSheet(f"font-weight: bold; background-color: {CLR_SUCCESS_LIGHT};")
        self.btn_apply_all.setEnabled(False)
        self.btn_apply_all.clicked.connect(self._on_batch_run_clicked)
        bottom_bar.addWidget(self.btn_apply_all)

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

        if self.filter_tree:
            all_rules = []
            
            # Rules are currently filters with actions
            # We collect all FILTER type nodes for categorization
            def collect_rules(node, path_prefix=""):
                for child in node.children:
                    if child.node_type == NodeType.FILTER:
                        localized_name = self.tr(child.name)
                        display = f"{path_prefix}{localized_name}" if path_prefix else localized_name
                        all_rules.append((display, child))
                    elif child.node_type == NodeType.FOLDER:
                        new_prefix = f"{path_prefix}{child.name} / " if path_prefix else f"{child.name} / "
                        collect_rules(child, new_prefix)

            collect_rules(self.filter_tree.root)

            # 1. Top 3 frequently used (Star prefix)
            top_3 = sorted([r for r in all_rules if r[1].usage_count > 0], 
                           key=lambda x: x[1].usage_count, reverse=True)[:3]
            
            if top_3:
                for display, node in top_3:
                    self.combo_rules.addItem(f"⭐ {display}", node)
                self.combo_rules.insertSeparator(self.combo_rules.count())

            # 2. All Rules (Alphabetical)
            all_rules.sort(key=lambda x: x[0].lower())
            for display, node in all_rules:
                self.combo_rules.addItem(display, node)

        self.combo_rules.blockSignals(False)

    def _on_load_rule_clicked(self):
        """Manually triggered loading of the selected rule."""
        data = self.combo_rules.currentData()
        if not data:
            self.clear_rule()
            return

        if isinstance(data, FilterNode) and data.node_type == NodeType.FILTER:
            data.usage_count += 1
            if self.save_callback:
                self.save_callback()
            
            # Refresh combo to update "Top 3"
            current_id = data.id
            self._load_rules_to_combo()
            
            # Relocate same item
            for i in range(self.combo_rules.count()):
                item_data = self.combo_rules.itemData(i)
                if isinstance(item_data, FilterNode) and item_data.id == current_id:
                    self.combo_rules.blockSignals(True)
                    self.combo_rules.setCurrentIndex(i)
                    self.combo_rules.blockSignals(False)
                    break

        self.btn_toggle_rules.setVisible(True)
        self.chk_rule_enabled.setEnabled(True)
        self.chk_rule_enabled.setChecked(True)
        self._set_rules_editor_visible(True)
        self._on_saved_rule_selected(0)

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
        if getattr(self, '_loading', False):
            return

        query = self.rules_root_group.get_query()
        has_query = bool(query and query.get("conditions"))
        has_tags = bool(self.edit_tags_add.text().strip() or self.edit_tags_rem.text().strip())
        rule = self.combo_rules.currentData()

        # If we have a rule loaded, any state might be a modification.
        # If we DON'T have a rule, only meaningful content is a modification.
        is_modified = has_query or has_tags or rule is not None

        self.btn_revert_rule.setEnabled(is_modified)
        self.btn_save_rule.setEnabled(is_modified)
        self.btn_apply_view.setEnabled(has_query)
        self.btn_apply_all.setEnabled(has_query)
        self.btn_clear_rule.setEnabled(has_query or has_tags)
        self.btn_create_view.setEnabled(has_tags)

        if is_modified:
            from gui.theme import CLR_WARNING_LIGHT
            self.btn_save_rule.setStyleSheet(f"background-color: {CLR_WARNING_LIGHT}; font-weight: bold;")
        else:
            self.btn_save_rule.setStyleSheet("")

        # Add * to combo if needed
        rule = self.combo_rules.currentData()
        if rule:
            idx = self.combo_rules.currentIndex()
            if idx >= 0:
                current_text = self.combo_rules.itemText(idx)
                if not current_text.endswith(" *"):
                     self.combo_rules.setItemText(idx, current_text + " *")

    def _reset_rule_dirty(self):
        """Disable buttons after save/load. Harmonized with Filter View."""
        self.btn_revert_rule.setEnabled(False)
        self.btn_save_rule.setEnabled(False)
        self.btn_save_rule.setStyleSheet("")
        self.btn_apply_view.setEnabled(False)
        self.btn_apply_all.setEnabled(False)

        query = self.rules_root_group.get_query()
        has_query = bool(query and query.get("conditions"))
        has_tags = bool(self.edit_tags_add.text().strip() or self.edit_tags_rem.text().strip())
        self.btn_clear_rule.setEnabled(has_query or has_tags)

        self.btn_create_view.setEnabled(has_tags)

        self.btn_save_rule.setStyleSheet("")

        # Remove * from combo
        idx = self.combo_rules.currentIndex()
        if idx >= 0:
            current_text = self.combo_rules.itemText(idx)
            if current_text.endswith(" *"):
                 self.combo_rules.setItemText(idx, current_text[:-2])

    def revert_rule_changes(self):
        self._on_saved_rule_selected(self.combo_rules.currentIndex())

    def clear_rule(self):
        self._loading = True
        try:
            self.rules_root_group.clear()
            self.edit_tags_add.clear()
            self.edit_tags_rem.clear()
            self.chk_rule_enabled.setChecked(True)
            self.chk_rule_auto.setChecked(False)
            self.combo_assign_wf.setCurrentIndex(0)
            self._reset_rule_dirty()
        finally:
            self._loading = False
        self.rules_scroll.setVisible(True) # Show editor
        self.btn_toggle_rules.setVisible(True) # Show toggle
        self.btn_toggle_rules.setText("🔼")
        self._update_stack_visibility()

    def _on_new_rule_clicked(self):
        self.combo_rules.blockSignals(True)
        self.combo_rules.setCurrentIndex(0)
        self.combo_rules.blockSignals(False)
        self.clear_rule()
        self.rules_editor_widget.setVisible(True)
        self.rules_scroll.setVisible(True)
        self.btn_toggle_rules.setVisible(True)
        self.btn_toggle_rules.setText("🔼")
        self.chk_rule_enabled.setEnabled(True)
        self.chk_rule_enabled.setChecked(True)
        self._reset_rule_dirty()
        self._update_stack_visibility()

    def _set_filter_editor_visible(self, visible: bool):
        self.scroll.setVisible(visible)
        if visible:
            self.scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.scroll.setMinimumHeight(320)
            self.scroll.setMaximumHeight(16777215)
        else:
            self.scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self.scroll.setMinimumHeight(0)
            self.scroll.setMaximumHeight(0)
        self.btn_toggle_editor.setText("🔼" if visible else "🔽")
        self._update_stack_visibility()

    def _toggle_editor_visibility(self):
        self._set_filter_editor_visible(not self.scroll.isVisible())

    def _set_rules_editor_visible(self, visible: bool):
        self.rules_scroll.setVisible(visible)
        self.rules_editor_widget.setVisible(visible)
        if visible:
            self.rules_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.rules_scroll.setMinimumHeight(320)
            self.rules_scroll.setMaximumHeight(16777215)
            self.rules_editor_widget.setMinimumHeight(320)
            self.rules_editor_widget.setMaximumHeight(16777215)
            self.btn_toggle_rules.setText("🔼")
        else:
            self.rules_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self.rules_scroll.setMinimumHeight(0)
            self.rules_scroll.setMaximumHeight(0)
            self.rules_editor_widget.setMinimumHeight(0)
            self.rules_editor_widget.setMaximumHeight(0)
            self.btn_toggle_rules.setText("🔽")
        self.size_changed.emit()
        self._update_stack_visibility()

    def _toggle_rules_visibility(self):
        self._set_rules_editor_visible(not self.rules_scroll.isVisible())

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
            if index == 0: # Search
                self.search_triggered.emit(self.txt_smart_search.text())
            elif index == 1: # Filter
                self._emit_change()
            
            _ = self.tr("Filter")
        
        self._update_stack_visibility()
    def _update_stack_visibility(self):
        has_selection = any(b.isChecked() for b in self.sub_mode_group.buttons())
        self.stack.setVisible(has_selection)
        self.sep_line.setVisible(has_selection)
        if hasattr(self, 'nav_spacer'):
            self.nav_spacer.setVisible(has_selection)
        
        # KEEP TOP MARGIN STABLE at 10 to avoid jumping!
        # Bottom margin is 0 to align flush with the list view
        self.layout().setContentsMargins(10, 10, 10, 0)
        
        if not has_selection:
            # Sub-nav + Spacer + Margins only.
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        elif self.stack.currentIndex() == 0:
            # SEARCH MODE: Must contain Sub-nav + Header Row + Search Status Row
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        elif self.stack.currentIndex() == 1:
            # FILTER MODE: Needs space for conditions IF VISIBLE
            if hasattr(self, 'scroll') and self.scroll.isVisible():
                self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            else:
                # Collapsed
                self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        else:
            # RULES MODE
            if hasattr(self, 'rules_scroll') and self.rules_scroll.isVisible():
                self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            else:
                # Collapsed
                self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        
        self.updateGeometry()
        self.stack.updateGeometry()
        if self.layout():
            self.layout().invalidate()
            self.layout().activate()
        if self.stack.layout():
            self.stack.layout().invalidate()
            self.stack.layout().activate()
        
        # Isolation: Ensure hidden pages don't influence stack size hint
        self.stack.setMinimumHeight(0)
        self.stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        
        for i in range(self.stack.count()):
            page = self.stack.widget(i)
            if i == self.stack.currentIndex():
                page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
                page.setMinimumHeight(0)
                page.updateGeometry()
            else:
                page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
                page.updateGeometry()

        # Notify Splitter
        self.size_changed.emit()

    def _on_smart_search(self):
        text = self.txt_smart_search.text().strip()
        logger.debug(f"[Search] Raw Input: '{text}'")

        # 1. Validation (Allow empty to clear)
        if text and len(text) < 3:
            self.lbl_search_status.setText(self.tr("Search string too short (min 3 chars)"))
            from gui.theme import CLR_DANGER
            self.lbl_search_status.setStyleSheet(f"color: {CLR_DANGER};")
            return
        
        if not text:
            self.lbl_search_status.setText("")
            self.filter_changed.emit({"_meta_fulltext": ""})
            self.search_triggered.emit("")
            return

        self.lbl_search_status.setText(self.tr("Searching..."))
        from gui.theme import CLR_TEXT
        self.lbl_search_status.setStyleSheet(f"color: {CLR_TEXT};")
        # Process UI updates immediately
        QCoreApplication.processEvents()

        criteria = {"fulltext": text}
        logger.debug(f"[Search] Literal Search Criteria: {criteria}")

        if criteria.get("fulltext") and self.db_manager:
             logger.debug(f"[Search] Performing Deep Search for text: '{criteria['fulltext']}'")
             # Find UUIDs that match the text in RAW or CACHE
             deep_uuids = self.db_manager.get_virtual_uuids_with_text_content(criteria["fulltext"])
             criteria["deep_uuids"] = deep_uuids
             logger.debug(f"[Search] Deep Search found {len(deep_uuids)} UUIDs")
             if len(deep_uuids) > 0:
                 logger.debug(f"[Search] Sample UUIDs: {deep_uuids[:3]}")

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

        logger.debug(f"[Search] Final Query: {final_query}")

        # 4. Count & Feedback
        count = 0
        if self.db_manager:
            try:
                count = self.db_manager.count_documents_advanced(final_query)
            except Exception as e:
                logger.warning(f"[Search] Count failed: {e}")

        logger.debug(f"[Search] Count Result: {count}")
        
        if count == 0:
            status_msg = self.tr("No documents found")
        else:
            # Base message: "X documents found"
            status_msg = self.tr("%1 documents found").replace("%1", str(count))
            
            if self.db_manager and text:
                total_hits = self.db_manager.count_total_text_occurrences_advanced(final_query, text)
                if total_hits >= count:
                    # Clearer format: "X documents found (Y occurrences)"
                    status_msg = self.tr("%1 documents found (%2 occurrences)") \
                                     .replace("%1", str(count)) \
                                     .replace("%2", str(total_hits))
                # If total_hits < count, we stick to the base message to avoid confusion

        self.lbl_search_status.setText(status_msg)
        from gui.theme import CLR_SUCCESS, CLR_DANGER
        self.lbl_search_status.setStyleSheet(f"color: {CLR_SUCCESS};" if count > 0 else f"color: {CLR_DANGER};")

        # Inject debug meta info for MainWindow
        final_query["_meta_fulltext"] = text
        
        # Hide hits initially on new search
        self.update_hit_status(-1, 0)

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

        logger.debug("AdvancedFilter: Refreshing dynamic metadata (Stamps/Tags)...")
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
        self._loading = True
        try:
            if reset_combo and isinstance(reset_combo, bool):
                self.combo_filters.setCurrentIndex(0)
                self.scroll.setVisible(False)
                self.btn_toggle_editor.setVisible(False) # Hide toggle on clear
                self.chk_active.setChecked(False)
                self.chk_active.setEnabled(False)
                self.loaded_filter_node = None
                self._update_stack_visibility()

            self.root_group.clear()
            self.root_group.set_read_only(False) # [NEW] Ensure clean state
            self._reset_dirty_indicator()
            # Auto-apply to update view immediately (UX feedback)
            self._emit_change()
        finally:
            self._loading = False

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

        # [NEW] Set Read-Only state for protected nodes
        is_protected = False
        if node and hasattr(node, "node_type"):
            if node.node_type in [NodeType.TRASH, NodeType.ARCHIVE]:
                 is_protected = True
        self.root_group.set_read_only(is_protected)

        # Auto-Apply on Load? Usually yes for saved filters.
        self._emit_change()


    def _set_dirty(self):
        if getattr(self, '_loading', False):
            return

        query = self.get_query_object()
        has_query = bool(query and query.get("conditions"))
        
        # Protected types cannot be saved or reverted
        is_protected = False
        if self.loaded_filter_node and hasattr(self.loaded_filter_node, "node_type"):
            if self.loaded_filter_node.node_type in [NodeType.TRASH, NodeType.ARCHIVE]:
                 is_protected = True

        is_modified = (has_query or self.loaded_filter_node is not None) and not is_protected

        if self.btn_apply:
            # [MOD] Apply is also disabled for protected nodes to enforce true read-only
            self.btn_apply.setEnabled((has_query or self.loaded_filter_node is not None) and not is_protected)

        if self.btn_clear:
            self.btn_clear.setEnabled(has_query)

        if self.btn_revert:
             self.btn_revert.setEnabled(is_modified)
        
        if self.btn_save:
             self.btn_save.setEnabled(is_modified)
             if is_modified:
                 from gui.theme import CLR_WARNING_LIGHT
                 self.btn_save.setStyleSheet(f"background-color: {CLR_WARNING_LIGHT}; font-weight: bold;")
             else:
                 self.btn_save.setStyleSheet("")

        # Ignore Protected Nodes for Dirty Indicator (*)
        if is_protected:
            return

        if self.loaded_filter_node:
            idx = self.combo_filters.findData(self.loaded_filter_node)
            if idx >= 0:
                current_text = self.combo_filters.itemText(idx)
                if not current_text.endswith(" *"):
                     self.combo_filters.setItemText(idx, current_text + " *")

    def _reset_dirty_indicator(self):
        """Removes the * from the currently loaded filter in the combo."""
        self.btn_revert.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("")
        if self.btn_apply:
            self.btn_apply.setEnabled(False)

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
        self.filter_active_changed.emit(checked)
        self._set_dirty()
        self._emit_change()

    def set_active(self, active: bool):
        """Programmatically set the 'Filter active' state without triggering dirty flag."""
        if self.chk_active:
            self.chk_active.blockSignals(True)
            self.chk_active.setChecked(active)
            self.chk_active.blockSignals(False)

    def _on_combo_filter_selected(self, index):
        """Triggered on every selection change. Controls the 'Load' button state."""
        data = self.combo_filters.currentData()
        
        # Enable Load button if we have a valid node selected
        # BROWSE_ALL is handled immediately, so it doesn't need the Load button enabled
        is_valid_selection = data is not None and data != "BROWSE_ALL"
        self.btn_load.setEnabled(is_valid_selection)

        if data == "BROWSE_ALL":
             self._on_saved_filter_selected(index)

    def _on_combo_rule_selected(self, index):
        """Triggered on every selection change in the Rules combo."""
        data = self.combo_rules.currentData()
        self.btn_load_rule.setEnabled(data is not None)

    def _emit_change(self):
        query = self.get_query_object()

        if self.btn_apply:
            self.btn_apply.setEnabled(False) # Clean state

        if not self.chk_active.isChecked():
            # If disabled, emit empty query (all docs)
            # But we keep the query object internally in UI
            self.filter_changed.emit({})
            return

        logger.debug(f"AdvancedFilter Emitting: {json.dumps(query, default=str)}")
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
            all_filters = []
            system_nodes = []
            
            def collect_nodes(node, path_prefix=""):
                for child in node.children:
                    if child.node_type == NodeType.FILTER:
                        localized_name = self.tr(child.name)
                        display = f"{path_prefix}{localized_name}" if path_prefix else localized_name
                        all_filters.append((display, child))
                    elif child.node_type in [NodeType.TRASH, NodeType.ARCHIVE]:
                        localized_name = self.tr(child.name)
                        display = f"[ {localized_name} ]"
                        system_nodes.append((display, child))
                    elif child.node_type == NodeType.FOLDER:
                        new_prefix = f"{path_prefix}{child.name} / " if path_prefix else f"{child.name} / "
                        collect_nodes(child, new_prefix)

            collect_nodes(self.filter_tree.root)

            # 1. Top 3 frequently used (Star prefix)
            top_3 = sorted([f for f in all_filters if f[1].usage_count > 0], 
                           key=lambda x: x[1].usage_count, reverse=True)[:3]
            
            if top_3:
                for display, node in top_3:
                    self.combo_filters.addItem(f"⭐ {display}", node)
                    if node.description:
                        self.combo_filters.setItemData(self.combo_filters.count()-1, node.description, Qt.ItemDataRole.ToolTipRole)
                self.combo_filters.insertSeparator(self.combo_filters.count())

            # 2. System Filters (Alphabetical)
            system_nodes.sort(key=lambda x: x[0].lower())
            if system_nodes:
                for display, node in system_nodes:
                    self.combo_filters.addItem(display, node)
                self.combo_filters.insertSeparator(self.combo_filters.count())

            # 3. User Filters (Alphabetical)
            all_filters.sort(key=lambda x: x[0].lower())
            for display, node in all_filters:
                self.combo_filters.addItem(display, node)
                if node.description:
                    self.combo_filters.setItemData(self.combo_filters.count()-1, node.description, Qt.ItemDataRole.ToolTipRole)

            # Extra: Command
            self.combo_filters.insertSeparator(self.combo_filters.count())
            self.combo_filters.addItem(self.tr("Browse All..."), "BROWSE_ALL")

        self.combo_filters.blockSignals(False)


    def _on_load_filter_clicked(self):
        """Manually triggered loading of the selected filter."""
        data = self.combo_filters.currentData()
        if not data:
            self.loaded_filter_node = None
            self.clear_all(reset_combo=True) # Reset if nothing to load
            return

        if isinstance(data, FilterNode) and data.node_type == NodeType.FILTER:
            data.usage_count += 1
            if self.save_callback:
                self.save_callback()
            
            # Refresh combo to update "Top 3" ordering
            current_id = data.id
            self.load_known_filters()
            
            # Find and select the same node again (it might have moved to Top 3)
            for i in range(self.combo_filters.count()):
                item_data = self.combo_filters.itemData(i)
                if isinstance(item_data, FilterNode) and item_data.id == current_id:
                    self.combo_filters.blockSignals(True)
                    self.combo_filters.setCurrentIndex(i)
                    self.combo_filters.blockSignals(False)
                    break

        self.btn_toggle_editor.setVisible(True) # Show toggle
        self.chk_active.setEnabled(True)
        self.chk_active.setChecked(True)
        self._set_filter_editor_visible(True)
        self._on_saved_filter_selected(0)

    def _on_new_filter_clicked(self):
        """Reset editor for a new filter."""
        self.combo_filters.blockSignals(True)
        self.combo_filters.setCurrentIndex(0)
        self.combo_filters.blockSignals(False)
        self.clear_all(reset_combo=False)
        self.root_group.set_read_only(False) # [NEW]
        self.btn_toggle_editor.setVisible(True) # Show toggle
        self.chk_active.setEnabled(True)
        self.chk_active.setChecked(True)
        self._set_filter_editor_visible(True)

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
             self.trash_mode_changed.emit(True)
             self.archive_mode_changed.emit(False) # [NEW]
             self._emit_change()
             return

        if hasattr(data, "node_type") and data.node_type == NodeType.ARCHIVE:
             self.loaded_filter_node = data
             # Standardize Archive as a normal filter Query
             # This ensures verify logic in DocumentList.apply_advanced_filter works.
             archive_query = {
                 "operator": "AND",
                 "conditions": [
                     {"field": "archived", "op": "equals", "value": True}
                 ]
             }
             self.load_from_object(archive_query)
             self.trash_mode_changed.emit(False)
             self.archive_mode_changed.emit(True) # [NEW]
             self._emit_change()
             return

        # It's a FilterNode or saved dict (legacy)
        # We stored FilterNode object in addItem

        # Ensure we exit special modes
        self.trash_mode_changed.emit(False)
        self.archive_mode_changed.emit(False) # [NEW]

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
            self.archive_mode_changed.emit(False) # [NEW]
            self._sync_combo_selection(node)
            return

        if node.node_type == NodeType.ARCHIVE:
             # Special Archive Handling
             self.loaded_filter_node = node
             self.trash_mode_changed.emit(False)
             self.archive_mode_changed.emit(True) # [NEW]
             self._sync_combo_selection(node)
             return

        # Normal Filter
        self.trash_mode_changed.emit(False) # Exit trash mode
        self.archive_mode_changed.emit(False) # [NEW]

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
            
            # [NEW] Set Read-Only state for protected nodes
            is_protected = False
            if self.loaded_filter_node and hasattr(self.loaded_filter_node, "node_type"):
                if self.loaded_filter_node.node_type in [NodeType.TRASH, NodeType.ARCHIVE]:
                     is_protected = True
            self.root_group.set_read_only(is_protected)
            
            self._set_dirty() # [NEW] Force UI update (disables Apply if protected)
            self.btn_apply.setEnabled(not is_protected and False) # Force clean state but respect protection
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

        # Request info (isolated for easier testing)
        default_name = self.loaded_filter_node.name if self.loaded_filter_node else ""
        default_desc = self.loaded_filter_node.description if self.loaded_filter_node else ""
        name, description, ok = self._request_save_info(default_name, default_desc)
        
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
                existing_node.name = name
                existing_node.description = description
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
                target_node.description = description

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

    def _request_save_info(self, default_name="", default_desc=""):
        """Displays the save dialog and returns (name, description, ok)."""
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Save Filter"))
        d_layout = QVBoxLayout(dialog)
        
        d_layout.addWidget(QLabel(self.tr("Filter Name:")))
        name_edit = QLineEdit()
        name_edit.setText(default_name)
        d_layout.addWidget(name_edit)
        
        d_layout.addWidget(QLabel(self.tr("Description:")))
        desc_edit = QLineEdit()
        desc_edit.setText(default_desc)
        d_layout.addWidget(desc_edit)
        
        btns = QHBoxLayout()
        btn_ok = QPushButton(self.tr("Save"))
        btn_ok.clicked.connect(dialog.accept)
        btn_ok.setDefault(True)
        btn_cancel = QPushButton(self.tr("Cancel"))
        btn_cancel.clicked.connect(dialog.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        d_layout.addLayout(btns)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return name_edit.text().strip(), desc_edit.text().strip(), True
        return None, None, False

    def _show_combo_context(self, pos):
        # MVP: Right click on the collapsed box deletes the currently selected item.
        data = self.combo_filters.currentData()
        idx = self.combo_filters.currentIndex()
        if idx <= 0 or data == "BROWSE_ALL":
             return

        # It's a filter node
        node_name = self.combo_filters.currentText()

        menu = QMenu(self)
        del_label = self.tr("Delete '%1'").replace("%1", node_name)
        del_action = QAction(del_label, self)
        del_action.triggered.connect(lambda: self._delete_node(data))
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

    def update_hit_status(self, current: int, total: int):
        """Updates the hit navigation UI in the search tab."""
        if total > 0:
            self.lbl_hits.setText(f"{current + 1} / {total}")
            self.lbl_hits.setVisible(True)
            self.btn_hit_prev.setVisible(True)
            self.btn_hit_next.setVisible(True)
        else:
            self.lbl_hits.setVisible(False)
            self.btn_hit_prev.setVisible(False)
            self.btn_hit_next.setVisible(False)

    def clear_search(self):
        """Clears all search-related UI elements."""
        self.txt_smart_search.clear()
        self.lbl_search_status.setText("")
        self.update_hit_status(0, 0)

    def retranslate_ui(self):
        """Updates all UI strings for on-the-fly localization."""
        # Modes - Use literals so pylupdate6 finds them
        self.btn_mode_search.setText("🔍 " + self.tr("Search"))
        self.btn_mode_filter.setText("🎯 " + self.tr("Filter"))
        self.btn_mode_rules.setText("🤖 " + self.tr("Rules"))
        
        # Search Tab
        self.lbl_search_header.setText(self.tr("Query:"))
        # This will be picked up by DocumentListWidget.update_breadcrumb indirectly
        self.txt_smart_search.setPlaceholderText(self.tr("e.g. Amazon 2024 Invoice..."))
        self.btn_apply_search.setText("🔍")
        self.chk_search_scope.setText(self.tr("Search in current view only"))
        self.chk_search_scope.setToolTip(self.tr("If checked, combines the search with the active filters from 'Filter View'."))
        
        # Filter Tab
        self.lbl_filter_select.setText(self.tr("Select:"))
        self.btn_load.setText(self.tr("Load"))
        self.btn_new.setText(self.tr("New"))
        self.btn_manage.setText("⚙️ " + self.tr("Manage"))
        self.btn_manage.setToolTip(self.tr("Manage Filters"))
        self.chk_active.setText(self.tr("Filter Active"))
        self.btn_export.setText("📤 " + self.tr("Export"))
        self.btn_export.setToolTip(self.tr("Export filter"))

        self.lbl_changes.setText(self.tr("Changes:"))
        self.btn_revert.setText(self.tr("Discard"))
        self.btn_revert.setToolTip(self.tr("Revert Changes"))
        self.btn_save.setText(self.tr("Save"))
        self.btn_clear.setText(self.tr("Clear All"))
        self.btn_apply.setText(self.tr("Apply"))
        self.btn_apply.setToolTip(self.tr("Changes are applied automatically when 'Filter active' is checked."))

        # Rules Tab
        self.lbl_rule_select.setText(self.tr("Select:"))
        self.btn_load_rule.setText(self.tr("Load"))
        self.btn_new_rule.setText(self.tr("New"))
        self.btn_manage_rules.setText(self.tr("Manage"))
        self.chk_rule_enabled.setText(self.tr("Active"))

        self.lbl_tags_add.setText(self.tr("Add Tags:"))
        self.lbl_tags_rem.setText(self.tr("Remove Tags:"))
        self.edit_tags_add.setToolTip(self.tr("Enter tags to add. Press comma or Enter to confirm (e.g. INVOICE, TELEKOM)"))
        self.edit_tags_rem.setToolTip(self.tr("Enter tags to remove. Press comma or Enter to confirm (e.g. DRAFT, REVIEW)"))
        self.lbl_assign_wf.setText(self.tr("Assign Workflow:"))

        self.lbl_changes_rule.setText(self.tr("Changes:"))
        self.btn_revert_rule.setText(self.tr("Discard"))
        self.btn_save_rule.setText(self.tr("Save..."))
        self.btn_clear_rule.setText(self.tr("Clear All"))
        self.btn_create_view.setText(self.tr("Create View-filter"))
        self.btn_create_view.setToolTip(self.tr("Create a search-view that filters for the tags this rule adds"))
        self.btn_apply_view.setText(self.tr("Apply to View"))
        self.btn_apply_all.setText(self.tr("Apply to all"))
        self.chk_rule_auto.setText(self.tr("Run on Import"))
        self.chk_rule_auto.setToolTip(self.tr("Automatically apply this rule to new documents during import/analysis"))

        # Recursively retranslate dynamic groups
        if hasattr(self, "root_group"):
            self.root_group.retranslate_ui()
        if hasattr(self, "rules_root_group"):
            self.rules_root_group.retranslate_ui()

        # Re-populate combos that have static "Select" headers
        self.load_known_filters()
        self._load_rules_to_combo()
        self._populate_wf_combo()
