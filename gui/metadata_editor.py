
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QMessageBox, QTabWidget, QCheckBox
)
import json
from PyQt6.QtCore import Qt, pyqtSignal, QSignalBlocker
from core.document import Document
from core.database import DatabaseManager
from gui.utils import format_datetime

class MetadataEditorWidget(QWidget):
    """
    Simplified Widget to edit virtual document metadata for Stage 0/1.
    """
    metadata_saved = pyqtSignal()

    def __init__(self, db_manager: DatabaseManager = None):
        super().__init__()
        self.db_manager = db_manager
        self.current_uuids = []
        self.doc = None
        
        self._init_ui()
        
    def set_db_manager(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Lock Checkbox
        self.chk_locked = QCheckBox("Locked (Immutable)")
        self.chk_locked.clicked.connect(self.on_lock_clicked)
        layout.addWidget(self.chk_locked)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # --- Tab 1: General ---
        self.general_scroll = QScrollArea()
        self.general_scroll.setWidgetResizable(True)
        self.general_content = QWidget()
        self.general_scroll.setWidget(self.general_content)
        
        general_layout = QFormLayout(self.general_content)
        
        self.uuid_lbl = QLabel()
        self.uuid_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        general_layout.addRow("UUID:", self.uuid_lbl)
        
        self.created_at_lbl = QLabel()
        general_layout.addRow(self.tr("Created At:"), self.created_at_lbl)
        
        self.page_count_lbl = QLabel()
        general_layout.addRow(self.tr("Pages:"), self.page_count_lbl)
        
        self.status_edit = QLineEdit()
        general_layout.addRow(self.tr("Status:"), self.status_edit)
        
        self.export_filename_edit = QLineEdit()
        general_layout.addRow(self.tr("Export Filename:"), self.export_filename_edit)
        
        self.tab_widget.addTab(self.general_scroll, self.tr("General"))
        
        # --- Tab 2: Source Mapping (Component List) ---
        self.source_tab = QWidget()
        source_layout = QVBoxLayout(self.source_tab)
        
        self.source_viewer = QTextEdit()
        self.source_viewer.setReadOnly(True)
        # Monospace for JSON/Structure
        font = self.source_viewer.font()
        font.setFamily("Monospace")
        font.setStyleHint(font.StyleHint.Monospace)
        self.source_viewer.setFont(font)
        
        source_layout.addWidget(QLabel(self.tr("Physical Source Components:")))
        source_layout.addWidget(self.source_viewer)
        
        self.tab_widget.addTab(self.source_tab, self.tr("Source Mapping"))

        # --- Tab 3: Raw Semantic Data ---
        self.semantic_tab = QWidget()
        semantic_layout = QVBoxLayout(self.semantic_tab)
        
        self.semantic_viewer = QTextEdit()
        self.semantic_viewer.setReadOnly(True)
        self.semantic_viewer.setFont(font)
        
        semantic_layout.addWidget(QLabel(self.tr("Raw Virtual Document Storage:")))
        semantic_layout.addWidget(self.semantic_viewer)
        self.tab_widget.addTab(self.semantic_tab, self.tr("Debug Data"))

        # Buttons
        self.btn_save = QPushButton(self.tr("Save Changes"))
        self.btn_save.clicked.connect(self.save_changes)
        layout.addWidget(self.btn_save)

    def on_lock_clicked(self, checked):
        if not self.current_uuids or not self.db_manager:
            return
        new_state = self.chk_locked.isChecked()
        for uuid in self.current_uuids:
             self.db_manager.update_document_metadata(uuid, {"locked": new_state})
        self.toggle_lock(new_state)
        self.metadata_saved.emit()

    def toggle_lock(self, checked):
        self.tab_widget.setEnabled(not checked)

    def display_documents(self, docs: list[Document]):
        self.doc = None 
        self.current_uuids = [d.uuid for d in docs]
        
        if not docs:
            self.clear()
            return
            
        self.setEnabled(True)    
        if len(docs) == 1:
            self.display_document(docs[0])
            return

        # Batch Display (Simplified)
        with QSignalBlocker(self.chk_locked):
            locked_values = {d.locked for d in docs}
            if len(locked_values) == 1:
                 val = locked_values.pop()
                 self.chk_locked.setTristate(False)
                 self.chk_locked.setChecked(val)
                 self.toggle_lock(val)
            else:
                 self.chk_locked.setTristate(True)
                 self.chk_locked.setCheckState(Qt.CheckState.PartiallyChecked)
                 self.toggle_lock(False)

        self.uuid_lbl.setText("<Multiple Selected>")
        self.created_at_lbl.setText("-")
        pages = sum((d.page_count or 0) for d in docs)
        self.page_count_lbl.setText(f"Total: {pages}")
        
        statuses = {getattr(d, "status", "NEW") for d in docs}
        if len(statuses) == 1:
            self.status_edit.setText(statuses.pop())
            self.status_edit.setPlaceholderText("")
        else:
            self.status_edit.clear()
            self.status_edit.setPlaceholderText("<Multiple Values>")
            
        self.export_filename_edit.clear()
        self.export_filename_edit.setPlaceholderText("<Multiple Values>")
        
        self.source_viewer.setPlainText(f"{len(docs)} documents selected.")
        self.semantic_viewer.setPlainText("-")

    def display_document(self, doc: Document):
        self.current_uuids = [doc.uuid]
        self.doc = doc
        
        with QSignalBlocker(self.chk_locked):
             self.chk_locked.setChecked(doc.locked)
        self.toggle_lock(doc.locked)
 
        self.uuid_lbl.setText(doc.uuid)
        self.created_at_lbl.setText(format_datetime(doc.created_at) or "-")
        self.page_count_lbl.setText(str(doc.page_count) if doc.page_count is not None else "-")
        self.status_edit.setText(doc.status or "NEW")
        self.export_filename_edit.setText(doc.original_filename or "")
        
        # Source Mapping
        mapping = doc.extra_data.get("source_mapping")
        if mapping:
            try:
                if isinstance(mapping, str): mapping_data = json.loads(mapping)
                else: mapping_data = mapping
                self.source_viewer.setPlainText(json.dumps(mapping_data, indent=2, ensure_ascii=False))
            except: self.source_viewer.setPlainText(str(mapping))
        else:
             self.source_viewer.setPlainText("No source mapping available.")

    def clear(self):
        self.current_uuids = []
        self.doc = None
        self.uuid_lbl.clear()
        self.created_at_lbl.clear()
        self.page_count_lbl.clear()
        self.status_edit.clear()
        self.export_filename_edit.clear()
        self.source_viewer.clear()
        self.semantic_viewer.clear()
        self.setEnabled(False) 

    def save_changes(self):
        if not self.current_uuids or not self.db_manager:
            return
        updates = {
            "status": self.status_edit.text().strip(),
            "export_filename": self.export_filename_edit.text().strip()
        }
        for uuid in self.current_uuids:
             self.db_manager.update_document_metadata(uuid, updates)
        self.metadata_saved.emit()
        QMessageBox.information(self, self.tr("Saved"), self.tr("Changes saved to Database."))
