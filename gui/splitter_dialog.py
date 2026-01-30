from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QLabel,
    QMessageBox, QApplication
)
from PyQt6.QtCore import Qt
import fitz
import os
import json

# Projekt-Imports
try:
    from gui.widgets.splitter_strip import SplitterStripWidget, PageThumbnailWidget, SplitDividerWidget
except ImportError:
    # Falls gui.widgets nicht existiert, Warnung drucken oder Mock verwenden
    print("Warnung: 'gui.widgets.splitter_strip' konnte nicht importiert werden.")
    # Dummy-Klassen für den Syntax-Check
    class SplitterStripWidget(QLabel):
        def __init__(self): super().__init__("Splitter Strip Placeholder")
    class PageThumbnailWidget: pass
    class SplitDividerWidget: pass

try:
    from gui.utils import show_selectable_message_box
except ImportError:
    def show_selectable_message_box(parent, title, text, icon=QMessageBox.Icon.Information, buttons=QMessageBox.StandardButton.Ok):
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(icon)
        msg.setStandardButtons(buttons)
        return msg.exec()

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

        # Increase vertical size by 20% ( from 400 to 480)
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
        if hasattr(self.strip, 'split_action_triggered'):
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
        if hasattr(self.strip, 'revert_last_edit'):
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
            total_pages = sum(len(ref.pages) for ref in v_doc.source_mapping)
            self.adjust_size_to_content(total_pages)

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
            verb = self.tr("Import & Split") if self.mode == "IMPORT" else self.tr("Save & Split")
            self.btn_confirm.setText(f"{verb} into {len(splits) + 1} Parts")
        else:
            base = self.tr("Import Document") if self.mode == "IMPORT" else self.tr("Save Changes")
            self.btn_confirm.setText(base)

    def on_cancel_import(self):
        """Abort import: Delete the entity and close."""
        target_uuid = self.strip.current_uuid
        if target_uuid:
            res = show_selectable_message_box(self, self.tr("Cancel Import"),
                                               self.tr("Are you sure you want to delete this document?"),
                                               icon=QMessageBox.Icon.Question,
                                               buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if res == QMessageBox.StandardButton.Yes:
                try:
                    # Soft delete or hard delete? User said "Cancel Import".
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
        """Build instructions and exit. Persistence is handled by the caller."""
        try:
            instructions = self._scrape_instructions(ignore_splits=False)
            self.import_instructions = instructions # Payload

            print(f"[DEBUG] SplitterDialog: Confirmed with {len(instructions)} entities.")
            # For debugging: print first entity summary
            if instructions:
                print(f"[DEBUG] Entity 1: {len(instructions[0]['pages'])} pages")

            self.accept()

        except Exception as e:
            print(f"[ERROR] SplitterDialog confirmation error: {e}")
            show_selectable_message_box(self, self.tr("Error"), f"Failed to prepare instructions: {e}", icon=QMessageBox.Icon.Critical)

    def accept(self):
        # Override accept to log SKIP if not handled by confirm
        super().accept()

    def _scrape_instructions(self, ignore_splits: bool = False) -> list:
        """
        Iterate visual widgets to build Instruction Payload.
        Respects Deletions (missing widgets) and Rotations.
        Returns: List of Document Instructions.
        Format: [ {"pages": [{"file_page_index": 0, "rotation": 90}, ...]}, ... ]
        """
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
                    "file_uuid": w.page_info.get("file_uuid"),
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
