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
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFrame, QAbstractItemView,
    QPlainTextEdit, QScrollBar
)
from PyQt6.QtGui import QPixmap, QImage
import json
import io
import logging
from core.logger import get_logger, get_silent_logger

logger = get_logger("gui.metadata_editor")
from datetime import datetime
from PyQt6.QtCore import Qt, pyqtSignal, QSignalBlocker, QDate, QTimer, QLocale, QSize, QEvent
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

# Core Models
from core.models.semantic import SemanticExtraction, WorkflowInfo, SubscriptionInfo
from core.workflow import WorkflowRuleRegistry

class NestedTableDialog(QDialog):
    """Dialog for editing lists of objects (tables in tables)."""
    def __init__(self, data: List[Any], title: str, parent=None, read_only: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 500)
        self.data = data
        self.read_only = read_only
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

        if self.read_only:
            add_btn.setEnabled(False)
            remove_btn.setEnabled(False)
            save_btn.setText(self.tr("Close"))
            save_btn.setStyleSheet("")
            cancel_btn.hide()
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

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
        except (json.JSONDecodeError, ValueError) as e:
            # Fallback to text, but logging for clarity during debugging
            get_silent_logger().debug(f"JSON/Numeric parse fallback for '{text}': {e}")
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

    def __init__(self, db_manager: Optional[DatabaseManager] = None, pipeline: Optional[Any] = None) -> None:
        super().__init__()
        self.db_manager = db_manager
        self.pipeline = pipeline
        self.current_uuids = []
        self.doc = None
        self._locked_for_load = False
        self.audit_window = None
        
        # Debounce timer for GiroCode updates
        self.giro_timer = QTimer()
        self.giro_timer.setSingleShot(True)
        self.giro_timer.timeout.connect(self.refresh_girocode)
        
        self._init_ui()

    @staticmethod
    def _set_qdate(widget: QDateEdit, val: Optional[str]):
        """Helper to safely set a QDateEdit from an ISO string, defaulting to 1900-01-01."""
        if val:
            try:
                d = QDate.fromString(val, Qt.DateFormat.ISODate)
                if d.isValid():
                    widget.setDate(d)
                else:
                    widget.setDate(QDate(1900, 1, 1))
            except Exception:
                widget.setDate(QDate(1900, 1, 1))
        else:
            widget.setDate(QDate(1900, 1, 1))

    @staticmethod
    def _get_qdate_str(widget: QDateEdit) -> Optional[str]:
        """Helper to get ISO string from QDateEdit, returning None if date is 1900/1901 (unset)."""
        d = widget.date()
        if d.year() <= 1901:
            return None
        return d.toString(Qt.DateFormat.ISODate)

    def set_db_manager(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def sizeHint(self) -> QSize:
        return QSize(200, 300)

    def minimumSizeHint(self) -> QSize:
        return QSize(100, 100)

    def changeEvent(self, event: QEvent) -> None:
        """Handle language change events."""
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self) -> None:
        """Updates all UI strings for on-the-fly localization."""
        self.chk_locked.setText(self.tr("Locked (Immutable)"))
        self.btn_audit.setText(self.tr("🔍 Audit"))
        self.btn_audit.setToolTip(self.tr("Open side-by-side verification window"))
        
        # Labels in General Tab
        self.chk_pkv.setText(self.tr("Eligible for PKV Reimbursement"))
        self.lbl_uuid_prefix.setText(self.tr("UUID:"))
        self.lbl_created_at_prefix.setText(self.tr("Created At:"))
        self.lbl_page_count_prefix.setText(self.tr("Pages:"))
        self.lbl_status_prefix.setText(self.tr("Status:"))
        self.lbl_export_filename_prefix.setText(self.tr("Export Name:"))
        self.lbl_tags_prefix.setText(self.tr("Tags:"))
        self.tags_edit.setToolTip(self.tr("Custom Tags: Enter keywords, separated by commas or Enter."))
        self.archived_chk.setText(self.tr("Archived"))
        self.lbl_storage_location_prefix.setText(self.tr("Storage Location:"))
        
        # Status Combo
        current_data = self.status_combo.currentData()
        self.status_combo.blockSignals(True)
        self.status_combo.clear()
        for tech_val, display_name in self.STATUS_MAP.items():
            self.status_combo.addItem(self.tr(display_name), tech_val)
        idx = self.status_combo.findData(current_data)
        if idx >= 0: self.status_combo.setCurrentIndex(idx)
        self.status_combo.blockSignals(False)

        # Labels in Analysis Tab
        self.lbl_doc_types_prefix.setText(self.tr("Document Types:"))
        self.lbl_direction_prefix.setText(self.tr("Direction:"))
        self.lbl_context_prefix.setText(self.tr("Tenant Context:"))
        self.lbl_extracted_data_header.setText("--- " + self.tr("Extracted Data") + " ---")
        self.lbl_sender_prefix.setText(self.tr("Sender:"))
        self.lbl_date_prefix.setText(self.tr("Document Date:"))

        # Combos in Analysis Tab
        self.direction_combo.blockSignals(True)
        cur_dir = self.direction_combo.currentData()
        self.direction_combo.clear()
        for d in ["Inbound", "Outbound", "Internal", "Unknown"]:
            self.direction_combo.addItem(self.tr(d), d)
        idx = self.direction_combo.findData(cur_dir)
        if idx >= 0: self.direction_combo.setCurrentIndex(idx)
        self.direction_combo.blockSignals(False)

        self.context_combo.blockSignals(True)
        cur_ctx = self.context_combo.currentData()
        self.context_combo.clear()
        for c in ["Private", "Business", "Unknown"]:
            self.context_combo.addItem(self.tr(c), c)
        idx = self.context_combo.findData(cur_ctx)
        if idx >= 0: self.context_combo.setCurrentIndex(idx)
        self.context_combo.blockSignals(False)

        # Payment Tab
        self.lbl_pay_recipient_prefix.setText(self.tr("Recipient:"))
        self.lbl_pay_iban_prefix.setText(self.tr("IBAN:"))
        self.lbl_pay_bic_prefix.setText(self.tr("BIC:"))
        self.lbl_pay_amount_prefix.setText(self.tr("Amount:"))
        self.lbl_pay_purpose_prefix.setText(self.tr("Purpose:"))
        self.lbl_giro_header.setText(self.tr("GiroCode (EPC)"))
        self.lbl_giro_header.setToolTip(self.tr("Standardized QR code for SEPA transfers (EPC-QR)."))
        self.btn_copy_pay_payload.setText(self.tr("Copy Payload"))
        self.btn_copy_pay_payload.setToolTip(self.tr("Copy the raw GiroCode data for banking apps"))

        # Subscription Section
        self.lbl_pay_sub_header.setText("--- " + self.tr("Subscription / Recurring") + " ---")
        self.chk_pay_recurring.setText(self.tr("Recurring Payment / Subscription"))
        self.lbl_pay_freq_prefix.setText(self.tr("Frequency:"))
        self.lbl_pay_service_start_prefix.setText(self.tr("Service Start:"))
        self.lbl_pay_service_end_prefix.setText(self.tr("Service End:"))
        self.lbl_pay_next_billing_prefix.setText(self.tr("Next Billing:"))

        self.pay_freq_combo.blockSignals(True)
        cur_freq = self.pay_freq_combo.currentData()
        self.pay_freq_combo.clear()
        for f in ["Once", "Daily", "Weekly", "Monthly", "Quarterly", "Yearly"]:
            self.pay_freq_combo.addItem(self.tr(f), f.upper())
        idx_f = self.pay_freq_combo.findData(cur_freq)
        if idx_f >= 0: self.pay_freq_combo.setCurrentIndex(idx_f)
        self.pay_freq_combo.blockSignals(False)

        # Stamps Table
        self.stamps_table.setHorizontalHeaderLabels([
            self.tr("Type"), self.tr("Text"), self.tr("Page"), self.tr("Confidence")
        ])
        self.btn_add_stamp.setText(self.tr("Add Stamp"))
        self.btn_remove_stamp.setText(self.tr("Remove Selected"))

        # Semantic Data Table
        self.semantic_table.setHorizontalHeaderLabels([
            self.tr("Section"), self.tr("Field"), self.tr("Value")
        ])
        self.btn_add_semantic.setText(self.tr("Add Entry"))
        self.btn_remove_semantic.setText(self.tr("Remove Selected"))

        # History Table
        self.history_table.setHorizontalHeaderLabels([
            self.tr("Time"), self.tr("Action"), self.tr("User"), self.tr("Comment")
        ])

        # Tab Titles
        self.tab_widget.setTabText(0, self.tr("General"))
        self.tab_widget.setTabText(1, self.tr("Analysis"))
        self.tab_widget.setTabText(2, self.tr("Payment"))
        self.tab_widget.setTabText(3, self.tr("Subscriptions & Contracts"))
        self.tab_widget.setTabText(4, self.tr("Stamps"))
        self.tab_widget.setTabText(5, self.tr("Semantic Data"))
        self.tab_widget.setTabText(6, self.tr("Source Mapping"))
        self.tab_widget.setTabText(7, self.tr("Debug Data"))
        self.tab_widget.setTabText(8, self.tr("History"))

        # Subscription & Contract Labels
        self.lbl_sub_recurring_header.setText("--- " + self.tr("Subscription / Recurring") + " ---")
        self.chk_sub_recurring.setText(self.tr("Recurring Payment / Subscription"))
        self.lbl_sub_freq_prefix.setText(self.tr("Frequency:"))
        self.lbl_sub_next_billing_prefix.setText(self.tr("Next Billing:"))
        self.lbl_sub_service_start_prefix.setText(self.tr("Service Period Start:"))
        self.lbl_sub_service_end_prefix.setText(self.tr("Service Period End:"))
        
        self.lbl_sub_legal_header.setText("--- " + self.tr("Contract Details") + " ---")
        self.lbl_sub_contract_id_prefix.setText(self.tr("Contract ID:"))
        self.lbl_sub_effective_date_prefix.setText(self.tr("Effective Date:"))
        self.lbl_sub_valid_until_prefix.setText(self.tr("Valid Until:"))
        self.lbl_sub_renewal_prefix.setText(self.tr("Renewal Clause:"))
        
        self.lbl_sub_notice_header.setText("--- " + self.tr("Notice Period") + " ---")
        self.lbl_sub_notice_value_prefix.setText(self.tr("Value:"))
        self.lbl_sub_notice_unit_prefix.setText(self.tr("Unit:"))
        self.lbl_sub_notice_anchor_prefix.setText(self.tr("Anchor:"))
        self.lbl_sub_notice_text_prefix.setText(self.tr("Original Text:"))

        self.sub_freq_combo.blockSignals(True)
        cur_sub_f = self.sub_freq_combo.currentData()
        self.sub_freq_combo.clear()
        for f in ["Once", "Daily", "Weekly", "Monthly", "Quarterly", "Yearly"]:
            self.sub_freq_combo.addItem(self.tr(f), f.upper())
        idx_sub_f = self.sub_freq_combo.findData(cur_sub_f)
        if idx_sub_f >= 0: self.sub_freq_combo.setCurrentIndex(idx_sub_f)
        self.sub_freq_combo.blockSignals(False)

        self.sub_notice_unit_combo.blockSignals(True)
        cur_u = self.sub_notice_unit_combo.currentData()
        self.sub_notice_unit_combo.clear()
        self.sub_notice_unit_combo.addItem(self.tr("None"), None)
        self.sub_notice_unit_combo.addItem(self.tr("Days"), "DAYS")
        self.sub_notice_unit_combo.addItem(self.tr("Weeks"), "WEEKS")
        self.sub_notice_unit_combo.addItem(self.tr("Months"), "MONTHS")
        self.sub_notice_unit_combo.addItem(self.tr("Years"), "YEARS")
        idx_u = self.sub_notice_unit_combo.findData(cur_u)
        if idx_u >= 0: self.sub_notice_unit_combo.setCurrentIndex(idx_u)
        self.sub_notice_unit_combo.blockSignals(False)

        self.lbl_source_mapping_header.setText(self.tr("Physical Source Components:"))
        self.lbl_raw_virtual_header.setText(self.tr("Raw Virtual Document Storage:"))
        self.lbl_cached_full_text_header.setText(self.tr("Cached Full Text:"))
        self.btn_save.setText(self.tr("Save Changes"))

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Lock Checkbox
        lock_layout = QHBoxLayout()
        self.chk_locked = QCheckBox()
        self.chk_locked.clicked.connect(self.on_lock_clicked)
        lock_layout.addWidget(self.chk_locked)
        
        lock_layout.addStretch()
        
        # Phase 111: Dynamic Workflow Controls
        self.workflow_controls = WorkflowControlsWidget()
        self.workflow_controls.transition_triggered.connect(self.on_workflow_transition)
        self.workflow_controls.rule_changed.connect(self.on_rule_changed)
        lock_layout.addWidget(self.workflow_controls)
        
        self.btn_audit = QPushButton()
        self.btn_audit.setFixedHeight(28)
        self.btn_audit.setStyleSheet("""
            QPushButton {
                background-color: #ffffff; 
                color: #555; 
                border: 1px solid #ccc;
                font-size: 14px;
                padding: 0px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f8f9fa;
                border-color: #bbb;
            }
        """)
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
        self.chk_pkv = QCheckBox()
        general_layout.addRow("", self.chk_pkv)

        self.lbl_uuid_prefix = QLabel()
        self.uuid_lbl = QLabel()
        self.uuid_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        general_layout.addRow(self.lbl_uuid_prefix, self.uuid_lbl)

        self.lbl_created_at_prefix = QLabel()
        self.created_at_lbl = QLabel()
        general_layout.addRow(self.lbl_created_at_prefix, self.created_at_lbl)

        self.lbl_page_count_prefix = QLabel()
        self.page_count_lbl = QLabel()
        general_layout.addRow(self.lbl_page_count_prefix, self.page_count_lbl)

        self.lbl_status_prefix = QLabel()
        self.status_combo = QComboBox()
        self.status_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.status_combo.setMinimumWidth(150)
        general_layout.addRow(self.lbl_status_prefix, self.status_combo)

        self.lbl_export_filename_prefix = QLabel()
        self.export_filename_edit = QLineEdit()
        general_layout.addRow(self.lbl_export_filename_prefix, self.export_filename_edit)

        self.lbl_tags_prefix = QLabel()
        self.tags_edit = TagInputWidget()
        general_layout.addRow(self.lbl_tags_prefix, self.tags_edit)

        self.archived_chk = QCheckBox()
        general_layout.addRow("", self.archived_chk)
        
        self.lbl_storage_location_prefix = QLabel()
        self.storage_location_edit = QLineEdit()
        general_layout.addRow(self.lbl_storage_location_prefix, self.storage_location_edit)

        self.tab_widget.addTab(self.general_scroll, "")

        # --- Tab 2: Analysis & AI Core ---
        self.analysis_scroll = QScrollArea()
        self.analysis_scroll.setWidgetResizable(True)
        self.analysis_content = QWidget()
        self.analysis_scroll.setWidget(self.analysis_content)
        analysis_layout = QFormLayout(self.analysis_content)

        # Core Selectors
        self.lbl_doc_types_prefix = QLabel()
        self.doc_types_combo = MultiSelectComboBox()
        # Sort and clean DocType labels
        for t in sorted([t.value for t in DocType]):
            label = t.replace("_", " ").title()
            self.doc_types_combo.addItem(self.tr(label), data=t)
        analysis_layout.addRow(self.lbl_doc_types_prefix, self.doc_types_combo)

        self.lbl_direction_prefix = QLabel()
        self.direction_combo = QComboBox()
        self.direction_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.direction_combo.setMinimumWidth(120)
        analysis_layout.addRow(self.lbl_direction_prefix, self.direction_combo)

        self.lbl_context_prefix = QLabel()
        self.context_combo = QComboBox()
        self.context_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.context_combo.setMinimumWidth(120)
        analysis_layout.addRow(self.lbl_context_prefix, self.context_combo)

        self.lbl_extracted_data_header = QLabel()
        analysis_layout.addRow(self.lbl_extracted_data_header)

        self.lbl_sender_prefix = QLabel()
        self.sender_edit = QLineEdit()
        analysis_layout.addRow(self.lbl_sender_prefix, self.sender_edit)

        self.lbl_date_prefix = QLabel()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setSpecialValueText(" ") # Allow 'empty' look
        analysis_layout.addRow(self.lbl_date_prefix, self.date_edit)

        # Reasoning field removed to save space/tokens in AI output

        self.tab_widget.addTab(self.analysis_scroll, "")
        
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
        
        self.lbl_pay_recipient_prefix = QLabel()
        self.pay_recipient_edit = QLineEdit()
        self.lbl_pay_iban_prefix = QLabel()
        self.pay_iban_edit = QLineEdit()
        self.lbl_pay_bic_prefix = QLabel()
        self.pay_bic_edit = QLineEdit()
        self.lbl_pay_amount_prefix = QLabel()
        self.pay_amount_edit = QLineEdit()
        self.lbl_pay_purpose_prefix = QLabel()
        self.pay_purpose_edit = QLineEdit()

        payment_form.addRow(self.lbl_pay_recipient_prefix, self.pay_recipient_edit)
        payment_form.addRow(self.lbl_pay_iban_prefix, self.pay_iban_edit)
        payment_form.addRow(self.lbl_pay_bic_prefix, self.pay_bic_edit)
        payment_form.addRow(self.lbl_pay_amount_prefix, self.pay_amount_edit)
        payment_form.addRow(self.lbl_pay_purpose_prefix, self.pay_purpose_edit)
        
        # Subscription Sub-Section
        self.lbl_pay_sub_header = QLabel()
        self.lbl_pay_sub_header.setStyleSheet("font-weight: bold; margin-top: 10px; color: #555;")
        payment_form.addRow(self.lbl_pay_sub_header)
        
        self.chk_pay_recurring = QCheckBox()
        payment_form.addRow("", self.chk_pay_recurring)
        
        self.lbl_pay_freq_prefix = QLabel()
        self.pay_freq_combo = QComboBox()
        payment_form.addRow(self.lbl_pay_freq_prefix, self.pay_freq_combo)
        
        self.lbl_pay_service_start_prefix = QLabel()
        self.pay_service_start_edit = QDateEdit()
        self.pay_service_start_edit.setCalendarPopup(True)
        self.pay_service_start_edit.setDisplayFormat("dd.MM.yyyy")
        self.pay_service_start_edit.setSpecialValueText(" ")
        payment_form.addRow(self.lbl_pay_service_start_prefix, self.pay_service_start_edit)
        
        self.lbl_pay_service_end_prefix = QLabel()
        self.pay_service_end_edit = QDateEdit()
        self.pay_service_end_edit.setCalendarPopup(True)
        self.pay_service_end_edit.setDisplayFormat("dd.MM.yyyy")
        self.pay_service_end_edit.setSpecialValueText(" ")
        payment_form.addRow(self.lbl_pay_service_end_prefix, self.pay_service_end_edit)
        
        self.lbl_pay_next_billing_prefix = QLabel()
        self.pay_next_billing_edit = QDateEdit()
        self.pay_next_billing_edit.setCalendarPopup(True)
        self.pay_next_billing_edit.setDisplayFormat("dd.MM.yyyy")
        self.pay_next_billing_edit.setSpecialValueText(" ")
        payment_form.addRow(self.lbl_pay_next_billing_prefix, self.pay_next_billing_edit)
        
        fields_layout.addStretch()
        fields_layout.addLayout(payment_form)
        fields_layout.addStretch()
        payment_master_layout.addWidget(self.fields_container, 1)
        
        # Right Side: GiroCode & Actions
        self.qr_container = QWidget()
        # Removed hardcoded setMinimumWidth(320) to prevent window expansion
        qr_sub_layout = QVBoxLayout(self.qr_container)
        qr_sub_layout.addStretch()
        
        self.lbl_giro_header = QLabel()
        self.lbl_giro_header.setStyleSheet("font-weight: bold; color: #1565c0; font-size: 14px;")
        
        qr_btn_row = QHBoxLayout()
        qr_btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        qr_image_col = QVBoxLayout()
        qr_image_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        qr_image_col.addWidget(self.lbl_giro_header, 0, Qt.AlignmentFlag.AlignCenter)
        
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
        
        self.btn_copy_pay_payload = QPushButton()
        self.btn_copy_pay_payload.clicked.connect(self.copy_girocode_payload)
        btn_col.addWidget(self.btn_copy_pay_payload)
        
        qr_btn_row.addLayout(btn_col)
        qr_sub_layout.addLayout(qr_btn_row)
        qr_sub_layout.addStretch()
        payment_master_layout.addWidget(self.qr_container)

        self.tab_widget.addTab(self.payment_scroll, "")
        self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.payment_scroll), False)

        # --- Tab 3: Subscriptions & Contracts (Phase 138) ---
        self.sub_contract_scroll = QScrollArea()
        self.sub_contract_scroll.setWidgetResizable(True)
        self.sub_contract_tab = QWidget()
        self.sub_contract_scroll.setWidget(self.sub_contract_tab)
        sub_layout = QVBoxLayout(self.sub_contract_tab)
        sub_form = QFormLayout()
        
        # Section: Recurring Info
        self.lbl_sub_recurring_header = QLabel()
        self.lbl_sub_recurring_header.setStyleSheet("font-weight: bold; color: #1565c0;")
        sub_form.addRow(self.lbl_sub_recurring_header)
        
        self.chk_sub_recurring = QCheckBox()
        sub_form.addRow("", self.chk_sub_recurring)
        
        self.lbl_sub_freq_prefix = QLabel()
        self.sub_freq_combo = QComboBox()
        self.sub_freq_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        sub_form.addRow(self.lbl_sub_freq_prefix, self.sub_freq_combo)
        
        self.lbl_sub_next_billing_prefix = QLabel()
        self.sub_next_billing_edit = QDateEdit()
        self.sub_next_billing_edit.setCalendarPopup(True)
        self.sub_next_billing_edit.setDisplayFormat("dd.MM.yyyy")
        self.sub_next_billing_edit.setSpecialValueText(" ")
        sub_form.addRow(self.lbl_sub_next_billing_prefix, self.sub_next_billing_edit)

        self.lbl_sub_service_start_prefix = QLabel()
        self.sub_service_start_edit = QDateEdit()
        self.sub_service_start_edit.setCalendarPopup(True)
        self.sub_service_start_edit.setDisplayFormat("dd.MM.yyyy")
        self.sub_service_start_edit.setSpecialValueText(" ")
        sub_form.addRow(self.lbl_sub_service_start_prefix, self.sub_service_start_edit)
        
        self.lbl_sub_service_end_prefix = QLabel()
        self.sub_service_end_edit = QDateEdit()
        self.sub_service_end_edit.setCalendarPopup(True)
        self.sub_service_end_edit.setDisplayFormat("dd.MM.yyyy")
        self.sub_service_end_edit.setSpecialValueText(" ")
        sub_form.addRow(self.lbl_sub_service_end_prefix, self.sub_service_end_edit)

        # Section: Legal Details
        self.lbl_sub_legal_header = QLabel()
        self.lbl_sub_legal_header.setStyleSheet("font-weight: bold; color: #1565c0; margin-top: 15px;")
        sub_form.addRow(self.lbl_sub_legal_header)
        
        self.lbl_sub_contract_id_prefix = QLabel()
        self.sub_contract_id_edit = QLineEdit()
        sub_form.addRow(self.lbl_sub_contract_id_prefix, self.sub_contract_id_edit)
        
        self.lbl_sub_effective_date_prefix = QLabel()
        self.sub_effective_date_edit = QDateEdit()
        self.sub_effective_date_edit.setCalendarPopup(True)
        self.sub_effective_date_edit.setDisplayFormat("dd.MM.yyyy")
        self.sub_effective_date_edit.setSpecialValueText(" ")
        sub_form.addRow(self.lbl_sub_effective_date_prefix, self.sub_effective_date_edit)
        
        self.lbl_sub_valid_until_prefix = QLabel()
        self.sub_valid_until_edit = QDateEdit()
        self.sub_valid_until_edit.setCalendarPopup(True)
        self.sub_valid_until_edit.setDisplayFormat("dd.MM.yyyy")
        self.sub_valid_until_edit.setSpecialValueText(" ")
        sub_form.addRow(self.lbl_sub_valid_until_prefix, self.sub_valid_until_edit)
        
        self.lbl_sub_renewal_prefix = QLabel()
        self.sub_renewal_edit = QLineEdit()
        sub_form.addRow(self.lbl_sub_renewal_prefix, self.sub_renewal_edit)

        # Section: Notice Period
        self.lbl_sub_notice_header = QLabel()
        self.lbl_sub_notice_header.setStyleSheet("font-weight: bold; color: #1565c0; margin-top: 15px;")
        sub_form.addRow(self.lbl_sub_notice_header)
        
        self.lbl_sub_notice_value_prefix = QLabel()
        self.sub_notice_value_edit = QLineEdit()
        sub_form.addRow(self.lbl_sub_notice_value_prefix, self.sub_notice_value_edit)
        
        self.lbl_sub_notice_unit_prefix = QLabel()
        self.sub_notice_unit_combo = QComboBox()
        sub_form.addRow(self.lbl_sub_notice_unit_prefix, self.sub_notice_unit_combo)
        
        self.lbl_sub_notice_anchor_prefix = QLabel()
        self.sub_notice_anchor_edit = QLineEdit()
        sub_form.addRow(self.lbl_sub_notice_anchor_prefix, self.sub_notice_anchor_edit)
        
        self.lbl_sub_notice_text_prefix = QLabel()
        self.sub_notice_text_edit = QLineEdit()
        sub_form.addRow(self.lbl_sub_notice_text_prefix, self.sub_notice_text_edit)

        sub_layout.addLayout(sub_form)
        sub_layout.addStretch()
        
        self.tab_widget.addTab(self.sub_contract_scroll, "")
        self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.sub_contract_scroll), False)

        # --- Tab: Stamps (Stage 1.5) - Phase 105 ---
        self.stamps_tab = QWidget()
        stamps_layout = QVBoxLayout(self.stamps_tab)

        self.stamps_table = QTableWidget()
        self.stamps_table.setColumnCount(4)
        self.stamps_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.stamps_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.stamps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        stamps_layout.addWidget(self.stamps_table)

        stamps_btn_layout = QHBoxLayout()
        self.btn_add_stamp = QPushButton()
        self.btn_add_stamp.clicked.connect(self._add_stamp_row)
        self.btn_remove_stamp = QPushButton()
        self.btn_remove_stamp.clicked.connect(self._remove_selected_stamps)
        stamps_btn_layout.addWidget(self.btn_add_stamp)
        stamps_btn_layout.addWidget(self.btn_remove_stamp)
        stamps_btn_layout.addStretch()
        stamps_layout.addLayout(stamps_btn_layout)

        # Hide by default, shown in display_document
        self.tab_widget.addTab(self.stamps_tab, "")
        self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.stamps_tab), False)

        # --- Tab: Semantic Data (Phase 110) ---
        self.semantic_data_tab = QWidget()
        semantic_data_layout = QVBoxLayout(self.semantic_data_tab)

        self.semantic_table = QTableWidget()
        self.semantic_table.setColumnCount(3)
        self.semantic_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.semantic_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.semantic_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        semantic_data_layout.addWidget(self.semantic_table)

        semantic_btn_layout = QHBoxLayout()
        self.btn_add_semantic = QPushButton()
        self.btn_add_semantic.clicked.connect(self._add_semantic_row)
        self.btn_remove_semantic = QPushButton()
        self.btn_remove_semantic.clicked.connect(self._remove_selected_semantic)
        semantic_btn_layout.addWidget(self.btn_add_semantic)
        semantic_btn_layout.addWidget(self.btn_remove_semantic)
        semantic_btn_layout.addStretch()
        semantic_data_layout.addLayout(semantic_btn_layout)

        self.tab_widget.addTab(self.semantic_data_tab, "")
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
        self.lbl_source_mapping_header = QLabel()
        source_layout.addWidget(self.lbl_source_mapping_header)
        source_layout.addWidget(self.source_viewer)

        self.tab_widget.addTab(self.source_tab, "")



        # --- Tab 3: Raw Semantic Data ---
        self.semantic_tab = QWidget()
        semantic_layout = QVBoxLayout(self.semantic_tab)

        self.semantic_viewer = QTextEdit()
        self.semantic_viewer.setReadOnly(True)
        self.semantic_viewer.setFont(font)

        self.lbl_raw_virtual_header = QLabel()
        semantic_layout.addWidget(self.lbl_raw_virtual_header)
        semantic_layout.addWidget(self.semantic_viewer)

        self.lbl_cached_full_text_header = QLabel()
        semantic_layout.addWidget(self.lbl_cached_full_text_header)
        self.full_text_viewer = QTextEdit()
        self.full_text_viewer.setReadOnly(True)
        self.full_text_viewer.setFont(font)
        semantic_layout.addWidget(self.full_text_viewer)
        self.tab_widget.addTab(self.semantic_tab, "")

        # --- Tab: Workflow History (Phase 112) ---
        self.history_tab = QWidget()
        history_layout = QVBoxLayout(self.history_tab)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        history_layout.addWidget(self.history_table)
        
        self.tab_widget.addTab(self.history_tab, "")
        self.tab_widget.setTabVisible(self.tab_widget.indexOf(self.history_tab), False)

        # Buttons
        self.btn_save = QPushButton()
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_save.setEnabled(False) # Only enabled if dirty
        layout.addWidget(self.btn_save)

        self.retranslate_ui()

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
        self.archived_chk.toggled.connect(self._mark_dirty)
        self.storage_location_edit.textChanged.connect(self._mark_dirty)

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

    def on_workflow_transition(self, action: str, target_state: str, is_auto: bool = False):
        """Action handler for workflow button clicks."""
        if not self.current_uuids or not self.db_manager or not self.doc:
            return
            
        source = "SYSTEM" if is_auto else "USER"
        comment = self.tr("Auto-transition triggered") if is_auto else self.tr("Action triggered via UI")
        
        print(f"[Workflow-GUI] Triggering ACTION '{action}' -> '{target_state}' (Auto: {is_auto})")
        
        # 1. Update In-Memory Object
        sd = self.doc.semantic_data
        if sd and sd.workflow:
            sd.workflow.apply_transition(action, target_state, user=source, comment=comment)
            
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
        show_notification(self, self.tr("Workflow Updated"), self.tr("State transitioned to %1").replace("%1", target_state))

    def on_rule_changed(self, new_rule_id: str):
        """Handler for manual rule reassignment."""
        if not self.current_uuids or not self.db_manager or not self.doc:
            return
            
        print(f"[Workflow-GUI] Changing Rule to '{new_rule_id}'")
        
        sd = self.doc.semantic_data
        if not sd: return
        
        if not sd.workflow:
            from core.models.semantic import WorkflowInfo
            sd.workflow = WorkflowInfo()
            
        sd.workflow.rule_id = new_rule_id if new_rule_id else None
        # Reset step to NEW if changing rule? Usually yes.
        sd.workflow.current_step = "NEW"
        
        # Log it
        from core.models.semantic import WorkflowLog
        sd.workflow.history.append(WorkflowLog(
            action=f"RULE_CHANGE: {new_rule_id or 'NONE'}",
            comment="Manual reassignment"
        ))
        
        # Persist
        for u in self.current_uuids:
            self.db_manager.update_document_metadata(u, {"semantic_data": sd})
            
        self.display_documents([self.doc])
        self.metadata_saved.emit()
        show_notification(self, self.tr("Workflow Updated"), self.tr("Rule assigned: %1").replace("%1", new_rule_id or self.tr("None")))
        
        # Live Update Audit Window
        if self.audit_window and self.audit_window.isVisible():
            self.audit_window.display_document(self.doc)

    def open_audit_window(self):
        """Launches the non-modal audit/verification interface."""
        if not self.doc:
            show_notification(self, self.tr("Audit"), self.tr("Please select a document first."))
            return

        if not self.audit_window:
            self.audit_window = AuditWindow(pipeline=self.pipeline)
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
            if wf and wf.rule_id:
                # Mock current data for the check
                current_data = {
                    "total_gross": self.pay_amount_edit.text(),
                    "iban": self.pay_iban_edit.text(),
                    "sender_name": self.sender_edit.text(),
                }
                self.workflow_controls.update_workflow(wf.rule_id, wf.current_step, current_data)

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
        """
        Switches between Edit and Read-Only mode. 
        Instead of disabling the whole tab widget (which stops navigation),
        we selectively make input fields read-only or disabled.
        """
        # 1. Main Workflow Controls
        self.workflow_controls.setEnabled(not checked)
        
        # 2. Main Save Button
        if checked:
            self._reset_dirty() # This disables btn_save
        
        # 3. Tab Navigation stays active (self.tab_widget is NOT disabled)
        # We walk through all children of the tab widget
        for widget in self.tab_widget.findChildren(QWidget):
            # Skip container widgets to avoid disabling the whole layout
            if widget in [self.general_content, self.analysis_content, self.payment_tab, 
                         self.stamps_tab, self.semantic_data_tab, self.source_tab, self.semantic_tab]:
                continue
                
            # Scrollbars and headers should not be disabled
            if isinstance(widget, (QScrollBar, QHeaderView)):
                continue

            # Read-only for text inputs
            if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QDateEdit)):
                widget.setReadOnly(checked)
                
            # Disabled for purely interactive selection boxes / buttons
            elif isinstance(widget, (QComboBox, QCheckBox, QPushButton)):
                # Note: self.chk_locked is outside tab_widget, so it stays enabled
                widget.setEnabled(not checked)
                
            # Table-specific locking
            elif isinstance(widget, QTableWidget):
                trigger = QAbstractItemView.EditTrigger.NoEditTriggers if checked else \
                          (QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed)
                widget.setEditTriggers(trigger)
            
            # Special case for MultiSelectComboBox and TagInput (if they are children)
            elif hasattr(widget, "setReadOnly") and not isinstance(widget, QPushButton):
                try:
                    widget.setReadOnly(checked)
                except AttributeError:
                    widget.setEnabled(not checked)
            elif widget.__class__.__name__ in ["TagInputWidget", "MultiSelectComboBox"]:
                widget.setEnabled(not checked)

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

        self.archived_chk.setTristate(True)
        self.archived_chk.setCheckState(Qt.CheckState.PartiallyChecked)
        self.storage_location_edit.clear()
        self.storage_location_edit.setPlaceholderText("<Multiple Values>")

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

        self.archived_chk.setTristate(False)
        self.archived_chk.setChecked(bool(doc.archived))
        self.storage_location_edit.setText(doc.storage_location or "")

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
        # Update Subscription & Contract Tab (Phase 138)
        sub_info = sd_dict.get("bodies", {}).get("subscription_info") or sd_dict.get("subscription_info") or {}
        legal_body = sd_dict.get("bodies", {}).get("legal_body") or sd_dict.get("legal_body") or {}

        # Populate Recurring Info
        self.chk_sub_recurring.setChecked(bool(sub_info.get("is_recurring")))
        freq = str(sub_info.get("frequency") or "ONCE").upper()
        idx_f = self.sub_freq_combo.findData(freq)
        if idx_f >= 0: self.sub_freq_combo.setCurrentIndex(idx_f)
        
        self._set_qdate(self.sub_next_billing_edit, sub_info.get("next_billing_date"))
        self._set_qdate(self.sub_service_start_edit, sub_info.get("service_period_start"))
        self._set_qdate(self.sub_service_end_edit, sub_info.get("service_period_end"))
        
        # Populate Legal Details
        self.sub_contract_id_edit.setText(str(legal_body.get("contract_id") or ""))
        self._set_qdate(self.sub_effective_date_edit, legal_body.get("effective_date"))
        self._set_qdate(self.sub_valid_until_edit, legal_body.get("valid_until"))
        self.sub_renewal_edit.setText(str(legal_body.get("renewal_clause") or ""))
        
        # Populate Notice Period
        notice = legal_body.get("notice_period") or {}
        self.sub_notice_value_edit.setText(str(notice.get("value") or ""))
        n_unit = str(notice.get("unit") or "").upper()
        idx_u = self.sub_notice_unit_combo.findData(n_unit)
        if idx_u >= 0: self.sub_notice_unit_combo.setCurrentIndex(idx_u)
        
        self.sub_notice_anchor_edit.setText(str(notice.get("anchor_scope") or notice.get("anchor_type") or ""))
        self.sub_notice_text_edit.setText(str(notice.get("original_text") or ""))

        # Update Payment Tab (Legacy Subscription Fields)
        pay_sub_info = sd_dict.get("bodies", {}).get("subscription_info") or sd_dict.get("subscription_info")
        if isinstance(pay_sub_info, dict):
            self.chk_pay_recurring.setChecked(bool(pay_sub_info.get("is_recurring")))
            freq = str(pay_sub_info.get("frequency") or "ONCE").upper()
            idx_f = self.pay_freq_combo.findData(freq)
            if idx_f >= 0: self.pay_freq_combo.setCurrentIndex(idx_f)
            
            self._set_qdate(self.pay_service_start_edit, pay_sub_info.get("service_period_start"))
            self._set_qdate(self.pay_service_end_edit, pay_sub_info.get("service_period_end"))
            self._set_qdate(self.pay_next_billing_edit, pay_sub_info.get("next_billing_date"))
        else:
            self.chk_pay_recurring.setChecked(False)
            self.pay_freq_combo.setCurrentIndex(0)
            self.pay_service_start_edit.setDate(QDate(1900, 1, 1))
            self.pay_service_end_edit.setDate(QDate(1900, 1, 1))
            self.pay_next_billing_edit.setDate(QDate(1900, 1, 1))

        self._populate_semantic_table(sd_dict)

        # Workflow Logic
        if sd and (not getattr(sd, "workflow", None) or not sd.workflow.rule_id):
            from core.workflow import WorkflowRuleRegistry
            registry = WorkflowRuleRegistry()
            tags = doc.type_tags or []
            matched_pb = registry.find_rule_for_tags(tags)
            if matched_pb:
                if not getattr(sd, "workflow", None):
                    sd.workflow = WorkflowInfo()
                sd.workflow.rule_id = matched_pb.id
                sd.workflow.current_step = "NEW"
                self._mark_dirty()

        wf_data = getattr(sd, "workflow", None)
        rule_id = wf_data.rule_id if wf_data else None
        current_step = wf_data.current_step if wf_data else "NEW"
        
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
                dd_str = doc.due_date
                if len(dd_str) == 10: dd_str += "T00:00:00"
                doc_data_for_wf["DAYS_UNTIL_DUE"] = (datetime.fromisoformat(dd_str) - now).days
        except Exception as e:
             logger.debug(f"Workflow date calculation skipped: {e}")

        self.workflow_controls.update_workflow(rule_id, current_step, doc_data_for_wf)
        
        with QSignalBlocker(self.chk_pkv):
            self.chk_pkv.setChecked(wf_data.pkv_eligible if wf_data else False)

        self._populate_history_table(wf_data)

        # Extracted Data
        self.sender_edit.setText(doc.sender_name or "")

        # Date Handling
        doc_date = doc.doc_date
        if doc_date:
            if isinstance(doc_date, str):
                qdate = QDate.fromString(doc_date, Qt.DateFormat.ISODate)
                if qdate.isValid(): self.date_edit.setDate(qdate)
            elif hasattr(doc_date, "isoformat"):
                self.date_edit.setDate(QDate.fromString(doc_date.isoformat(), Qt.DateFormat.ISODate))
        else:
            self.date_edit.setDate(QDate(1900, 1, 1))

        # Payment / GiroCode Logic
        iban = doc.iban or ""
        total = doc.total_amount
        sender = doc.sender_name or ""
        
        # We handle visibility centrally via _update_tab_visibility now
        self.pay_recipient_edit.setText(sender)
        self.pay_iban_edit.setText(iban)
        self.pay_bic_edit.setText(doc.bic or "")
        self.pay_amount_edit.setText(f"{float(total or 0):.2f}" if total is not None else "")
        self.pay_purpose_edit.setText(doc.doc_number or "")
        self.refresh_girocode()

        # Sync Audit Window
        if self.audit_window and self.audit_window.isVisible():
            self.audit_window.display_document(doc)

        # Source Mapping
        try:
            mapping = doc.source_mapping
            if mapping:
                resolved_mapping = []
                for segment in mapping:
                    seg_dict = segment.model_dump()
                    if self.db_manager:
                        p_file = self.db_manager.get_physical_file(segment.file_uuid)
                        if p_file:
                            seg_dict["vault_filename"] = p_file.get("original_filename")
                            seg_dict["vault_path"] = p_file.get("file_path")
                    resolved_mapping.append(seg_dict)
                self.source_viewer.setPlainText(json.dumps(resolved_mapping, indent=2, ensure_ascii=False, default=str))
            else:
                 self.source_viewer.setPlainText(self.tr("No source mapping available."))
        except Exception as e:
            self.source_viewer.setPlainText(f"Error: {e}")

        # Full Text & Semantic Data
        self.full_text_viewer.setPlainText(getattr(doc, "cached_full_text", ""))

        if hasattr(doc, "semantic_data") and doc.semantic_data:
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
        
        # CALL CENTRAL VISIBILITY HELPER (Phase 138+)
        self._update_tab_visibility(doc, sd_dict)

        if not externally_locked:
            self._reset_dirty()
            self._locked_for_load = False

    def _update_tab_visibility(self, doc: Document, sd_dict: Dict[str, Any]):
        """General helper to hide/show tabs based on document data content (Universal Rule)."""
        # 0: General
        has_general = any([
            doc.uuid, doc.status, doc.original_filename, doc.tags,
            doc.archived, doc.storage_location
        ])
        self.tab_widget.setTabVisible(0, bool(has_general))

        # 1: Analysis
        has_analysis = any([
            doc.type_tags, sd_dict.get("direction"), sd_dict.get("tenant_context"),
            doc.sender_name, doc.doc_date
        ])
        self.tab_widget.setTabVisible(1, bool(has_analysis))

        # 2: Payment
        relevant_pay_types = {"INVOICE", "RECEIPT", "UTILITY_BILL", "EXPENSE_REPORT"}
        has_pay_type = any(t.upper() in relevant_pay_types for t in (doc.type_tags or []))
        has_pay_data = any([doc.iban, doc.bic, doc.total_amount, doc.doc_number])
        self.tab_widget.setTabVisible(2, has_pay_type or has_pay_data)

        # 3: Subscriptions & Contracts
        sub_info = sd_dict.get("bodies", {}).get("subscription_info") or sd_dict.get("subscription_info") or {}
        legal_body = sd_dict.get("bodies", {}).get("legal_body") or sd_dict.get("legal_body") or {}
        contract_types = {"CONTRACT", "INSURANCE_POLICY", "MEMBERSHIP_DOC"}
        has_contract_type = any(t.upper() in contract_types for t in (doc.type_tags or []))
        has_sub_data = bool(sub_info.get("is_recurring")) or any(v for k, v in sub_info.items() if v and k != "is_recurring")
        has_legal_data = any(v for v in legal_body.values() if v)
        self.tab_widget.setTabVisible(3, has_contract_type or has_sub_data or has_legal_data)

        # 4: Stamps
        audit_data = sd_dict.get("visual_audit") or sd_dict
        stamps = audit_data.get("layer_stamps") or audit_data.get("stamps") or []
        self.tab_widget.setTabVisible(4, bool(stamps))

        # 5: Semantic Data (Table)
        # Deep check for meaningful semantic content
        def is_meaningful(val):
            if isinstance(val, dict):
                return any(is_meaningful(v) for v in val.values())
            if isinstance(val, list):
                return any(is_meaningful(v) for v in val)
            return val is not None and val != "" and val is not False

        has_meaningful_semantic = False
        if sd_dict:
            # 1. Check custom fields
            if sd_dict.get("custom_fields") and is_meaningful(sd_dict["custom_fields"]):
                has_meaningful_semantic = True
            # 2. Check bodies (excluding default empty ones)
            elif sd_dict.get("bodies"):
                for k, v in sd_dict["bodies"].items():
                    if v and is_meaningful(v):
                        has_meaningful_semantic = True
                        break
        
        self.tab_widget.setTabVisible(5, has_meaningful_semantic)

        # 6: Source Mapping
        has_source = bool(doc.source_mapping)
        self.tab_widget.setTabVisible(6, has_source)

        # 7: Raw Semanticviewer / Debug Data
        has_raw_sd = bool(sd_dict) and sd_dict != {}
        self.tab_widget.setTabVisible(7, has_raw_sd)

        # 8: History
        wf_data = getattr(doc.semantic_data, "workflow", None) if doc.semantic_data else None
        has_history = bool(wf_data and wf_data.history)
        self.tab_widget.setTabVisible(8, has_history)

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
                is_read_only = self.chk_locked.isChecked()
                dlg = NestedTableDialog(data, f"Edit List: {key_path}", self, read_only=is_read_only)
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
            "tags": custom_tags,
            "archived": int(self.archived_chk.isChecked()),
            "storage_location": self.storage_location_edit.text().strip()
        }

        # 2. Semantic Metadata (Extracted Data)
        # We merge existing semantic_data with UI changes
        sd = self.doc.semantic_data if self.doc else None
        if not sd:
            sd = SemanticExtraction()

        sd.type_tags = final_tags
        sd.direction = direction.upper()
        sd.tenant_context = context.upper()
        
        # Workflow Persistence
        if not sd.workflow:
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

        sd_dict_final = sd.model_dump()
        sd_dict_final["visual_audit"] = sd_dict_final.get("visual_audit") or {}
        sd_dict_final["visual_audit"]["layer_stamps"] = stamps_list

        # Reconstruct SubscriptionInfo
        sub_info = {
            "is_recurring": self.chk_sub_recurring.isChecked(),
            "frequency": self.sub_freq_combo.currentData(),
            "next_billing_date": self._get_qdate_str(self.sub_next_billing_edit),
            "service_period_start": self._get_qdate_str(self.sub_service_start_edit),
            "service_period_end": self._get_qdate_str(self.sub_service_end_edit)
        }
        
        # Reconstruct LegalBody
        try:
            val_text = self.sub_notice_value_edit.text().strip()
            n_val = int(val_text) if val_text.isdigit() else None
        except Exception:
             n_val = None
        
        legal_body = {
            "contract_id": self.sub_contract_id_edit.text().strip() or None,
            "effective_date": self._get_qdate_str(self.sub_effective_date_edit),
            "valid_until": self._get_qdate_str(self.sub_valid_until_edit),
            "renewal_clause": self.sub_renewal_edit.text().strip() or None,
            "notice_period": {
                "value": n_val,
                "unit": self.sub_notice_unit_combo.currentData(),
                "original_text": self.sub_notice_text_edit.text().strip() or None
            }
        }
        
        if "bodies" not in sd_dict_final: sd_dict_final["bodies"] = {}
        sd_dict_final["bodies"]["subscription_info"] = sub_info
        
        # Merge legal_body into existing one if present to preserve issuer/beneficiary not in UI
        existing_legal = sd_dict_final["bodies"].get("legal_body") or {}
        existing_legal.update({k: v for k, v in legal_body.items() if v is not None})
        sd_dict_final["bodies"]["legal_body"] = existing_legal

        # 4. Payment Tab Subscription Persistence (Legacy)
        if self.chk_pay_recurring.isChecked():
            pay_sub_info = {
                "is_recurring": True,
                "frequency": self.pay_freq_combo.currentData(),
                "service_period_start": self._get_qdate_str(self.pay_service_start_edit),
                "service_period_end": self._get_qdate_str(self.pay_service_end_edit),
                "next_billing_date": self._get_qdate_str(self.pay_next_billing_edit)
            }
            if "bodies" not in sd_dict_final: sd_dict_final["bodies"] = {}
            sd_dict_final["bodies"]["subscription_info"] = pay_sub_info
        else:
            if "bodies" in sd_dict_final:
                sd_dict_final["bodies"].pop("subscription_info", None)

        # 5. Semantic Table Persistence (Mapping Back)
        for r in range(self.semantic_table.rowCount()):
            item_sec = self.semantic_table.item(r, 0)
            item_key = self.semantic_table.item(r, 1)
            item_val = self.semantic_table.item(r, 2)
            if not item_sec or not item_key or not item_val:
                continue

            section = item_sec.text()
            field_path = item_key.text()
            val_text = item_val.text()
            if not field_path:
                continue

            # Map back to target dict
            root = sd_dict_final
            if section == "Meta":
                if "meta_header" not in sd_dict_final:
                    sd_dict_final["meta_header"] = {}
                root = sd_dict_final["meta_header"]
            elif section == "Custom":
                if "custom_fields" not in sd_dict_final:
                    sd_dict_final["custom_fields"] = {}
                root = sd_dict_final["custom_fields"]
            else:
                body_key = section.lower() + "_body"
                if "bodies" in sd_dict_final and (body_key in sd_dict_final["bodies"] or section.lower() in sd_dict_final["bodies"]):
                    if body_key in sd_dict_final["bodies"]:
                        root = sd_dict_final["bodies"][body_key]
                    else:
                        root = sd_dict_final["bodies"][section.lower()]
                elif section.lower() in sd_dict_final:
                    root = sd_dict_final[section.lower()]
                elif body_key in sd_dict_final:
                    root = sd_dict_final[body_key]
                else:
                    if "bodies" not in sd_dict_final:
                        sd_dict_final["bodies"] = {}
                    if body_key not in sd_dict_final["bodies"]:
                        sd_dict_final["bodies"][body_key] = {}
                    root = sd_dict_final["bodies"][body_key]

            parts = field_path.split(".")
            target = root
            for i, part in enumerate(parts[:-1]):
                if part.isdigit():
                    idx = int(part)
                    if isinstance(target, list):
                        while len(target) <= idx:
                            target.append({})
                        target = target[idx]
                    else:
                        if part not in target:
                            target[part] = {}
                        target = target[part]
                else:
                    if part not in target:
                        if i + 1 < len(parts) and parts[i + 1].isdigit():
                            target[part] = []
                        else:
                            target[part] = {}
                    target = target[part]

            last_key = parts[-1]
            typed_val = val_text
            try:
                if val_text.strip().startswith(("[", "{")):
                    typed_val = json.loads(val_text)
                elif val_text.lower() == "true":
                    typed_val = True
                elif val_text.lower() == "false":
                    typed_val = False
                elif not val_text:
                    typed_val = None
                elif "." in val_text and val_text.replace(".", "", 1).isdigit():
                    typed_val = float(val_text)
                elif val_text.isdigit():
                    typed_val = int(val_text)
            except (json.JSONDecodeError, ValueError) as e:
                get_silent_logger().debug(f"Metadata auto-typing failed for '{val_text}': {e}")

            if isinstance(target, list) and last_key.isdigit():
                idx = int(last_key)
                while len(target) <= idx:
                    target.append(None)
                target[idx] = typed_val
            else:
                target[last_key] = typed_val

        # Update root metadata in sd_dict_final
        if sd_dict_final.get("meta_header") is None: sd_dict_final["meta_header"] = {}
        if sd_dict_final["meta_header"].get("sender") is None: sd_dict_final["meta_header"]["sender"] = {}
        sd_dict_final["meta_header"]["sender"]["name"] = self.sender_edit.text().strip()
        
        if self.date_edit.date().year() > 2000:
             sd_dict_final["meta_header"]["doc_date"] = self.date_edit.date().toString(Qt.DateFormat.ISODate)
        
        # Re-validate back to SemanticExtraction model
        try:
             # Prune empty bodies if they were created during traversal
             if "bodies" in sd_dict_final:
                 sd_dict_final["bodies"] = {k: v for k, v in sd_dict_final["bodies"].items() if v}
             
             updated_sd = SemanticExtraction.model_validate(sd_dict_final)
             updates["semantic_data"] = updated_sd
        except Exception as e:
             logger.error(f"Failed to validate updated semantic data: {e}")
             pass

        for uuid in self.current_uuids:
             self.db_manager.update_document_metadata(uuid, updates)

        self.metadata_saved.emit()
        self._reset_dirty()
        show_notification(self, self.tr("Saved"), self.tr("Changes saved to Database."))
