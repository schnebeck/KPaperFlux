from typing import Dict, List, Optional, Any
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QMessageBox, QTabWidget, QCheckBox, QComboBox, QDateEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog
)
import json
from PyQt6.QtCore import Qt, pyqtSignal, QSignalBlocker, QDate
from core.document import Document
from core.database import DatabaseManager
from core.models.canonical_entity import DocType

# GUI Imports
from gui.utils import format_datetime, show_selectable_message_box
from gui.widgets.multi_select_combo import MultiSelectComboBox
from gui.widgets.tag_input import TagInputWidget

class NestedTableDialog(QDialog):
    """Dialog for editing lists of objects (tables in tables)."""
    def __init__(self, data: List[Any], title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 500)
        self.data = data
        self.__init_ui()

    def __init_ui(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        
        # Determine columns from keys
        items_list = self.data if isinstance(self.data, list) else []
        keys = []
        for item in items_list:
            if isinstance(item, dict):
                for k in item.keys():
                    if k not in keys: keys.append(k)
        
        if not keys: keys = ["Value"]
        
        self.table.setColumnCount(len(keys))
        self.table.setHorizontalHeaderLabels(keys)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self.table.setRowCount(len(items_list))
        for r, item in enumerate(items_list):
            for c, key in enumerate(keys):
                val = ""
                if isinstance(item, dict):
                    val = item.get(key, "")
                else:
                    val = item if c == 0 else ""
                
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, ensure_ascii=False)
                
                self.table.setItem(r, c, QTableWidgetItem(str(val) if val is not None else ""))
        
        layout.addWidget(self.table)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.clicked.connect(self._add_row)
        remove_btn = QPushButton("Remove Row")
        remove_btn.clicked.connect(self._remove_row)
        
        save_btn = QPushButton("Save / Apply")
        save_btn.setStyleSheet("font-weight: bold; background-color: #e1f5fe;")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)

    def _remove_row(self):
        indices = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for row in indices:
            self.table.removeRow(row)

    def get_data(self) -> List[Any]:
        out = []
        cols = self.table.columnCount()
        keys = [self.table.horizontalHeaderItem(c).text() for c in range(cols)]
        
        for r in range(self.table.rowCount()):
            if cols == 1 and keys[0] == "Value":
                it = self.table.item(r, 0)
                val_text = it.text() if it else ""
                out.append(self._parse_value(val_text))
            else:
                item_dict = {}
                for c in range(cols):
                    it = self.table.item(r, c)
                    val_text = it.text() if it else ""
                    item_dict[keys[c]] = self._parse_value(val_text)
                out.append(item_dict)
        return out

    def _parse_value(self, text: str) -> Any:
        try:
            val_clean = text.strip()
            if val_clean.startswith(("[", "{")):
                return json.loads(val_clean)
            if val_clean.lower() == "true": return True
            if val_clean.lower() == "false": return False
            if not val_clean: return None
            if "." in val_clean and val_clean.replace(".", "", 1).replace("-","",1).isdigit():
                return float(val_clean)
            if val_clean.isdigit() or (val_clean.startswith("-") and val_clean[1:].isdigit()):
                return int(val_clean)
        except: pass
        return text

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

        self.status_combo = QComboBox()
        self.status_combo.addItems([
            "NEW", "READY_FOR_PIPELINE", 
            "PROCESSING", "PROCESSING_S1", "PROCESSING_S1_5", "PROCESSING_S2",
            "STAGE1_HOLD", "STAGE1_5_HOLD", "STAGE2_HOLD",
            "PROCESSED", "ERROR"
        ])
        general_layout.addRow(self.tr("Status:"), self.status_combo)

        self.export_filename_edit = QLineEdit()
        general_layout.addRow(self.tr("Export Name:"), self.export_filename_edit)

        self.tags_edit = TagInputWidget()
        self.tags_edit.setToolTip(self.tr("Custom Tags: Enter keywords, separated by commas or Enter."))
        general_layout.addRow(self.tr("Tags:"), self.tags_edit)

        self.tab_widget.addTab(self.general_scroll, self.tr("General"))

        # --- Tab 2: Analysis & AI Core ---
        self.analysis_scroll = QScrollArea()
        self.analysis_scroll.setWidgetResizable(True)
        self.analysis_content = QWidget()
        self.analysis_scroll.setWidget(self.analysis_content)
        analysis_layout = QFormLayout(self.analysis_content)

        # Core Selectors
        self.doc_types_combo = MultiSelectComboBox()
        self.doc_types_combo.addItems(sorted([t.value for t in DocType]))
        analysis_layout.addRow(self.tr("Document Types:"), self.doc_types_combo)

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["INBOUND", "OUTBOUND", "INTERNAL", "UNKNOWN"])
        analysis_layout.addRow(self.tr("Direction:"), self.direction_combo)

        self.context_combo = QComboBox()
        self.context_combo.addItems(["PRIVATE", "BUSINESS", "UNKNOWN"])
        analysis_layout.addRow(self.tr("Tenant Context:"), self.context_combo)

        analysis_layout.addRow(QLabel("--- " + self.tr("Extracted Data") + " ---"))

        self.sender_edit = QLineEdit()
        analysis_layout.addRow(self.tr("Sender:"), self.sender_edit)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setSpecialValueText(" ") # Allow 'empty' look
        analysis_layout.addRow(self.tr("Document Date:"), self.date_edit)

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("0.00")
        analysis_layout.addRow(self.tr("Amount:"), self.amount_edit)

        self.reasoning_view = QTextEdit()
        self.reasoning_view.setMaximumHeight(80)
        analysis_layout.addRow(self.tr("AI Reasoning:"), self.reasoning_view)

        self.tab_widget.addTab(self.analysis_scroll, self.tr("Analysis"))

        # --- Tab: Stamps (Stage 1.5) - Phase 105 ---
        self.stamps_tab = QWidget()
        stamps_layout = QVBoxLayout(self.stamps_tab)

        self.stamps_table = QTableWidget()
        self.stamps_table.setColumnCount(4)
        self.stamps_table.setHorizontalHeaderLabels([
            self.tr("Type"), self.tr("Text"), self.tr("Page"), self.tr("Confidence")
        ])
        self.stamps_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        stamps_layout.addWidget(self.stamps_table)

        stamps_btn_layout = QHBoxLayout()
        self.btn_add_stamp = QPushButton(self.tr("Add Stamp"))
        self.btn_add_stamp.clicked.connect(self._add_stamp_row)
        self.btn_remove_stamp = QPushButton(self.tr("Remove Selected"))
        self.btn_remove_stamp.clicked.connect(self._remove_selected_stamps)
        stamps_btn_layout.addWidget(self.btn_add_stamp)
        stamps_btn_layout.addWidget(self.btn_remove_stamp)
        stamps_btn_layout.addStretch()
        stamps_layout.addLayout(stamps_btn_layout)

        # Hide by default, shown in display_document
        self.tab_widget.addTab(self.stamps_tab, self.tr("Stamps"))
        self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.stamps_tab), False)

        # --- Tab: Semantic Data (Phase 110) ---
        self.semantic_data_tab = QWidget()
        semantic_data_layout = QVBoxLayout(self.semantic_data_tab)

        self.semantic_table = QTableWidget()
        self.semantic_table.setColumnCount(3)
        self.semantic_table.setHorizontalHeaderLabels([
            self.tr("Section"), self.tr("Field"), self.tr("Value")
        ])
        self.semantic_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.semantic_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.semantic_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        semantic_data_layout.addWidget(self.semantic_table)

        semantic_btn_layout = QHBoxLayout()
        self.btn_add_semantic = QPushButton(self.tr("Add Entry"))
        self.btn_add_semantic.clicked.connect(self._add_semantic_row)
        self.btn_remove_semantic = QPushButton(self.tr("Remove Selected"))
        self.btn_remove_semantic.clicked.connect(self._remove_selected_semantic)
        semantic_btn_layout.addWidget(self.btn_add_semantic)
        semantic_btn_layout.addWidget(self.btn_remove_semantic)
        semantic_btn_layout.addStretch()
        semantic_data_layout.addLayout(semantic_btn_layout)

        self.tab_widget.addTab(self.semantic_data_tab, self.tr("Semantic Data"))
        self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.semantic_data_tab), False)

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

        semantic_layout.addWidget(QLabel(self.tr("Cached Full Text:")))
        self.full_text_viewer = QTextEdit()
        self.full_text_viewer.setReadOnly(True)
        self.full_text_viewer.setFont(font)
        semantic_layout.addWidget(self.full_text_viewer)
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
            # Use status_combo for batch display as well
            stat = statuses.pop().upper()
            idx = self.status_combo.findText(stat, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)
            else:
                self.status_combo.setCurrentText(stat) # Fallback if not in list
        else:
            self.status_combo.setCurrentIndex(-1) # No selection
            self.status_combo.setPlaceholderText("<Multiple Values>")

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
        # Robust Status Sync (Case Insensitive)
        stat = (doc.status or "NEW").upper()
        idx = self.status_combo.findText(stat, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)
        else:
            self.status_combo.setCurrentText(stat)

        self.export_filename_edit.setText(doc.original_filename or "")

        # Phase 106: Display User Tags from the dedicated 'tags' column
        user_tags = getattr(doc, "tags", []) or []
        if isinstance(user_tags, list):
            self.tags_edit.setTags(user_tags)
        else:
            self.tags_edit.setText(str(user_tags))

        # AI / Analysis Fields
        sd = doc.semantic_data or {}

        # Doc Types (Dynamic via Enum)
        dt = sd.get("doc_types", [])
        if not dt and getattr(doc, 'doc_type', None):
            # Legacy field compat
            dt = doc.doc_type if isinstance(doc.doc_type, list) else [doc.doc_type]
        self.doc_types_combo.setCheckedItems(dt)

        # Directions & Context (Dynamic via standard values)
        # Note: We keep these UNKNOWN by default if nothing found
        # They will grow as the system evolves.
        self.direction_combo.setCurrentText(sd.get("direction", "UNKNOWN"))
        self.context_combo.setCurrentText(sd.get("tenant_context", "UNKNOWN"))
        self.reasoning_view.setText(sd.get("reasoning", ""))

        # Stage 1.5 Stamps (Phase 105 Fix)
        # Check both direct 'layer_stamps' and nested 'visual_audit'
        audit_data = sd.get("visual_audit") or sd
        stamps = audit_data.get("layer_stamps") or audit_data.get("stamps") or []

        self.stamps_table.setRowCount(0)
        idx_stamps = self.tab_widget.indexOf(self.stamps_tab)

        if stamps:
            self.tab_widget.setTabVisible(idx_stamps, True)
            for s in stamps:
                # A stamp block can have multiple fields (form_fields) or just raw_content
                s_type = s.get("type", "STAMP")

                # Check for nested form fields (Forensic Auditor Output)
                fields = s.get("form_fields", [])
                if fields:
                    for f in fields:
                        row = self.stamps_table.rowCount()
                        self.stamps_table.insertRow(row)
                        label = f.get("label", "")
                        val = f.get("normalized_value") or f.get("raw_value") or ""

                        self.stamps_table.setItem(row, 0, QTableWidgetItem(f"{s_type}: {label}"))
                        self.stamps_table.setItem(row, 1, QTableWidgetItem(str(val)))
                        self.stamps_table.setItem(row, 2, QTableWidgetItem(str(s.get("page", 1))))
                        self.stamps_table.setItem(row, 3, QTableWidgetItem("1.0")) # Heuristic
                else:
                    # Simple Stamp entry
                    row = self.stamps_table.rowCount()
                    self.stamps_table.insertRow(row)
                    self.stamps_table.setItem(row, 0, QTableWidgetItem(str(s_type)))
                    self.stamps_table.setItem(row, 1, QTableWidgetItem(str(s.get("text") or s.get("raw_content") or "")))
                    self.stamps_table.setItem(row, 2, QTableWidgetItem(str(s.get("page", 1))))
                    self.stamps_table.setItem(row, 3, QTableWidgetItem(str(s.get("confidence", 1.0))))
        else:
            self.tab_widget.setTabVisible(idx_stamps, False)

        # Semantic Data Table (Phase 110)
        self._populate_semantic_table(sd)

        # Extracted Data
        self.sender_edit.setText(doc.sender or sd.get("sender", ""))

        # Date Handling
        doc_date = doc.doc_date or sd.get("doc_date")
        if doc_date:
            if isinstance(doc_date, str):
                qdate = QDate.fromString(doc_date, Qt.DateFormat.ISODate)
                if qdate.isValid(): self.date_edit.setDate(qdate)
            elif hasattr(doc_date, "isoformat"):
                self.date_edit.setDate(QDate.fromString(doc_date.isoformat(), Qt.DateFormat.ISODate))
        else:
            self.date_edit.setDate(QDate(2000, 1, 1)) # Default

        self.amount_edit.setText(str(doc.amount) if doc.amount is not None else "")

        # Source Mapping
        try: # Added try-except block for source mapping parsing
            mapping = doc.extra_data.get("source_mapping")
            if mapping:
                try:
                    if isinstance(mapping, str): mapping_data = json.loads(mapping)
                    else: mapping_data = mapping
                    self.source_viewer.setPlainText(json.dumps(mapping_data, indent=2, ensure_ascii=False))
                except json.JSONDecodeError: # Specific exception for JSON parsing
                    self.source_viewer.setPlainText(str(mapping)) # Fallback to string if not valid JSON
            else:
                 self.source_viewer.setPlainText("No source mapping available.")
        except Exception as e:
            print(f"Error displaying source mapping: {e}")

        # Full Text & Semantic Data
        self.full_text_viewer.setPlainText(getattr(doc, "text_content", "")) # Document object uses 'text_content'

        # Display raw semantic data (AI Results) for debugging
        if hasattr(doc, "semantic_data") and doc.semantic_data:
            self.semantic_viewer.setPlainText(json.dumps(doc.semantic_data, indent=2, ensure_ascii=False))
        else:
            self.semantic_viewer.setPlainText("{}")

    def _add_stamp_row(self):
        row = self.stamps_table.rowCount()
        self.stamps_table.insertRow(row)
        self.stamps_table.setItem(row, 0, QTableWidgetItem("OTHER"))
        self.stamps_table.setItem(row, 1, QTableWidgetItem(""))
        self.stamps_table.setItem(row, 2, QTableWidgetItem("1"))
        self.stamps_table.setItem(row, 3, QTableWidgetItem("1.0"))

    def _remove_selected_stamps(self):
        indices = sorted({idx.row() for idx in self.stamps_table.selectedIndexes()}, reverse=True)
        for row in indices:
            self.stamps_table.removeRow(row)

    def _add_semantic_row(self):
        row = self.semantic_table.rowCount()
        self.semantic_table.insertRow(row)
        self.semantic_table.setItem(row, 0, QTableWidgetItem("Custom"))
        self.semantic_table.setItem(row, 1, QTableWidgetItem(""))
        self.semantic_table.setItem(row, 2, QTableWidgetItem(""))

    def _remove_selected_semantic(self):
        indices = sorted({idx.row() for idx in self.semantic_table.selectedIndexes()}, reverse=True)
        for row in indices:
            self.semantic_table.removeRow(row)

    def _make_nested_editor_callback(self, key_path, initial_json, row):
        def callback():
            try:
                # Always get LATEST json from the item (it might have been edited before)
                it = self.semantic_table.item(row, 2)
                current_json = it.text() if it else initial_json
                
                data = json.loads(current_json)
                dlg = NestedTableDialog(data, f"Edit List: {key_path}", self)
                if dlg.exec():
                    new_data = dlg.get_data()
                    new_json = json.dumps(new_data, ensure_ascii=False)
                    
                    # Update background item (which save_changes reads)
                    if it:
                        it.setText(new_json)
                    
                    # Update Button Text
                    btn = self.semantic_table.cellWidget(row, 2)
                    if isinstance(btn, QPushButton):
                        btn.setText(f"Open Table ({len(new_data)} items)")
                    
                    # Mark as dirty?
                    self.save_btn.setEnabled(True)
            except Exception as e:
                show_selectable_message_box(self, "Error", f"Could not open nested editor: {e}")
        return callback

    def _populate_semantic_table(self, sd: Dict):
        """Flat representation of bodies & meta_header for the table."""
        self.semantic_table.setRowCount(0)
        idx_tab = self.tab_widget.indexOf(self.semantic_data_tab)
        
        if not sd:
            self.tab_widget.setTabVisible(idx_tab, False)
            return

        rows = []
        
        # Helper to traverse and flatten
        def traverse(data, section, prefix=""):
            if isinstance(data, dict):
                for k, v in data.items():
                    key_path = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, dict):
                        traverse(v, section, key_path)
                    elif isinstance(v, list):
                        # Detect if this list should be a "Table" (nested editor)
                        # Rule: list of dicts or more than 3 elements (for readability)
                        is_complex = any(isinstance(x, dict) for x in v)
                        if is_complex or (len(v) > 3 and all(not isinstance(x, (dict, list)) for x in v)):
                             rows.append((section, key_path, json.dumps(v, ensure_ascii=False), "NESTED_TABLE"))
                        elif not v: # Empty list
                             rows.append((section, key_path, "[]"))
                        else:
                            for idx, item in enumerate(v):
                                traverse(item, section, f"{key_path}.{idx}")
                    else:
                        rows.append((section, key_path, str(v) if v is not None else ""))
            elif isinstance(data, (str, int, float, bool)) or data is None:
                rows.append((section, prefix, str(data) if data is not None else ""))
            else:
                rows.append((section, prefix, json.dumps(data, ensure_ascii=False)))

        # 1. Known Main Sections
        if "meta_header" in sd:
             traverse(sd["meta_header"], "Meta")
        if "custom_fields" in sd:
             traverse(sd["custom_fields"], "Custom")
        
        # 2. Bodies (Phase 107/110)
        handled_keys = {"meta_header", "custom_fields", "bodies", "visual_audit", "layer_stamps", "summary", "doc_types", "direction", "tenant_context", "reasoning"}
        
        if "bodies" in sd and isinstance(sd["bodies"], dict):
            for body_name, body_data in sd["bodies"].items():
                traverse(body_data, body_name.replace("_body", "").capitalize())
        
        # 3. Catch-all for any other keys (like internal_routing or root-level finance_body)
        for k, v in sd.items():
            if k not in handled_keys:
                sec_name = k.replace("_body", "").capitalize()
                traverse(v, sec_name)

        if rows:
            self.tab_widget.setTabVisible(idx_tab, True)
            for item in rows:
                sec = item[0]
                key_path = item[1]
                val = item[2]
                type_hint = item[3] if len(item) > 3 else None

                row = self.semantic_table.rowCount()
                self.semantic_table.insertRow(row)
                
                it_sec = QTableWidgetItem(sec)
                it_sec.setFlags(it_sec.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it_sec.setBackground(Qt.GlobalColor.lightGray)
                
                it_key = QTableWidgetItem(key_path)
                # it_key should be editable if it's "Custom" or if we want to allow renaming?
                # Usually keys are fixed by AI, but for manual entries it's better to allow editing.
                if sec == "Custom":
                    it_key.setFlags(it_key.flags() | Qt.ItemFlag.ItemIsEditable)
                else:
                    it_key.setFlags(it_key.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                self.semantic_table.setItem(row, 0, it_sec)
                self.semantic_table.setItem(row, 1, it_key)

                if type_hint == "NESTED_TABLE":
                    data_obj = json.loads(val)
                    btn = QPushButton(f"Open Table ({len(data_obj)} items)")
                    # Connect with closure capturing current row and key
                    btn.clicked.connect(self._make_nested_editor_callback(key_path, val, row))
                    self.semantic_table.setCellWidget(row, 2, btn)
                    
                    # Store data in a hidden way as well for save_changes
                    it_val = QTableWidgetItem(val)
                    it_val.setFlags(it_val.flags() & ~Qt.ItemFlag.ItemIsEditable) # Make the underlying item non-editable
                    self.semantic_table.setItem(row, 2, it_val)
                else:
                    it_val = QTableWidgetItem(val)
                    self.semantic_table.setItem(row, 2, it_val)

            self.semantic_table.resizeRowsToContents()
        else:
            self.tab_widget.setTabVisible(idx_tab, False)

    def clear(self):
        self.current_uuids = []
        self.doc = None
        self.uuid_lbl.clear()
        self.created_at_lbl.clear()
        self.page_count_lbl.clear()
        self.status_combo.setCurrentIndex(0)
        self.export_filename_edit.clear()
        self.doc_types_combo.setCheckedItems([])
        self.direction_combo.setCurrentIndex(3) # UNKNOWN
        self.context_combo.setCurrentIndex(2) # UNKNOWN
        self.sender_edit.clear()
        self.amount_edit.clear()
        self.reasoning_view.clear()
        self.source_viewer.clear()
        self.semantic_viewer.clear()
        self.setEnabled(False)

    def save_changes(self):
        if not self.current_uuids or not self.db_manager:
            return
        # 1. Base Metadata
        custom_tags = self.tags_edit.getTags()

        # 2. Get Structured Data
        doc_types = self.doc_types_combo.getCheckedItems()
        direction = self.direction_combo.currentText()
        context = self.context_combo.currentText()

        # 3. Reconstruct full type_tags (System + Custom)
        final_tags = list(doc_types) # Start with doc types
        if direction != "UNKNOWN" and direction not in final_tags:
            final_tags.append(direction)
        if context != "UNKNOWN":
            ctx_tag = f"CTX_{context}"
            if ctx_tag not in final_tags:
                final_tags.append(ctx_tag)

        # Append Custom Tags
        for ct in custom_tags:
            if ct not in final_tags:
                final_tags.append(ct)

        updates = {
            "status": self.status_combo.currentText(),
            "export_filename": self.export_filename_edit.text().strip(),
            "type_tags": final_tags,
            "tags": custom_tags
        }

        # 2. Semantic Metadata (Extracted Data)
        # We merge existing semantic_data with UI changes
        sd = self.doc.semantic_data or {}
        sd["doc_types"] = doc_types
        sd["direction"] = direction
        sd["tenant_context"] = context
        sd["reasoning"] = self.reasoning_view.toPlainText().strip()

        # Phase 107: Automatic Pruning of mismatched semantic bodies
        # Logic: If doc_types changed, remove bodies that don't belong to any of the NEW types.
        mapping = {
            "INVOICE": "finance_body", "RECEIPT": "finance_body", "ORDER_CONFIRMATION": "finance_body",
            "DUNNING": "finance_body", "BANK_STATEMENT": "ledger_body", "CONTRACT": "legal_body",
            "OFFICIAL_LETTER": "legal_body", "PAYSLIP": "hr_body", "MEDICAL_DOCUMENT": "health_body",
            "UTILITY_BILL": "finance_body", "EXPENSE_REPORT": "travel_body"
        }
        if "bodies" in sd:
            allowed_bodies = {mapping.get(dt.upper()) for dt in doc_types if mapping.get(dt.upper())}
            # Keep bodies that are either allowed OR not in our known mapping (to avoid accidental data loss of custom bodies)
            new_bodies = {k: v for k, v in sd["bodies"].items() if k in allowed_bodies or k not in mapping.values()}
            if len(new_bodies) != len(sd["bodies"]):
                print(f"[Phase 107] Pruned semantic bodies due to type change: {list(sd['bodies'].keys())} -> {list(new_bodies.keys())}")
                sd["bodies"] = new_bodies

        # 3. Stamps Persistence (Phase 105 Fix: Handle hierarchy & overwriting)
        stamps_list = []
        for r in range(self.stamps_table.rowCount()):
            try:
                page_val = int(self.stamps_table.item(r, 2).text())
            except: page_val = 1
            try:
                conf_val = float(self.stamps_table.item(r, 3).text())
            except: conf_val = 1.0

            raw_type = self.stamps_table.item(r, 0).text()
            val = self.stamps_table.item(r, 1).text()

            # Un-flatten: "TYPE: Label" -> type=TYPE, form_field={label: Label, value: val}
            if ":" in raw_type:
                parts = [p.strip() for p in raw_type.split(":", 1)]
                s_type = parts[0]
                label = parts[1]

                # Check if we already have a block for this type on this page
                # (Simplification: treat each row as its own block for now, or group by type/page)
                stamps_list.append({
                    "type": s_type,
                    "page": page_val,
                    "form_fields": [{
                        "label": label,
                        "raw_value": val,
                        "normalized_value": val
                    }]
                })
            else:
                stamps_list.append({
                    "type": raw_type,
                    "raw_content": val,
                    "page": page_val,
                    "confidence": conf_val
                })

        # Persist as 'layer_stamps' inside visual_audit for consistency with filters
        if stamps_list or "visual_audit" in sd:
            if "visual_audit" not in sd: sd["visual_audit"] = {}
            # Overwrite both locations to stay safe
            sd["visual_audit"]["layer_stamps"] = stamps_list
            sd["visual_audit"]["stamps"] = stamps_list
            # Also check if it exists at root (Phase 105 AI compatibility)
            if "layer_stamps" in sd:
                sd["layer_stamps"] = stamps_list

        # 4. Semantic Table Sync (Phase 110)
        # We read changes back into sd. We reconstruct nested structures from dotted keys.
        if "custom_fields" not in sd: sd["custom_fields"] = {} 

        for r in range(self.semantic_table.rowCount()):
            item_sec = self.semantic_table.item(r, 0)
            item_key = self.semantic_table.item(r, 1)
            item_val = self.semantic_table.item(r, 2)
            if not item_sec or not item_key or not item_val: continue

            section = item_sec.text()
            field_path = item_key.text().strip()
            val_text = item_val.text()
            if not field_path: continue
            
            # Map back to target dict
            root = sd
            if section == "Meta":
                if "meta_header" not in sd: sd["meta_header"] = {}
                root = sd["meta_header"]
            elif section == "Custom":
                if "custom_fields" not in sd: sd["custom_fields"] = {}
                root = sd["custom_fields"]
            else:
                # Check if it's in a body or other root key
                body_key = section.lower() + "_body"
                if "bodies" in sd and (body_key in sd["bodies"] or section.lower() in sd["bodies"]):
                    if body_key in sd["bodies"]: root = sd["bodies"][body_key]
                    else: root = sd["bodies"][section.lower()]
                elif section.lower() in sd:
                    root = sd[section.lower()]
                elif body_key in sd:
                    root = sd[body_key]
                else:
                    # New dynamic section
                    if "bodies" not in sd: sd["bodies"] = {}
                    sd["bodies"][body_key] = {}
                    root = sd["bodies"][body_key]

            # Reconstruct Nested Path
            parts = field_path.split(".")
            target = root
            for i, part in enumerate(parts[:-1]):
                # If part is numeric, we might be inside a list?
                # For simplicity, if Target is a list and part is digit, use index
                # If Target is dict, use key. 
                if part.isdigit():
                    idx = int(part)
                    if isinstance(target, list):
                        while len(target) <= idx: target.append({})
                        target = target[idx]
                    else:
                        # Fallback for ill-formed data
                        if part not in target: target[part] = {}
                        target = target[part]
                else:
                    if part not in target:
                        # Peek at next part to decide if list or dict
                        if i + 1 < len(parts) and parts[i+1].isdigit():
                            target[part] = []
                        else:
                            target[part] = {}
                    target = target[part]

            # Set Value
            last_key = parts[-1]
            typed_val = val_text
            try:
                if val_text.strip().startswith(("[", "{")):
                    typed_val = json.loads(val_text)
                elif val_text.lower() == "true": typed_val = True
                elif val_text.lower() == "false": typed_val = False
                elif not val_text: typed_val = None
                elif "." in val_text and val_text.replace(".", "", 1).isdigit():
                    typed_val = float(val_text)
                elif val_text.isdigit():
                    typed_val = int(val_text)
            except:
                pass
            
            if isinstance(target, list) and last_key.isdigit():
                idx = int(last_key)
                while len(target) <= idx: target.append(None)
                target[idx] = typed_val
            else:
                target[last_key] = typed_val

        # Update flat document fields as well (Redundancy for filtering)
        updates["sender"] = self.sender_edit.text().strip()
        updates["amount"] = self.amount_edit.text().strip()

        if self.date_edit.date().year() > 2000:
             updates["doc_date"] = self.date_edit.date().toString(Qt.DateFormat.ISODate)

        updates["semantic_data"] = sd

        for uuid in self.current_uuids:
             self.db_manager.update_document_metadata(uuid, updates)
             self.db_manager.touch_last_used(uuid)

        self.metadata_saved.emit()
        show_selectable_message_box(self, self.tr("Saved"), self.tr("Changes saved to Database."), icon=QMessageBox.Icon.Information)
