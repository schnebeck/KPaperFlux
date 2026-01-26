from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, 
    QMessageBox, QSplitter, QMenuBar, QMenu, QCheckBox, QDialog, QDialogButtonBox, QStatusBar,
    QStackedWidget, QToolBar, QAbstractItemView
)
from PyQt6.QtGui import QAction, QIcon, QDragEnterEvent, QDropEvent, QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QSettings, QSize
import platform
import os
import PyQt6.QtCore
import shutil
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from core.stamper import DocumentStamper
from core.stamper import DocumentStamper
from core.filter_tree import FilterTree, NodeType
import json
from pathlib import Path
from gui.workers import AIQueueWorker, ImportWorker
from gui.document_list import DocumentListWidget
from gui.metadata_editor import MetadataEditorWidget
from gui.pdf_viewer import PdfViewerWidget
from gui.filter_widget import FilterWidget
from gui.advanced_filter import AdvancedFilterWidget
from gui.filter_widget import FilterWidget
from gui.advanced_filter import AdvancedFilterWidget
from gui.settings_dialog import SettingsDialog
from gui.settings_dialog import SettingsDialog
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
    def __init__(self, pipeline: Optional[PipelineProcessor] = None, db_manager: Optional[DatabaseManager] = None):
        super().__init__()
        self.pipeline = pipeline
        self.db_manager = db_manager
        
        # If pipeline is provided but db_manager checks, try to extract db from pipeline
        if self.pipeline and not self.db_manager:
            self.db_manager = self.pipeline.db

        self.setWindowTitle(self.tr("KPaperFlux"))
        self.setWindowIcon(QIcon("resources/icon.png"))
        self.resize(1000, 700)
        self.setAcceptDrops(True)
        self.pending_selection = []
        
        self.filter_config_path = Path("filter_tree.json").resolve()
        
        self.create_menu_bar()
        self.create_tool_bar() 
        self.setup_shortcuts()
        
        # Central Widget is now a Stacked Widget
        self.central_stack = QStackedWidget()
        self.setCentralWidget(self.central_stack)
        
        # --- Page 0: Dashboard (Home) ---
        from gui.dashboard import DashboardWidget
        self.dashboard_widget = DashboardWidget(self.db_manager)
        self.dashboard_widget.navigation_requested.connect(self.navigate_to_list_filter)
        self.central_stack.addWidget(self.dashboard_widget)
        
        # --- Page 1: Explorer (Splitter) ---
        self.explorer_widget = QWidget()
        explorer_layout = QVBoxLayout(self.explorer_widget)
        explorer_layout.setContentsMargins(0, 0, 0, 0)
        
        # Main Splitter (Left Pane | Right Pane) -- Re-parented to explorer_layout
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        explorer_layout.addWidget(self.main_splitter)
        
        self.central_stack.addWidget(self.explorer_widget)
        self.central_stack.setCurrentIndex(0) # Start with Dashboard
        
        # --- Left Pane (Filter | List | Editor) ---
        
        # --- Left Pane (Filter | List | Editor) ---
        self.left_pane_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 1. Filter (Fixed/Small)
        # Note: Splitter usually takes widgets directly.
        # But FilterWidget might need a container or simply add it.
        self.filter_widget = FilterWidget()
        self.left_pane_splitter.addWidget(self.filter_widget)
        
        self.filter_tree = FilterTree()
        self.load_filter_tree()
        
        self.advanced_filter = AdvancedFilterWidget(
            db_manager=self.db_manager, 
            filter_tree=self.filter_tree,
            save_callback=self.save_filter_tree
        )
        self.advanced_filter.setVisible(False)
        self.left_pane_splitter.addWidget(self.advanced_filter)
        
        self.filter_widget.complex_filter_toggled.connect(self.advanced_filter.setVisible)
        
        # 2. Document List
        if self.db_manager:
            self.list_widget = DocumentListWidget(self.db_manager)
            self.list_widget.document_selected.connect(self.on_document_selected)
            self.list_widget.delete_requested.connect(self.delete_document_slot)
            self.list_widget.reprocess_requested.connect(self.reprocess_document_slot)
            self.list_widget.merge_requested.connect(self.merge_documents_slot)
            # self.list_widget.export_requested.connect(self.export_documents_slot) # Handled internally
            self.list_widget.stamp_requested.connect(self.stamp_document_slot)
            self.list_widget.tags_update_requested.connect(self.manage_tags_slot)
            self.list_widget.edit_requested.connect(self.open_splitter_dialog_slot)
            self.list_widget.document_count_changed.connect(self.update_status_bar)
            self.list_widget.save_list_requested.connect(self.save_static_list)
            
            # Connect Filter
            self.filter_widget.filter_changed.connect(self.list_widget.apply_filter)
            self.advanced_filter.filter_changed.connect(self.list_widget.apply_advanced_filter)
            self.advanced_filter.trash_mode_changed.connect(self.set_trash_mode)
            
            # Phase 92: Trash Actions
            self.list_widget.restore_requested.connect(self.restore_documents_slot)
            self.list_widget.purge_requested.connect(self.purge_documents_slot)
            self.list_widget.active_filter_changed.connect(self._on_view_filter_changed)
            
            self.left_pane_splitter.addWidget(self.list_widget)


        # 3. Metadata Editor
        # 3. Metadata Editor
        self.editor_widget = MetadataEditorWidget(self.db_manager)
        if hasattr(self.list_widget, 'refresh_list'):
            self.editor_widget.metadata_saved.connect(self.list_widget.refresh_list)
        self.left_pane_splitter.addWidget(self.editor_widget)
        
        # Add Left Pane to Main Splitter
        self.main_splitter.addWidget(self.left_pane_splitter)
        
        
        # --- Right Pane (PDF Viewer) ---
        self.pdf_viewer = PdfViewerWidget(self.pipeline)
        self.pdf_viewer.stamp_requested.connect(self.stamp_document_slot)
        self.pdf_viewer.tags_update_requested.connect(self.manage_tags_slot)
        self.pdf_viewer.export_requested.connect(self.export_documents_slot)
        self.pdf_viewer.reprocess_requested.connect(self.reprocess_document_slot)
        self.pdf_viewer.delete_requested.connect(self.delete_document_slot)
        self.pdf_viewer.document_changed.connect(self.list_widget.refresh_list)
        self.pdf_viewer.split_requested.connect(self.open_splitter_dialog_slot)
        self.main_splitter.addWidget(self.pdf_viewer)
        
        # Set Initial Sizes
        # Left Pane: 10% Filter, 60% List, 30% Editor
        # Height ratio. QSplitter uses pixels or absolute sizes initially.
        # Let's assume height 700. Filter ~70, List ~420, Editor ~210.
        self.left_pane_splitter.setSizes([70, 420, 210])
        self.left_pane_splitter.setCollapsible(0, False) # Keep filter visible
        
        # Main Splitter: Left 40%, Right 60%
        # Width 1000. Left 400, Right 600.
        # Main Splitter: Left 40%, Right 60%
        # Width 1000. Left 400, Right 600.
        self.main_splitter.setSizes([400, 600])
        self.main_splitter.setCollapsible(1, True) # Allow shrinking viewer
        self.main_splitter.setHandleWidth(4) # Slightly wider for easier grabbing

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(self.tr("Ready"))
        
        self.read_settings()
        
        # Initial Refresh
        if self.db_manager and hasattr(self, 'list_widget') and isinstance(self.list_widget, DocumentListWidget):
            self.list_widget.refresh_list()

        # Start AI Worker
        if self.pipeline:
             self.ai_worker = AIQueueWorker(self.pipeline)
             self.ai_worker.doc_updated.connect(self._on_ai_doc_updated)
             self.ai_worker.status_changed.connect(self._on_ai_status_changed)
             self.ai_worker.doc_updated.connect(self._on_ai_doc_updated)
             self.ai_worker.status_changed.connect(self._on_ai_status_changed)
             self.ai_worker.start()

    def load_filter_tree(self):
        """Load Filter Tree from JSON file."""
        if self.filter_config_path.exists():
            print(f"[DEBUG] Loading Filter Tree from: {self.filter_config_path}")
            try:
                with open(self.filter_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.filter_tree.load(data)
                print(f"[DEBUG] Loaded {len(self.filter_tree.root.children)} root items.")
            except Exception as e:
                print(f"[ERROR] Error loading filter tree: {e}")
            except Exception as e:
                print(f"[ERROR] Error loading filter tree: {e}")
        
        # Phase 92: Ensure Trash Node exists
        root = self.filter_tree.root
        trash_exists = any(child.node_type == NodeType.TRASH for child in root.children)
        if not trash_exists:
            self.filter_tree.add_trash(root)
            
        # Check for Legacy Filters (QSettings) and migrate
        self.migrate_legacy_filters()

    def migrate_legacy_filters(self):
        settings = QSettings("KPaperFlux", "AdvancedFilters")
        if settings.contains("saved_filters"):
            try:
                saved_json = settings.value("saved_filters")
                if isinstance(saved_json, str):
                    legacy_map = json.loads(saved_json)
                    if legacy_map:
                        # Create "Imported" folder
                        folder = self.filter_tree.add_folder(self.filter_tree.root, "Imported (Legacy)")
                        count = 0
                        for name, query in legacy_map.items():
                            self.filter_tree.add_filter(folder, name, query)
                            count += 1
                        
                        print(f"Migrated {count} legacy filters.")
                        
                # Clean up "Dead Files"
                settings.remove("saved_filters")
                settings.sync()
                print("Legacy filter config removed.")
                
            except Exception as e:
                print(f"Migration error: {e}")

    def save_filter_tree(self):
        """Save Filter Tree to JSON file."""
        try:
            print(f"[DEBUG] Saving Filter Tree to: {self.filter_config_path}")
            with open(self.filter_config_path, "w", encoding="utf-8") as f:
                f.write(self.filter_tree.to_json())
                f.flush()
                os.fsync(f.fileno()) # Force write to disk
            print("[DEBUG] Filter Tree saved successfully.")
        except Exception as e:
             print(f"[ERROR] Error saving filter tree: {e}")

    def create_menu_bar(self):
        menubar = self.menuBar()
        
        # -- File Menu --
        file_menu = menubar.addMenu(self.tr("&File"))
        
        action_import = QAction(self.tr("&Import Document"), self)
        action_import.setShortcut("Ctrl+O")
        action_import.triggered.connect(self.import_document_slot)
        file_menu.addAction(action_import)
        
        action_scan = QAction(self.tr("&Scan..."), self)
        action_scan.setShortcut("Ctrl+S")
        action_scan.triggered.connect(self.open_scanner_slot)
        # action_scan.setEnabled(False) # Now enabled
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
        action_extra.setChecked(True) # Default Checked?
        action_extra.triggered.connect(self.toggle_editor_visibility)
        view_menu.addAction(action_extra)
        
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

        # -- Config Menu --
        config_menu = menubar.addMenu(self.tr("&Config"))
        
        action_settings = QAction(self.tr("&Settings..."), self)
        action_settings.triggered.connect(self.open_settings_slot)
        config_menu.addAction(action_settings)
        
        # -- Help Menu --
        help_menu = menubar.addMenu(self.tr("&Help"))
        
        action_about = QAction(self.tr("&About"), self)
        action_about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(action_about)

    def on_document_selected(self, uuids: list):
        """Handle document selection (single or batch)."""
        if not self.db_manager or not uuids:
            self.editor_widget.clear()
            self.pdf_viewer.clear()
            return

        docs = []
        for uuid in uuids:
            # Try loading as Physical Document
            d = self.db_manager.get_document_by_uuid(uuid)
            
            if not d:
                 # Try loading as Entity (Phase 98)
                 source_uuid = self.db_manager.get_source_uuid_from_entity(uuid)
                 if source_uuid:
                     d = self.db_manager.get_document_by_uuid(source_uuid)
                     # Optionally attach context about WHICH entity was selected?
                     # d.selected_entity_uuid = uuid 
            
            if d: docs.append(d)
            
        if not docs:
             self.editor_widget.clear()
             self.pdf_viewer.clear()
             return
             
        # Update Editor (Batch aware)
        print(f"[DEBUG] Ensuring Editor Visible. Current: {self.editor_widget.isVisible()}")
        self.editor_widget.setVisible(True)
        self.editor_widget.display_documents(docs)
        
        # Check Splitter Sizes
        sizes = self.left_pane_splitter.sizes()
        print(f"[DEBUG] Left Splitter Sizes: {sizes}")
        if sizes[2] == 0:
            print("[DEBUG] Editor pane collapsed! Forcing expand.")
            # Heuristic: Give 30% to editor
            total = sum(sizes)
            new_sizes = [sizes[0], int(total*0.6), int(total*0.4)]
            self.left_pane_splitter.setSizes(new_sizes)

        # Update PDF Viewer
        if not self.pdf_viewer.isVisible():
            print(f"[DEBUG] Ensuring Viewer Visible.")
            self.pdf_viewer.setVisible(True)
        
        if docs:
            # Show first doc as reference (works for single and batch)
            self.pdf_viewer.load_document(docs[0].uuid, uuid=docs[0].uuid)
        else:
            self.pdf_viewer.clear()

    def delete_selected_slot(self):
        """Handle deletion via Menu Hack."""
        if hasattr(self, 'list_widget'):
            uuids = self.list_widget.get_selected_uuids()
            if uuids:
                self.delete_document_slot(uuids)
            else:
                 QMessageBox.information(self, self.tr("Info"), self.tr("Please select documents to delete."))

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
        
        reply = QMessageBox.question(self, self.tr("Confirm Delete"), 
                                   msg,
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.db_manager and self.pipeline:
                deleted_count = 0
                is_trash_mode = getattr(self.list_widget, 'is_trash_mode', False)
                
                for uuid in uuids:
                    # 0. If in Trash Mode, Purge Immediately
                    if is_trash_mode:
                        if self.db_manager.purge_entity(uuid):
                             deleted_count += 1
                        continue
                        
                    # 1. Try Deleting as Entity (Smart Delete)
                    # This removes the semantic row. If it was the last one, it trashes the source doc.
                    if self.db_manager.delete_entity(uuid):
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
                            
                self.list_widget.refresh_list()
                self.editor_widget.clear()
                self.pdf_viewer.clear()
                
                # Refresh Stats
                if hasattr(self, "dashboard_widget"):
                     self.dashboard_widget.refresh_stats()
                if hasattr(self, "filter_tree_widget"):
                     self.filter_tree_widget.load_tree()
                
                if count > 1:
                    QMessageBox.information(self, self.tr("Deleted"), self.tr(f"Deleted {deleted_count} items."))
                    
    def reprocess_document_slot(self, uuids: list):
        """Re-run pipeline for list of documents."""
        if not self.pipeline:
            return
            
        # Phase 98: Resolve Entity UUIDs to Source UUIDs
        # Pipeline expects physical document UUIDs.
        source_uuids = set()
        for u in uuids:
            # Check if it's an entity by trying to resolve it
            src = self.db_manager.get_source_uuid_from_entity(u)
            if src:
                 source_uuids.add(src)
                 # Optional: Delete the entity implementation so re-analysis is fresh?
                 # User said: "re-analyse behavior... delete semantic-data-row"
                 # It's safer to delete this specific entity now, so the new analysis 
                 # replaces it instead of duplicating or confusing things.
                 # But if we have multiple entities for one doc, deleting ONE and re-running 
                 # might re-create ALL?
                 # The Analyzer runs on the *Source Document*. It will find all entities again.
                 # So we should probably allow the Pipeline/Canonizer to handle "update".
                 # BUT, the current Canonizer logic typically ADDS.
                 # Optimization: Delete ALL entities for this Source Doc before re-running?
                 # Yes, clear slate for this document.
                 # But wait, what if user only wanted to re-analyze one page? 
                 # No, Analyzer is per-document.
                 pass 
            else:
                 source_uuids.add(u)
                 
        start_uuids = list(source_uuids)
        if not start_uuids: return

        success_count = 0
        from PyQt6.QtWidgets import QProgressDialog
        
        count = len(start_uuids)

        progress = QProgressDialog(self.tr("Reprocessing..."), self.tr("Cancel"), 0, count, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0) # Show immediately
        progress.forceShow() # Ensure visibility
        progress.setValue(0)
        
        # Ensure it paints
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        # Loop
        # Worker Setup
        from gui.workers import ReprocessWorker
        
        # Disable main window interaction? Or just modal dialog.
        # Dialog is already modal.
        
        uuid_to_restore = None
        if self.pdf_viewer and self.pdf_viewer.current_uuid in start_uuids:
             uuid_to_restore = self.pdf_viewer.current_uuid
             self.pdf_viewer.unload()
             
        self.reprocess_worker = ReprocessWorker(self.pipeline, start_uuids)
        
        # Connect Signals
        self.reprocess_worker.progress.connect(
            lambda i, uid: (
                progress.setLabelText(self.tr(f"Reprocessing {i+1} of {count}...")),
                progress.setValue(i)
            )
        )
        
        # Capture UUID to restore if any
        # We assume self.pdf_viewer.current_uuid was just unloaded so it's None NOW if we called unload.
        # But we called unload above.
        # So we need to capture it BEFORE unload.
        # Wait, I need to restructure the slot to capture it before unload.
        # See correction below (I will use a local var captured in closure).
        
        self.reprocess_worker.finished.connect(
            lambda success, total, processed_uuids: self._on_reprocess_finished(success, total, processed_uuids, uuids, progress, uuid_to_restore)
        )
        
        progress.canceled.connect(self.reprocess_worker.cancel)
        
        self.reprocess_worker.start()

    def _on_reprocess_finished(self, success_count, total, processed_uuids, original_uuids, progress_dialog, uuid_to_restore=None):
        progress_dialog.close()
        
        # Safe Thread Cleanup
        if self.reprocess_worker:
            self.reprocess_worker.wait() # Ensure it's fully done
            self.reprocess_worker.deleteLater() # Schedule deletion
            self.reprocess_worker = None # Clear ref
        
        # Refresh Editor logic
        if self.editor_widget:
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
        
        # Restore Selection and Viewer
        # If we select the document in the list, on_document_selected will fire and reload the viewer.
        # This is cleaner than manually calling load_document.
        if uuid_to_restore and uuid_to_restore in processed_uuids:
             self.list_widget.select_document(uuid_to_restore)
             
        # Async: Queue for AI Analysis
        if self.ai_worker and processed_uuids:
            for uid in processed_uuids:
                self.ai_worker.add_task(uid)
                
        QMessageBox.information(self, self.tr("Reprocessed"), f"Reprocessed {success_count}/{total} documents.\nAI Analysis queued.")

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
        
        from gui.splitter_dialog import SplitterDialog
        
        pdf_files = [f for f in files if f.lower().endswith(".pdf")]
        other_files = [f for f in files if not f.lower().endswith(".pdf")]
        
        # 1. Handle PDFs via Batch Assistant
        if pdf_files:
            dialog = SplitterDialog(self.pipeline, self)
            dialog.load_for_batch_import(pdf_files)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                instrs = dialog.import_instructions
                # instructions is a LIST of doc definitions.
                # But ImportWorker currently expects LIST of (path, instructions_for_that_path)
                # We need to change how ImportWorker (or MainWindow) handles this.
                # New Logic: If instructions is a LIST of DOCS, we need a "Batch Mode" in ImportWorker.
                
                # For now, let's pass a special item to ImportWorker if it's a batch.
                import_items.append(("BATCH", instrs))
            else:
                print("PDF Import cancelled by user.")
                
        # 2. Handle non-PDFs (Direct)
        for fpath in other_files:
            import_items.append((fpath, None))
                 
        if not import_items:
             print("No files to import (User cancelled all).")
             return

        is_batch = any(item[0] == "BATCH" for item in import_items if isinstance(item, tuple))
        count = len(import_items)
        
        # Progress Dialog
        from PyQt6.QtWidgets import QProgressDialog
        from PyQt6.QtCore import QCoreApplication
        
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
                progress.setLabelText(self.tr(f"Importing {i+1}/{count}: {os.path.basename(fname)}...")),
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
        # Supports multiple files now
        files, _ = QFileDialog.getOpenFileNames(
            self, self.tr("Select Documents"), "", self.tr("PDF Files (*.pdf);;All Files (*)")
        )
        
        if files:
            # Default to Copy (move_source=False) for menu import, 
            # or we could ask via dialog, but simple behavior is best for standard 'Open'.
            self.start_import_process(files, move_source=False)
        
    def open_scanner_slot(self):
        """Open scanner dialog and process result."""
        from gui.scanner_dialog import ScannerDialog
        dialog = ScannerDialog(self)
        if dialog.exec():
            path = dialog.get_scanned_file()
            if path and self.pipeline:
                try:
                    # Treat scanned file as a normal import (Async AI)
                    doc = self.pipeline.process_document(path, skip_ai=True)
                    
                    # Queue for background analysis
                    if doc:
                         self.ai_worker.add_task(doc.uuid)
                         
                    QMessageBox.information(
                        self, self.tr("Success"), self.tr("Scanned document imported successfully!") + f"\nUUID: {doc.uuid}"
                    )
                    if self.list_widget:
                        self.list_widget.refresh_list()
                except Exception as e:
                    QMessageBox.critical(
                        self, self.tr("Error"), self.tr("Failed to process scanned document: {}").format(e)
                    )
            
            # Note: The temp file from scanner (path) is now in Vault (processed).
            # We can optionally delete the temp file if not handled by Scanner/Vault logic,
            # but Vault usually copies it. 
            # ScannerWorker creates a temp file. process_document stores it.
            # We should cleanup the original temp file? 
            # process_document reads from path, Vault stores it. 
            # Yes, Scanner generated a temp file. We should delete it after processing.
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

    def refresh_list_slot(self):
        if self.list_widget:
            self.list_widget.refresh_list()

    def open_settings_slot(self):
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self.on_settings_changed)
        dialog.exec()
        
    def on_settings_changed(self):
        # Handle dynamic updates if needed (e.g., changing language instantly)
        # For now, maybe just prompt restart if language changes
        # But OCR/Vault settings might take effect next time action is called.
        pass

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
                    
                    self.statusBar().showMessage(self.tr("Documents merged successfully."))
                    self.list_widget.refresh_list()
                else:
                    QMessageBox.warning(self, self.tr("Error"), self.tr("Merge failed."))
            except Exception as e:
                import traceback
                print(f"[ERROR] Merge error: {e}")
                traceback.print_exc()
                QMessageBox.critical(self, self.tr("Error"), self.tr(f"Merge error: {e}"))

    def show_about_dialog(self):
        """Show the About dialog with system info."""
        qt_version = PyQt6.QtCore.QT_VERSION_STR
        py_version = sys.version.split()[0]
        platform_info = platform.system() + " " + platform.release()
        
        # Try to get KDE version
        kde_version = os.environ.get('KDE_FULL_SESSION', self.tr("Unknown"))
        if kde_version == 'true':
            # Try to fetch specific version if possible, otherwise just indicate KDE is present
            kde_version = self.tr("KDE Plasma (Detected)")
        else:
            kde_version = self.tr("Not Detected")

        QMessageBox.about(
            self,
            self.tr("About KPaperFlux"),
            self.tr(
                "<h3>KPaperFlux v1.0</h3>"
                "<p>A modern document management tool.</p>"
                "<hr>"
                "<p><b>Qt Version:</b> {qt_ver}</p>"
                "<p><b>Python:</b> {py_ver}</p>"
                "<p><b>System:</b> {sys_ver}</p>"
                "<p><b>Desktop Environment:</b> {kde_ver}</p>"
            ).format(
                qt_ver=qt_version,
                py_ver=py_version,
                sys_ver=platform_info,
                kde_ver=kde_version
            )
        )

    def find_duplicates_slot(self):
        """Open Duplicate Finder."""
        from core.similarity import SimilarityManager
        from gui.duplicate_dialog import DuplicateFinderDialog
        
        sim_manager = SimilarityManager(self.db_manager, self.pipeline.vault)
        duplicates = sim_manager.find_duplicates()
        
        if not duplicates:
             QMessageBox.information(self, self.tr("No Duplicates"), self.tr("No duplicates found with current threshold."))
             return

        dialog = DuplicateFinderDialog(duplicates, self.db_manager, self)
        dialog.exec()
        
        # Refresh list as files might have been deleted
        if self.list_widget:
            self.list_widget.refresh_list()

    def open_maintenance_slot(self):
        """Open Maintenance Dialog."""
        from gui.maintenance_dialog import MaintenanceDialog
        from core.integrity import IntegrityManager
        
        if not self.pipeline or not self.db_manager:
            return
            
        dialog.exec()
        
        # Refresh list as documents might have been deleted/imported
        # regardless of how dialog was closed
        if self.list_widget:
            self.list_widget.refresh_list()

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle Drag Enter: Check for PDFs."""
        if event.mimeData().hasUrls():
            # Check if any file is PDF
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle Drop: Extract files."""
        files = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith('.pdf') and os.path.exists(path):
                    files.append(path)
        
        if files:
            self.handle_dropped_files(files)
            event.acceptProposedAction()

    def handle_dropped_files(self, files: list[str]):
        """Confirm import and options."""
        if not self.pipeline:
            return

        # Custom Dialog for Options
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Import Dropped Files"))
        
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(self.tr(f"Import {len(files)} files into KPaperFlux?")))
        
        chk_move = QCheckBox(self.tr("Move files to Vault (Delete source)"))
        layout.addWidget(chk_move)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            move_source = chk_move.isChecked()
            self.start_import_process(files, move_source=move_source)

    def _on_import_finished(self, success_count, total, imported_uuids, error_msg, progress_dialog, skip_splitter=False):
        progress_dialog.close()
        
        # Safe Thread Cleanup
        if self.import_worker:
            self.import_worker.wait() # Ensure finished
            self.import_worker.deleteLater()
            self.import_worker = None
        
        if error_msg:
             print(f"[ERROR] Import Finished with error: {error_msg}")
             QMessageBox.critical(self, self.tr("Import Error"), error_msg)
        else:
             # Only show generic "Import Finished" if we DON'T open the splitter immediately?
             # Or show a toast? 
             # For now, let's keep it but make it less "AI Queued" specific if we open splitter.
             # We determine logic below.
             pass
             
        # Refresh List
        if self.list_widget:
            self.list_widget.refresh_list()
            
        # Queue for AI (DISABLED per User Request: Stage 1 capping)
        if self.pipeline and imported_uuids:
             splitter_opened = False
             queued_count = 0
             
             for uid in imported_uuids:
                  # Check page count
                  d = self.db_manager.get_document_by_uuid(uid)
                  
                  if d:
                      print(f"[DEBUG] Import Finished: UUID={uid}, Pages={d.page_count}, Filename={d.original_filename}")
                  else:
                      print(f"[DEBUG] Import Finished: UUID={uid} NOT FOUND in DB!")

                  if d and d.page_count and d.page_count > 1 and not skip_splitter:
                      # Candidate for splitting, but only open ONE dialog per batch
                      if not splitter_opened:
                          self.open_splitter_dialog_slot(uid)
                          splitter_opened = True
                  
                  # [CAP] Do not queue for AI worker. Status remains 'NEW'.
                  # self.db_manager.update_document_status(uid, "READY_FOR_PIPELINE")
                  # self.ai_worker.add_task(uid)

             
             if not error_msg and not splitter_opened:
                  QMessageBox.information(self, self.tr("Import Finished"), 
                                        self.tr(f"Imported {success_count} documents.\n{queued_count} queued for AI."))
                 
        # 4. Refresh Dashboard & Filters
        if hasattr(self, "dashboard_widget"):
             self.dashboard_widget.refresh_stats()
             
        if hasattr(self, "filter_tree_widget"):
             self.filter_tree_widget.load_tree()

    def _on_ai_doc_updated(self, uuid, doc):
        """Called when AI finishes a doc in background."""
        # Refresh specific item in list?
        # Or just refresh list fully? Full refresh is safer but maybe flickering?
        # Let's try to update specific item if possible?
        # ListWidget doesn't expose update_item easily.
        # Just refresh_list() for now.
        # To avoid scroll jump, maybe store state?
        # Refreshing is fast enough usually.
        # But wait, if we process 10 docs, it will refresh 10 times?
        # Ideally we only update the changed row.
        # For MVP, full refresh is acceptable.
        if self.list_widget:
            # Maybe restrict refresh?
            # self.list_widget.refresh_list() # Full refresh causes UI jump
            # We can rely on user refreshing OR simple silent refresh?
            # Let's emit signal to list widget to update specific uuid?
            # ListWidget logic: it reads from DB.
            # If DB is updated, we just need to repaint row.
            # But we don't know the row for UUID easily without search.
            # Let's assume refresh_list for now.
            # User experience: "Pop in".
            # If user is scrolling, random refresh is annoying.
            # But user wants to see results...
            # Compromise: Status bar shows progress. List refreshes.
            self.list_widget.refresh_list()

    def _on_ai_status_changed(self, msg):
        self.statusBar().showMessage(msg)
            


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
            QMessageBox.information(self, self.tr("Export"), self.tr("No documents visible to export."))
            return
            
        self.list_widget.open_export_dialog(docs)

    def stamp_document_slot(self, uuid_or_list):
        """Stamp a document (or multiple)."""
        if not self.pipeline:
            return
            
        # Normalize input to list
        if isinstance(uuid_or_list, list):
            uuids = uuid_or_list
        else:
            uuids = [uuid_or_list]
            
        if not uuids:
            return
            
        # Use FIRST document for visual configuration
        target_uuid = uuids[0]
        src_path = self.pipeline.vault.get_file_path(target_uuid)
        
        # Fallback for Virtual Entities (Shadow Docs)
        if not src_path or not os.path.exists(src_path) or src_path == "/dev/null":
             if self.db_manager:
                 # Try to find source mapping
                 mapping = self.db_manager.get_source_mapping_from_entity(target_uuid)
                 if mapping and len(mapping) > 0:
                      phys_uuid = mapping[0].get("file_uuid")
                      if phys_uuid:
                          src_path = self.pipeline.vault.get_file_path(phys_uuid)
        
        if not src_path or not os.path.exists(src_path):
            QMessageBox.warning(self, self.tr("Error"), self.tr(f"Could not locate physical file for UUID: {target_uuid}"))
            return

        from gui.stamper_dialog import StamperDialog
        dialog = StamperDialog(self)
        
        # Check for existing stamps
        stamper = DocumentStamper()
        existing_stamps = stamper.get_stamps(src_path)
        
        dialog.populate_stamps(existing_stamps)
        
        if dialog.exec():
            action, text, pos, color, rotation, remove_id = dialog.get_data()
            try:
                successful_count = 0
                
                if action == "remove":
                    if len(uuids) > 1:
                        QMessageBox.warning(self, self.tr("Batch Operation"), self.tr("Removing stamps is only supported for single documents."))
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
                            print(f"[Stamper] Failed to resolve path for {uid}")
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
                     
                QMessageBox.information(self, self.tr("Success"), msg)
                
                # Refresh viewer if essential
                self.list_widget.document_selected.emit([target_uuid])
                
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error"), self.tr(f"Stamping operation failed: {e}"))

    def manage_tags_slot(self, uuids: list[str]):
        """Open dialog to add/remove tags for selected documents."""
        if not uuids: return
        
        from gui.batch_tag_dialog import BatchTagDialog
        
        available_tags = []
        if self.db_manager:
            available_tags = list(self.db_manager.get_all_tags_with_counts().keys())
            
        # Calculate Common Tags
        common_tags = None
        if uuids:
             first_doc = self.db_manager.get_document_by_uuid(uuids[0])
             if first_doc:
                 common_tags = set([t.strip() for t in (first_doc.tags or "").split(",") if t.strip()])
                 
                 for i in range(1, len(uuids)):
                     doc = self.db_manager.get_document_by_uuid(uuids[i])
                     if doc:
                         doc_tags = set([t.strip() for t in (doc.tags or "").split(",") if t.strip()])
                         common_tags = common_tags.intersection(doc_tags)
        
        # Sort lists for UX
        available_tags.sort(key=lambda x: x.lower())
        common_tags_list = sorted(list(common_tags), key=lambda x: x.lower()) if common_tags else []
            
        dialog = BatchTagDialog(available_tags, common_tags_list, self)
        if dialog.exec():
            add_tags, remove_tags = dialog.get_data()
            
            # Iterate
            count = 0
            for uuid in uuids:
                doc = self.db_manager.get_document_by_uuid(uuid)
                if not doc: continue
                
                # Split current tags by comma
                current_tags_list = [t.strip() for t in (doc.tags or "").split(",") if t.strip()]
                
                # Add
                for t in add_tags:
                    # Check case insensitive existence? Or exact? 
                    # Let's assume exact for now, but case-insesitive check is better UX.
                    if t not in current_tags_list:
                        current_tags_list.append(t)
                        
                # Remove
                # remove_tags also exact match
                current_tags_list = [t for t in current_tags_list if t not in remove_tags]
                
                new_tags_str = ", ".join(current_tags_list)
                
                # Update if changed
                if new_tags_str != (doc.tags or ""):
                    # Avoid updating creation date etc? update_metadata keeps valid columns
                    success = self.db_manager.update_document_metadata(uuid, {'tags': new_tags_str})
                    if success:
                        count += 1
                    
            if count > 0:
                self.list_widget.refresh_list()
                QMessageBox.information(self, self.tr("Tags Updated"), self.tr(f"Updated tags for {count} documents."))

    def toggle_editor_visibility(self, checked: bool):
        """Toggle the visibility of the metadata editor widget."""
        self.editor_widget.setVisible(checked)
        
    def update_status_bar(self, visible_count: int, total_count: int):
        """Update status bar with document counts."""
        print(f"[DEBUG] MainWindow: Received count visible={visible_count}, total={total_count}")
        self.statusBar().showMessage(self.tr(f"Documents: {visible_count} (Total: {total_count})"))
        
        # Phase 58: Clear viewer if list is empty
        if visible_count == 0:
            if self.pdf_viewer:
                self.pdf_viewer.clear()
            # Clear pending selection since nothing can be selected
            self.pending_selection = []
        
        # Selection Persistence logic
        if visible_count > 0 and hasattr(self, 'pending_selection') and self.pending_selection:
             self.list_widget.select_rows_by_uuids(self.pending_selection)
             self.pending_selection = []
             
        # Default Selection if none (and we just loaded)
        # Note: update_status_bar is called on filter change.
        # If user clears selection manually, we don't want to re-select 0.
        # But initially pending_selection handles restore.
        # How to detect "Initial Load" vs "User cleared"?
        # For now, simplistic: If nothing selected after refresh, select first.
        # But this prevents "No Selection" state which might be desired?
        # User requested: "Wiederherstellen oder als Default das erste Element"
        # If we enable "Select First if None", it enforces always-selected?
        # Let's try it. If annoying, we restrict it to startup.
        # Actually `update_status_bar` called often. 
        # Checking `self.list_widget.selectedItems()` ensures we only act if empty.
        # But filtering might clear selection naturally.
        # Let's only do default selection if we just restored/loaded (pending_selection was checked).
        # OR: Check if we are in "startup" phase? Hard.
        # Let's trust user preference: "Nach Programmstart..." 
        # So we only want this logic if `pending_selection` path was used or failed?
        # I'll rely on pending_selection check. 
        # But if pending_selection is empty initially? (First run) -> select row 0.
        pass
        
        # Improved Logic:
        # If no selection, select row 0.
        if self.list_widget.rowCount() > 0 and not self.list_widget.selectedItems():
             self.list_widget.selectRow(0)

    def closeEvent(self, event: QCloseEvent):
        """Handle window close."""
        self.write_settings()
        self.save_filter_tree()
        super().closeEvent(event)

    def write_settings(self):
        settings = QSettings("KPaperFlux", "MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("mainSplitter", self.main_splitter.saveState())
        settings.setValue("leftPaneSplitter", self.left_pane_splitter.saveState())
        
        # Save List Widget State
        if hasattr(self, 'list_widget') and hasattr(self.list_widget, 'save_state'):
            self.list_widget.save_state()
        
        # Save Selection
        if hasattr(self.list_widget, 'get_selected_uuids'):
             settings.setValue("selectedUUIDs", self.list_widget.get_selected_uuids())
        
    def read_settings(self):
        settings = QSettings("KPaperFlux", "MainWindow")
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
            
        state = settings.value("windowState")
        if state:
            self.restoreState(state)
            
        main_splitter = settings.value("mainSplitter")
        if main_splitter:
            self.main_splitter.restoreState(main_splitter)
            
        left_splitter = settings.value("leftPaneSplitter")
        if left_splitter:
             self.left_pane_splitter.restoreState(left_splitter)
             
             # Safety Check: Enforce minimum visibility for Editor
             # If Editor (index 2) is collapsed (0), reset to defaults.
             sizes = self.left_pane_splitter.sizes()
             if len(sizes) >= 3 and sizes[2] < 50:
                 print(f"[Splitter Fix] Editor pane too small ({sizes[2]}), resetting layout.")
                 # Reset to standard ratio: Filter=10%, List=60%, Editor=30%
                 total = sum(sizes) if sum(sizes) > 0 else 700
                 self.left_pane_splitter.setSizes([70, int(total*0.6), int(total*0.3)])
            
        # Restore List Widget State (Sorting, Columns)
        if hasattr(self, 'list_widget') and hasattr(self.list_widget, 'restore_state'):
            self.list_widget.restore_state()
            
        # Restore Pending Selection
        self.pending_selection = settings.value("selectedUUIDs", [])
        if not isinstance(self.pending_selection, list):
             self.pending_selection = []

    def save_static_list(self, name: str, uuids: list):
        """Save a static list of UUIDs as a filter."""
        if not self.filter_tree:
             return
             
        # Create Filter Data: {field: uuid, operator: in, value: [ids]}
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
        
        # Add to Tree (Root)
        self.filter_tree.add_filter(self.filter_tree.root, name, filter_data)
        
        # Persist
        self.save_filter_tree()
        
        # Refresh UI
        self.advanced_filter.load_known_filters()
        
        self.statusBar().showMessage(self.tr(f"List '{name}' saved with {len(uuids)} items."), 3000)

    # Phase 92: Trash Bin Slots
    def set_trash_mode(self, enabled: bool):
        self.list_widget.show_trash_bin(enabled)
        if enabled:
            self.statusBar().showMessage(self.tr("Viewing Trash Bin"))
        else:
            self.statusBar().showMessage(self.tr("Ready"))

    def restore_documents_slot(self, uuids: list[str]):
        count = 0
        for uid in uuids:
            if self.db_manager.restore_document(uid):
                count += 1
        if count > 0:
            self.list_widget.refresh_list()
            QMessageBox.information(self, self.tr("Restored"), self.tr(f"Restored {count} document(s)."))
            
    def purge_data_slot(self):
        """
        Handle 'Purge All Data' request.
        """
        reply = QMessageBox.critical(
            self,
            self.tr("Confirm Global Purge"),
            self.tr("DANGER: This will delete ALL documents, files, and database entries.\n\n"
                    "This action cannot be undone.\n\n"
                    "Are you completely sure you want to reset the system?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Get Vault Path
            from core.config import AppConfig
            config = AppConfig()
            vault_path = config.get_vault_path()
            
            success = self.db_manager.purge_all_data(vault_path)
            
            if success:
                # Clear UI
                self.list_widget.refresh_list() # Should indicate empty
                self.editor_widget.clear()
                self.pdf_viewer.clear()
                
                if hasattr(self, "dashboard_widget"):
                    self.dashboard_widget.refresh_stats()
                
                if hasattr(self, "filter_tree_widget"):
                    self.filter_tree_widget.load_tree() # Reload counts (0)

                # Reset Filter Text/State
                if hasattr(self, "filter_input"):
                    self.filter_input.clear()
                
                QMessageBox.information(self, self.tr("Success"), self.tr("System has been reset."))
            else:
                QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to purge data. Check logs."))

    def purge_documents_slot(self, uuids: list[str]):
        # Confirmation already handled in DocumentListWidget
        count = 0
        for uid in uuids:
             # Get doc first to potentially remove file from Vault/Repo?
             # For V1 MVP, just DB Purge. File integrity is handled by Maintenance Tool.
            if self.db_manager.purge_entity(uid):
                count += 1
        if count > 0:
            self.list_widget.refresh_list()
            QMessageBox.information(self, self.tr("Deleted"), self.tr(f"Permanently deleted {count} document(s)."))

    
    def navigate_to_list_filter(self, filter_query: dict):
        """Switch to Explorer View and apply filter."""
        self.central_stack.setCurrentIndex(1) # Explorer
        
        if self.advanced_filter:
            if hasattr(self.advanced_filter, "set_filter_from_dict"):
                 # Assuming AdvancedFilter has this or load_from_object
                 self.advanced_filter.load_from_object(filter_query)
                 self.advanced_filter.apply_advanced_filter()
            elif hasattr(self.advanced_filter, "load_from_object"):
                 self.advanced_filter.load_from_object(filter_query)
                 self.advanced_filter.apply_advanced_filter()


    def open_splitter_dialog_slot(self, uuid: str):
        """Open Splitter Dialog for specific UUID."""
        print(f"[DEBUG] open_splitter_dialog_slot called for UUID: {uuid}")
        if not uuid or not self.pipeline: return
        
        from gui.splitter_dialog import SplitterDialog
        dialog = SplitterDialog(self.pipeline, self)
        dialog.load_document(uuid)
        
        # We need to know if splitting happened to refresh UI and queue AI
        # Hook into internal signal or just refresh blindly?
        # Let's refresh blindly on close for now, but queueing AI is important.
        # Dialog handles the *Action*.
        # Let's inspect Dialog's handling.
        # It calls pipeline.split_entity.
        # It does NOT queue AI.
        # We need to pass AI Worker or handle return.
        
        # Better: Dialog emits 'document_split(uuid_a, uuid_b)' signal.
        # But Dialog is modal `exec()`.
        # I'll modify SplitterDialog to store result.
        
        if dialog.exec():
             # Check if split happened?
             # For now, simplest is to assume if user split, they want refresh.
             # Phase 98: Apply Structural Changes
             instructions = dialog.import_instructions
             if instructions is not None:
                  try:
                      # If 0 instructions -> Delete
                      if not instructions:
                          self.pipeline.delete_entity(uuid)
                          self.statusBar().showMessage(self.tr("Document deleted (empty structure)."))
                      else:
                          new_uuids = self.pipeline.apply_restructure_instructions(uuid, instructions)
                          self.statusBar().showMessage(self.tr(f"Document updated ({len(new_uuids)} parts)."))
                          
                      # Refresh everything
                      self.list_widget.refresh_list()
                      self.pdf_viewer.clear()
                      self.editor_widget.clear()
                      
                      # Phase 92: Dashboard update
                      if hasattr(self, "dashboard_widget"):
                          self.dashboard_widget.refresh_stats()
                          
                  except Exception as e:
                       import traceback
                       print(f"[ERROR] Failed to apply structural changes: {e}")
                       traceback.print_exc()
                       QMessageBox.critical(self, self.tr("Error"), f"Failed to apply structural changes: {e}")
             
             # Re-queue? We don't have the new UUIDs easily unless we stored them.
             # But the user will see NEW documents in the list.
             # The Pipeline/Canonizer sets their status to NEW.
             # The `AIQueueWorker` (if running) might pick them up if it polls DB?
             # `AIQueueWorker` usually takes explicit `add_task`.
             # Does it poll? `process_next` pulls from queue.
             # We need to add them.
             
              # [CAP] Do not automatically queue split parts for AI.
              # if hasattr(dialog, 'new_uuids') and dialog.new_uuids:
              #     if self.ai_worker:
              #         for uid in dialog.new_uuids:
              #             self.ai_worker.add_task(uid)

    def go_home_slot(self):
        """Switch to Dashboard."""
        self.central_stack.setCurrentIndex(0)
        if self.dashboard_widget:
            self.dashboard_widget.refresh_stats()

    def create_tool_bar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        
        # Home (Dashboard)
        action_home = QAction(self.tr("Dashboard"), self)
        action_home.triggered.connect(self.go_home_slot)
        # Shortcut handled globally in setup_shortcuts or here?
        # Let's set it here for tooltip visibility
        # action_home.setShortcut(QKeySequence("Ctrl+H")) 
        # But we also want Alt+Home.
        toolbar.addAction(action_home)
        
        toolbar.addSeparator()
        
        # Explorer (List)
        action_list = QAction(self.tr("Documents"), self)
        action_list.triggered.connect(lambda: self.central_stack.setCurrentIndex(1))
        toolbar.addAction(action_list)

    def setup_shortcuts(self):
        """Initialize global keyboard shortcuts."""
        # Ctrl+S: Save Metadata
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(lambda: self.editor_widget.save_changes())
        
        # Ctrl+F: Focus Search
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(lambda: self.filter_widget.txt_smart_search.setFocus())
        
        # Ctrl+H: Home
        self.shortcut_home = QShortcut(QKeySequence("Ctrl+H"), self)
        self.shortcut_home.activated.connect(self.go_home_slot)
        
        # Alt+Home: Home (Alternative)
        self.shortcut_home_alt = QShortcut(QKeySequence("Alt+Home"), self)
        self.shortcut_home_alt.activated.connect(self.go_home_slot)



    def open_tag_manager_slot(self):
        """Open the Tag Manager dialog."""
        from gui.tag_manager import TagManagerDialog
        dlg = TagManagerDialog(self.db_manager, parent=self)
        dlg.exec()
        # Refresh lists in case tags changed
        self.list_widget.refresh_list()
        
    def _on_view_filter_changed(self, filter_data):
        """Called when a Saved View loads a filter."""
        if self.advanced_filter:
            # Load into UI
            self.advanced_filter.load_from_object(filter_data)
            # Force Apply (updates list via signal loop)
            # load_from_object disables 'Apply' button since it matches current state,
            # but we need to trigger the actual list update.
            self.advanced_filter.apply_advanced_filter()
