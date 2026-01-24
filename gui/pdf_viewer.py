from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea, QFrame, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path
from gui.widgets.canvas_page import CanvasPageWidget

class PdfViewerWidget(QWidget):
    """
    Modern PDF Viewer / Editor.
    Uses custom CanvasStack for high-fidelity "Live Edit" (Rotation/Deletion).
    """
    # Signals
    stamp_requested = pyqtSignal(str)
    tags_update_requested = pyqtSignal(list)
    reprocess_requested = pyqtSignal(list)
    export_requested = pyqtSignal(list)
    delete_requested = pyqtSignal(str)
    split_requested = pyqtSignal(str)
    
    def __init__(self, pipeline=None, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.current_uuid = None
        self.page_widgets = []
        
        self._init_ui()
        
    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(5, 5, 5, 5)
        
        self.lbl_title = QLabel("Document Viewer")
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.btn_save = QPushButton("💾 Save Changes")
        self.btn_save.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_save.setVisible(False) # Hidden until changes made
        
        self.btn_split = QPushButton("✂️ Split")
        self.btn_split.setToolTip("Open Splitter Assistant for multi-page documents.")
        self.btn_split.clicked.connect(self.on_split_clicked)
        self.btn_split.setVisible(False) # Conditional
        
        self.toolbar_layout.addWidget(self.lbl_title)
        self.toolbar_layout.addStretch()
        self.toolbar_layout.addWidget(self.btn_split)
        self.toolbar_layout.addWidget(self.btn_save)
        
        self.layout.addLayout(self.toolbar_layout)
        
        # Scroll Area for Canvas Stack
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: #505050;") # Dark background for canvas
        
        self.canvas_container = QWidget()
        self.canvas_container.setStyleSheet("background: transparent;")
        self.canvas_layout = QVBoxLayout(self.canvas_container)
        self.canvas_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.canvas_layout.setSpacing(20) # Gap between pages
        
        self.scroll.setWidget(self.canvas_container)
        self.layout.addWidget(self.scroll)
        
    def load_document(self, file_path_or_uuid, uuid: str = None, initial_page: int = 1):
        """
        Load document into the Canvas Stack.
        Supports both File Path (Legacy / Preview) and Entity UUID (Edit Mode).
        """
        # Clear existing
        self.clear()
        
        if uuid:
            self.current_uuid = uuid
        else:
            # Maybe file_path_or_uuid IS the uuid?
            # Or this is legacy call with just path.
            # We try to deduce.
            if self.pipeline and not Path(file_path_or_uuid).exists(): 
                # Assume UUID
                self.current_uuid = file_path_or_uuid
            pass

        self.lbl_title.setText(f"Viewing: {self.current_uuid}")
        
        # 1. Resolve State
        if self.pipeline and self.current_uuid:
             self._load_from_entity(self.current_uuid)
        elif isinstance(file_path_or_uuid, str) and Path(file_path_or_uuid).exists():
             self._load_from_file(file_path_or_uuid)
             
    def _load_from_entity(self, entity_uuid):
        """
        Builds the view from the Virtual Entity's source mapping.
        """
        v_doc = self.pipeline.logical_repo.get_by_uuid(entity_uuid)
        if not v_doc:
             self.lbl_title.setText("Error: Entity not found.")
             return

        # Iterate Source Mapping
        # Mapping: [{"file_uuid": "...", "pages": [1, 2], "rotation": 90}]
        if not v_doc.source_mapping:
            self.lbl_title.setText("Empty Document (No Source).")
            return
            
        print(f"[Viewer] Loading Entity {entity_uuid} with {len(v_doc.source_mapping)} segments.")
        
        page_global_idx = 0
        
        for ref in v_doc.source_mapping:
             file_uuid = ref.file_uuid
             # Resolve Physical Path
             phys_path = self.pipeline.vault.get_file_path(file_uuid)
             if not phys_path: continue
             
             # Create Page Widgets
             for p_num in ref.pages:
                 page_data = {
                     "file_path": phys_path,
                     "file_uuid": file_uuid, # Added ID 
                     "page_index": p_num - 1,
                     "rotation": getattr(ref, 'rotation', 0),
                     "is_deleted": False
                 }
                 self._add_page_widget(page_data)
                 page_global_idx += 1
                 
        self.btn_save.setVisible(False)

    def _load_from_file(self, path):
         """Legacy Preview Mode."""
         import fitz
         try:
             doc = fitz.open(path)
             pages = doc.pageCount
             doc.close()
             
             for i in range(pages):
                 page_data = {
                     "file_path": path,
                     "file_uuid": None, # No UUID for raw files
                     "page_index": i,
                     "rotation": 0,
                     "is_deleted": False
                 }
                 self._add_page_widget(page_data)
         except Exception as e:
             print(f"Error loading file: {e}")

    def _add_page_widget(self, page_data):
        widget = CanvasPageWidget(page_data)
        widget.state_changed.connect(self.on_page_updated)
        self.canvas_layout.addWidget(widget)
        self.page_widgets.append(widget)
        self._update_toolbar_state()
        
    def _update_toolbar_state(self):
        """Toggle button visibility based on document state."""
        page_count = len(self.page_widgets)
        can_split = page_count > 1
        self.btn_split.setVisible(can_split)
        print(f"[Viewer] Update UI: Pages={page_count}, CanSplit={can_split}")

    def on_split_clicked(self):
        if self.current_uuid:
            print(f"[Viewer] Triggering split for: {self.current_uuid}")
            self.split_requested.emit(self.current_uuid)
            
    def on_page_updated(self):
        """Called when any page rotates or deletes."""
        self.btn_save.setVisible(True)
        self.btn_save.setText(self.tr("💾 Save *"))
        
    def save_changes(self):
        """
        Commit changes to Backend (Edit Mode).
        Reconstructs new SourceMapping.
        """
        if not self.pipeline or not self.current_uuid:
            return
            
        print("[Viewer] Saving changes...")
        new_mapping = []
        
        # Grouping Logic (Re-used from Splitter concept)
        from core.models.virtual import SourceReference
        
        current_file_uuid = None
        current_rot = -1
        current_pages = []
        
        for widget in self.page_widgets:
            data = widget.page_data
            if data["is_deleted"]:
                continue # Skip deleted pages
                
            f_uuid = data.get("file_uuid")
            if not f_uuid:
                print("Error: Cannot save raw file changes (No UUID).")
                return
                
            p_idx = data["page_index"] + 1 # 1-based
            rot = data["rotation"]
            
            # Check continuity
            if f_uuid != current_file_uuid or rot != current_rot:
                # Flush
                if current_pages:
                    new_mapping.append(SourceReference(
                        file_uuid=current_file_uuid,
                        pages=current_pages,
                        rotation=current_rot
                    ))
                # Start new
                current_file_uuid = f_uuid
                current_rot = rot
                current_pages = [p_idx]
            else:
                # Continue
                current_pages.append(p_idx)
                
        # Flush last
        if current_pages and current_file_uuid:
             new_mapping.append(SourceReference(
                file_uuid=current_file_uuid,
                pages=current_pages,
                rotation=current_rot
            ))
            
        # Send to Pipeline
        try:
            self.pipeline.update_entity_structure(self.current_uuid, new_mapping)
            self.btn_save.setVisible(False)
            QMessageBox.information(self, "Saved", "Document structure updated.")
            
            # Optional: Reload to verify
            self.load_document(self.current_uuid, uuid=self.current_uuid)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def clear(self):
        while self.canvas_layout.count():
             child = self.canvas_layout.takeAt(0)
             if child.widget():
                 child.widget().deleteLater()
        self.page_widgets = []
        self.current_uuid = None
        self.btn_save.setVisible(False)
        self.btn_split.setVisible(False)
