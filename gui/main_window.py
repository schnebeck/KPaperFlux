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
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
    QMessageBox, QSplitter, QCheckBox, QDialog, QDialogButtonBox, QStatusBar,
    QStackedWidget, QProgressDialog,
)
from PyQt6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QSettings, QCoreApplication, QTimer, PYQT_VERSION_STR
import PyQt6
import platform
import os
import sys
import tempfile
import json
from core.logger import get_logger, get_silent_logger
from PyQt6.QtCore import QEvent

logger = get_logger("gui.main_window")
import fitz
from pathlib import Path

# Core Imports
from gui.utils import show_selectable_message_box
from core.importer import PreFlightImporter
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from core.filter_tree import FilterTree, NodeType
from core.config import AppConfig
from core.integrity import IntegrityManager
from core.exchange import ExchangeService, ExchangePayload
# GUI Imports
from gui.workers import MainLoopWorker, SimilarityWorker
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
from gui.reporting import ReportingWidget
from gui.audit_window import AuditWindow
from gui.main_menu import MainWindowMenuMixin
from core.plugins.manager import PluginManager
from core.plugins.base import ApiContext

class MergeConfirmDialog(QDialog):
    def __init__(self, count, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Confirm Merge"))
        layout = QVBoxLayout(self)

        label = QLabel(self.tr("Merge %s documents into a new combined entry?") % count)
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

class MainWindow(MainWindowMenuMixin, QMainWindow):
    """
    Main application window for KPaperFlux.
    """
    def __init__(self,
                 pipeline: Optional[PipelineProcessor] = None,
                 db_manager: Optional[DatabaseManager] = None,
                 app_config: Optional[AppConfig] = None) -> None:
        super().__init__()
        self._translators: list[PyQt6.QtCore.QTranslator] = []
        self.pipeline = pipeline
        self.db_manager = db_manager
        self.app_config = app_config or AppConfig()

        lang = self.app_config.get_language()
        logger.debug(f"[MainWindow] Initial language from config: '{lang}' (File: {self.app_config.settings.fileName()})")
        self._switch_language(lang, refresh_ui=False)

        if self.pipeline and not self.db_manager:
            self.db_manager = self.pipeline.db

        self._last_selected_uuid = None
        self.current_search_text = ""
        self._visible_count = 0
        self._total_count = 0
        self._selected_sum = 0.0
        self.pending_selection = []
        self._cockpit_selections: dict = {}
        self.filter_config_path = self.app_config.get_config_dir() / "filter_tree.json"

        self.setWindowTitle(self.tr("KPaperFlux"))
        self.setWindowIcon(QIcon("resources/icon.png"))
        self.resize(1000, 700)
        self.setAcceptDrops(True)

        self._setup_plugins()
        self.create_menu_bar()

        self.filter_tree = FilterTree(self.db_manager)
        self.load_filter_tree()

        self._setup_pages()
        self._setup_explorer_pane()
        self._setup_status_bar()
        self._setup_doc_controller()
        self._setup_debug_controller()

        self.create_tool_bar()
        self.retranslate_ui()
        self.setup_shortcuts()
        self.read_settings()

        self._on_tab_changed(0)

        if self.db_manager and hasattr(self, "list_widget") and isinstance(self.list_widget, DocumentListWidget):
            self.list_widget.refresh_list()

        if self.db_manager:
            QTimer.singleShot(0, self._sweep_stale_workflow_states)

    # ── Setup helpers (called once from __init__) ─────────────────────────────

    def _setup_plugins(self) -> None:
        """Discover and initialise the plugin system."""
        plugin_dirs = [str(self.app_config.get_plugins_dir())]
        local_plugins = Path(__file__).resolve().parent.parent / "plugins"
        if local_plugins.exists():
            plugin_dirs.append(str(local_plugins))

        self.plugin_api = ApiContext(
            db=self.db_manager,
            vault=getattr(self.pipeline, "vault", None) if self.pipeline else None,
            config=self.app_config,
            main_window=self,
        )
        self.plugin_manager = PluginManager(plugin_dirs=plugin_dirs, api_context=self.plugin_api)
        self.plugin_manager.discover_plugins()

    def _setup_pages(self) -> None:
        """Build the central QStackedWidget with all top-level pages."""
        self.central_stack = QStackedWidget()
        self.setCentralWidget(self.central_stack)

        # Page 0: Cockpit
        self.cockpit_widget = CockpitWidget(self.db_manager, filter_tree=self.filter_tree, app_config=self.app_config)
        self.cockpit_widget.navigation_requested.connect(self.navigate_to_list_filter)
        self.central_stack.addWidget(self.cockpit_widget)

        # Page 1: Explorer (hosts the main_splitter)
        self.explorer_widget = QWidget()
        explorer_layout = QVBoxLayout(self.explorer_widget)
        explorer_layout.setContentsMargins(0, 0, 0, 0)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        explorer_layout.addWidget(self.main_splitter)
        self.central_stack.addWidget(self.explorer_widget)

        # Page 2: Workflow rules editor + dashboard
        self.workflow_manager = WorkflowManagerWidget(
            filter_tree=self.filter_tree,
            pipeline=self.pipeline,
        )
        self.workflow_manager.navigation_requested.connect(self.navigate_to_list_filter)
        self.central_stack.addWidget(self.workflow_manager)

        # Page 3: Reporting
        self.reporting_widget = ReportingWidget(self.db_manager, filter_tree=self.filter_tree)
        self.reporting_widget.filter_requested.connect(self.navigate_to_list_filter)
        self.central_stack.addWidget(self.reporting_widget)

        self.central_stack.setCurrentIndex(0)
        self.central_stack.currentChanged.connect(self._on_tab_changed)

    def _setup_explorer_pane(self) -> None:
        """Build left pane (filter | list | editor) and right pane (viewer)."""
        self.left_pane_splitter = QSplitter(Qt.Orientation.Vertical)

        self.advanced_filter = AdvancedFilterWidget(
            db_manager=self.db_manager,
            filter_tree=self.filter_tree,
            save_callback=self.save_filter_tree,
        )
        self.left_pane_splitter.addWidget(self.advanced_filter)

        if self.db_manager:
            self._setup_list_and_editor()

        self.main_splitter.addWidget(self.left_pane_splitter)

        # Right pane: PDF viewer
        self.pdf_viewer = PdfViewerWidget(self.pipeline)
        self.pdf_viewer.stamp_requested.connect(self.stamp_document_slot)
        self.pdf_viewer.tags_update_requested.connect(self.manage_tags_slot)
        self.pdf_viewer.export_requested.connect(self.export_documents_slot)
        self.pdf_viewer.reprocess_requested.connect(self.reprocess_document_slot)
        self.pdf_viewer.delete_requested.connect(self.delete_document_slot)
        if hasattr(self, "list_widget"):
            self.pdf_viewer.document_changed.connect(self.list_widget.refresh_list)
        self.pdf_viewer.split_requested.connect(self.open_splitter_dialog_slot)
        self.pdf_viewer.canvas.hit_overflow.connect(self._on_pdf_hit_overflow)
        self.pdf_viewer.canvas.hits_updated.connect(self._on_pdf_hits_updated)
        self.main_splitter.addWidget(self.pdf_viewer)

        self.left_pane_splitter.setSizes([70, 420, 210])
        self.left_pane_splitter.setCollapsible(0, False)
        self.main_splitter.setSizes([400, 600])
        self.main_splitter.setCollapsible(1, True)
        self.main_splitter.setHandleWidth(4)

    def _setup_list_and_editor(self) -> None:
        """Build DocumentListWidget, MetadataEditorWidget and wire their signals."""
        self.list_widget = DocumentListWidget(
            self.db_manager, filter_tree=self.filter_tree, plugin_manager=self.plugin_manager
        )
        self.list_widget.document_selected.connect(self._on_document_selected)
        self.list_widget.delete_requested.connect(self.delete_document_slot)
        self.list_widget.reprocess_requested.connect(self.reprocess_document_slot)
        self.list_widget.re_ocr_requested.connect(lambda uuids: self.reprocess_document_slot(uuids, force_ocr=True))
        self.list_widget.merge_requested.connect(self.merge_documents_slot)
        self.list_widget.stamp_requested.connect(self.stamp_document_slot)
        self.list_widget.tags_update_requested.connect(self.manage_tags_slot)
        self.list_widget.edit_requested.connect(self.open_splitter_dialog_slot)
        self.list_widget.document_count_changed.connect(self.update_status_bar)
        self.list_widget.save_list_requested.connect(self.save_static_list)
        self.list_widget.apply_rule_requested.connect(self._on_rule_apply_requested)
        self.list_widget.restore_requested.connect(self.restore_documents_slot)
        self.list_widget.archive_requested.connect(self.archive_document_slot)
        self.list_widget.purge_requested.connect(self.purge_documents_slot)
        self.list_widget.stage2_requested.connect(self.run_stage_2_selected_slot)
        self.list_widget.active_filter_changed.connect(self._on_view_filter_changed)
        self.list_widget.show_generic_requested.connect(self.open_debug_audit_window)
        self.list_widget.search_cleared.connect(self._on_search_cleared)

        self.advanced_filter.filter_changed.connect(self._on_filter_changed)
        self.advanced_filter.filter_changed.connect(self.list_widget.apply_advanced_filter)
        self.advanced_filter.search_triggered.connect(self._on_global_search_triggered)
        self.advanced_filter.prev_hit_requested.connect(lambda: self.pdf_viewer.canvas.prev_hit())
        self.advanced_filter.next_hit_requested.connect(lambda: self.pdf_viewer.canvas.next_hit())
        self.advanced_filter.trash_mode_changed.connect(self.set_trash_mode)
        self.advanced_filter.archive_mode_changed.connect(self.set_archive_mode)
        self.advanced_filter.filter_active_changed.connect(self.list_widget.set_advanced_filter_active)
        self.advanced_filter.size_changed.connect(self.left_pane_splitter.updateGeometry)
        self.advanced_filter.request_apply_rule.connect(self._on_rule_apply_requested)
        self.list_widget.advanced_filter_active = self.advanced_filter.chk_active.isChecked()

        self.left_pane_splitter.addWidget(self.list_widget)
        self.left_pane_splitter.setStretchFactor(0, 0)
        self.left_pane_splitter.setStretchFactor(1, 1)

        self.editor_widget = MetadataEditorWidget(self.db_manager, pipeline=self.pipeline)
        self.editor_widget.metadata_saved.connect(self.list_widget.refresh_list)
        self.editor_widget.metadata_saved.connect(self.cockpit_widget.refresh_stats)
        self.editor_widget.metadata_saved.connect(self.advanced_filter.refresh_dynamic_data)
        self.editor_widget.open_workflow_process.connect(self._navigate_to_workflow_process)
        self.left_pane_splitter.addWidget(self.editor_widget)
        self.editor_widget.setVisible(False)

        self.left_pane_splitter.setStretchFactor(0, 0)
        self.left_pane_splitter.setStretchFactor(1, 1)
        self.left_pane_splitter.setStretchFactor(2, 0)

    def _setup_status_bar(self) -> None:
        """Build the status bar with activity panel and label widgets."""
        self.setStatusBar(QStatusBar())

        self.status_container = QWidget()
        self.status_layout = QHBoxLayout(self.status_container)
        self.status_layout.setContentsMargins(5, 0, 5, 0)
        self.status_layout.setSpacing(10)

        self.activity_panel = BackgroundActivityStatusBar()
        self.status_layout.addWidget(self.activity_panel)

        self.main_status_label = QLabel(self.tr("Ready"))
        self.status_layout.addWidget(self.main_status_label)
        self.status_layout.addStretch(1)

        self.sum_status_label = QLabel("")
        self.sum_status_label.setObjectName("SumStatusLabel")
        self.sum_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sum_status_label.setStyleSheet("""
            #SumStatusLabel {
                color: #1976d2;
                font-weight: bold;
                font-size: 13px;
                min-width: 120px;
            }
        """)
        self.sum_status_label.hide()
        self.status_layout.addWidget(self.sum_status_label)
        self.status_layout.addStretch(1)

        self.statusBar().addWidget(self.status_container, 1)
        self.workflow_manager.status_message.connect(self.main_status_label.setText)

    def _setup_doc_controller(self) -> None:
        """Instantiate DocumentActionController and wire all its signals."""
        from gui.controllers.document_action_controller import DocumentActionController

        self.doc_controller = DocumentActionController(self, self.pipeline, self.db_manager)

        self.doc_controller.list_refresh_requested.connect(
            self.list_widget.refresh_list if hasattr(self, "list_widget") else lambda: None
        )
        self.doc_controller.stats_refresh_requested.connect(self.cockpit_widget.refresh_stats)
        self.doc_controller.status_updated.connect(self.main_status_label.setText)
        self.doc_controller.editor_reload_requested.connect(self._on_editor_reload)
        self.doc_controller.editor_clear_requested.connect(
            self.editor_widget.clear if hasattr(self, "editor_widget") else lambda: None
        )
        self.doc_controller.viewer_clear_requested.connect(self.pdf_viewer.clear)
        self.doc_controller.list_select_requested.connect(
            self.list_widget.select_document if hasattr(self, "list_widget") else lambda u: None
        )
        self.doc_controller.document_reselect_requested.connect(
            lambda u: self.list_widget.document_selected.emit([u])
            if hasattr(self, "list_widget") else None
        )
        self.doc_controller.splitter_dialog_requested.connect(self.open_splitter_dialog_slot)

        # Keep controller in sync with trash-mode toggling
        if hasattr(self, "advanced_filter"):
            self.advanced_filter.trash_mode_changed.connect(self.doc_controller.set_trash_mode)

    def _on_editor_reload(self, processed_uuids: list) -> None:
        """Reload editor if any of the processed docs are currently shown."""
        if not hasattr(self, "editor_widget") or not self.editor_widget or not self.db_manager:
            return
        if not self.editor_widget.isVisible():
            return
        intersect = set(processed_uuids) & set(self.editor_widget.current_uuids)
        if intersect:
            docs = [
                self.db_manager.get_document_by_uuid(u)
                for u in self.editor_widget.current_uuids
            ]
            docs = [d for d in docs if d]
            if docs:
                self.editor_widget.display_documents(docs)

    def _setup_debug_controller(self) -> None:
        """Instantiate DebugController and wire its signals."""
        from gui.controllers.debug_controller import DebugController

        self.debug_controller = DebugController(self, self.pipeline, self.db_manager)
        self.debug_controller.list_refresh_requested.connect(
            self.list_widget.refresh_list if hasattr(self, "list_widget") else lambda: None
        )

    def _sweep_stale_workflow_states(self) -> None:
        """Background sweep: reset stale workflow states across all rules."""
        from core.workflow import WorkflowRuleRegistry, sanitize_documents_for_rule
        registry = WorkflowRuleRegistry()
        total = 0
        for rule in registry.list_rules():
            count, _ = sanitize_documents_for_rule(self.db_manager, rule, stale_only=True)
            total += count
        if total:
            logger.info(f"Startup sweep: reset {total} document(s) with stale workflow states.")
            if hasattr(self, "list_widget"):
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
             self._init_main_loop_worker()

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
        if hasattr(self, 'list_widget'):
            self.list_widget.current_filter_text = search_text
            self.list_widget.view_context = "Search"
            self.list_widget.refresh_list(force_select_first=True)
        
        if hasattr(self, 'pdf_viewer') and self.pdf_viewer.current_uuid:
            self._sync_global_search_context(self.pdf_viewer.current_uuid)
            self.pdf_viewer.set_highlight_text(search_text)
        elif hasattr(self, 'pdf_viewer'):
            self.pdf_viewer.set_highlight_text(search_text)

    def _sync_global_search_context(self, current_uuid: str):
        """Calculates global hit offset and total for the PDF viewer."""
        if not hasattr(self, 'pdf_viewer') or not self.current_search_text or not self.list_widget:
            if hasattr(self, 'pdf_viewer'):
                self.pdf_viewer.global_search_total = 0
                self.pdf_viewer.global_search_offset = 0
            return

        uuids_in_view = self.list_widget.get_all_uuids_in_view()
        hit_map = self.list_widget.current_hit_map
        
        total_hits = sum(hit_map.values())
        offset = 0
        for u in uuids_in_view:
            if u == current_uuid:
                break
            offset += hit_map.get(u, 0)
        
        self.pdf_viewer.global_search_total = total_hits
        self.pdf_viewer.global_search_offset = offset
    def _on_search_cleared(self):
        """Resets all search-related state when 'Show All' is clicked."""
        self.current_search_text = ""
        if hasattr(self, 'advanced_filter'):
            self.advanced_filter.clear_search()
            self.advanced_filter.set_active(False) # [NEW] Sync reset
        if hasattr(self, "pdf_viewer"):
            self.pdf_viewer.set_highlight_text("")
            self.pdf_viewer.global_search_total = 0
            self.pdf_viewer.global_search_offset = 0

    def _on_pdf_hits_updated(self, current: int, total: int):
        """Routes hit updates from viewer to sidebar with global context."""
        if not hasattr(self, 'advanced_filter'):
            return
            
        # Use global totals if session-wide search is active
        if self.pdf_viewer.global_search_total > 0:
            display_total = self.pdf_viewer.global_search_total
            display_current = current + self.pdf_viewer.global_search_offset
        else:
            display_total = total
            display_current = current
            
        self.advanced_filter.update_hit_status(display_current, display_total)

    def _on_pdf_hit_overflow(self, forward: bool):
        """Logic to switch to next/prev document containing search hits."""
        if not self.current_search_text or not self.list_widget:
            return
            
        current_uuid = self.pdf_viewer.current_uuid
        if not current_uuid:
            return
            
        uuids = self.list_widget.get_all_uuids_in_view()
        if not uuids:
            return
            
        try:
            current_idx = uuids.index(current_uuid)
        except ValueError:
            return
            
        # Search range (excluding current)
        if forward:
            indices = range(current_idx + 1, len(uuids))
        else:
            indices = range(current_idx - 1, -1, -1)
            
        target_uuid = None
        for i in indices:
            uid = uuids[i]
            # Check hit map from list widget
            if self.list_widget.current_hit_map.get(uid, 0) > 0:
                target_uuid = uid
                break
                
        if target_uuid:
            logger.info(f"[Search] Navigating to next doc with hits: {target_uuid}")
            self.list_widget.select_rows_by_uuids([target_uuid])
            # Give UI time to load document, then trigger search jump
            jump_first = True if forward else False
            jump_last = not forward
            QTimer.singleShot(400, lambda: self.pdf_viewer.canvas.perform_text_search(
                self.current_search_text, 
                jump_to_first=jump_first,
                jump_to_last=jump_last
            ))

    def load_filter_tree(self):
        """Load Filter Tree using ExchangeService, with fallback to starter kit."""
        if self.filter_config_path.exists():
            logger.debug(f"Loading Filter Tree from: {self.filter_config_path}")
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
                            logger.error(f"Found exchange payload in filter tree, but type is {payload.type}")
                    except Exception:
                        # Fallback for transient period/starter: Load raw JSON
                        data = json.loads(content)
                        self.filter_tree.load(data)
                logger.debug(f"Loaded {len(self.filter_tree.root.children)} root items.")
            except Exception as e:
                logger.error(f"Error loading filter tree: {e}")
        else:
            starter_path = Path(__file__).resolve().parent.parent / "resources" / "filter_tree_starter.json"
            if starter_path.exists():
                logger.debug(f"Initializing with Starter Kit: {starter_path}")
                try:
                    with open(starter_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.filter_tree.load(data)
                except Exception as e:
                    logger.error(f"Error loading starter kit: {e}")

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
            logger.debug(f"Saving Filter Tree to: {self.filter_config_path}")
            # Save the full tree data (including favorites)
            tree_data = json.loads(self.filter_tree.to_json())
            ExchangeService.save_to_file("filter_tree", tree_data, str(self.filter_config_path))
            logger.debug("Filter Tree saved successfully.")
        except Exception as e:
             logger.error(f"Error saving filter tree: {e}")


    # --- Debug Handlers (delegate to DebugController) ---

    def _debug_show_orphans_slot(self) -> None:
        self.debug_controller.show_orphans()

    def _debug_show_broken_slot(self) -> None:
        self.debug_controller.show_broken()

    def _debug_prune_orphans_slot(self) -> None:
        self.debug_controller.prune_orphans()

    def _debug_prune_broken_slot(self) -> None:
        self.debug_controller.prune_broken()

    def _debug_deduplicate_vault_slot(self) -> None:
        self.debug_controller.deduplicate_vault()

    def _debug_prune_orphan_workflows_slot(self) -> None:
        self.debug_controller.prune_orphan_workflows()

    def _on_filter_changed(self, criteria: dict):
        """Update local state when filter changes."""
        # Check for explicit meta-key first (added by AdvancedFilter)
        text = criteria.get('_meta_fulltext')
        if text is None:
             text = criteria.get('fulltext', '')

        self.current_search_text = text
        
        if hasattr(self, 'pdf_viewer'):
            self.pdf_viewer.set_highlight_text(text)
            
        logger.debug(f"MainWindow updated current_search_text to: '{self.current_search_text}'")

    def _on_pipeline_documents_processed(self):
        """Unified handler for background pipeline completions."""
        if hasattr(self, 'list_widget'):
            self.list_widget.refresh_list()
        
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
            
    def _refresh_status_bar(self):
        """Unified status bar text update."""
        status_text = self.tr("Docs: %s/%s") % (self._visible_count, self._total_count)
        self.main_status_label.setText(status_text)
        
        if self._selected_sum > 0:
            # Display sum in the dedicated centered label with localized prefix
            label_text = self.tr("Selection Gross (total): %s EUR") % f"{self._selected_sum:,.2f}"
            self.sum_status_label.setText(label_text)
            self.sum_status_label.show()
        else:
            self.sum_status_label.hide()

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

        # Sync Search Context (offsets for global navigation)
        self._sync_global_search_context(uuid)

        # Update Status Bar with Sum (Phase 4) - Always update on selection!
        total_sum = 0.0
        for d in docs:
            if d.total_gross:
                total_sum += float(d.total_gross or 0)
        
        self._selected_sum = total_sum
        self._refresh_status_bar()

        # Check for Search Hits for Deferred Navigation (Jumping to relevant page)
        target_index = -1
        if self.current_search_text and self.db_manager:
            hits = self.db_manager.find_text_pages_in_document(uuid, self.current_search_text)
            if hits:
                target_index = hits[0] # 0-based
                logger.info(f"[Search-Hit-Debug] Term: '{self.current_search_text}', UUID: '{uuid}', Found on Pages: {hits} -> Jumping to {target_index}")

        # Update Info Panel
        if hasattr(self, 'info_panel') and self.info_panel:
            self.info_panel.load_document(primary_doc)

        # Update Editor (Batch aware)
        if hasattr(self, 'editor_widget'):
            self.editor_widget.setVisible(True)
            self.editor_widget.display_documents(docs)

            # Robust Status Sync (Case Insensitive)
            stat = (primary_doc.status or "NEW").upper()
            idx = self.editor_widget.status_combo.findText(stat)
            if idx >= 0:
                self.editor_widget.status_combo.setCurrentIndex(idx)
            else:
                self.editor_widget.status_combo.setCurrentText(stat)
            self.editor_widget.export_filename_edit.setText(primary_doc.original_filename or "")

        main_sizes = self.main_splitter.sizes()
        if main_sizes and len(main_sizes) > 1 and main_sizes[1] == 0:
            total = sum(main_sizes)
            self.main_splitter.setSizes([int(total*0.4), int(total*0.6)])

        sizes = self.left_pane_splitter.sizes()
        if sizes and len(sizes) > 2 and sizes[2] == 0:
            total = sum(sizes)
            self.left_pane_splitter.setSizes([sizes[0], int(total*0.6), int(total*0.4)])

        # Update PDF Viewer - CONSOLIDATED SINGLE LOAD CALL
        if hasattr(self, 'pdf_viewer'):
            if not self.pdf_viewer.isVisible():
                self.pdf_viewer.setVisible(True)

            # Load via UUID (PdfViewer handles resolution and stitching internally)
            self.pdf_viewer.load_document(uuid, uuid=uuid, jump_to_index=target_index)
            
            # Apply current global search highlight if any
            if self.current_search_text:
                self.pdf_viewer.set_highlight_text(self.current_search_text)

    def delete_selected_slot(self):
        """Handle deletion via Menu Hack."""
        if hasattr(self, 'list_widget'):
            uuids = self.list_widget.get_selected_uuids()
            if uuids:
                self.delete_document_slot(uuids)
            else:
                show_selectable_message_box(self, self.tr("Info"), self.tr("Please select documents to delete."), icon=QMessageBox.Icon.Information)

    def delete_document_slot(self, uuids):
        """Handle delete request — delegates to DocumentActionController."""
        if not isinstance(uuids, list):
            uuids = [uuids]
        self.doc_controller.delete_documents(uuids)

    def reprocess_document_slot(self, uuids: list, force_ocr: bool = False):
        """Re-run pipeline — delegates to DocumentActionController."""
        self.doc_controller.reprocess_documents(uuids, force_ocr=force_ocr)

    def start_import_process(self, files: list[str], move_source: bool = False):
        """Unified entry point for importing documents — delegates to DocumentActionController."""
        self.doc_controller.start_import(files, move_source=move_source)

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

        new_lang = self.app_config.get_language()
        self._switch_language(new_lang, refresh_ui=True)

    def _switch_language(self, lang: str, refresh_ui: bool = True):
        """Swaps the QTranslator at runtime."""
        logger.debug(f"[L10n] _switch_language called with lang='{lang}', refresh_ui={refresh_ui}")
        app = QCoreApplication.instance()
        if not app:
            return

        # Remove old translators
        for t in self._translators:
            app.removeTranslator(t)
        self._translators.clear()

        # Load new translator if not English
        if lang != "en":
            from PyQt6.QtCore import QTranslator
            translator = QTranslator()
            base_dir = Path(__file__).resolve().parent.parent
            qm_path = base_dir / "resources" / "l10n" / lang / "gui_strings.qm"

            if qm_path.exists():
                if translator.load(str(qm_path)):
                    app.installTranslator(translator)
                    self._translators.append(translator)
                    logger.info(f"[L10n] Switched language to {lang} (hot-reload)")
                    logger.debug(f"[L10n] Loaded QM from: {qm_path}")
                    # Force immediate retranslation if requested and UI is ready
                    if refresh_ui:
                        self.retranslate_ui()
                else:
                    logger.error(f"[L10n] Failed to load translation: {qm_path}")
            else:
                logger.warning(f"[L10n] Translation file missing: {qm_path}")
        else:
            logger.info("[L10n] Switched language to English (default)")
            # Force immediate retranslation if requested and UI is ready
            if refresh_ui:
                self.retranslate_ui()

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

        msg = self.tr("Found %s files in transfer folder. Do you want to import them now?") % len(files)
        reply = show_selectable_message_box(self, self.tr("Import from Transfer"), msg, 
                                           icon=QMessageBox.Icon.Question,
                                           buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.start_import_process(files, move_source=False)

    # --- Stage 2: Semantic Data Management Slots ---

    def _show_semantic_filter(self, docs: list, empty_msg: str, filter_label: str, status_msg: str) -> None:
        """Applies a UUID-based filter for a list of flagged documents, or shows a notification if empty."""
        if not docs:
            show_notification(self, self.tr("Semantic Data"), empty_msg)
            return
        self.central_stack.setCurrentIndex(1)
        query = {"field": "uuid", "op": "in", "value": [d.uuid for d in docs]}
        self.list_widget.apply_advanced_filter(query, label=filter_label)
        self.main_status_label.setText(status_msg)

    def list_missing_semantic_data_slot(self):
        """Query DB for documents lacking semantic data and display them."""
        docs = self.db_manager.get_documents_missing_semantic_data()
        self._show_semantic_filter(
            docs,
            empty_msg=self.tr("All documents have semantic data."),
            filter_label="Semantic Data > Missing",
            status_msg=self.tr("Showing %s docs with missing semantic data.") % len(docs),
        )

    def list_mismatched_semantic_data_slot(self):
        """Query DB for documents with mismatched data."""
        docs = self.db_manager.get_documents_mismatched_semantic_data()
        self._show_semantic_filter(
            docs,
            empty_msg=self.tr("No data mismatches found."),
            filter_label="Semantic Data > Mismatched",
            status_msg=self.tr("Showing %s docs with data mismatches.") % len(docs),
        )

    def run_stage_2_selected_slot(self, uuids: list[str] = None):
        """Manually trigger Stage 2 for selected documents — delegates to DocumentActionController."""
        if not uuids:
            uuids = self.list_widget.get_selected_uuids()
        self.doc_controller.run_stage_2(uuids)

    def run_stage_2_all_missing_slot(self):
        """Find all documents with empty semantic data — delegates to DocumentActionController."""
        self.doc_controller.run_stage_2_all_missing()

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
                logger.error(f"Merge error: {e}")
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
            progress.setLabelText(self.tr("Comparing documents (%s/%s)...") % (current, total))

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



    def _on_ai_status_changed(self, msg: str) -> None:
        self.activity_panel.update_status(self.tr("AI: %s") % msg)

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
        """Stamp a document (or multiple) — delegates to DocumentActionController."""
        self.doc_controller.stamp_documents(uuid_or_list)

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
                show_notification(self, self.tr("Tags Updated"), self.tr("Updated tags for %n documents.", "", count))

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
        if hasattr(self, 'ai_worker') and self.ai_worker:
            self.ai_worker.stop()
            self.ai_worker.wait(2000)
        # Cancel background workers to kill subprocesses
        if hasattr(self, 'main_loop_worker') and self.main_loop_worker:
            self.main_loop_worker.stop()
            self.main_loop_worker.wait(2000)
        if hasattr(self, 'import_worker') and self.import_worker:
            self.import_worker.cancel()
            self.import_worker.wait(2000)
        if hasattr(self, 'batch_worker') and self.batch_worker:
            self.batch_worker.cancel()
            self.batch_worker.wait(2000)
        if hasattr(self, 'reprocess_worker') and self.reprocess_worker:
            self.reprocess_worker.cancel()
            self.reprocess_worker.wait(2000)

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

        if hasattr(self, 'main_loop_worker') and hasattr(self.main_loop_worker, 'is_paused'):
             settings.setValue("ai_paused", bool(self.main_loop_worker.is_paused))

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

    def set_archive_mode(self, enabled: bool):
        """Displays documents currently in the archive."""
        self.list_widget.show_archive(enabled)
        if enabled:
            self.main_status_label.setText(self.tr("Viewing Archive"))
        else:
            self.main_status_label.setText(self.tr("Ready"))

    def restore_documents_slot(self, uuids: list[str]):
        """Restore soft-deleted documents — delegates to DocumentActionController."""
        self.doc_controller.restore_documents(uuids)

    def archive_document_slot(self, uuids: list[str], archive: bool = True):
        """Archive or unarchive documents — delegates to DocumentActionController."""
        self.doc_controller.archive_documents(uuids, archive)

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
            if hasattr(self, 'main_loop_worker') and self.main_loop_worker:
                self.main_loop_worker.stop()
                self.main_loop_worker.wait(5000)

            config = AppConfig()
            vault_path = config.get_vault_path()

            success = self.db_manager.purge_all_data(vault_path)

            if success:
                # Clear all caches and views
                self.list_widget.refresh_list()
                if hasattr(self, 'editor_widget'): self.editor_widget.clear()
                if hasattr(self, 'pdf_viewer'): self.pdf_viewer.clear()

                if hasattr(self, "cockpit_widget"):
                    self.cockpit_widget.refresh_stats()

                if hasattr(self, "filter_tree_widget"):
                    self.filter_tree_widget.load_tree()

                if hasattr(self, "filter_input"):
                    self.filter_input.clear()

                if self.pipeline:
                    self._init_main_loop_worker()

                show_notification(self, self.tr("Success"), self.tr("System has been reset."))
            else:
                # Try to recovery worker even on fail
                if self.pipeline:
                    self._init_main_loop_worker()
                show_selectable_message_box(self, self.tr("Error"), self.tr("Failed to purge data. Check logs."), icon=QMessageBox.Icon.Warning)

    def _init_main_loop_worker(self):
        """Initializes and connects the background pipeline worker."""
        if not self.pipeline:
            return

        if hasattr(self, 'main_loop_worker') and self.main_loop_worker:
            self.main_loop_worker.stop()
            self.main_loop_worker.wait(2000)

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

    def purge_documents_slot(self, uuids: list[str]):
        """Permanently delete documents — delegates to DocumentActionController."""
        self.doc_controller.purge_documents(uuids)
    def open_debug_audit_window(self, uuid: str):
        """Opens the Audit Window in debug/generic mode with only a Close button."""
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


    def _navigate_to_workflow_process(self, rule_id: str, doc) -> None:
        """Switch to Workflow > Process view and open *doc* under *rule_id*."""
        # Preserve the Explorer selection so it is restored when the user returns.
        doc_uuid = str(doc.uuid)
        self._last_selected_uuid = doc_uuid
        if hasattr(self, "list_widget"):
            self.list_widget.target_uuid_to_restore = doc_uuid
        self.central_stack.setCurrentIndex(2)   # Workflow Manager page
        self.workflow_manager.open_document_in_process(rule_id, doc)

    def navigate_to_list_filter(self, payload: dict):
        """Switch to Explorer View and apply filter."""

        # New payload can be just query (legacy) or dict with metadata
        if "query" in payload:
            filter_query = payload["query"]
        else:
            filter_query = payload

        self.central_stack.setCurrentIndex(1) # Explorer
        q_str = json.dumps(filter_query, sort_keys=True)
        target_uuid = self._cockpit_selections.get("DASH:" + q_str)
        self.list_widget.target_uuid_to_restore = target_uuid
        self.list_widget.current_cockpit_query = filter_query

        label = payload.get("label") or payload.get("name")
        self.list_widget.view_context = label if label else "Cockpit View"
        
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
        except Exception as e:
            get_silent_logger().debug(f"Selection persistence failed: {e}")

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
                       logger.error(f"Failed to apply structural changes: {e}")
                       traceback.print_exc()
                       show_selectable_message_box(self, self.tr("Error"), f"Failed to apply structural changes: {e}", icon=QMessageBox.Icon.Critical)

    def go_home_slot(self):
        """Switch to Cockpit."""
        self.central_stack.setCurrentIndex(0)
        if hasattr(self, "cockpit_widget") and self.cockpit_widget:
            self.cockpit_widget.refresh_stats()



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

    def changeEvent(self, event):
        """Handle language change events."""
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

