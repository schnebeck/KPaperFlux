"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/main_window.py
Version:        2.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    Main application window orchestrating the UI and backend logic.
------------------------------------------------------------------------------
"""

from typing import Optional, List, Any, Dict
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog,
    QMessageBox, QSplitter, QMenuBar, QMenu, QCheckBox, QDialog, QDialogButtonBox, QStatusBar,
    QStackedWidget, QToolBar, QAbstractItemView, QProgressDialog, QToolButton, QSizePolicy,
    QButtonGroup, QFrame
)
from PyQt6.QtGui import QAction, QIcon, QDragEnterEvent, QDropEvent, QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QSettings, QSize, QCoreApplication, QTimer, PYQT_VERSION_STR
import PyQt6
import platform
import os
import sys
import tempfile
import shutil
import json
from core.logger import get_logger

logger = get_logger("gui.main_window")
import fitz
from pathlib import Path

# Core Imports
from gui.utils import show_selectable_message_box
from core.importer import PreFlightImporter
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from core.stamper import DocumentStamper
from core.filter_tree import FilterTree, NodeType
from core.config import AppConfig
from core.integrity import IntegrityManager
from core.utils.forensics import check_pdf_immutable, PDFClass, get_pdf_class
from core.exchange import ExchangeService, ExchangePayload

# GUI Imports
from gui.workers import ImportWorker, MainLoopWorker, SimilarityWorker, ReprocessWorker
from gui.document_list import DocumentListWidget
from gui.metadata_editor import MetadataEditorWidget
from gui.pdf_viewer import PdfViewerWidget
from gui.cockpit import CockpitWidget
from gui.advanced_filter import AdvancedFilterWidget
from gui.settings_dialog import SettingsDialog
from gui.splitter_dialog import SplitterDialog
from gui.scanner_dialog import ScannerDialog
from gui.duplicate_dialog import DuplicateFinderDialog
from gui.maintenance_dialog import MaintenanceDialog
from gui.stamper_dialog import StamperDialog
from gui.batch_tag_dialog import BatchTagDialog
from gui.tag_manager import TagManagerDialog
from gui.activity_widgets import BackgroundActivityStatusBar
from gui.utils import (
    format_datetime,
    format_date,
    show_selectable_message_box,
    show_notification
)
from gui.workflow_manager import WorkflowManagerWidget
from core.plugins.manager import PluginManager
from core.plugins.base import ApiContext

class MergeConfirmDialog(QDialog):
    def __init__(self, count, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Confirm Merge"))
        layout = QVBoxLayout(self)

        label = QLabel(self.tr(f"Merge {count} documents into a new combined entry?"))
        layout.addWidget(label)

        self.check_keep = QCheckBox(self.tr("Keep original documents"))
        self.check_keep.setChecked(True)
        layout.addWidget(self.check_keep)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def keep_originals(self):
        return self.check_keep.isChecked()

class MainWindow(QMainWindow):
    """
    Main application window for KPaperFlux.
    """
    def __init__(self, 
                 pipeline: Optional[PipelineProcessor] = None, 
                 db_manager: Optional[DatabaseManager] = None,
                 app_config: Optional[AppConfig] = None) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.db_manager = db_manager
        self.app_config = app_config or AppConfig()

        # If pipeline is provided but db_manager checks, try to extract db from pipeline
        if self.pipeline and not self.db_manager:
            self.db_manager = self.pipeline.db

        self._last_selected_uuid = None
        self.current_search_text = "" # Phase 106: Persistent search terms
        self._visible_count = 0
        self._total_count = 0
        self._selected_sum = 0.0
        self.setWindowTitle(self.tr("KPaperFlux"))
        self.setWindowIcon(QIcon("resources/icon.png"))
        self.resize(1000, 700)
        self.setAcceptDrops(True)
        self.pending_selection = []

        # Phase 105: Selection Tracking
        self._cockpit_selections = {} # query_str -> uuid
        self.filter_config_path = self.app_config.get_config_dir() / "filter_tree.json"

        # --- Phase 200: Plugin System ---
        plugin_dirs = [str(self.app_config.get_plugins_dir())]
        
        # Absolute path to project root
        project_root = Path(__file__).resolve().parent.parent
        local_plugins = project_root / "plugins"
        
        if local_plugins.exists():
            plugin_dirs.append(str(local_plugins))
            
        self.plugin_api = ApiContext(
            db=self.db_manager,
            vault=getattr(self.pipeline, 'vault', None) if self.pipeline else None,
            config=self.app_config,
            main_window=self
        )
        self.plugin_manager = PluginManager(plugin_dirs=plugin_dirs, api_context=self.plugin_api)
        self.plugin_manager.discover_plugins()

        self.create_menu_bar()
        # Toolbar/Shortcuts moved down to ensure all widgets like list_widget exist before initial status update

        # --- Global Models ---
        self.filter_tree = FilterTree(self.db_manager)
        self.load_filter_tree()

        # Central Widget is now a Stacked Widget
        self.central_stack = QStackedWidget()
        self.setCentralWidget(self.central_stack)

        # --- Page 0: Cockpit (Home) ---
        self.cockpit_widget = CockpitWidget(self.db_manager, filter_tree=self.filter_tree, app_config=self.app_config)
        self.cockpit_widget.navigation_requested.connect(self.navigate_to_list_filter)
        self.central_stack.addWidget(self.cockpit_widget)

        # --- Page 1: Explorer (Splitter) ---
        self.explorer_widget = QWidget()
        explorer_layout = QVBoxLayout(self.explorer_widget)
        explorer_layout.setContentsMargins(0, 0, 0, 0)

        # Main Splitter (Left Pane | Right Pane) -- Re-parented to explorer_layout
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        explorer_layout.addWidget(self.main_splitter)
        self.central_stack.addWidget(self.explorer_widget)
        
        # --- Page 2: Workflow Rules ---
        self.workflow_manager = WorkflowManagerWidget(filter_tree=self.filter_tree)
        self.workflow_manager.navigation_requested.connect(self.navigate_to_list_filter)
        self.central_stack.addWidget(self.workflow_manager)

        # --- Page 3: Reporting ---
        from gui.reporting import ReportingWidget
        self.reporting_widget = ReportingWidget(self.db_manager, filter_tree=self.filter_tree)
        self.reporting_widget.filter_requested.connect(self.navigate_to_list_filter)
        self.central_stack.addWidget(self.reporting_widget)

        self.central_stack.setCurrentIndex(0) # Start with Cockpit
        self.central_stack.currentChanged.connect(self._on_tab_changed)

        # --- Left Pane (Filter | List | Editor) ---
        self.left_pane_splitter = QSplitter(Qt.Orientation.Vertical)

        # 1. Unified Filter Controller (Tabs: Suche | Ansicht | Auto-Tagging)
        self.advanced_filter = AdvancedFilterWidget(
            db_manager=self.db_manager,
            filter_tree=self.filter_tree,
            save_callback=self.save_filter_tree
        )
        self.left_pane_splitter.addWidget(self.advanced_filter)

        if self.db_manager:
            self.list_widget = DocumentListWidget(self.db_manager, filter_tree=self.filter_tree, plugin_manager=self.plugin_manager)
            self.list_widget.document_selected.connect(self._on_document_selected)
            self.list_widget.delete_requested.connect(self.delete_document_slot)
            self.list_widget.reprocess_requested.connect(self.reprocess_document_slot)
            self.list_widget.merge_requested.connect(self.merge_documents_slot)
            # self.list_widget.export_requested.connect(self.export_documents_slot) # Handled internally
            self.list_widget.stamp_requested.connect(self.stamp_document_slot)
            self.list_widget.tags_update_requested.connect(self.manage_tags_slot)
            self.list_widget.edit_requested.connect(self.open_splitter_dialog_slot)
            self.list_widget.document_count_changed.connect(self.update_status_bar)
            self.list_widget.save_list_requested.connect(self.save_static_list)
            self.list_widget.apply_rule_requested.connect(self._on_rule_apply_requested)

            # Connect Filter
            # IMPORTANT: Connect local handler FIRST so current_search_text is updated
            # BEFORE the list refreshes and triggers selection logic.
            self.advanced_filter.filter_changed.connect(self._on_filter_changed)
            self.advanced_filter.filter_changed.connect(self.list_widget.apply_advanced_filter)

            self.advanced_filter.trash_mode_changed.connect(self.set_trash_mode)

            # Phase 92: Trash Actions
            self.list_widget.restore_requested.connect(self.restore_documents_slot)
            self.list_widget.purge_requested.connect(self.purge_documents_slot)
            self.list_widget.stage2_requested.connect(self.run_stage_2_selected_slot)
            self.list_widget.active_filter_changed.connect(self._on_view_filter_changed)
            self.list_widget.show_generic_requested.connect(self.open_debug_audit_window)

            # Phase 105: Active Filter Precedence
            self.advanced_filter.chk_active.toggled.connect(self.list_widget.set_advanced_filter_active)
            # Synchronize initial state
            self.list_widget.advanced_filter_active = self.advanced_filter.chk_active.isChecked()

            # Phase 106: Rule Application Scope
            self.advanced_filter.request_apply_rule.connect(self._on_rule_apply_requested)
            self.advanced_filter.search_triggered.connect(self._on_global_search_triggered)

            self.left_pane_splitter.addWidget(self.list_widget)

            # --- FIX: Metadata Editor (Unten links) ---
            # Dieser Block fehlte oder war unvollständig, was zum Absturz führte.
            self.editor_widget = MetadataEditorWidget(self.db_manager, pipeline=self.pipeline)

            # Connect Editor Signals
            self.editor_widget.metadata_saved.connect(self.list_widget.refresh_list)
            if hasattr(self, 'cockpit_widget'):
                 self.editor_widget.metadata_saved.connect(self.cockpit_widget.refresh_stats)
            # Phase 105: Ensure Rule Editor stays in sync
            self.editor_widget.metadata_saved.connect(self.advanced_filter.refresh_dynamic_data)

            self.left_pane_splitter.addWidget(self.editor_widget)
            self.editor_widget.setVisible(False)
            # ------------------------------------------

        # Add Left Pane to Main Splitter
        self.main_splitter.addWidget(self.left_pane_splitter)


        # --- Right Pane (PDF Viewer) ---
        self.pdf_viewer = PdfViewerWidget(self.pipeline)
        self.pdf_viewer.stamp_requested.connect(self.stamp_document_slot)
        self.pdf_viewer.tags_update_requested.connect(self.manage_tags_slot)
        self.pdf_viewer.export_requested.connect(self.export_documents_slot)
        self.pdf_viewer.reprocess_requested.connect(self.reprocess_document_slot)
        self.pdf_viewer.delete_requested.connect(self.delete_document_slot)
        if hasattr(self, 'list_widget'):
            self.pdf_viewer.document_changed.connect(self.list_widget.refresh_list)
        self.pdf_viewer.split_requested.connect(self.open_splitter_dialog_slot)
        self.main_splitter.addWidget(self.pdf_viewer)

        # Set Initial Sizes
        # Left Pane: 10% Filter, 60% List, 30% Editor
        self.left_pane_splitter.setSizes([70, 420, 210])
        self.left_pane_splitter.setCollapsible(0, False) # Keep filter visible

        # Main Splitter: Left 40%, Right 60%
        self.main_splitter.setSizes([400, 600])
        self.main_splitter.setCollapsible(1, True) # Allow shrinking viewer
        self.main_splitter.setHandleWidth(4)

        self.setStatusBar(QStatusBar())
        
        # Unified Status Container (Left Side)
        self.status_container = QWidget()
        self.status_layout = QHBoxLayout(self.status_container)
        self.status_layout.setContentsMargins(5, 0, 5, 0)
        self.status_layout.setSpacing(10)
        
        self.main_status_label = QLabel(self.tr("Ready"))
        self.status_layout.addWidget(self.main_status_label)
        
        self.activity_panel = BackgroundActivityStatusBar()
        self.status_layout.addWidget(self.activity_panel)
        
        self.status_layout.addStretch()
        self.statusBar().addWidget(self.status_container, 1)

        self.create_tool_bar()
        self.setup_shortcuts()

        self.read_settings()

        # Initial Refresh & UI Sync
        # We explicitly trigger _on_tab_changed(0) here to ensure the Cockpit looks active 
        # and the Filter button is hidden from the very first frame.
        self._on_tab_changed(0)

        if self.db_manager and hasattr(self, 'list_widget') and isinstance(self.list_widget, DocumentListWidget):
            self.list_widget.refresh_list()

    def setup_shortcuts(self):
        # Global shortcuts for main navigation
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(lambda: self.central_stack.setCurrentIndex(0))
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(lambda: self.central_stack.setCurrentIndex(1))
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(lambda: self.central_stack.setCurrentIndex(2))
        QShortcut(QKeySequence("Ctrl+4"), self).activated.connect(lambda: self.central_stack.setCurrentIndex(3))

        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        # self.shortcut_save.activated.connect(lambda: self.editor_widget.save_changes()) # editor_widget might be MetadataEditor or something else

        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        if hasattr(self, "advanced_filter"):
            def focus_search():
                if not self.advanced_filter.isVisible():
                    self._toggle_filter_view(True)
                self.advanced_filter.stack.setCurrentIndex(0)
                # Also select the button in sub-nav
                btn = self.advanced_filter.sub_mode_group.button(0)
                if btn: btn.setChecked(True)
                self.advanced_filter.txt_smart_search.setFocus()
            self.shortcut_search.activated.connect(focus_search)

        self.shortcut_home = QShortcut(QKeySequence("Ctrl+H"), self)
        self.shortcut_home.activated.connect(self.go_home_slot)

        if self.pipeline:
             self.main_loop_worker = MainLoopWorker(self.pipeline, self.filter_tree)
             self.main_loop_worker.documents_processed.connect(self._on_pipeline_documents_processed)
             self.main_loop_worker.status_changed.connect(self._on_ai_status_changed)
             self.main_loop_worker.fatal_error.connect(self._on_fatal_pipeline_error)

             # Activity Panel Connections
             self.main_loop_worker.progress.connect(self.activity_panel.update_progress)
             self.main_loop_worker.status_changed.connect(self.activity_panel.update_status)
             self.main_loop_worker.pause_state_changed.connect(self.activity_panel.on_pause_state_changed)
             self.activity_panel.pause_requested.connect(self.main_loop_worker.set_paused)
             self.activity_panel.stop_requested.connect(self.main_loop_worker.stop)

             self.main_loop_worker.start()

    def _on_rule_apply_requested(self, rule, scope):
        """Resolves target UUIDs based on scope and passes them to the filter widget to run."""
        uuids = None # default ALL
        if scope == "SELECTED":
            uuids = self.list_widget.get_selected_uuids()
            if not uuids:
                show_selectable_message_box(self, self.tr("Apply Rule"), self.tr("No documents selected."), icon=QMessageBox.Icon.Warning)
                return
        elif scope == "FILTERED":
            uuids = self.list_widget.get_all_uuids_in_view()
            if not uuids:
                show_selectable_message_box(self, self.tr("Apply Rule"), self.tr("Current list is empty."), icon=QMessageBox.Icon.Warning)
                return

        # Call the actual worker logic in the filter widget
        self.advanced_filter.run_batch_tagging(rule, uuids)

    def _on_global_search_triggered(self, search_text: str):
        """Stores global search terms and updates viewer if active."""
        self.current_search_text = search_text
        if hasattr(self, 'pdf_viewer'):
            self.pdf_viewer.set_highlight_text(search_text)

    def load_filter_tree(self):
        """Load Filter Tree using ExchangeService, with fallback to starter kit."""
        if self.filter_config_path.exists():
            logger.info(f"[DEBUG] Loading Filter Tree from: {self.filter_config_path}")
            try:
                with open(self.filter_config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    try:
                        # Try loading as a modern exchange payload
                        payload = ExchangePayload.model_validate_json(content)
                        if payload.type == "filter_tree":
                            self.filter_tree.load(payload.payload)
                        else:
                            # If it's a payload but wrong type, log and skip
                            logger.info(f"[ERROR] Found exchange payload in filter tree, but type is {payload.type}")
                    except Exception:
                        # Fallback for transient period/starter: Load raw JSON
                        data = json.loads(content)
                        self.filter_tree.load(data)
                logger.info(f"[DEBUG] Loaded {len(self.filter_tree.root.children)} root items.")
            except Exception as e:
                logger.info(f"[ERROR] Error loading filter tree: {e}")
        else:
            # Phase 130: Starter Kit Fallback
            starter_path = Path(__file__).resolve().parent.parent / "resources" / "filter_tree_starter.json"
            if starter_path.exists():
                logger.info(f"[DEBUG] Initializing with Starter Kit: {starter_path}")
                try:
                    with open(starter_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.filter_tree.load(data)
                except Exception as e:
                    logger.info(f"[ERROR] Error loading starter kit: {e}")

        # Phase 92: Ensure Trash/Archive Nodes exist
        root = self.filter_tree.root
        trash_exists = any(child.node_type == NodeType.TRASH for child in root.children)
        if not trash_exists:
            self.filter_tree.add_trash(root)
            
        archive_exists = any(child.node_type == NodeType.ARCHIVE for child in root.children)
        if not archive_exists:
            self.filter_tree.add_archive(root)

    def save_filter_tree(self):
        """Save Filter Tree using ExchangeService (Universal Standard)."""
        try:
            logger.info(f"[DEBUG] Saving Filter Tree to: {self.filter_config_path}")
            # Save the full tree data (including favorites)
            tree_data = json.loads(self.filter_tree.to_json())
            ExchangeService.save_to_file("filter_tree", tree_data, str(self.filter_config_path))
            logger.info("[DEBUG] Filter Tree saved successfully.")
        except Exception as e:
             logger.info(f"[ERROR] Error saving filter tree: {e}")

    def create_menu_bar(self):
        menubar = self.menuBar()

        # -- File Menu --
        file_menu = menubar.addMenu(self.tr("&File"))

        action_import = QAction(self.tr("&Import Document"), self)
        action_import.setShortcut("Ctrl+O")
        action_import.triggered.connect(self.import_document_slot)
        file_menu.addAction(action_import)

        self.action_import_transfer = QAction(self.tr("Import from Transfer"), self)
        self.action_import_transfer.triggered.connect(self.import_from_transfer_slot)
        file_menu.addAction(self.action_import_transfer)
        self._update_transfer_menu_visibility()

        action_scan = QAction(self.tr("&Scan..."), self)
        action_scan.setShortcut("Ctrl+S")
        action_scan.triggered.connect(self.open_scanner_slot)
        file_menu.addAction(action_scan)

        action_print = QAction(self.tr("&Print"), self)
        action_print.setShortcut("Ctrl+P")
        action_print.setEnabled(False) # Placeholder
        file_menu.addAction(action_print)

        file_menu.addSeparator()

        action_delete = QAction(self.tr("&Delete Selected"), self)
        action_delete.setShortcut("Del")
        action_delete.triggered.connect(self.delete_selected_slot)
        file_menu.addAction(action_delete)

        file_menu.addSeparator()

        action_export = QAction(self.tr("Export shown List..."), self)
        action_export.triggered.connect(self.export_visible_documents_slot)
        file_menu.addAction(action_export)

        file_menu.addSeparator()

        action_exit = QAction(self.tr("E&xit"), self)
        action_exit.setShortcut("Ctrl+Q")
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)


        view_menu = menubar.addMenu(self.tr("&View"))

        action_refresh = QAction(self.tr("&Refresh List"), self)
        action_refresh.setShortcut("F5")
        action_refresh.triggered.connect(self.refresh_list_slot)
        view_menu.addAction(action_refresh)

        action_extra = QAction(self.tr("Show Extra Data"), self)
        action_extra.setShortcut("Ctrl+E")
        action_extra.setCheckable(True)
        action_extra.setChecked(True)
        action_extra.triggered.connect(self.toggle_editor_visibility)
        view_menu.addAction(action_extra)

        view_menu.addSeparator()

        # Action toggle_filter is created later in create_tool_bar, but we need it here
        # or we create it here and reuse it there. Let's move its creation here.
        self.action_toggle_filter = QAction("🗂️ " + self.tr("Filter Panel"), self)
        self.action_toggle_filter.setCheckable(True)
        self.action_toggle_filter.setChecked(True)
        self.action_toggle_filter.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.action_toggle_filter.triggered.connect(self._toggle_filter_view)
        view_menu.addAction(self.action_toggle_filter)

        # -- Maintenance Menu --
        maintenance_menu = menubar.addMenu(self.tr("&Maintenance"))

        orphans_action = QAction(self.tr("Check Integrity (Orphans/Ghosts)"), self)
        orphans_action.triggered.connect(self.open_maintenance_slot)
        maintenance_menu.addAction(orphans_action)

        duplicates_action = QAction(self.tr("Find Duplicates"), self)
        duplicates_action.triggered.connect(self.find_duplicates_slot)
        maintenance_menu.addAction(duplicates_action)

        tags_action = QAction(self.tr("Manage Tags"), self)
        tags_action.triggered.connect(self.open_tag_manager_slot)
        maintenance_menu.addAction(tags_action)

        # -- Tools Menu --
        tools_menu = menubar.addMenu(self.tr("&Tools"))

        purge_all_action = QAction(self.tr("Purge All Data (Reset)"), self)
        purge_all_action.triggered.connect(self.purge_data_slot)
        tools_menu.addAction(purge_all_action)
        
        tools_menu.addSeparator()
        self.plugin_submenu = tools_menu.addMenu(self.tr("External Plugins"))
        self._refresh_plugin_menu()

        # -- Debug Menu (Phase 102) --
        debug_menu = menubar.addMenu(self.tr("&Debug"))

        debug_orphans = QAction(self.tr("Show Orphaned Vault Files"), self)
        debug_orphans.triggered.connect(self._debug_show_orphans_slot)
        debug_menu.addAction(debug_orphans)

        prune_orphans = QAction(self.tr("Prune Orphaned Vault Files (Console)"), self)
        prune_orphans.triggered.connect(self._debug_prune_orphans_slot)
        debug_menu.addAction(prune_orphans)

        debug_menu.addSeparator()

        debug_broken = QAction(self.tr("Show Broken Entity References"), self)
        debug_broken.triggered.connect(self._debug_show_broken_slot)
        debug_menu.addAction(debug_broken)

        prune_broken = QAction(self.tr("Prune Broken Entity References (Console)"), self)
        prune_broken.triggered.connect(self._debug_prune_broken_slot)
        debug_menu.addAction(prune_broken)

        debug_menu.addSeparator()

        debug_dedup = QAction(self.tr("Deduplicate Vault (Inhaltsbasiert)"), self)
        debug_dedup.triggered.connect(self._debug_deduplicate_vault_slot)
        debug_menu.addAction(debug_dedup)

        # -- Config Menu --
        config_menu = menubar.addMenu(self.tr("&Config"))

        action_settings = QAction(self.tr("&Settings..."), self)
        action_settings.triggered.connect(self.open_settings_slot)
        config_menu.addAction(action_settings)

        # -- Semantic Data Menu (Phase 107) --
        self.semantic_menu = menubar.addMenu(self.tr("&Semantic Data"))

        missing_semantic_action = QAction(self.tr("List Missing"), self)
        missing_semantic_action.triggered.connect(self.list_missing_semantic_data_slot)
        self.semantic_menu.addAction(missing_semantic_action)

        mismatched_semantic_action = QAction(self.tr("List Mismatched"), self)
        mismatched_semantic_action.triggered.connect(self.list_mismatched_semantic_data_slot)
        self.semantic_menu.addAction(mismatched_semantic_action)

        self.semantic_menu.addSeparator()

        run_stage2_selected = QAction(self.tr("Run Extraction (Selected)"), self)
        run_stage2_selected.triggered.connect(self.run_stage_2_selected_slot)
        self.semantic_menu.addAction(run_stage2_selected)

        run_stage2_missing = QAction(self.tr("Process empty Documents"), self)
        run_stage2_missing.triggered.connect(self.run_stage_2_all_missing_slot)
        self.semantic_menu.addAction(run_stage2_missing)

        # -- Help Menu --
        help_menu = menubar.addMenu(self.tr("&Help"))

        action_about = QAction(self.tr("&About"), self)
        action_about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(action_about)

    def _refresh_plugin_menu(self):
        """Populates the Plugins submenu with actions from loaded plugins."""
        if not hasattr(self, 'plugin_submenu') or not self.plugin_manager:
            return
            
        self.plugin_submenu.clear()
        
        found_any = False
        for plugin in self.plugin_manager.plugins:
            try:
                actions = plugin.get_tool_actions(parent=self)
                if actions:
                    found_any = True
                    for action in actions:
                        self.plugin_submenu.addAction(action)
            except Exception as e:
                logger.info(f"[PluginError] Error loading tools from {plugin.__class__.__name__}: {e}")
                
        if not found_any:
            load_errors = getattr(self.plugin_manager, 'load_errors', {})
            if load_errors:
                self.plugin_submenu.addAction(self.tr("Plugin Loading Errors...")).setEnabled(False)
                self.plugin_submenu.addSeparator()
                err_menu = self.plugin_submenu.addMenu(self.tr("Details"))
                for path, err in load_errors.items():
                    err_menu.addAction(f"{Path(path).name}: {err}").setEnabled(False)
            else:
                self.plugin_submenu.addAction(self.tr("No plugin actions")).setEnabled(False)


    # --- Debug Handlers ---
    def _debug_show_orphans_slot(self):
        mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
        mgr.show_orphaned_vault_files()

    def _debug_show_broken_slot(self):
        mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
        mgr.show_broken_entity_references()

    def _debug_prune_orphans_slot(self):
        msg = "Permanently delete ALL files in the vault that are NOT referenced by any entity? Check console for progress."
        if show_selectable_message_box(self, "Prune Vault", msg, icon=QMessageBox.Icon.Warning, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
            mgr.prune_orphaned_vault_files()

    def _debug_prune_broken_slot(self):
        msg = "Permanently delete ALL database entries (entities) that point to missing files? Check console for progress."
        if show_selectable_message_box(self, "Prune Database", msg, icon=QMessageBox.Icon.Warning, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
            mgr.prune_broken_entity_references()
            if self.list_widget:
                self.list_widget.refresh_list()

    def _debug_deduplicate_vault_slot(self):
        msg = ("This will IDENTIFY duplicates by HASH and SIZE.\n\n"
               "STEP 1: Delete newer duplicate files from Vault.\n"
               "STEP 2: Remove ALL entities from the list that pointed to these files.\n\n"
               "This is DESTRUCTIVE. Continue?")
        reply = show_selectable_message_box(self, "Physical Deduplication", msg,
                                           icon=QMessageBox.Icon.Question,
                                           buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
            mgr.deduplicate_vault()
            if self.list_widget:
                self.list_widget.refresh_list()

    def _on_filter_changed(self, criteria: dict):
        """Update local state when filter changes."""
        # Check for explicit meta-key first (added by AdvancedFilter)
        text = criteria.get('_meta_fulltext')
        if text is None:
             text = criteria.get('fulltext', '')

        self.current_search_text = text
        logger.info(f"[DEBUG] MainWindow updated current_search_text to: '{self.current_search_text}'")

    def _resolve_pdf_path(self, doc_uuid: str) -> Optional[str]:
        """
        Resolve the filesystem path for the PDF of a Virtual Document.
        Stage 0/1 Simplified: Returns path of the FIRST source file.
        TODO: Implement stitching for merged documents.
        """
        if not self.db_manager or not self.db_manager.connection:
            return None

        cursor = self.db_manager.connection.cursor()

        # 1. Get Source Mapping
        cursor.execute("SELECT source_mapping FROM virtual_documents WHERE uuid = ?", (doc_uuid,))
        row = cursor.fetchone()
        if not row or not row[0]:
            # Fallback: check legacy (uuid.pdf in vault) - but vault path is configurable
            return None

        try:
            mapping = json.loads(row[0])
            if not mapping: return None

            # 2. Get First Source
            first_seg = mapping[0]
            file_uuid = first_seg.get("file_uuid")
            if not file_uuid: return None

            # 3. Get Physical File Path
            cursor.execute("SELECT file_path FROM physical_files WHERE uuid = ?", (file_uuid,))
            f_row = cursor.fetchone()
            if f_row and f_row[0]:
                path = f_row[0]
                if os.path.exists(path):
                    return path
        except Exception as e:
            logger.info(f"Error resolving PDF path for {doc_uuid}: {e}")

        return None

    def _on_pipeline_documents_processed(self):
        """Unified handler for background pipeline completions."""
        if hasattr(self, 'list_widget'):
            self.list_widget.refresh_list()
        
        # Phase 107: Auto-refresh editor if something is selected
        self._refresh_current_editor_selection()
        
        # Refresh Stats
        if hasattr(self, "cockpit_widget"):
             self.cockpit_widget.refresh_stats()

    def _refresh_current_editor_selection(self):
        """Re-fetches and updates the content of the metadata editor for current selection."""
        if not hasattr(self, 'list_widget') or not hasattr(self, 'editor_widget') or not self.db_manager:
            return
            
        # Only refresh if editor is actually open/visible 
        if not self.editor_widget.isVisible():
            return

        uuids = self.list_widget.get_selected_uuids()
        if not uuids:
            return

        docs = []
        for uuid in uuids:
            d = self.db_manager.get_document_by_uuid(uuid)
            if d: docs.append(d)

        if docs:
            self.editor_widget.display_documents(docs)
            
        # Update Status Bar with Sum (Phase 4)
        total_sum = 0.0
        for d in docs:
            if d.total_gross:
                total_sum += float(d.total_gross or 0)
        
        self._selected_sum = total_sum
        self._refresh_status_bar()

    def _refresh_status_bar(self):
        """Unified status bar text update."""
        status_text = self.tr("Docs: %s/%s") % (self._visible_count, self._total_count)
        
        if self._selected_sum > 0:
            # Localized formatting for Currency
            status_text += f" | Σ {self._selected_sum:,.2f} EUR"
            
        self.main_status_label.setText(status_text)

    def _on_document_selected(self, uuids: list[str]):
        """Callback when selection changes in document list."""
        if not uuids:
            if hasattr(self, 'editor_widget'): self.editor_widget.clear()
            if hasattr(self, 'pdf_viewer'): self.pdf_viewer.clear()
            self._selected_sum = 0.0
            self._refresh_status_bar()
            return

        # Fetch Documents from DB
        docs = []
        for uuid in uuids:
             d = self.db_manager.get_document_by_uuid(uuid)
             if d: docs.append(d)

        if not docs:
             return

        # Use the first document for Single-View components (PDF, Info)
        primary_doc = docs[0]
        uuid = primary_doc.uuid
        self._last_selected_uuid = uuid

        # Load into PDF Viewer
        path = self._resolve_pdf_path(uuid)
        if path:
             # Check for Search Hits for Deferred Navigation
             target_index = -1
             if self.current_search_text and self.db_manager:
                 hits = self.db_manager.find_text_pages_in_document(uuid, self.current_search_text)
                 if hits:
                     target_index = hits[0] # 0-based
                     logger.info(f"[Search-Hit-Debug] Term: '{self.current_search_text}', UUID: '{uuid}', Found on Pages: {hits} -> Jumping to {target_index}")

             self.pdf_viewer.load_document(path, jump_to_index=target_index)
        else:
             logger.info(f"Error: Could not resolve PDF path for {uuid}")

        # Update Info Panel
        if hasattr(self, 'info_panel') and self.info_panel:
            self.info_panel.load_document(primary_doc)

        # Update Editor (Batch aware)
        if hasattr(self, 'editor_widget'):
            logger.info(f"[DEBUG] Ensuring Editor Visible. Current: {self.editor_widget.isVisible()}")
            self.editor_widget.setVisible(True)
            self.editor_widget.display_documents(docs)

            # Robust Status Sync (Case Insensitive)
            doc = primary_doc
            stat = (doc.status or "NEW").upper()
            idx = self.editor_widget.status_combo.findText(stat)
            if idx >= 0:
                self.editor_widget.status_combo.setCurrentIndex(idx)
            else:
                self.editor_widget.status_combo.setCurrentText(stat) # Fallback if not in list
            self.editor_widget.export_filename_edit.setText(doc.original_filename or "")

        # Phase 105: UI Resilience - Check Splitter Sizes
        # 1. Main Splitter (Left Pane | PDF Viewer)
        main_sizes = self.main_splitter.sizes()
        if main_sizes and main_sizes[1] == 0:
            logger.info("[DEBUG] PDF Viewer collapsed! Forcing expand.")
            total = sum(main_sizes)
            self.main_splitter.setSizes([int(total*0.4), int(total*0.6)])

        # 2. Left Pane Splitter (Filter | List | Editor)
        sizes = self.left_pane_splitter.sizes()
        if sizes and sizes[2] == 0:
            logger.info("[DEBUG] Editor pane collapsed! Forcing expand.")
            total = sum(sizes)
            new_sizes = [sizes[0], int(total*0.6), int(total*0.4)]
            self.left_pane_splitter.setSizes(new_sizes)

        # Update PDF Viewer
        if hasattr(self, 'pdf_viewer'):
            if not self.pdf_viewer.isVisible():
                logger.info(f"[DEBUG] Ensuring Viewer Visible.")
                self.pdf_viewer.setVisible(True)

            if docs:
                # Show first doc as reference (works for single and batch)
                self.pdf_viewer.load_document(docs[0].uuid, uuid=docs[0].uuid)
                # Apply current global search highlight if any
                if self.current_search_text:
                    self.pdf_viewer.set_highlight_text(self.current_search_text)
            else:
                self.pdf_viewer.clear()

    def delete_selected_slot(self):
        """Handle deletion via Menu Hack."""
        if hasattr(self, 'list_widget'):
            uuids = self.list_widget.get_selected_uuids()
            if uuids:
                self.delete_document_slot(uuids)
            else:
                show_selectable_message_box(self, self.tr("Info"), self.tr("Please select documents to delete."), icon=QMessageBox.Icon.Information)

    def delete_document_slot(self, uuids):
        """
        Handle delete request from List (Single or Batch).
        Supports both Entity Deletion (Smart) and Document Deletion (Trash).
        """
        if not isinstance(uuids, list):
            uuids = [uuids]

        if not uuids:
            return

        count = len(uuids)
        msg = self.tr("Are you sure you want to delete this item?") if count == 1 else self.tr(f"Are you sure you want to delete {count} items?")

        reply = show_selectable_message_box(self, self.tr("Confirm Delete"),
                                     msg,
                                     icon=QMessageBox.Icon.Question,
                                     buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            if self.db_manager and self.pipeline:
                deleted_count = 0
                is_trash_mode = getattr(self.list_widget, 'is_trash_mode', False)

                for uuid in uuids:
                    # 0. If in Trash Mode, Purge Immediately
                    if is_trash_mode:
                        if self.pipeline.delete_entity(uuid):
                             deleted_count += 1
                        continue

                    # 1. Try Deleting as Entity (Smart Delete)
                    # This removes the semantic row. If it was the last one, it trashes the source doc.
                    if self.pipeline.delete_entity(uuid):
                        deleted_count += 1
                        continue

                    # 2. Fallback: Deleting a Source Doc (e.g. from Trash or Inbox if raw)
                    doc = self.db_manager.get_document_by_uuid(uuid)
                    if doc:
                        # If we are in Trash Mode, we Purge.
                        # If not, we Move to Trash.
                        if getattr(self.list_widget, 'is_trash_mode', False):
                             self.db_manager.purge_document(uuid)
                        else:
                             self.db_manager.mark_documents_deleted([uuid])
                        deleted_count += 1

                self.editor_widget.clear()
                self.pdf_viewer.clear()
                self.list_widget.refresh_list()

                # Refresh Stats
                if hasattr(self, "cockpit_widget"):
                     self.cockpit_widget.refresh_stats()
                if hasattr(self, "filter_tree_widget"):
                     self.filter_tree_widget.load_tree()

                if count > 1:
                    show_notification(self, self.tr("Deleted"), self.tr(f"Deleted {deleted_count} items."))

    def reprocess_document_slot(self, uuids: list):
        """Re-run pipeline for list of documents."""
        if not self.pipeline:
            return

        # Phase 98: Resolve Entity UUIDs to Source UUIDs
        # Pipeline expects physical document UUIDs.
        source_uuids = set()
        for u in uuids:
            # v28.2: Soft Reset instead of Purge.
            self.db_manager.reset_document_for_reanalysis(u)
            source_uuids.add(u)

        start_uuids = list(source_uuids)
        if not start_uuids: return

        count = len(start_uuids)

        progress = QProgressDialog(self.tr("Reprocessing..."), self.tr("Cancel"), 0, count, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0) # Show immediately
        progress.forceShow() # Ensure visibility
        progress.setValue(0)

        # Ensure it paints
        QCoreApplication.processEvents()

        uuid_to_restore = None
        if hasattr(self, 'pdf_viewer') and self.pdf_viewer.current_uuid in start_uuids:
             uuid_to_restore = self.pdf_viewer.current_uuid
             self.pdf_viewer.clear()

        self.reprocess_worker = ReprocessWorker(self.pipeline, start_uuids)

        # Connect Signals
        self.reprocess_worker.progress.connect(
            lambda i, uid: (
                progress.setLabelText(self.tr(f"Reprocessing {i+1} of {count}...")),
                progress.setValue(i)
            )
        )

        self.reprocess_worker.finished.connect(
            lambda success, total, processed_uuids: self._on_reprocess_finished(success, total, processed_uuids, uuids, progress, uuid_to_restore)
        )

        progress.canceled.connect(self.reprocess_worker.cancel)

        self.reprocess_worker.start()

    def _on_reprocess_finished(self, success_count, total, processed_uuids, original_uuids, progress_dialog, uuid_to_restore=None):
        progress_dialog.close()

        # Safe Thread Cleanup
        if hasattr(self, 'reprocess_worker') and self.reprocess_worker:
            self.reprocess_worker.wait() # Ensure it's fully done
            self.reprocess_worker.deleteLater() # Schedule deletion
            self.reprocess_worker = None # Clear ref

        # Refresh Editor logic
        if hasattr(self, 'editor_widget') and self.editor_widget:
            intersect = set(processed_uuids) & set(self.editor_widget.current_uuids)
            if intersect:
                 docs_to_refresh = []
                 for uid in self.editor_widget.current_uuids:
                     d = self.db_manager.get_document_by_uuid(uid)
                     if d: docs_to_refresh.append(d)
                 if docs_to_refresh:
                     self.editor_widget.display_documents(docs_to_refresh)

        # Refresh List First (this typically clears selection and viewer)
        self.list_widget.refresh_list()

        # Restore Selection
        if uuid_to_restore and uuid_to_restore in processed_uuids:
             self.list_widget.select_document(uuid_to_restore)

        # Trigger Cockpit Refresh
        if hasattr(self, 'cockpit_widget') and self.cockpit_widget:
            self.cockpit_widget.refresh_stats()

        # Phase 107 Update: We NO LONGER add tasks manually to ai_worker.
        # The MainLoopWorker will pick up 'NEW' documents automatically.

        show_notification(self, self.tr("Reprocessed"), f"Reprocessed {success_count}/{total} documents.\nProcessing will continue in background.")

    def start_import_process(self, files: list[str], move_source: bool = False):
        """
        Unified entry point for importing documents (Menu or Drop).
        Starts the ImportWorker with a modal ProgressDialog.
        Intercepts with Splitter Dialog for Pre-Flight Check.
        """
        if not files or not self.pipeline:
            return

        # Phase 9: Pre-Flight Check
        # We process files one by one via Dialog to get Instructions
        import_items = []

        pdf_files = [f for f in files if f.lower().endswith(".pdf")]
        other_files = [f for f in files if not f.lower().endswith(".pdf")]

        # 1. Handle PDFs via Batch Assistant
        if pdf_files:
            file_infos = []
            for f in pdf_files:
                try:
                    p_class = get_pdf_class(f)
                    is_prot = (p_class != PDFClass.STANDARD)
                    file_infos.append({
                        "path": f,
                        "pdf_class": p_class.value,
                        "is_protected": is_prot
                    })
                except Exception as e:
                    logger.info(f"Error classifying PDF {f}: {e}")
                    # Default to standard if check fails
                    file_infos.append({
                        "path": f,
                        "pdf_class": "C",
                        "is_protected": False
                    })
            
            # ALL PDFs now go through splitter, but protected ones are locked
            if file_infos:
                dialog = SplitterDialog(self.pipeline, self)
                dialog.load_for_batch_import(file_infos)

                if dialog.exec() == QDialog.DialogCode.Accepted:
                    instrs = dialog.import_instructions
                    import_items.append(("BATCH", instrs))
                else:
                    logger.info("PDF Import cancelled by user.")
                    # If we only had PDFs, we might want to return here.
                    # But other_files might still need processing.

        # 2. Handle non-PDFs (Direct)
        for fpath in other_files:
            import_items.append((fpath, None))

        if not import_items:
             logger.info("No files to import (User cancelled all).")
             return

        is_batch = any(item[0] == "BATCH" for item in import_items if isinstance(item, tuple))
        
        # Calculate effective total (including sub-items in batches)
        count = 0
        for item in import_items:
            if isinstance(item, tuple) and item[0] == "BATCH" and isinstance(item[1], list):
                count += len(item[1])
            else:
                count += 1

        # Progress Dialog
        progress = QProgressDialog(self.tr("Initializing Import..."), self.tr("Cancel"), 0, count, self)
        progress.setWindowTitle(self.tr("Importing..."))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        # Force Render
        progress.show()
        QCoreApplication.processEvents()

        # Worker Setup
        self.import_worker = ImportWorker(self.pipeline, import_items, move_source=move_source)

        # Signals
        self.import_worker.progress.connect(
            lambda i, fname: (
                self.main_status_label.setText(self.tr(f"Importing {i+1}/{count}: {os.path.basename(fname)}...")),
                progress.setValue(i)
            )
        )

        self.import_worker.finished.connect(
            lambda s, t, uuids, err: self._on_import_finished(s, t, uuids, err, progress, skip_splitter=is_batch)
        )

        progress.canceled.connect(self.import_worker.cancel)

        self.import_worker.start()

    def import_document_slot(self):
        """Handle import button click (File Menu)."""
        files, _ = QFileDialog.getOpenFileNames(
            self, self.tr("Select Documents"), "", self.tr("PDF Files (*.pdf);;All Files (*)")
        )

        if files:
            # Default to Copy (move_source=False) for menu import
            self.start_import_process(files, move_source=False)

    def open_scanner_slot(self):
        """Open scanner dialog and process result."""
        dialog = ScannerDialog(self)
        if dialog.exec():
            path = dialog.get_scanned_file()
            if path and self.pipeline:
                # Delegate to the unified import process
                # This fixes the GUI freeze (background worker) and enables Splitter support
                self.start_import_process([path], move_source=True)

    def refresh_list_slot(self):
        if self.list_widget:
            self.list_widget.refresh_list()

    def open_settings_slot(self):
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self.on_settings_changed)
        dialog.exec()

    def on_settings_changed(self):
        self.list_widget.refresh_list()
        self._update_transfer_menu_visibility()
        
        # Phase 2.0: Hot-Reload AI Components
        if hasattr(self, 'main_loop_worker') and self.main_loop_worker:
            logger.info("[Core] Settings changed. Re-initializing AI Analyzer...")
            from core.ai_analyzer import AIAnalyzer
            new_analyzer = AIAnalyzer(self.app_config.get_api_key(), self.app_config.get_gemini_model())
            # Update the canonizer's analyzer
            if hasattr(self.main_loop_worker, 'canonizer'):
                self.main_loop_worker.canonizer.analyzer = new_analyzer
                # Also update visual auditor if present
                if hasattr(self.main_loop_worker.canonizer, 'visual_auditor'):
                    self.main_loop_worker.canonizer.visual_auditor.ai = new_analyzer

    def _update_transfer_menu_visibility(self):
        """Show/Hide transfer action based on config."""
        path = self.app_config.get_transfer_path()
        exists = os.path.exists(path) if path else False
        self.action_import_transfer.setVisible(exists)

    def import_from_transfer_slot(self):
        """Imports all files from the defined transfer folder."""
        path = self.app_config.get_transfer_path()
        if not path or not os.path.exists(path):
            return

        # Collect files
        files = []
        try:
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                if os.path.isfile(full_path) and not item.startswith('.'):
                    # Check extension via PreFlightImporter
                    _, ext = os.path.splitext(item)
                    if ext.lower() == '.pdf' or ext.lower() in PreFlightImporter.ALLOWED_EXTENSIONS:
                        files.append(full_path)
        except Exception as e:
            show_selectable_message_box(self, self.tr("Error"), f"Could not read transfer folder: {e}", icon=QMessageBox.Icon.Critical)
            return

        if not files:
            show_notification(self, self.tr("Transfer"), self.tr("No compatible files found in transfer folder."))
            return

        msg = self.tr(f"Found {len(files)} files in transfer folder. Do you want to import them now?")
        reply = show_selectable_message_box(self, self.tr("Import from Transfer"), msg, 
                                           icon=QMessageBox.Icon.Question,
                                           buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.start_import_process(files, move_source=False)

    # --- Stage 2: Semantic Data Management Slots ---

    def list_missing_semantic_data_slot(self):
        """Query DB for documents lacking semantic data and display them."""
        docs = self.db_manager.get_documents_missing_semantic_data()
        count = len(docs)
        if count == 0:
            show_notification(self, self.tr("Semantic Data"), self.tr("All documents have semantic data."))
            return

        self.central_stack.setCurrentIndex(1) # Explorer View

        uuids = [d.uuid for d in docs]
        query = {"field": "uuid", "op": "in", "value": uuids}
        self.list_widget.apply_advanced_filter(query, label="Semantic Data > Missing")
        self.main_status_label.setText(self.tr(f"Showing {count} docs with missing semantic data."))

    def list_mismatched_semantic_data_slot(self):
        """Query DB for documents with mismatched data."""
        docs = self.db_manager.get_documents_mismatched_semantic_data()
        count = len(docs)
        if count == 0:
            show_notification(self, self.tr("Semantic Data"), self.tr("No data mismatches found."))
            return

        self.central_stack.setCurrentIndex(1) # Explorer View

        uuids = [d.uuid for d in docs]
        query = {"field": "uuid", "op": "in", "value": uuids}
        self.list_widget.apply_advanced_filter(query, label="Semantic Data > Mismatched")
        self.main_status_label.setText(self.tr(f"Showing {count} docs with data mismatches."))

    def run_stage_2_selected_slot(self, uuids: list[str] = None):
        """Manually trigger Stage 2 for selected documents."""
        if not uuids:
            uuids = self.list_widget.get_selected_uuids()

        if not uuids:
            show_selectable_message_box(self, self.tr("Action required"), self.tr("Please select at least one document."), icon=QMessageBox.Icon.Warning)
            return

        # Phase 107: Smart routing
        to_shortcut = []
        to_full = []

        # We need to check current status. List widget has objects or we ask DB.
        for uid in uuids:
            doc = self.db_manager.get_document_by_uuid(uid)
            if doc and doc.status in ('PROCESSED', 'ERROR_AI') and doc.type_tags:
                to_shortcut.append(uid)
            else:
                to_full.append(uid)

        if to_shortcut:
            self.db_manager.queue_for_semantic_extraction(to_shortcut)
        if to_full:
            self.reprocess_document_slot(to_full)

        self.main_status_label.setText(self.tr(f"Queued {len(uuids)} docs for extraction."))

    def run_stage_2_all_missing_slot(self):
        """Find all documents with empty semantic data and trigger processing."""
        docs = self.db_manager.get_documents_missing_semantic_data()
        if not docs:
            show_notification(self, self.tr("Semantic Data"), self.tr("No empty documents found."))
            return

        uuids = [d.uuid for d in docs]
        confirm = show_selectable_message_box(self, self.tr("Process empty Documents"),
                                             self.tr(f"Start semantic extraction for {len(uuids)} documents without details?"),
                                             icon=QMessageBox.Icon.Question,
                                             buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            to_shortcut = []
            to_full = []
            for uid in uuids:
                # Optimized check: docs are already loaded in 'docs' list
                match = next((d for d in docs if d.uuid == uid), None)
                if match and match.status in ('PROCESSED', 'ERROR_AI') and match.type_tags:
                    to_shortcut.append(uid)
                else:
                    to_full.append(uid)

            if to_shortcut:
                self.db_manager.queue_for_semantic_extraction(to_shortcut)
            if to_full:
                self.reprocess_document_slot(to_full)

            self.main_status_label.setText(self.tr("Queued %n doc(s) for background extraction.", "", len(uuids)))

    def merge_documents_slot(self, uuids: list[str]):
        """Handle merge request."""
        if not self.pipeline:
            return

        dlg = MergeConfirmDialog(len(uuids), self)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                keep_originals = dlg.keep_originals()
                # Merge
                success = self.pipeline.merge_documents(uuids)
                if success:
                    if not keep_originals:
                         # Delete originals (Stage 0/1)
                         for uid in uuids:
                             self.pipeline.delete_entity(uid)

                    self.main_status_label.setText(self.tr("Documents merged successfully."))
                    self.list_widget.refresh_list()
                else:
                    show_selectable_message_box(self, self.tr("Error"), self.tr("Merge failed."), icon=QMessageBox.Icon.Warning)
            except Exception as e:
                import traceback
                logger.info(f"[ERROR] Merge error: {e}")
                traceback.print_exc()
                show_selectable_message_box(
                    self, 
                    self.tr("Error"), 
                    self.tr("Merge error: %s") % str(e), 
                    icon=QMessageBox.Icon.Critical
                )

    def show_about_dialog(self) -> None:
        """Show the About dialog with system info."""
        qt_version: str = PYQT_VERSION_STR
        py_version: str = sys.version.split()[0]
        platform_info: str = f"{platform.system()} {platform.release()}"

        # Try to get KDE version
        kde_version = os.environ.get('KDE_FULL_SESSION', self.tr("Unknown"))
        if kde_version == 'true':
            # Try to fetch specific version if possible, otherwise just indicate KDE is present
            kde_version = self.tr("KDE Plasma (Detected)")
        else:
            kde_version = self.tr("Not Detected")

        about_text: str = self.tr(
            "<h3>KPaperFlux v1.0</h3>"
            "<p>A modern document management tool.</p>"
            "<hr>"
            "<p><b>Qt Version:</b> %1</p>"
            "<p><b>Python:</b> %2</p>"
            "<p><b>System:</b> %3</p>"
            "<p><b>Desktop Environment:</b> %4</p>"
        ).replace("%1", qt_version).replace("%2", py_version).replace("%3", platform_info).replace("%4", kde_version)

        QMessageBox.about(self, self.tr("About KPaperFlux"), about_text)

    def find_duplicates_slot(self):
        """Open Duplicate Finder with Progress Spinner."""
        if not hasattr(self, "db_manager") or not self.db_manager: return

        # Create and Show Progress Dialog
        progress = QProgressDialog(self.tr("Searching for duplicates..."), self.tr("Cancel"), 0, 100, self)
        progress.setWindowTitle(self.tr("Please Wait"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0) # Show immediately
        progress.setValue(0)

        # Create Worker
        worker = SimilarityWorker(self.db_manager, self.pipeline.vault)

        # Track worker for safety
        self._current_sim_worker = worker

        def on_progress(current, total):
            if progress.wasCanceled():
                worker.terminate()
                return
            percent = int((current / total) * 100) if total > 0 else 0
            progress.setValue(percent)
            progress.setLabelText(self.tr(f"Comparing documents ({current}/{total})..."))

        def on_finished(duplicates):
            progress.close()
            self._current_sim_worker = None

            if not duplicates:
                show_notification(self, self.tr("No Duplicates"), self.tr("No duplicates found with current threshold."))
                return

            dialog = DuplicateFinderDialog(duplicates, self.db_manager, self)
            dialog.exec()

            if self.list_widget:
                self.list_widget.refresh_list()

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        worker.start()

        # Keep a reference to prevent GC
        self._sim_thread = worker

    def open_maintenance_slot(self):
        """Open Maintenance Dialog."""
        if not self.pipeline or not self.db_manager:
            return

        mgr = IntegrityManager(self.db_manager, self.pipeline.vault)
        dialog = MaintenanceDialog(self, mgr, self.pipeline)
        dialog.exec()

        if self.list_widget:
            self.list_widget.refresh_list()

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle Drag Enter: Check for valid files (PDF, Images, ZIP)."""
        if event.mimeData().hasUrls():
            convertible_exts = PreFlightImporter.ALLOWED_EXTENSIONS.union({'.zip'})

            for url in event.mimeData().urls():
                path = url.toLocalFile()
                _, ext = os.path.splitext(path)
                ext = ext.lower()

                if path.endswith('.pdf') or ext in convertible_exts:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle Drop: Extract files with Pre-Flight Conversion."""
        files = []
        if event.mimeData().hasUrls():
            temp_dir = tempfile.gettempdir()
            convertible_exts = PreFlightImporter.ALLOWED_EXTENSIONS.union({'.zip'})

            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if not os.path.exists(path): continue

                _, ext = os.path.splitext(path)
                ext = ext.lower()

                if ext == '.pdf':
                    files.append(path)
                elif ext in convertible_exts:
                    # Conversion
                    base_name = os.path.basename(path)
                    temp_pdf_path = os.path.join(temp_dir, f"KPaperFlux_{base_name}.pdf")

                    self.setCursor(Qt.CursorShape.WaitCursor)
                    try:
                        logger.info(f"[Importer] Converting {path} -> {temp_pdf_path}...")
                        success = PreFlightImporter.convert_to_pdf(path, temp_pdf_path)
                        if success:
                            files.append(temp_pdf_path)
                        else:
                            logger.info(f"[Importer] Failed to convert: {path}")
                    finally:
                        self.setCursor(Qt.CursorShape.ArrowCursor)

        if files:
            self.handle_dropped_files(files)
            event.acceptProposedAction()
        else:
            event.ignore()

    def handle_dropped_files(self, files: list[str]):
        """Confirm import and options."""
        if not self.pipeline:
            return

        # Custom Dialog for Options
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Import Dropped Files"))
        dialog.setMinimumWidth(400) # Ensure title is visible

        layout = QVBoxLayout(dialog)
        
        # Phase 105: Fix pluralization and translation
        msg = self.tr("Import %n file(s) into KPaperFlux?", "", len(files))
        layout.addWidget(QLabel(msg))

        chk_move = QCheckBox(self.tr("Delete source files after import"))
        layout.addWidget(chk_move)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        # Use our tr() for buttons to ensure l10n consistency
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("OK"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("Cancel"))
        
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            move_source = chk_move.isChecked()
            self.start_import_process(files, move_source=move_source)

    def _on_import_finished(self, success_count, total, imported_uuids, error_msg, progress_dialog, skip_splitter=False):
        progress_dialog.close()

        if hasattr(self, 'import_worker') and self.import_worker:
            self.import_worker.wait() # Ensure finished
            self.import_worker.deleteLater()
            self.import_worker = None

        if error_msg:
             logger.info(f"[ERROR] Import Finished with error: {error_msg}")
             show_selectable_message_box(self, self.tr("Import Error"), error_msg, icon=QMessageBox.Icon.Critical)

        # Refresh List
        if self.list_widget:
            self.list_widget.refresh_list()

        if self.pipeline and imported_uuids:
             splitter_opened = False
             queued_count = 0

             for uid in imported_uuids:
                  d = self.db_manager.get_document_by_uuid(uid)

                  if d:
                      logger.info(f"[DEBUG] Import Finished: UUID={uid}, Pages={d.page_count}, Filename={d.original_filename}")
                      # Note: MainLoopWorker will pick this up via status 'NEW'
                      queued_count += 1
                  else:
                      logger.info(f"[DEBUG] Import Finished: UUID={uid} NOT FOUND in DB!")

                  if d and d.page_count and d.page_count > 1 and not skip_splitter:
                      if not splitter_opened:
                          self.open_splitter_dialog_slot(uid)
                          splitter_opened = True

             if not error_msg and not splitter_opened:
                  show_notification(self, self.tr("Import Finished"),
                                    self.tr(f"Imported {len(imported_uuids)} documents.\nBackground processing started."))

        if hasattr(self, "cockpit_widget"):
             self.cockpit_widget.refresh_stats()

        if hasattr(self, "filter_tree_widget"):
             self.filter_tree_widget.load_tree()


    def _on_ai_status_changed(self, msg: str) -> None:
        self.main_status_label.setText(self.tr("AI: %s") % msg)

    def export_documents_slot(self, uuids: list[str]):
        """Export selected documents via ListWidget dialog."""
        if not uuids or not self.list_widget:
            return

        docs = []
        for u in uuids:
            doc = self.db_manager.get_document_by_uuid(u)
            if doc:
                docs.append(doc)

        if docs:
            self.list_widget.open_export_dialog(docs)

    def export_visible_documents_slot(self):
        """Export all currently visible documents."""
        if not self.list_widget: return

        docs = self.list_widget.get_visible_documents()
        if not docs:
            show_notification(self, self.tr("Export"), self.tr("No documents visible to export."))
            return

        self.list_widget.open_export_dialog(docs)

    def stamp_document_slot(self, uuid_or_list):
        """Stamp a document (or multiple)."""
        if not self.pipeline:
            return

        if isinstance(uuid_or_list, list):
            uuids = uuid_or_list
        else:
            uuids = [uuid_or_list]

        if not uuids:
            return

        target_uuid = uuids[0]
        src_path = self.pipeline.vault.get_file_path(target_uuid)

        # Fallback for Virtual Entities
        if not src_path or not os.path.exists(src_path) or src_path == "/dev/null":
             if self.db_manager:
                 mapping = self.db_manager.get_source_mapping_from_entity(target_uuid)
                 if mapping and len(mapping) > 0:
                      phys_uuid = mapping[0].get("file_uuid")
                      if phys_uuid:
                          src_path = self.pipeline.vault.get_file_path(phys_uuid)

        if not src_path or not os.path.exists(src_path):
            show_selectable_message_box(self, self.tr("Error"), self.tr(f"Could not locate physical file for UUID: {target_uuid}"), icon=QMessageBox.Icon.Warning)
            return

        dialog = StamperDialog(self)

        stamper = DocumentStamper()
        existing_stamps = stamper.get_stamps(src_path)

        dialog.populate_stamps(existing_stamps)

        if dialog.exec():
            action, text, pos, color, rotation, remove_id = dialog.get_data()
            try:
                successful_count = 0

                if action == "remove":
                    if len(uuids) > 1:
                        show_selectable_message_box(self, self.tr("Batch Operation"), self.tr("Removing stamps is only supported for single documents."), icon=QMessageBox.Icon.Warning)
                        uuids = [target_uuid]

                    removed = stamper.remove_stamp(src_path, stamp_id=remove_id)
                    if removed:
                        successful_count = 1
                else:
                    # APPLY BATCH
                    for uid in uuids:
                        fpath = self.pipeline.vault.get_file_path(uid)

                        # Fallback for Virtual
                        if not fpath or not os.path.exists(fpath) or fpath == "/dev/null":
                             if self.db_manager:
                                 mapping = self.db_manager.get_source_mapping_from_entity(uid)
                                 if mapping and len(mapping) > 0:
                                      phys_uuid = mapping[0].get("file_uuid")
                                      if phys_uuid:
                                          fpath = self.pipeline.vault.get_file_path(phys_uuid)

                        if not fpath or not os.path.exists(fpath):
                            logger.info(f"[Stamper] Failed to resolve path for {uid}")
                            continue

                        base, ext = os.path.splitext(fpath)
                        tmp_path = f"{base}_stamped{ext}"

                        stamper.apply_stamp(fpath, tmp_path, text, position=pos, color=color, rotation=rotation)
                        shutil.move(tmp_path, fpath)
                        successful_count += 1

                msg = ""
                if action == "remove":
                     msg = self.tr("Stamp removed.")
                else:
                     msg = self.tr(f"Stamp applied to {successful_count} document(s).")

                show_notification(self, self.tr("Success"), msg)

                self.list_widget.document_selected.emit([target_uuid])

            except Exception as e:
                show_selectable_message_box(self, self.tr("Error"), self.tr(f"Stamping operation failed: {e}"), icon=QMessageBox.Icon.Critical)

    def manage_tags_slot(self, uuids: list[str]):
        """Open dialog to add/remove tags for selected documents."""
        if not uuids: return

        available_tags = []
        if self.db_manager:
            available_tags = list(self.db_manager.get_all_tags_with_counts().keys())

        common_tags = None
        if uuids:
             first_doc = self.db_manager.get_document_by_uuid(uuids[0])
             if first_doc:
                 # Phase 102/105: Use tags (User) separately from type_tags (System)
                 common_tags = set(first_doc.tags or [])

                 for i in range(1, len(uuids)):
                     doc = self.db_manager.get_document_by_uuid(uuids[i])
                     if doc:
                         doc_tags = set(doc.tags or [])
                         common_tags = common_tags.intersection(doc_tags)

        available_tags.sort(key=lambda x: x.lower())
        common_tags_list = sorted(list(common_tags), key=lambda x: x.lower()) if common_tags else []

        dialog = BatchTagDialog(available_tags, common_tags_list, self)
        if dialog.exec():
            add_tags, remove_tags = dialog.get_data()

            count = 0
            for uuid in uuids:
                doc = self.db_manager.get_document_by_uuid(uuid)
                if not doc: continue

                current_tags_list = doc.tags or []

                # Create new list
                new_tags = [t for t in current_tags_list]

                for t in add_tags:
                    if t not in new_tags:
                        new_tags.append(t)

                new_tags = [t for t in new_tags if t not in remove_tags]

                if new_tags != current_tags_list:
                    # Update DB using User tags
                    success = self.db_manager.update_document_metadata(uuid, {'tags': new_tags})
                    if success:
                        count += 1

            if count > 0:
                self.list_widget.refresh_list()
                show_notification(self, self.tr("Tags Updated"), self.tr(f"Updated tags for {count} documents."))

    def toggle_editor_visibility(self, checked: bool):
        """Toggle the visibility of the metadata editor widget."""
        if hasattr(self, 'editor_widget'):
            self.editor_widget.setVisible(checked)

    def update_status_bar(self, visible_count: int, total_count: int) -> None:
        """Update status bar with document counts."""
        self._visible_count = visible_count
        self._total_count = total_count
        self._refresh_status_bar()

        if visible_count == 0:
            if hasattr(self, 'pdf_viewer'):
                self.pdf_viewer.clear()
            self.pending_selection = []

        if visible_count > 0 and hasattr(self, 'pending_selection') and self.pending_selection:
             self.list_widget.select_rows_by_uuids(self.pending_selection)
             self.pending_selection = []

    def closeEvent(self, event: QCloseEvent):
        """Handle window close."""
        if hasattr(self, 'ai_worker') and self.ai_worker: self.ai_worker.stop()
        # Cancel background workers to kill subprocesses
        if hasattr(self, 'main_loop_worker') and self.main_loop_worker: self.main_loop_worker.stop()
        if hasattr(self, 'import_worker') and self.import_worker: self.import_worker.cancel()
        if hasattr(self, 'batch_worker') and self.batch_worker: self.batch_worker.cancel()
        if hasattr(self, 'reprocess_worker') and self.reprocess_worker: self.reprocess_worker.cancel()

        self.write_settings()
        self.save_filter_tree()
        super().closeEvent(event)

    def write_settings(self):
        settings = QSettings()
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("mainSplitter", self.main_splitter.saveState())
        settings.setValue("leftPaneSplitter", self.left_pane_splitter.saveState())

        if hasattr(self, 'list_widget') and hasattr(self.list_widget, 'save_state'):
            self.list_widget.save_state()

        if hasattr(self.list_widget, 'get_selected_uuids'):
             settings.setValue("selectedUUIDs", self.list_widget.get_selected_uuids())

        if hasattr(self, 'main_loop_worker'):
             settings.setValue("ai_paused", self.main_loop_worker.is_paused)

    def read_settings(self):
        settings = QSettings()
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        state = settings.value("windowState")
        if state:
            self.restoreState(state)

        main_splitter = settings.value("mainSplitter")
        if main_splitter:
            self.main_splitter.restoreState(main_splitter)

        # Restore AI Pause State
        try:
            ai_paused = str(settings.value("ai_paused", "false")).lower() == "true"
        except Exception:
            ai_paused = False
        if ai_paused and hasattr(self, 'main_loop_worker'):
            self.main_loop_worker.set_paused(True)
            self.activity_panel.on_pause_state_changed(True)

        left_splitter = settings.value("leftPaneSplitter")
        if left_splitter:
             self.left_pane_splitter.restoreState(left_splitter)

             sizes = self.left_pane_splitter.sizes()
             if len(sizes) >= 3 and sizes[2] < 50:
                 total = sum(sizes) if sum(sizes) > 0 else 700
                 self.left_pane_splitter.setSizes([70, int(total*0.6), int(total*0.3)])

        if hasattr(self, 'list_widget') and hasattr(self.list_widget, 'restore_state'):
            self.list_widget.restore_state()

        self.pending_selection = settings.value("selectedUUIDs", [])
        if not isinstance(self.pending_selection, list):
             self.pending_selection = []

    def save_static_list(self, name: str, uuids: list):
        """Save a static list of UUIDs as a filter."""
        if not self.filter_tree:
             return

        filter_data = {
            'operator': 'AND',
            'conditions': [
                {
                    'field': 'uuid',
                    'op': 'in',
                    'value': uuids
                }
            ]
        }

        self.filter_tree.add_filter(self.filter_tree.root, name, filter_data)
        self.save_filter_tree()
        self.advanced_filter.load_known_filters()

        self.main_status_label.setText(self.tr("List '%s' saved with %n item(s).", "", len(uuids)) % name)

    def set_trash_mode(self, enabled: bool):
        self.list_widget.show_trash_bin(enabled)
        if enabled:
            self.main_status_label.setText(self.tr("Viewing Trash Bin"))
        else:
            self.main_status_label.setText(self.tr("Ready"))

    def restore_documents_slot(self, uuids: list[str]):
        count = 0
        for uid in uuids:
            if self.db_manager.restore_document(uid):
                count += 1
        if count > 0:
            self.list_widget.refresh_list()
            show_notification(self, self.tr("Restored"), self.tr(f"Restored {count} document(s)."))

    def purge_data_slot(self):
        """
        Handle 'Purge All Data' request.
        """
        reply = show_selectable_message_box(self, self.tr("Confirm Global Purge"),
                                     self.tr("DANGER: This will delete ALL documents, files, and database entries.\n\n"
                                             "This action cannot be undone.\n\n"
                                             "Are you completely sure you want to reset the system?"),
                                     icon=QMessageBox.Icon.Critical,
                                     buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            config = AppConfig()
            vault_path = config.get_vault_path()

            success = self.db_manager.purge_all_data(vault_path)

            if success:
                self.list_widget.refresh_list()
                if hasattr(self, 'editor_widget'): self.editor_widget.clear()
                if hasattr(self, 'pdf_viewer'): self.pdf_viewer.clear()

                if hasattr(self, "cockpit_widget"):
                    self.cockpit_widget.refresh_stats()

                if hasattr(self, "filter_tree_widget"):
                    self.filter_tree_widget.load_tree()

                if hasattr(self, "filter_input"):
                    self.filter_input.clear()

                show_notification(self, self.tr("Success"), self.tr("System has been reset."))
            else:
                show_selectable_message_box(self, self.tr("Error"), self.tr("Failed to purge data. Check logs."), icon=QMessageBox.Icon.Warning)

    def purge_documents_slot(self, uuids: list[str]):
        count = 0
        for uid in uuids:
            if self.pipeline.delete_entity(uid):
                count += 1
        if count > 0:
            self.list_widget.refresh_list()
            show_notification(self, self.tr("Deleted"), self.tr(f"Permanently deleted {count} document(s)."))
    def open_debug_audit_window(self, uuid: str):
        """Opens the Audit Window in debug/generic mode with only a Close button."""
        from gui.audit_window import AuditWindow
        doc = self.db_manager.get_document_by_uuid(uuid)
        if not doc:
            return

        # Create a non-modal debug window
        win = AuditWindow(pipeline=self.pipeline)
        win.set_debug_mode(True)
        win.display_document(doc)
        
        # Ensure it stays alive while open
        if not hasattr(self, '_debug_windows'):
            self._debug_windows = []
        self._debug_windows.append(win)
        win.closed.connect(lambda: self._debug_windows.remove(win) if win in self._debug_windows else None)
        
        win.show()
        win.raise_()


    def navigate_to_list_filter(self, payload: dict):
        """Switch to Explorer View and apply filter."""

        # New payload can be just query (legacy) or dict with metadata
        if "query" in payload:
            filter_query = payload["query"]
        else:
            filter_query = payload

        self.central_stack.setCurrentIndex(1) # Explorer
        QCoreApplication.processEvents()

        q_str = json.dumps(filter_query, sort_keys=True)
        target_uuid = self._cockpit_selections.get("DASH:" + q_str)
        self.list_widget.target_uuid_to_restore = target_uuid
        self.list_widget.current_cockpit_query = filter_query

        # Phase 107: Breadcrumb Support for Cockpit
        # Phase 107: Breadcrumb Support for Cockpit
        label = payload.get("label") or payload.get("name")
        self.list_widget.view_context = label if label else "Cockpit View"
        
        # Phase 115: Pass select_query to list_widget
        self.list_widget.target_select_query = payload.get("select_query")

        if self.advanced_filter.chk_active.isChecked():
             self.advanced_filter.chk_active.setChecked(False)

        QTimer.singleShot(100, lambda: self._apply_navigation_filter(payload))

    def _save_current_selection_to_persistence(self, uuid: str):
        """Save selected UUID for the current active filter context."""
        try:
            if self.advanced_filter.chk_active.isChecked():
                query = self.advanced_filter.get_query_object()
                key = "RULE:" + json.dumps(query, sort_keys=True)
            else:
                query = self.list_widget.current_cockpit_query or {}
                key = "DASH:" + json.dumps(query, sort_keys=True)

            self._cockpit_selections[key] = uuid
        except:
            pass

    def _apply_navigation_filter(self, payload: dict):
        if self.advanced_filter:
            if "query" in payload:
                filter_query = payload["query"]
                filter_id = payload.get("filter_id")
                preset_id = payload.get("preset_id")
            else:
                filter_query = payload
                filter_id = None
                preset_id = None

            self.advanced_filter.blockSignals(True)
            self.advanced_filter.load_from_object(filter_query)

            # Sync the Combo Box if possible
            if filter_id:
                # Find the node in the tree and select it in combo
                node = self.filter_tree.find_node_by_id(filter_id)
                if node:
                    idx = self.advanced_filter.combo_filters.findData(node)
                    if idx >= 0:
                        self.advanced_filter.combo_filters.setCurrentIndex(idx)
                        self.advanced_filter.loaded_filter_node = node
            elif preset_id:
                # Handle preset selection (Inbox, Proccessed etc)
                # We need to find the itemData that matches the preset
                for i in range(self.advanced_filter.combo_filters.count()):
                    d = self.advanced_filter.combo_filters.itemData(i)
                    if isinstance(d, dict) and d.get("id") == preset_id:
                        self.advanced_filter.combo_filters.setCurrentIndex(i)
                        break

            self.advanced_filter.chk_active.setChecked(False)
            self.list_widget.advanced_filter_active = False
            self.advanced_filter.blockSignals(False)

            self.list_widget.refresh_list(force_select_first=True)
            self.list_widget.tree.setFocus()

    def open_splitter_dialog_slot(self, uuid: str):
        """Open Splitter Dialog for specific UUID."""
        if not uuid or not self.pipeline: return

        # Phase 9: Protection Check
        v_doc = self.pipeline.logical_repo.get_by_uuid(uuid)
        if v_doc and getattr(v_doc, 'is_immutable', False):
            show_selectable_message_box(self, self.tr("Document Protected"),
                                           self.tr("This document is a digital original and cannot be restructured."),
                                           icon=QMessageBox.Icon.Information)
            return

        dialog = SplitterDialog(self.pipeline, self)
        dialog.load_document(uuid)

        if dialog.exec():
             instructions = dialog.import_instructions
             if instructions is not None:
                  try:
                      if not instructions:
                          self.pipeline.delete_entity(uuid)
                          self.main_status_label.setText(self.tr("Document deleted (empty structure)."))
                      else:
                          new_uuids = self.pipeline.apply_restructure_instructions(uuid, instructions)
                          self.main_status_label.setText(self.tr("Document updated (%n part(s)).", "", len(new_uuids)))

                      self.list_widget.refresh_list()
                      if hasattr(self, 'pdf_viewer'): self.pdf_viewer.clear()
                      if hasattr(self, 'editor_widget'): self.editor_widget.clear()

                      if hasattr(self, "cockpit_widget"):
                          self.cockpit_widget.refresh_stats()

                  except Exception as e:
                       import traceback
                       logger.info(f"[ERROR] Failed to apply structural changes: {e}")
                       traceback.print_exc()
                       show_selectable_message_box(self, self.tr("Error"), f"Failed to apply structural changes: {e}", icon=QMessageBox.Icon.Critical)

    def go_home_slot(self):
        """Switch to Cockpit."""
        self.central_stack.setCurrentIndex(0)
        if hasattr(self, "cockpit_widget") and self.cockpit_widget:
            self.cockpit_widget.refresh_stats()

    def create_tool_bar(self):
        self.navbar = QToolBar("Navigation")
        self.navbar.setIconSize(QSize(20, 20))
        self.navbar.setMovable(False)
        self.navbar.setStyleSheet("""
            QToolBar {
                background-color: #f5f5f5;
                border-bottom: 1px solid #ddd;
                padding-top: 12px;
                spacing: 2px;
            }
            QToolButton {
                padding: 6px 15px;
                border: 1px solid transparent;
                border-bottom: 3px solid transparent;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 500;
                font-size: 14px; /* Enforce same height as sub-modes */
                color: #666;
            }
            QToolButton:hover {
                background-color: #eee;
            }
            /* Tab Container Styling */
            QWidget#tabContainer {
                background-color: transparent;
                border: 1px solid transparent;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-bottom: -1px;
                margin-top: 10px; /* Explicit spacing to the menu bar */
                min-height: 35px; /* Hard anchor for vertical height stability */
            }
            QWidget#tabContainer[active="true"] {
                background-color: #ffffff;
                border-color: #ddd;
                border-bottom: 1px solid #ffffff;
            }
            QWidget#tabContainer[active="true"] QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                color: #1976d2; /* Blue accent for active tab */
                font-weight: bold;
            }
            /* Visual underline for active tab */
            QWidget#tabContainer[active="true"]::after {
                /* Note: QWidget doesn't support ::after, using border-top instead or just the button underline */
            }
            
            /* Underline for the main tab button when active */
            QToolButton#mainTabBtn[active="true"] {
                border-bottom: 3px solid #1976d2;
                color: #1976d2;
            }

            /* Filter Button specific styling */
            QWidget#tabContainer QToolButton#filterBtn {
                margin: 0px 6px;
                padding: 4px 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #f8f8f8;
                font-size: 13px;
                color: #333;
            }
            QWidget#tabContainer QToolButton#filterBtn:hover {
                background-color: #efefef;
                border-color: #bbb;
            }
            QWidget#tabContainer QToolButton#filterBtn:checked {
                background-color: #e3f2fd;
                border: 1px solid #2196f3;
                color: #1976d2;
                font-weight: bold;
            }
            /* Sub-mode buttons */
            QWidget#tabContainer QToolButton#subModeBtn {
                background: transparent;
                border: none;
                border-bottom: 3px solid transparent;
                border-radius: 0px;
                padding: 6px 15px;
                color: #888;
                font-size: 14px;
            }
            QWidget#tabContainer QToolButton#subModeBtn:hover {
                background-color: #f1f7fd;
                color: #1976d2;
            }
            QWidget#tabContainer QToolButton#subModeBtn:checked {
                color: #1976d2;
                border-bottom: 3px solid #1976d2;
                background-color: #f0f7ff;
                font-weight: bold;
            }
        """)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.navbar)

        # Tab: Cockpit
        self.cockpit_nav_container = QWidget()
        self.cockpit_nav_container.setObjectName("tabContainer")
        cockpit_nav_layout = QHBoxLayout(self.cockpit_nav_container)
        cockpit_nav_layout.setContentsMargins(0, 0, 0, 0)
        cockpit_nav_layout.setSpacing(0)
        cockpit_nav_layout.setAlignment(Qt.AlignmentFlag.AlignBottom) # Consistent bottom alignment
        
        self.btn_cockpit = QToolButton()
        self.btn_cockpit.setObjectName("mainTabBtn")
        self.btn_cockpit.setCheckable(True)
        self.btn_cockpit.setText(self.tr("Cockpit"))
        self.btn_cockpit.setToolTip(self.tr("Main overview and statistics"))
        self.btn_cockpit.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_cockpit.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        self.btn_cockpit.clicked.connect(self.go_home_slot)
        cockpit_nav_layout.addWidget(self.btn_cockpit)
        self.navbar.addWidget(self.cockpit_nav_container)

        # Tab Area: Documents
        self.doc_container = QWidget()
        self.doc_container.setObjectName("tabContainer")
        doc_layout = QHBoxLayout(self.doc_container)
        doc_layout.setContentsMargins(0, 0, 0, 0)
        doc_layout.setSpacing(0)
        doc_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        
        self.btn_documents = QToolButton()
        self.btn_documents.setObjectName("mainTabBtn")
        self.btn_documents.setCheckable(True)
        self.btn_documents.setText(self.tr("Documents"))
        self.btn_documents.setToolTip(self.tr("Browse and manage document list"))
        self.btn_documents.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_documents.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon))
        self.btn_documents.clicked.connect(lambda: self.central_stack.setCurrentIndex(1))
        doc_layout.addWidget(self.btn_documents)

        self.navbar.addWidget(self.doc_container)
        
        # Tab Area: Workflows
        self.wf_container = QWidget()
        self.wf_container.setObjectName("tabContainer")
        wf_layout = QHBoxLayout(self.wf_container)
        wf_layout.setContentsMargins(0, 0, 0, 0)
        wf_layout.setSpacing(0)
        wf_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        
        self.btn_workflows = QToolButton()
        self.btn_workflows.setObjectName("mainTabBtn")
        self.btn_workflows.setCheckable(True)
        self.btn_workflows.setText("🤖 " + self.tr("Workflows"))
        self.btn_workflows.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_workflows.setIcon(QIcon()) # Remove the arrow icon
        self.btn_workflows.clicked.connect(lambda: self.central_stack.setCurrentIndex(2))
        wf_layout.addWidget(self.btn_workflows)
        self.navbar.addWidget(self.wf_container)

        # Tab Area: Reporting
        self.report_container = QWidget()
        self.report_container.setObjectName("tabContainer")
        report_layout = QHBoxLayout(self.report_container)
        report_layout.setContentsMargins(0, 0, 0, 0)
        report_layout.setSpacing(0)
        report_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        
        self.btn_reports = QToolButton()
        self.btn_reports.setObjectName("mainTabBtn")
        self.btn_reports.setCheckable(True)
        self.btn_reports.setText(self.tr("Reports"))
        self.btn_reports.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_reports.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogDetailedView))
        self.btn_reports.clicked.connect(lambda: self.central_stack.setCurrentIndex(3))
        report_layout.addWidget(self.btn_reports)
        self.navbar.addWidget(self.report_container)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.navbar.addWidget(spacer)

    def _on_tab_changed(self, index):
        """Update navigation UI when stack changes."""
        is_cockpit = (index == 0)
        is_explorer = (index == 1)
        is_workflow = (index == 2)
        is_reporting = (index == 3)
        
        # Update Tab Highlighting
        self.cockpit_nav_container.setProperty("active", is_cockpit)
        self.doc_container.setProperty("active", is_explorer)
        self.wf_container.setProperty("active", is_workflow)
        self.report_container.setProperty("active", is_reporting)
        
        # Force Style Refresh
        for btn in [self.btn_cockpit, self.btn_documents, self.btn_reports, self.btn_workflows]:
            btn.setProperty("active", False)
            if (is_cockpit and btn == self.btn_cockpit) or \
               (is_explorer and btn == self.btn_documents) or \
               (is_reporting and btn == self.btn_reports) or \
               (is_workflow and btn == self.btn_workflows):
                btn.setProperty("active", True)
            
        for container in [self.cockpit_nav_container, self.doc_container, self.report_container, self.wf_container]:
            container.style().unpolish(container)
            container.style().polish(container)

        self.btn_cockpit.setChecked(is_cockpit)
        self.btn_documents.setChecked(is_explorer)
        self.btn_reports.setChecked(is_reporting)
        self.btn_workflows.setChecked(is_workflow)
        
        # Sub-mode visibility is now handled internally in Documents and Workflows
        
        # Refresh Data for specific tabs
        if is_cockpit:
            self.cockpit_widget.refresh_stats()
        elif is_reporting:
            self.reporting_widget.refresh_data()
        elif is_workflow:
            self.workflow_manager.load_workflows()
        if index == 1 and hasattr(self, 'list_widget'):
            if self._last_selected_uuid:
                self.list_widget.target_uuid_to_restore = self._last_selected_uuid
            self.list_widget.refresh_list(force_select_first=True)

        for container in [self.cockpit_nav_container, self.doc_container, self.report_container, self.wf_container]:
            container.style().unpolish(container)
            container.style().polish(container)
            # Ensure children are also refreshed specifically for text colors
            for child in container.findChildren(QToolButton):
                child.style().unpolish(child)
                child.style().polish(child)

    def _toggle_filter_view(self, checked):
        """Toggle visibility of the unified filter console."""
        if hasattr(self, "advanced_filter"):
            self.advanced_filter.setVisible(checked)
            if hasattr(self, "action_toggle_filter"):
                self.action_toggle_filter.setChecked(checked)

    def open_tag_manager_slot(self):
        """Open the Tag Manager dialog."""
        dlg = TagManagerDialog(self.db_manager, parent=self)
        dlg.exec()
        self.list_widget.refresh_list()

    def _on_view_filter_changed(self, filter_data):
        """Called when a Saved View loads a filter."""
        if self.advanced_filter:
            self.advanced_filter.load_from_object(filter_data)
            self.advanced_filter.apply_advanced_filter()

    def _on_fatal_pipeline_error(self, title, message):
        """Called when a background worker hits a logic error."""
        show_selectable_message_box(self, title, message, icon=QMessageBox.Icon.Critical)
        self.main_status_label.setText(self.tr("Pipeline STOPPED due to fatal error."))
