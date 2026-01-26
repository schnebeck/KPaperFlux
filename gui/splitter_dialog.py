from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QLabel, QMessageBox
from PyQt6.QtCore import Qt
from gui.widgets.splitter_strip import SplitterStripWidget
import fitz
import os
import json

class SplitterDialog(QDialog):
    """
    Dialog hosting the Filmstrip View for splitting documents.
    """
    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.mode = "RESTRUCTURE" # Options: "RESTRUCTURE" (Default), "IMPORT"
        self.import_instructions = None # Result payload for IMPORT mode
        self.import_paths = [] # List of paths for batch mode
        
        self.setWindowTitle(self.tr("Split Document"))
        
        # Increase vertical size by 20% (from 400 to 480)
        self.target_height = 480
        self.setMinimumHeight(200)
        self.resize(1000, self.target_height) 
        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10) # Safe zone for OS resize handles
        
        # Info
        lbl_info = QLabel(self.tr("Hover between pages to find split points. Click the scissors to toggle cuts."))
        # lbl_info.setStyleSheet("color: #666;") # Use native theme colors
        self.layout.addWidget(lbl_info)
        
        # Strip
        self.strip = SplitterStripWidget()
        self.strip.split_action_triggered.connect(self.update_ui_state)
        self.layout.addWidget(self.strip)
        
        # Buttons
        btn_box = QHBoxLayout()
        
        # Cancel / Delete
        self.btn_cancel = QPushButton(self.tr("Cancel Import"))
        self.btn_cancel.setToolTip(self.tr("Delete this file and abort import."))
        self.btn_cancel.clicked.connect(self.on_cancel_import)
        
        btn_box.addWidget(self.btn_cancel)
        btn_box.addStretch()
        
        self.btn_revert = QPushButton(self.tr("Revert Edits"))
        self.btn_revert.setToolTip(self.tr("Step-by-step undo of splits, rotations and deletions."))
        self.btn_revert.clicked.connect(self.strip.revert_last_edit)
        self.btn_revert.setEnabled(False)
        
        self.btn_confirm = QPushButton(self.tr("Split Document"))
        self.btn_confirm.setEnabled(True) # Always allowed to confirm current state
        self.btn_confirm.clicked.connect(self.on_confirm_split)
        
        btn_box.addWidget(self.btn_revert)
        btn_box.addWidget(self.btn_confirm)
        self.layout.addLayout(btn_box)
        
    def load_document(self, entity_uuid: str):
        self.mode = "RESTRUCTURE"
        self.strip.import_mode = False
        self.strip.load_document(self.pipeline, entity_uuid)
        
        # Estimate page count for resizing
        v_doc = self.pipeline.logical_repo.get_by_uuid(entity_uuid)
        if v_doc and v_doc.source_mapping:
            file_uuid = v_doc.source_mapping[0].file_uuid
            path = self.pipeline.vault.get_file_path(file_uuid)
            if path:
                doc = fitz.open(path)
                self.adjust_size_to_content(doc.page_count)
                doc.close()
                
        self.update_ui_state() # Initial check

    def load_for_import(self, file_path: str):
        """Mode: IMPORT. Load raw file Pre-Flight."""
        self.mode = "IMPORT"
        self.import_path = file_path
        self.strip.import_mode = True
        self.setWindowTitle(self.tr("Import Assistant: ") + os.path.basename(file_path))
        self.strip.load_from_path(file_path)
        
        try:
             doc = fitz.open(file_path)
             self.adjust_size_to_content(doc.page_count)
             doc.close()
        except: pass
        
        self.btn_cancel.setText(self.tr("Abort Import"))
        self.update_ui_state()

    def load_for_batch_import(self, file_paths: list[str]) -> None:
        """Mode: IMPORT (Batch). Load multiple files as one stream."""
        self.mode = "IMPORT"
        self.import_paths = file_paths
        self.strip.import_mode = True
        
        total_pages = 0
        for p in file_paths:
            try:
                doc = fitz.open(p)
                total_pages += doc.page_count
                doc.close()
            except: pass
            
        count = len(file_paths)
        self.setWindowTitle(self.tr(f"Import Assistant: Batch ({count} files)"))
        self.strip.load_from_paths(file_paths)
        self.adjust_size_to_content(total_pages)
        self.btn_cancel.setText(self.tr("Abort Import"))
        self.update_ui_state()

    def adjust_size_to_content(self, page_count: int):
        """Dynamically resize and center the window based on page count."""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        
        # Constants for estimation
        # Thumb height is target_height minus margins/buttons (approx 120px)
        thumb_h = self.target_height - 120
        # Thumb width (A4 ratio approx 0.707, but with margins let's use 0.75)
        thumb_w = int(thumb_h * 0.72)
        
        # Content width: thumbs + dividers (small) + dialog margins
        ideal_width = (page_count * thumb_w) + (page_count * 10) + 100
        
        # Constraints: Min 800, Max screen width
        final_w = max(800, min(ideal_width, screen.width() - 40))
        final_h = self.target_height
        
        self.resize(final_w, final_h)
        
        # Center on screen
        geo = self.frameGeometry()
        geo.moveCenter(screen.center())
        self.move(geo.topLeft())

    def update_ui_state(self, ignored_arg=None):
        """Update button states based on active splits and undo stack."""
        splits = self.strip.get_active_splits()
        has_splits = len(splits) > 0
        
        # Enable undo only if stack is not empty
        if hasattr(self.strip, 'undo_stack'):
            self.btn_revert.setEnabled(len(self.strip.undo_stack) > 0)
        
        # Confirm is always allowed (imports as single doc if no splits)
        self.btn_confirm.setEnabled(True)
        
        # Dynamic Text to be helpful
        if has_splits:
            verb = self.tr("Import & Split") if self.mode == "IMPORT" else self.tr("Split")
            self.btn_confirm.setText(f"{verb} into {len(splits) + 1} Parts")
        else:
            base = self.tr("Import Document") if self.mode == "IMPORT" else self.tr("Confirm Document")
            self.btn_confirm.setText(base)
            
    def on_cancel_import(self):
        """Abort import: Delete the entity and close."""
        target_uuid = self.strip.current_uuid
        if target_uuid:
            res = QMessageBox.question(self, self.tr("Cancel Import"), 
                                     self.tr("Are you sure you want to delete this document?"),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if res == QMessageBox.StandardButton.Yes:
                try:
                    # Soft delete or hard delete? User said "Cancel Import".
                    # Let's use delete_requested via signal or direct pipeline call?
                    # Using pipeline directly since we are in a dialog owned by main window loop context
                    # But pipeline might not have delete exposed nicely.
                    # Best: LogicalRepo delete + Physical cleanup?
                    # Pipeline should have delete_document.
                    if hasattr(self.pipeline, 'delete_document'):
                         self.pipeline.delete_document(target_uuid)
                    elif hasattr(self.pipeline, 'logical_repo'):
                         self.pipeline.logical_repo.update(target_uuid, deletes=True) # Soft delete
                    
                    
                    debug_result = {
                         "action": "CANCEL",
                         "source_entity": target_uuid,
                         "reason": "Import Aborted by User",
                         "next_steps": ["DELETE_ENTITY", "CLEANUP_FILES"]
                    }
                    print(f"[DEBUG] Splitter Result: {json.dumps(debug_result, indent=2)}")
                         
                    self.reject()
                except Exception as e:
                    print(f"Error cancelling import: {e}")
                    self.reject()

    def on_confirm_split(self):
        splits = self.strip.get_active_splits() # returns list of split points (e.g. [1, 3]) which are 0-based indices for NEW docs
        
        if not splits:
            # User confirmed but no splits? Treat as Skip or No-Op
            self.accept()
            return

        try:
             # Common Logic: Calculate Page Ranges
             # Need Total Page Count
             if self.mode == "IMPORT":
                 # In IMPORT mode, we scrape instructions which handle everything.
                 # No need to build ranges manually here.
                 instructions = self._scrape_instructions(ignore_splits=False)
                 self.import_instructions = instructions
                 print(f"[DEBUG] Import Instructions (Batch): {instructions}")
                 self.accept()
                 return
             else:
                 target_uuid = self.strip.current_uuid
                 if not target_uuid: return
                 # Fetch Virtual Doc to get file_uuid
                 v_doc = self.pipeline.logical_repo.get_by_uuid(target_uuid)
                 if not v_doc or not v_doc.source_mapping: return
                 file_uuid = v_doc.source_mapping[0].file_uuid
                 # Get Physical Page Count
                 phys_file = self.pipeline.physical_repo.get_by_uuid(file_uuid)
                 total_pages = phys_file.page_count_phys
             
             # Build Ranges
             
             # Build Ranges
             # Splits = [2, 5] means:
             # Doc 1: 1..2
             # Doc 2: 3..5
             # Doc 3: 6..total
             # Wait, get_active_splits returned `page_index_before + 1`.
             # If I click between Page 1 (idx 0) and Page 2 (idx 1), `page_index_before` is 0.
             # So split point is 1. Doc 1: [1], Doc 2: [2...]
             
             ranges = []
             current_start = 1
             
             sorted_splits = sorted(splits)
             
             for split_point in sorted_splits:
                 # Range is [current_start, split_point] (Exclusive? No, split point is START of new doc)
                 # So range is [current_start, split_point - 1]
                 # Example: Split at 3 (Starts at Page 3). Range 1: 1..2. Range 2: 3..End.
                 
                 # wait, `page_index_before` is 0-based.
                 # If I select after Page 1 (which is 1-based "1"), index is 0. +1 = 1?
                 # Visual: Page 1 | Page 2. Divider is between.
                 # index_before = 0.
                 # If we return `index_before + 1` = 1.
                 # Does that mean new doc starts at 0-based index 1 (Page 2)? Yes.
                 # So Split Point 1 means "New Doc Starts at Page 2".
                 # Previous Doc ends at Page 1.
                 
                 end_of_prev = split_point # Because split_point is 1-based Page 2. 
                 # Wait. 
                 # Let's stick to 1-based Pages.
                 # Split Index 1 (from get_active) means "Cut occurs AFTER Page 1".
                 # So Doc A is 1..1. Doc B starts at 2.
                 
                 ranges.append(list(range(current_start, split_point + 1))) 
                 current_start = split_point + 1
                 
             # Final Range
             if current_start <= total_pages:
                 ranges.append(list(range(current_start, total_pages + 1)))
                 
             # Correct logic check:
             # active_splits returns `page_index_before + 1`.
             # Range 1: 1 .. 1. Correct.
             
             if self.mode == "IMPORT":
                 # Generate INSTRUCTIONS for Pre-Flight Ingest
                 # New Format: Page List with Rotation/Deletion support
                 instructions = self._scrape_instructions(ignore_splits=False)
                 
                 self.import_instructions = instructions
                 print(f"[DEBUG] Import Instructions: {instructions}")
                 self.accept()
                 return

             # RESTRUCTURE MODE (Legacy/Post-Ingest)
             # Convert to Mappings List
             new_mappings = []
             for rng in ranges:
                 new_mappings.append([{"file_uuid": file_uuid, "pages": rng, "rotation": 0}])
                 
             # CALL RESTURCTURE (Phase 8.2 Backend)
             # Note: restructure_file_entities returns the NEW entity UUIDs
             new_uuids = self.pipeline.canonizer.restructure_file_entities(file_uuid, new_mappings)
             
             import json
             debug_result = {
                 "action": "SPLIT",
                 "source_entity": target_uuid,
                 "physical_file": file_uuid,
                 "parts_created": len(new_uuids),
                 "new_entities": new_uuids,
                 "next_steps": ["QUEUE_FOR_ANALYSIS", "REFRESH_DASHBOARD"]
             }
             print(f"[DEBUG] Splitter Result: {json.dumps(debug_result, indent=2)}")
             
             QMessageBox.information(self, self.tr("Split Successful"), 
                                   self.tr(f"Document restructured into {len(new_mappings)} parts."))
             
             self.accept()
                 
        except Exception as e:
            QMessageBox.critical(self, self.tr("Split Failed"), f"Error: {e}")
            
    def accept(self):
        # Override accept to log SKIP if not handled by confirm
        # Note: confirm calls self.accept(), so we need to know if we really skipped
        # Check source signal? Or just rely on confirm having its own log.
        # If this is called directly (via Skip button), confirm logic wasn't hit.
        super().accept()
        # We can't easily detect "Skip" here vs "Post-Confirm Accept" without state.
        # But we added logging to confirm, so if we see this log without the other...
        # Let's add explicit logging to the Skip button connection instead.

    def _scrape_instructions(self, ignore_splits: bool = False) -> list:
        """
        Iterate visual widgets to build Instruction Payload.
        Respects Deletions (missing widgets) and Rotations.
        Returns: List of Document Instructions.
        Format: [ {"pages": [{"file_page_index": 0, "rotation": 90}, ...]}, ... ]
        """
        from gui.widgets.splitter_strip import PageThumbnailWidget, SplitDividerWidget
        
        instructions = []
        current_pages = []
        
        layout = self.strip.content_layout
        
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if not item: continue
            w = item.widget()
            if not w: continue
            
            if isinstance(w, PageThumbnailWidget):
                # Skip Soft Deleted Pages
                if getattr(w, 'is_deleted', False):
                    continue
                    
                # Add page to current group
                page_data = {
                    "file_path": w.page_info.get("file_path") or w.page_info.get("raw_path"),
                    "file_page_index": w._page_num - 1, # 0-based
                    "rotation": w.current_rotation
                }
                current_pages.append(page_data)
                
            elif isinstance(w, SplitDividerWidget):
                if not ignore_splits and w.is_active:
                    # End of current doc
                    if current_pages:
                        instructions.append({"pages": current_pages})
                        current_pages = []
                        
        # Flush last group
        if current_pages:
            instructions.append({"pages": current_pages})
            
        return instructions

