from typing import Dict, List, Optional, Any
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QMessageBox, QTabWidget, QCheckBox, QComboBox, QDateEdit,
    QTableWidget, QTableWidgetItem, QHeaderView
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
        self.status_combo.addItems(["NEW", "PROCESSING", "PROCESSED", "ERROR"])
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

        # --- Tab: Detailed Data (Phase 110) ---
        self.details_tab = QWidget()
        details_layout = QVBoxLayout(self.details_tab)

        self.details_table = QTableWidget()
        self.details_table.setColumnCount(3)
        self.details_table.setHorizontalHeaderLabels([
            self.tr("Section"), self.tr("Field"), self.tr("Value")
        ])
        self.details_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.details_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.details_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        details_layout.addWidget(self.details_table)

        self.tab_widget.addTab(self.details_tab, self.tr("Detailed Data"))
        self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.details_tab), False)

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

        # Detailed Semantic Data (Phase 110)
        self._populate_details_table(sd)

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

    def _populate_details_table(self, sd: Dict):
        """Flat representation of bodies & meta_header for the table."""
        self.details_table.setRowCount(0)
        if not sd:
            self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.details_tab), False)
            return

        rows = []
        
        # Helper to traverse and flatten
        def traverse(data, section=""):
            if isinstance(data, dict):
                for k, v in data.items():
                    current_path = f"{section}.{k}" if section else k
                    if isinstance(v, (dict, list)):
                        # For complex types, show as JSON string in value, but mark section
                        rows.append((section or "Root", k, json.dumps(v, ensure_ascii=False)))
                    else:
                        rows.append((section or "Root", k, str(v) if v is not None else ""))
            elif isinstance(data, list):
                pass # Already handled top-level list in dict traverse

        # Only show if there are actual bodies or header
        if "meta_header" in sd:
             traverse(sd["meta_header"], "Meta")
        if "bodies" in sd:
            for body_name, body_data in sd["bodies"].items():
                traverse(body_data, body_name.replace("_body", "").capitalize())

        if rows:
            self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.details_tab), True)
            for sec, key, val in rows:
                row = self.details_table.rowCount()
                self.details_table.insertRow(row)
                
                it_sec = QTableWidgetItem(sec)
                it_sec.setFlags(it_sec.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it_sec.setBackground(Qt.GlobalColor.lightGray)
                
                it_key = QTableWidgetItem(key)
                it_key.setFlags(it_key.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                self.details_table.setItem(row, 0, it_sec)
                self.details_table.setItem(row, 1, it_key)
                self.details_table.setItem(row, 2, QTableWidgetItem(val))
        else:
            self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.details_tab), False)

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

        # 4. Detailed Table Sync (Phase 110)
        # We read changes back into sd. We only update leaf values or JSON blocks.
        for r in range(self.details_table.rowCount()):
            section = self.details_table.item(r, 0).text()
            field = self.details_table.item(r, 1).text()
            val_text = self.details_table.item(r, 2).text()
            
            # Map back to target dict
            target = None
            if section == "Meta":
                target = sd.get("meta_header")
            else:
                body_key = section.lower() + "_body"
                if "bodies" in sd and body_key in sd["bodies"]:
                    target = sd["bodies"][body_key]
                elif "bodies" in sd and section.lower() in sd["bodies"]: # fallback
                    target = sd["bodies"][section.lower()]
            
            if target is not None:
                # Type conversion attempt
                try:
                    # If it looks like JSON list/dict, parse it
                    if val_text.strip().startswith(("[", "{")):
                        target[field] = json.loads(val_text)
                    else:
                        # try numeric
                        if "." in val_text:
                            target[field] = float(val_text)
                        elif val_text.isdigit():
                            target[field] = int(val_text)
                        elif val_text.lower() == "true": target[field] = True
                        elif val_text.lower() == "false": target[field] = False
                        elif not val_text: target[field] = None
                        else: target[field] = val_text
                except:
                    target[field] = val_text

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
