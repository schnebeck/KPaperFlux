"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/metadata_editor.py
Version:        2.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    Widget for editing document metadata and managing workflows.
------------------------------------------------------------------------------
"""

from typing import Dict, List, Optional, Any
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QMessageBox, QTabWidget, QCheckBox, QComboBox, QDateEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFrame
)
from PyQt6.QtGui import QPixmap, QImage
import json
import io
from datetime import datetime
from PyQt6.QtCore import Qt, pyqtSignal, QSignalBlocker, QDate, QTimer, QLocale
from core.models.virtual import VirtualDocument as Document
from core.database import DatabaseManager
from core.models.types import DocType
from core.utils.girocode import GiroCodeGenerator

# GUI Imports
from gui.utils import format_datetime, show_selectable_message_box, show_notification
from gui.widgets.multi_select_combo import MultiSelectComboBox
from gui.widgets.tag_input import TagInputWidget
from gui.widgets.workflow_controls import WorkflowControlsWidget
from gui.audit_window import AuditWindow

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
                    val = json.dumps(val, ensure_ascii=False, default=str)

                self.table.setItem(r, c, QTableWidgetItem(str(val) if val is not None else ""))

        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()
        add_btn = QPushButton(self.tr("Add Row"))
        add_btn.clicked.connect(self._add_row)
        remove_btn = QPushButton(self.tr("Remove Row"))
        remove_btn.clicked.connect(self._remove_row)

        save_btn = QPushButton(self.tr("Save / Apply"))
        save_btn.setStyleSheet("font-weight: bold; background-color: #e1f5fe;")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(self.tr("Cancel"))
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
            if not val_clean: return None
            if val_clean.startswith(("[", "{")):
                return json.loads(val_clean)
            if val_clean.lower() == "true": return True
            if val_clean.lower() == "false": return False
            
            # Numeric conversion
            if "." in val_clean and val_clean.replace(".", "", 1).replace("-","",1).isdigit():
                return float(val_clean)
            if val_clean.isdigit() or (val_clean.startswith("-") and val_clean[1:].isdigit()):
                return int(val_clean)
        except (json.JSONDecodeError, ValueError):
            pass # Return text as fallback
        return text

class MetadataEditorWidget(QWidget):
    """
    Simplified Widget to edit virtual document metadata for Stage 0/1.
    """
    metadata_saved = pyqtSignal()

    STATUS_MAP = {
        "NEW": "New",
        "READY_FOR_PIPELINE": "Ready for Pipeline",
        "PROCESSING": "Processing",
        "PROCESSING_S1": "Processing (Stage 1)",
        "PROCESSING_S1_5": "Processing (Stamps)",
        "PROCESSING_S2": "Processing (Semantic)",
        "STAGE1_HOLD": "On Hold (Stage 1)",
        "STAGE1_5_HOLD": "On Hold (Stamps)",
        "STAGE2_HOLD": "On Hold (Semantic)",
        "PROCESSED": "Processed",
        "ERROR": "Error"
    }

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__()
        self.db_manager = db_manager
        self.current_uuids = []
        self.doc = None
        self._locked_for_load = False
        self.audit_window = None
        
        # Debounce timer for GiroCode updates
        self.giro_timer = QTimer()
        self.giro_timer.setSingleShot(True)
        self.giro_timer.timeout.connect(self.refresh_girocode)
        
        self._init_ui()

    def set_db_manager(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Lock Checkbox
        lock_layout = QHBoxLayout()
        self.chk_locked = QCheckBox(self.tr("Locked (Immutable)"))
        self.chk_locked.clicked.connect(self.on_lock_clicked)
        lock_layout.addWidget(self.chk_locked)
        
        lock_layout.addStretch()
        
        # Phase 111: Dynamic Workflow Controls
        self.workflow_controls = WorkflowControlsWidget()
        self.workflow_controls.transition_triggered.connect(self.on_workflow_transition)
        self.workflow_controls.playbook_changed.connect(self.on_playbook_changed)
        lock_layout.addWidget(self.workflow_controls)
        
        self.btn_audit = QPushButton(self.tr("🔍 Audit"))
        self.btn_audit.setToolTip(self.tr("Open side-by-side verification window"))
        self.btn_audit.clicked.connect(self.open_audit_window)
        lock_layout.addWidget(self.btn_audit)
        
        layout.addLayout(lock_layout)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # --- Tab 1: General ---
        self.general_scroll = QScrollArea()
        self.general_scroll.setWidgetResizable(True)
        self.general_content = QWidget()
        self.general_scroll.setWidget(self.general_content)

        general_layout = QFormLayout(self.general_content)
        
        # PKV Toggle
        self.chk_pkv = QCheckBox(self.tr("Eligible for PKV Reimbursement"))
        general_layout.addRow("", self.chk_pkv)

        self.uuid_lbl = QLabel()
        self.uuid_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        general_layout.addRow(self.tr("UUID:"), self.uuid_lbl)

        self.created_at_lbl = QLabel()
        general_layout.addRow(self.tr("Created At:"), self.created_at_lbl)

        self.page_count_lbl = QLabel()
        general_layout.addRow(self.tr("Pages:"), self.page_count_lbl)

        self.status_combo = QComboBox()
        for tech_val, display_name in self.STATUS_MAP.items():
            self.status_combo.addItem(self.tr(display_name), tech_val)
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
        # Sort and clean DocType labels
        for t in sorted([t.value for t in DocType]):
            label = t.replace("_", " ").title()
            self.doc_types_combo.addItem(self.tr(label), data=t)
        analysis_layout.addRow(self.tr("Document Types:"), self.doc_types_combo)

        self.direction_combo = QComboBox()
        for d in ["Inbound", "Outbound", "Internal", "Unknown"]:
            self.direction_combo.addItem(self.tr(d), d)
        analysis_layout.addRow(self.tr("Direction:"), self.direction_combo)

        self.context_combo = QComboBox()
        for c in ["Private", "Business", "Unknown"]:
            self.context_combo.addItem(self.tr(c), c)
        analysis_layout.addRow(self.tr("Tenant Context:"), self.context_combo)

        analysis_layout.addRow(QLabel("--- " + self.tr("Extracted Data") + " ---"))

        self.sender_edit = QLineEdit()
        analysis_layout.addRow(self.tr("Sender:"), self.sender_edit)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setSpecialValueText(" ") # Allow 'empty' look
        self.date_edit.setDisplayFormat(QLocale.system().dateFormat(QLocale.FormatType.ShortFormat))
        analysis_layout.addRow(self.tr("Document Date:"), self.date_edit)

        # Reasoning field removed to save space/tokens in AI output

        self.tab_widget.addTab(self.analysis_scroll, self.tr("Analysis"))
        
        # Move Payment Tab initialization up to prevent AttributeError (Crash Fix)
        self.payment_scroll = QScrollArea()
        self.payment_scroll.setWidgetResizable(True)
        self.payment_tab = QWidget()
        self.payment_scroll.setWidget(self.payment_tab)
        
        # Redesign: Horizontal Split
        payment_master_layout = QHBoxLayout(self.payment_tab)
        
        # Left Side: Input Fields
        self.fields_container = QWidget()
        fields_layout = QVBoxLayout(self.fields_container)
        payment_form = QFormLayout()
        
        self.pay_recipient_edit = QLineEdit()
        self.pay_iban_edit = QLineEdit()
        self.pay_bic_edit = QLineEdit()
        self.pay_amount_edit = QLineEdit()
        self.pay_purpose_edit = QLineEdit()

        payment_form.addRow(self.tr("Recipient:"), self.pay_recipient_edit)
        payment_form.addRow(self.tr("IBAN:"), self.pay_iban_edit)
        payment_form.addRow(self.tr("BIC:"), self.pay_bic_edit)
        payment_form.addRow(self.tr("Amount:"), self.pay_amount_edit)
        payment_form.addRow(self.tr("Purpose:"), self.pay_purpose_edit)
        
        fields_layout.addStretch()
        fields_layout.addLayout(payment_form)
        fields_layout.addStretch()
        payment_master_layout.addWidget(self.fields_container, 2)
        
        # Right Side: GiroCode & Actions
        self.qr_container = QWidget()
        self.qr_container.setMinimumWidth(320)
        qr_sub_layout = QVBoxLayout(self.qr_container)
        qr_sub_layout.addStretch()
        
        giro_header = QLabel(self.tr("GiroCode (EPC)"))
        giro_header.setStyleSheet("font-weight: bold; color: #1565c0; font-size: 14px;")
        giro_header.setToolTip(self.tr("Standardized QR code for SEPA transfers (EPC-QR)."))
        
        qr_btn_row = QHBoxLayout()
        qr_btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        qr_image_col = QVBoxLayout()
        qr_image_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        qr_image_col.addWidget(giro_header, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(150, 150) 
        self.qr_label.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.qr_label.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        qr_image_col.addWidget(self.qr_label)
        
        qr_btn_row.addLayout(qr_image_col)
        
        btn_col = QVBoxLayout()
        btn_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        btn_col.addSpacing(20) 
        
        self.btn_copy_pay_payload = QPushButton(self.tr("Copy Payload"))
        self.btn_copy_pay_payload.setToolTip(self.tr("Copy the raw GiroCode data for banking apps"))
        self.btn_copy_pay_payload.clicked.connect(self.copy_girocode_payload)
        btn_col.addWidget(self.btn_copy_pay_payload)
        
        qr_btn_row.addLayout(btn_col)
        qr_sub_layout.addLayout(qr_btn_row)
        qr_sub_layout.addStretch()
        payment_master_layout.addWidget(self.qr_container)

        self.tab_widget.addTab(self.payment_scroll, self.tr("Payment"))
        self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.payment_scroll), False)

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

        # --- Tab: Workflow History (Phase 112) ---
        self.history_tab = QWidget()
        history_layout = QVBoxLayout(self.history_tab)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels([
            self.tr("Time"), self.tr("Action"), self.tr("User"), self.tr("Comment")
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        history_layout.addWidget(self.history_table)
        
        self.tab_widget.addTab(self.history_tab, self.tr("History"))
        self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.history_tab), False)

        # Buttons
        self.btn_save = QPushButton(self.tr("Save Changes"))
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_save.setEnabled(False) # Only enabled if dirty
        layout.addWidget(self.btn_save)

        # Connect Change Signals for Dirty Tracking
        self.status_combo.currentIndexChanged.connect(self._mark_dirty)
        self.export_filename_edit.textChanged.connect(self._mark_dirty)
        self.tags_edit.tagsChanged.connect(self._mark_dirty)
        self.doc_types_combo.selectionChanged.connect(self._mark_dirty)
        self.direction_combo.currentIndexChanged.connect(self._mark_dirty)
        self.context_combo.currentIndexChanged.connect(self._mark_dirty)
        self.sender_edit.textChanged.connect(self._mark_dirty)
        self.date_edit.dateChanged.connect(self._mark_dirty)
        self.stamps_table.itemChanged.connect(self._mark_dirty)
        self.semantic_table.itemChanged.connect(self._mark_dirty)
        self.chk_pkv.toggled.connect(self._mark_dirty)

        # Payment field changes
        self.pay_recipient_edit.textChanged.connect(self._trigger_giro_refresh)
        self.pay_iban_edit.textChanged.connect(self._trigger_giro_refresh)
        self.pay_bic_edit.textChanged.connect(self._trigger_giro_refresh)
        self.pay_amount_edit.textChanged.connect(self._trigger_giro_refresh)
        self.pay_purpose_edit.textChanged.connect(self._trigger_giro_refresh)
        
        # Connect change signals for dirty tracking (also)
        for w in [self.pay_recipient_edit, self.pay_iban_edit, self.pay_bic_edit, 
                  self.pay_amount_edit, self.pay_purpose_edit]:
            w.textChanged.connect(self._mark_dirty)

    def on_workflow_transition(self, action: str, target_state: str):
        """Action handler for workflow button clicks."""
        if not self.current_uuids or not self.db_manager or not self.doc:
            return
            
        print(f"[Workflow-GUI] Triggering ACTION '{action}' -> '{target_state}'")
        
        # 1. Update In-Memory Object
        sd = self.doc.semantic_data
        if sd and sd.workflow:
            sd.workflow.apply_transition(action, target_state, user="USER", comment=self.tr("Action triggered via UI"))
            
            # If target state is 'PAID', we might want to update status to 'DONE' etc.
            # But the playbook should ideally define if a state is 'final'.
            # For now, we also sync the STATUS combo if it's a final state.
            
            # 2. Persist to DB
            for u in self.current_uuids:
                # In most cases it's just one, but we support batch if needed.
                self.db_manager.update_document_metadata(u, {"semantic_data": sd})
        
        # 3. Refresh UI
        self.display_documents([self.doc]) 
        self.metadata_saved.emit()
        show_notification(self, "Workflow Updated", f"State transitioned to {target_state}")

    def on_playbook_changed(self, new_pb_id: str):
        """Handler for manual playbook reassignment."""
        if not self.current_uuids or not self.db_manager or not self.doc:
            return
            
        print(f"[Workflow-GUI] Changing Playbook to '{new_pb_id}'")
        
        sd = self.doc.semantic_data
        if not sd: return
        
        if not sd.workflow:
            from core.models.semantic import WorkflowInfo
            sd.workflow = WorkflowInfo()
            
        sd.workflow.playbook_id = new_pb_id if new_pb_id else None
        # Reset step to NEW if changing playbook? Usually yes.
        sd.workflow.current_step = "NEW"
        
        # Log it
        from core.models.semantic import WorkflowLog
        sd.workflow.history.append(WorkflowLog(
            action=f"AGENT_CHANGE: {new_pb_id or 'NONE'}",
            comment="Manual reassignment"
        ))
        
        # Persist
        for u in self.current_uuids:
            self.db_manager.update_document_metadata(u, {"semantic_data": sd})
            
        self.display_documents([self.doc])
        self.metadata_saved.emit()
        show_notification(self, "Agent Updated", f"Workflow assigned: {new_pb_id or 'None'}")
        
        # Live Update Audit Window
        if self.audit_window and self.audit_window.isVisible():
            self.audit_window.display_document(self.doc)

    def open_audit_window(self):
        """Launches the non-modal audit/verification interface."""
        if not self.doc:
            show_notification(self, "Audit", "Please select a document first.")
            return

        if not self.audit_window:
            self.audit_window = AuditWindow(pipeline=getattr(self.db_manager, 'pipeline', None))
            self.audit_window.workflow_triggered.connect(self.on_workflow_transition)
            self.audit_window.closed.connect(self._on_audit_closed)
            
        self.audit_window.display_document(self.doc)
        self.audit_window.show()
        self.audit_window.raise_()

    def _on_audit_closed(self):
        self.audit_window = None

    def _mark_dirty(self):
        """Enable save button and update live workflow previews."""
        if getattr(self, "_locked_for_load", False):
            return
        self.btn_save.setEnabled(True)
        self.btn_save.setStyleSheet("background-color: #e8f5e9; font-weight: bold; border: 1px solid #c8e6c9;")
        
        # Phase 111: Hot-update workflow buttons as the user types
        if self.doc and self.doc.semantic_data:
            wf = self.doc.semantic_data.workflow
            if wf and wf.playbook_id:
                # Mock current data for the check
                current_data = {
                    "total_gross": self.pay_amount_edit.text(),
                    "iban": self.pay_iban_edit.text(),
                    "sender_name": self.sender_edit.text(),
                }
                self.workflow_controls.update_workflow(wf.playbook_id, wf.current_step, current_data)

    def _reset_dirty(self):
        """Disable save button and reset style."""
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("")

    def on_lock_clicked(self, checked):
        if not self.current_uuids or not self.db_manager:
            return
        new_state = self.chk_locked.isChecked()
        for uuid in self.current_uuids:
             self.db_manager.update_document_metadata(uuid, {"is_immutable": new_state})
        self.toggle_lock(new_state)
        self.metadata_saved.emit()

    def toggle_lock(self, checked):
        self.tab_widget.setEnabled(not checked)

    def display_documents(self, docs: list[Document]):
        self._locked_for_load = True
        self.doc = None
        self.current_uuids = [d.uuid for d in docs]

        if not docs:
            self.clear()
            return

        self.setEnabled(True)
        if len(docs) == 1:
            self.display_document(docs[0])
            self._reset_dirty()
            self._locked_for_load = False
            return

        # Batch Display (Simplified)
        with QSignalBlocker(self.chk_locked):
            is_immutable_values = {d.is_immutable for d in docs}
            if len(is_immutable_values) == 1:
                 val = is_immutable_values.pop()
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

        self.sender_edit.clear()
        self.sender_edit.setPlaceholderText("<Multiple Values>")

        self.source_viewer.setPlainText(self.tr("%n document(s) selected.", "", len(docs)))
        self.semantic_viewer.setPlainText("-")
        
        self._reset_dirty()
        self._locked_for_load = False

    def display_document(self, doc: Document):
        # Note: if called from display_documents, _locked_for_load is already True
        externally_locked = getattr(self, "_locked_for_load", False)
        self._locked_for_load = True
        self.current_uuids = [doc.uuid]
        self.doc = doc

        with QSignalBlocker(self.chk_locked):
             self.chk_locked.setChecked(doc.is_immutable)
        self.toggle_lock(doc.is_immutable)

        self.uuid_lbl.setText(doc.uuid)
        self.created_at_lbl.setText(format_datetime(doc.created_at) or "-")
        self.page_count_lbl.setText(str(doc.page_count) if doc.page_count is not None else "-")
        # Robust Status Sync (Case Insensitive)
        stat = (doc.status or "NEW").upper()
        # Use findData since we store the technical 'stat' as UserData in _init_ui
        idx = self.status_combo.findData(stat, Qt.ItemDataRole.UserRole, Qt.MatchFlag.MatchExactly)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)
        else:
            # Fallback if status not in our standard map (e.g. from DB migration)
            self.status_combo.setCurrentText(stat)

        self.export_filename_edit.setText(doc.original_filename or "")

        # Phase 106: Display User Tags from the dedicated 'tags' column
        user_tags = getattr(doc, "tags", []) or []
        if isinstance(user_tags, list):
            self.tags_edit.setTags(user_tags)
        else:
            self.tags_edit.setText(str(user_tags))

        # AI / Analysis Fields
        sd = doc.semantic_data  # This is a SemanticExtraction object in V2
        sd_dict = sd.model_dump() if sd else {}

        # Doc Types (Dynamic via Enum)
        dt = doc.type_tags or []
        self.doc_types_combo.setCheckedItems(dt)
        self.doc_types_combo.setPlaceholderText("") # Clear any residual placeholder

        # Directions & Context (Dynamic via standard values)
        # Robust case-insensitive sync
        dir_val = str(sd_dict.get("direction", "Unknown")).strip().upper()
        ctx_val = str(sd_dict.get("tenant_context", "Unknown")).strip().upper()
        
        # CTX_ prefix for context tags logic
        if ctx_val.startswith("CTX_"): ctx_val = ctx_val[4:]

        # Sync combos via data keys (using correct role and flags)
        idx_dir = self.direction_combo.findData(
            dir_val.title(), 
            role=Qt.ItemDataRole.UserRole, 
            flags=Qt.MatchFlag.MatchExactly
        )
        if idx_dir >= 0: 
            self.direction_combo.setCurrentIndex(idx_dir)
        else: 
            self.direction_combo.setCurrentText(dir_val.title())

        idx_ctx = self.context_combo.findData(
            ctx_val.title(), 
            role=Qt.ItemDataRole.UserRole, 
            flags=Qt.MatchFlag.MatchExactly
        )
        if idx_ctx >= 0: 
            self.context_combo.setCurrentIndex(idx_ctx)
        else: 
            self.context_combo.setCurrentText(ctx_val.title())

        # Stage 1.5 Stamps (Phase 105 Fix)
        # Check both direct 'layer_stamps' and nested 'visual_audit'
        audit_data = sd_dict.get("visual_audit") or sd_dict
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

        self._populate_semantic_table(sd_dict)

        # Phase 113: Auto-assign Playbook based on Tags if none is set
        if sd and (not getattr(sd, "workflow", None) or not sd.workflow.playbook_id):
            from core.workflow import WorkflowRegistry
            registry = WorkflowRegistry()
            # Try type tags first
            tags = doc.type_tags or []
            matched_pb = registry.find_playbook_for_tags(tags)
            if matched_pb:
                if not getattr(sd, "workflow", None):
                    from core.models.semantic import WorkflowInfo
                    sd.workflow = WorkflowInfo()
                
                print(f"[Workflow-GUI] Auto-assigning agent '{matched_pb.id}' for document {doc.uuid}")
                sd.workflow.playbook_id = matched_pb.id
                sd.workflow.current_step = "NEW"
                self._mark_dirty()

        # Workflow Logic (Dynamic)
        wf_data = getattr(sd, "workflow", None)
        playbook_id = wf_data.playbook_id if wf_data else None
        current_step = wf_data.current_step if wf_data else "NEW"
        
        # Prepare flat data for requirement check (e.g. amount, iban, etc.)
        # + Virtual time-based fields (Phase 112)
        now = datetime.now()
        
        doc_data_for_wf = {
            "total_gross": doc.total_amount,
            "iban": doc.iban,
            "sender_name": doc.sender_name,
            "doc_date": doc.doc_date,
            "doc_number": doc.doc_number,
            "AGE_DAYS": 0,
            "DAYS_IN_STATE": 0,
            "DAYS_UNTIL_DUE": 999
        }
        
        try:
            if doc.created_at:
                doc_data_for_wf["AGE_DAYS"] = (now - datetime.fromisoformat(doc.created_at)).days
            
            if wf_data and wf_data.history:
                last_ts = wf_data.history[-1].timestamp
                doc_data_for_wf["DAYS_IN_STATE"] = (now - datetime.fromisoformat(last_ts)).days
                
            if doc.due_date:
                # Handle YYYY-MM-DD by ensuring it looks like ISO
                dd_str = doc.due_date
                if len(dd_str) == 10: dd_str += "T00:00:00"
                doc_data_for_wf["DAYS_UNTIL_DUE"] = (datetime.fromisoformat(dd_str) - now).days
        except Exception as e:
            logger.debug(f"Time calculation failed: {e}")

        self.workflow_controls.update_workflow(playbook_id, current_step, doc_data_for_wf)
        
        # PKV Sync
        with QSignalBlocker(self.chk_pkv):
            self.chk_pkv.setChecked(wf_data.pkv_eligible if wf_data else False)

        # 112: Populate History
        self._populate_history_table(wf_data)

        # Extracted Data
        self.sender_edit.setText(doc.sender_name or "")

        # Date Handling
        doc_date = doc.doc_date
        if doc_date:
            from PyQt6.QtCore import QDate
            if isinstance(doc_date, str):
                qdate = QDate.fromString(doc_date, Qt.DateFormat.ISODate)
                if qdate.isValid(): self.date_edit.setDate(qdate)
            elif hasattr(doc_date, "isoformat"):
                self.date_edit.setDate(QDate.fromString(doc_date.isoformat(), Qt.DateFormat.ISODate))
        else:
            from PyQt6.QtCore import QDate
            self.date_edit.setDate(QDate(2000, 1, 1)) # Default

        # Payment / GiroCode Logic
        idx_payment = self.tab_widget.indexOf(self.payment_scroll)
        
        # Robust lookup for bank info
        # Check both the primary fields and fallback (Phase 125 Improved)
        iban = doc.iban or ""
        total = doc.total_amount
        sender = doc.sender_name or ""
        
        # Show payment tab for financial documents OR if payment info exists
        is_financial = any(t in ["INVOICE", "RECEIPT", "UTILITY_BILL", "EXPENSE_REPORT"] for t in (doc.type_tags or []))
        
        if is_financial or iban or (total and float(total) > 0):
            self.tab_widget.setTabVisible(idx_payment, True)
            self.pay_recipient_edit.setText(sender)
            self.pay_iban_edit.setText(iban)
            self.pay_bic_edit.setText(doc.bic or "")
            self.pay_amount_edit.setText(f"{float(total or 0):.2f}" if total is not None else "")
            self.pay_purpose_edit.setText(doc.doc_number or "")
            self.refresh_girocode()
        else:
            self.tab_widget.setTabVisible(idx_payment, False)
            self.qr_label.setPixmap(QPixmap())

        # Sync Audit Window if visible
        if self.audit_window and self.audit_window.isVisible():
            self.audit_window.display_document(doc)


        # Source Mapping
        try: # Added try-except block for source mapping parsing
            mapping = doc.extra_data.get("source_mapping")
            if mapping:
                try:
                    if isinstance(mapping, str): mapping_data = json.loads(mapping)
                    else: mapping_data = mapping
                    self.source_viewer.setPlainText(json.dumps(mapping_data, indent=2, ensure_ascii=False, default=str))
                except json.JSONDecodeError: # Specific exception for JSON parsing
                    self.source_viewer.setPlainText(str(mapping)) # Fallback to string if not valid JSON
            else:
                 self.source_viewer.setPlainText("No source mapping available.")
        except Exception as e:
            print(f"Error displaying source mapping: {e}")

        # Full Text & Semantic Data
        self.full_text_viewer.setPlainText(getattr(doc, "cached_full_text", ""))

        # Display raw semantic data (AI Results) for debugging
        if hasattr(doc, "semantic_data") and doc.semantic_data:
            # Pydantic model dump for JSON serialization
            try:
                if hasattr(doc.semantic_data, "model_dump"):
                    raw_data = doc.semantic_data.model_dump()
                else:
                    raw_data = doc.semantic_data
                self.semantic_viewer.setPlainText(json.dumps(raw_data, indent=2, ensure_ascii=False, default=str))
            except Exception as e:
                self.semantic_viewer.setPlainText(f"Error displaying semantic data: {e}")
        else:
            self.semantic_viewer.setPlainText("{}")
        
        if not externally_locked:
            self._reset_dirty()
            self._locked_for_load = False

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

    def _populate_history_table(self, wf_data):
        """Displays the audit log of workflow transitions."""
        self.history_table.setRowCount(0)
        idx_history = self.tab_widget.indexOf(self.history_tab)
        
        if not wf_data or not wf_data.history:
            self.tab_widget.setTabVisible(idx_history, False)
            return
            
        self.tab_widget.setTabVisible(idx_history, True)
        # Reverse display to show newest first
        for entry in reversed(wf_data.history):
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            
            # Timestamp formatting
            ts = format_datetime(entry.timestamp)
            
            self.history_table.setItem(row, 0, QTableWidgetItem(ts))
            self.history_table.setItem(row, 1, QTableWidgetItem(entry.action))
            self.history_table.setItem(row, 2, QTableWidgetItem(entry.user or "SYSTEM"))
            self.history_table.setItem(row, 3, QTableWidgetItem(entry.comment or ""))
            
        self.history_table.resizeRowsToContents()

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
                    new_json = json.dumps(new_data, ensure_ascii=False, default=str)

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
                             rows.append((section, key_path, json.dumps(v, ensure_ascii=False, default=str), "NESTED_TABLE"))
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
                rows.append((section, prefix, json.dumps(data, ensure_ascii=False, default=str)))

        # 1. Known Main Sections
        if "meta_header" in sd:
            traverse(sd["meta_header"], "Meta")
        if "custom_fields" in sd:
            traverse(sd["custom_fields"], "Custom")

        # 2. Bodies (Phase 107/110)
        handled_keys = {"meta_header", "custom_fields", "bodies", "visual_audit", "layer_stamps", "summary", "entity_types", "direction", "tenant_context"}

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

    def _trigger_giro_refresh(self):
        """Debounced GiroCode refresh."""
        self.giro_timer.start(500) # 500ms delay

    def refresh_girocode(self):
        """Generates and displays the EPC-QR Code (GiroCode)."""
        recipient = self.pay_recipient_edit.text().strip()
        iban = self.pay_iban_edit.text().strip()
        bic = self.pay_bic_edit.text().strip()
        amount_str = self.pay_amount_edit.text().strip().replace(",", ".")
        purpose = self.pay_purpose_edit.text().strip()

        if not all([recipient, iban, amount_str]):
            missing = []
            if not recipient: missing.append(self.tr("Recipient"))
            if not iban: missing.append(self.tr("IBAN"))
            if not amount_str: missing.append(self.tr("Amount"))
            
            self.qr_label.setText(self.tr("Incomplete data for GiroCode:\nMissing") + " " + ", ".join(missing))
            self.qr_label.setPixmap(QPixmap())
            return

        # Phase 125: Strict IBAN Checksum Verification before QR generation
        from core.utils.validation import validate_iban
        is_valid_iban = validate_iban(iban)
        
        # UI Feedback for IBAN field
        if iban and not is_valid_iban:
            self.pay_iban_edit.setStyleSheet("background-color: #ffebee; border: 1px solid #c62828;")
        else:
            self.pay_iban_edit.setStyleSheet("")

        if not is_valid_iban:
            self.qr_label.setText(self.tr("Invalid IBAN Checksum!\nCannot generate Payment Code."))
            self.qr_label.setPixmap(QPixmap())
            return

        try:
            amount = float(amount_str)
            payload = GiroCodeGenerator.generate_payload(
                recipient_name=recipient,
                iban=iban,
                amount=amount,
                purpose=purpose,
                bic=bic
            )
            
            img = GiroCodeGenerator.get_qr_image(payload)
            if img:
                # Convert PIL to QPixmap
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                qimg = QImage.fromData(buffer.getvalue())
                self.qr_label.setPixmap(QPixmap.fromImage(qimg).scaled(
                    150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                ))
            else:
                self.qr_label.setText(self.tr("QR Library not installed.\nPlease install 'qrcode' package."))
                self.qr_label.setPixmap(QPixmap())
        except ValueError:
            self.qr_label.setText(self.tr("Invalid Amount format."))
            self.qr_label.setPixmap(QPixmap())
        except Exception as e:
            self.qr_label.setText(self.tr("Error generating QR:") + " " + str(e))
            self.qr_label.setPixmap(QPixmap())

    def copy_girocode_payload(self):
        """Copies the current GiroCode payload to the clipboard."""
        recipient = self.pay_recipient_edit.text().strip()
        iban = self.pay_iban_edit.text().strip()
        amount_str = self.pay_amount_edit.text().strip().replace(",", ".")
        
        if not all([recipient, iban, amount_str]):
            show_notification(self, self.tr("Cannot copy: Incomplete GiroCode data."))
            return

        try:
            payload = GiroCodeGenerator.generate_payload(
                recipient_name=recipient,
                iban=iban,
                amount=float(amount_str),
                purpose=self.pay_purpose_edit.text().strip(),
                bic=self.pay_bic_edit.text().strip()
            )
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(payload)
            show_notification(self, self.tr("GiroCode payload copied to clipboard."))
        except Exception as e:
            show_selectable_message_box(self, self.tr("Copy Error"), str(e), icon=QMessageBox.Icon.Critical)

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
        dir_upper = direction.upper()
        ctx_upper = context.upper()
        
        if dir_upper != "UNKNOWN" and dir_upper not in final_tags:
            final_tags.append(dir_upper)
            
        if ctx_upper != "UNKNOWN":
            ctx_tag = f"CTX_{ctx_upper}"
            if ctx_tag not in final_tags:
                final_tags.append(ctx_tag)

        # Append Custom Tags
        for ct in custom_tags:
            if ct not in final_tags:
                final_tags.append(ct)

        updates = {
            "status": self.status_combo.currentData(),
            "export_filename": self.export_filename_edit.text().strip(),
            "type_tags": final_tags,
            "tags": custom_tags
        }

        # 2. Semantic Metadata (Extracted Data)
        # We merge existing semantic_data with UI changes
        from core.models.semantic import SemanticExtraction
        sd = self.doc.semantic_data if self.doc else None
        if not sd:
            sd = SemanticExtraction()

        sd.type_tags = final_tags
        sd.direction = direction.upper()
        sd.tenant_context = context.upper()
        
        # Workflow Persistence
        if not sd.workflow:
            from core.models.semantic import WorkflowInfo
            sd.workflow = WorkflowInfo()
        sd.workflow.pkv_eligible = self.chk_pkv.isChecked()

        # Phase 107: Automatic Pruning of mismatched semantic bodies
        mapping = {
            "INVOICE": "finance_body", "RECEIPT": "finance_body", "ORDER_CONFIRMATION": "finance_body",
            "DUNNING": "finance_body", "BANK_STATEMENT": "ledger_body", "CONTRACT": "legal_body",
            "OFFICIAL_LETTER": "legal_body", "PAYSLIP": "hr_body", "MEDICAL_DOCUMENT": "health_body",
            "UTILITY_BILL": "finance_body", "EXPENSE_REPORT": "travel_body"
        }
        allowed_bodies = {mapping.get(dt.upper()) for dt in doc_types if mapping.get(dt.upper())}
        # Keep bodies that are either allowed OR not in our known mapping
        sd.bodies = {k: v for k, v in sd.bodies.items() if k in allowed_bodies or k not in mapping.values()}

        # 3. Stamps Persistence
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

            if ":" in raw_type:
                parts = [p.strip() for p in raw_type.split(":", 1)]
                s_type = parts[0]
                label = parts[1]
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
                    "text": val,
                    "page": page_val,
                    "confidence": conf_val
                })

        sd_dict = sd.model_dump()
        sd_dict["visual_audit"] = sd_dict.get("visual_audit") or {}
        sd_dict["visual_audit"]["layer_stamps"] = stamps_list

        # 4. Semantic Table Persistence (Mapping Back)
        for r in range(self.semantic_table.rowCount()):
            item_sec = self.semantic_table.item(r, 0)
            item_key = self.semantic_table.item(r, 1)
            item_val = self.semantic_table.item(r, 2)
            if not item_sec or not item_key or not item_val: continue

            section = item_sec.text()
            field_path = item_key.text()
            val_text = item_val.text()
            if not field_path: continue

            # Map back to target dict
            root = sd_dict
            if section == "Meta":
                if "meta_header" not in sd_dict: sd_dict["meta_header"] = {}
                root = sd_dict["meta_header"]
            elif section == "Custom":
                if "custom_fields" not in sd_dict: sd_dict["custom_fields"] = {}
                root = sd_dict["custom_fields"]
            else:
                body_key = section.lower() + "_body"
                if "bodies" in sd_dict and (body_key in sd_dict["bodies"] or section.lower() in sd_dict["bodies"]):
                    if body_key in sd_dict["bodies"]: root = sd_dict["bodies"][body_key]
                    else: root = sd_dict["bodies"][section.lower()]
                elif section.lower() in sd_dict:
                    root = sd_dict[section.lower()]
                elif body_key in sd_dict:
                    root = sd_dict[body_key]
                else:
                    if "bodies" not in sd_dict: sd_dict["bodies"] = {}
                    sd_dict["bodies"][body_key] = {}
                    root = sd_dict["bodies"][body_key]

            parts = field_path.split(".")
            target = root
            for i, part in enumerate(parts[:-1]):
                if part.isdigit():
                    idx = int(part)
                    if isinstance(target, list):
                        while len(target) <= idx: target.append({})
                        target = target[idx]
                    else:
                        if part not in target: target[part] = {}
                        target = target[part]
                else:
                    if part not in target:
                        if i + 1 < len(parts) and parts[i+1].isdigit():
                            target[part] = []
                        else:
                            target[part] = {}
                    target = target[part]

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
            except (json.JSONDecodeError, ValueError):
                pass

            if isinstance(target, list) and last_key.isdigit():
                idx = int(last_key)
                while len(target) <= idx: target.append(None)
                target[idx] = typed_val
            else:
                target[last_key] = typed_val

        # Update root metadata in sd_dict
        if sd_dict.get("meta_header") is None: sd_dict["meta_header"] = {}
        if sd_dict["meta_header"].get("sender") is None: sd_dict["meta_header"]["sender"] = {}
        sd_dict["meta_header"]["sender"]["name"] = self.sender_edit.text().strip()
        
        if self.date_edit.date().year() > 2000:
             sd_dict["meta_header"]["doc_date"] = self.date_edit.date().toString(Qt.DateFormat.ISODate)
        
        # Re-validate back to SemanticExtraction model
        from core.models.semantic import SemanticExtraction
        updates["semantic_data"] = SemanticExtraction.model_validate(sd_dict)

        for uuid in self.current_uuids:
             self.db_manager.update_document_metadata(uuid, updates)

        self.metadata_saved.emit()
        self._reset_dirty()
        show_notification(self, self.tr("Saved"), self.tr("Changes saved to Database."))
