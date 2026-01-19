
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QMessageBox, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QDateEdit, QComboBox, QCompleter, QCheckBox, QFileDialog
)
import json
import datetime
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QLocale, QSignalBlocker
from core.document import Document
from core.document import Document
from core.database import DatabaseManager
from core.vocabulary import VocabularyManager
from gui.utils import format_date, format_datetime
from core.metadata_normalizer import MetadataNormalizer
from core.semantic_translator import SemanticTranslator
from gui.widgets.multi_select_combo import MultiSelectComboBox
from PyQt6.QtWidgets import QGroupBox, QCompleter
from PyQt6.QtCore import QStringListModel
from gui.completers import MultiTagCompleter

class MetadataEditorWidget(QWidget):
    """
    Widget to edit document metadata with extended fields organized in tabs.
    """
    metadata_saved = pyqtSignal()

    def __init__(self, db_manager: DatabaseManager = None):
        super().__init__()
        self.db_manager = db_manager
        self.vocabulary = VocabularyManager()
        self.current_uuids = []
        self.mixed_fields = set()
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
        
        self.updated_at_lbl = QLabel()
        general_layout.addRow(self.tr("Updated At:"), self.updated_at_lbl)
        
        self.page_count_lbl = QLabel()
        general_layout.addRow(self.tr("Pages:"), self.page_count_lbl)
        
        self.sender_edit = QLineEdit()
        general_layout.addRow(self.tr("Sender (Summary):"), self.sender_edit)
        
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        # Force 4-digit year as requested ("17.12.2025")
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        # Initial invalid date to represent "None" if needed? 
        # For simplicity, we just set Date. Empty is hard.
        # Let's add a "Clear Date" action or button? 
        # Or just accept that a document has a date (default today).
        # User said "Eingabehilfe", implies calendar.
        general_layout.addRow(self.tr("Date:"), self.date_edit)
        
        self.amount_edit = QLineEdit()
        # Rename to "Netto-Betrag"
        general_layout.addRow(self.tr("Netto-Betrag:"), self.amount_edit)
        
        self.gross_amount_edit = QLineEdit()
        general_layout.addRow(self.tr("Brutto-Betrag:"), self.gross_amount_edit)
        
        # Financial Row (Postage, Packaging, Tax, Currency)
        # We use a Grid or HBoxes. Let's use simple rows for now or grouped.
        
        self.postage_edit = QLineEdit()
        general_layout.addRow(self.tr("Porto:"), self.postage_edit)
        
        self.packaging_edit = QLineEdit()
        general_layout.addRow(self.tr("Verpackung:"), self.packaging_edit)
        
        self.tax_rate_edit = QLineEdit()
        general_layout.addRow(self.tr("Tax %:"), self.tax_rate_edit)
        
        self.currency_edit = QLineEdit()
        general_layout.addRow(self.tr("Währung:"), self.currency_edit)
        
        self.type_edit = MultiSelectComboBox()
        self.type_edit.setEditable(True)
        self.type_edit.addItems(self.vocabulary.get_all_types())
        general_layout.addRow(self.tr("Type:"), self.type_edit)
        
        # Export Filename
        export_container = QWidget()
        export_layout = QHBoxLayout(export_container)
        export_layout.setContentsMargins(0, 0, 0, 0)
        self.export_filename_edit = QLineEdit()
        self.btn_regen_export = QPushButton("↺")
        self.btn_regen_export.setToolTip(self.tr("Regenerate Filename based on Sender/Type/Date"))
        self.btn_regen_export.clicked.connect(self.regenerate_export_filename)
        self.btn_regen_export.setFixedWidth(30)
        export_layout.addWidget(self.export_filename_edit)
        export_layout.addWidget(self.btn_regen_export)
        general_layout.addRow(self.tr("Export Filename:"), export_container)
        
        self.iban_edit = QLineEdit()
        general_layout.addRow(self.tr("IBAN:"), self.iban_edit)
        
        self.phone_edit = QLineEdit()
        general_layout.addRow(self.tr("Phone:"), self.phone_edit)
        
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Tag1, Tag2...")
        
        # Completer for tags (Custom Multi-Tag support)
        # We need to refresh this when DB changes
        self.tags_completer = MultiTagCompleter([], self)
        self.tags_edit.setCompleter(self.tags_completer)
        
        general_layout.addRow(self.tr("Tags:"), self.tags_edit)
        
        self.tab_widget.addTab(self.general_scroll, self.tr("General"))
        
        # --- Tab 2: Sender Details ---
        self.sender_scroll = QScrollArea()
        self.sender_scroll.setWidgetResizable(True)
        self.sender_content = QWidget()
        self.sender_scroll.setWidget(self.sender_content)
        
        sender_layout = QFormLayout(self.sender_content)
        
        self.sender_company_edit = QLineEdit()
        sender_layout.addRow(self.tr("Company:"), self.sender_company_edit)
        
        self.sender_name_edit = QLineEdit()
        sender_layout.addRow(self.tr("Name:"), self.sender_name_edit)
        
        self.sender_street_edit = QLineEdit()
        sender_layout.addRow(self.tr("Street:"), self.sender_street_edit)
        
        self.sender_zip_edit = QLineEdit()
        sender_layout.addRow(self.tr("ZIP:"), self.sender_zip_edit)
        
        self.sender_city_edit = QLineEdit()
        sender_layout.addRow(self.tr("City:"), self.sender_city_edit)
        
        self.sender_country_edit = QLineEdit()
        sender_layout.addRow(self.tr("Country:"), self.sender_country_edit)
        
        self.sender_address_raw = QTextEdit()
        self.sender_address_raw.setMaximumHeight(60)
        sender_layout.addRow(self.tr("Full Address (Raw):"), self.sender_address_raw)
        
        self.tab_widget.addTab(self.sender_scroll, self.tr("Sender"))
        
        # --- Tab 3: Recipient Details ---
        self.recipient_scroll = QScrollArea()
        self.recipient_scroll.setWidgetResizable(True)
        self.recipient_content = QWidget()
        self.recipient_scroll.setWidget(self.recipient_content)
        
        recipient_layout = QFormLayout(self.recipient_content)
        
        self.recipient_company_edit = QLineEdit()
        recipient_layout.addRow(self.tr("Company:"), self.recipient_company_edit)
        
        self.recipient_name_edit = QLineEdit()
        recipient_layout.addRow(self.tr("Name:"), self.recipient_name_edit)
        
        self.recipient_street_edit = QLineEdit()
        recipient_layout.addRow(self.tr("Street:"), self.recipient_street_edit)
        
        self.recipient_zip_edit = QLineEdit()
        recipient_layout.addRow(self.tr("ZIP:"), self.recipient_zip_edit)
        
        self.recipient_city_edit = QLineEdit()
        recipient_layout.addRow(self.tr("City:"), self.recipient_city_edit)
        
        self.recipient_country_edit = QLineEdit()
        recipient_layout.addRow(self.tr("Country:"), self.recipient_country_edit)

        self.tab_widget.addTab(self.recipient_scroll, self.tr("Recipient"))
        
        # --- Tab 4: Extra JSON Data ---
        self.extra_tab = QWidget()
        extra_layout = QVBoxLayout(self.extra_tab)
        
        self.extra_table = QTableWidget()
        self.extra_table.setColumnCount(2)
        self.extra_table.setHorizontalHeaderLabels([self.tr("Key"), self.tr("Value")])
        self.extra_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.extra_table.setAlternatingRowColors(True)
        
        # Toolbar for adding keys?
        extra_tools = QHBoxLayout()
        self.btn_add_key = QPushButton("+")
        self.btn_add_key.setToolTip(self.tr("Add new field"))
        self.btn_add_key.clicked.connect(self.add_extra_field)
        self.btn_remove_key = QPushButton("-")
        self.btn_remove_key.setToolTip(self.tr("Remove selected field"))
        self.btn_remove_key.clicked.connect(self.remove_extra_field)
        
        extra_tools.addWidget(self.btn_add_key)
        extra_tools.addWidget(self.btn_remove_key)
        extra_tools.addStretch()
        
        extra_layout.addLayout(extra_tools)
        extra_layout.addWidget(self.extra_table)
        
        self.tab_widget.addTab(self.extra_tab, self.tr("Extra Data"))

        # --- Tab 5: Formatted Metadata (Type-Based) ---
        self.normalized_scroll = QScrollArea()
        self.normalized_scroll.setWidgetResizable(True)
        self.normalized_content = QWidget()
        self.normalized_scroll.setWidget(self.normalized_content)
        self.normalized_layout = QVBoxLayout(self.normalized_content)
        # We will populate this dynamically in display_document
        
        self.tab_widget.addTab(self.normalized_scroll, self.tr("Type Data"))
        
        # --- Tab 5: Semantic Data (Phase 70) ---
        self.semantic_tab = QWidget()
        semantic_layout = QVBoxLayout(self.semantic_tab)
        
        self.semantic_viewer = QTextEdit()
        self.semantic_viewer.setReadOnly(True)
        self.semantic_viewer.setFont(self.font()) # Or monospace?
        # Set monospace font for JSON
        font = self.semantic_viewer.font()
        font.setFamily("Monospace")
        font.setStyleHint(font.StyleHint.Monospace)
        self.semantic_viewer.setFont(font)
        
        semantic_layout.addWidget(self.semantic_viewer)
        self.tab_widget.addTab(self.semantic_tab, self.tr("Semantic"))

        
        # --- Tab 6: Canonical Entities (CDM) ---
        self.entities_content = QWidget()
        entities_layout = QVBoxLayout(self.entities_content)
        
        # Table to list entities
        self.entities_table = QTableWidget()
        self.entities_table.setColumnCount(4)
        self.entities_table.setHorizontalHeaderLabels(["Type", "ID", "Date", "Status"])
        self.entities_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.entities_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.entities_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        entities_layout.addWidget(self.entities_table)
        
        # Detail view for selected entity
        self.entity_detail = QTextEdit()
        self.entity_detail.setReadOnly(True)
        self.entity_detail.setPlaceholderText("Select an entity to view Canonical Data...")
        entities_layout.addWidget(self.entity_detail)
        
        self.entities_table.itemSelectionChanged.connect(self._on_entity_selected)
        
        self.tab_widget.addTab(self.entities_content, "Canonical Entities (CDM)")
        
        # Buttons
        self.btn_save = QPushButton(self.tr("Save Changes"))
        self.btn_save.clicked.connect(self.save_changes)
        layout.addWidget(self.btn_save)

    def on_lock_clicked(self, checked):
        """Handle immediate locking/unlocking."""
        if not self.current_uuids or not self.db_manager:
            return
            
        # Determine new state based on checkstate (Checked/Unchecked)
        # If partial, clicking usually sets to Checked or Unchecked depending on cycle.
        # But we get the boolean 'checked' here.
        
        # Enforce consistency: If clicked, we apply this state to ALL current documents.
        new_state = self.chk_locked.isChecked()
        
        # Update DB immediately
        for uuid in self.current_uuids:
             self.db_manager.update_document_metadata(uuid, {"locked": new_state})
             # Update local doc reference if single
             if self.doc and self.doc.uuid == uuid:
                 self.doc.locked = new_state
        
        # Update UI state
        self.toggle_lock(new_state)
        
        # Notify others (List refresh)
        self.metadata_saved.emit()

    def toggle_lock(self, checked):
        """Disable editing fields when locked."""
        self.tab_widget.setEnabled(not checked)

    def display_documents(self, docs: list[Document]):
        """Populate fields for multiple documents."""
        print(f"[DEBUG] MetadataEditor.display_documents called with {len(docs)} documents")
        self.doc = None # Single doc reference invalid
        self.current_uuids = [d.uuid for d in docs]
        
        # Refresh Tag Completer
        if self.db_manager:
            tags = list(self.db_manager.get_all_tags_with_counts().keys())
            self.tags_completer.setModel(QStringListModel(tags))
        
        if not docs:
            self.clear()
            return
            
        self.setEnabled(True)    
        if len(docs) == 1:
            self.display_document(docs[0])
            return

        if len(docs) == 1:
            self.display_document(docs[0])
            return

        # Batch Display
        
        # Locking Logic
        locked_values = {d.locked for d in docs}
        with QSignalBlocker(self.chk_locked):
            if len(locked_values) == 1:
                 val = locked_values.pop()
                 self.chk_locked.setTristate(False)
                 self.chk_locked.setChecked(val)
                 self.toggle_lock(val)
            else:
                 self.chk_locked.setTristate(True)
                 self.chk_locked.setCheckState(Qt.CheckState.PartiallyChecked)
                 self.toggle_lock(False) # Enable editing if mixed

        # Determine common values
        
        # Fields mapping: attr -> widget
        fields = {
            "sender": self.sender_edit,
            "doc_date": self.date_edit,
            "amount": self.amount_edit,
            "gross_amount": self.gross_amount_edit,
            "postage": self.postage_edit,
            "packaging": self.packaging_edit,
            "tax_rate": self.tax_rate_edit,
            "currency": self.currency_edit,
            
            "doc_type": self.type_edit,
            "export_filename": self.export_filename_edit,
            "iban": self.iban_edit,
            "phone": self.phone_edit,
            "tags": self.tags_edit,
            
            "sender_company": self.sender_company_edit,
            "sender_name": self.sender_name_edit,
            "sender_street": self.sender_street_edit,
            "sender_zip": self.sender_zip_edit,
            "sender_city": self.sender_city_edit,
            "sender_country": self.sender_country_edit,
            "sender_address": self.sender_address_raw,
            
            "recipient_company": self.recipient_company_edit,
            "recipient_name": self.recipient_name_edit,
            "recipient_street": self.recipient_street_edit,
            "recipient_zip": self.recipient_zip_edit,
            "recipient_city": self.recipient_city_edit,
            "recipient_country": self.recipient_country_edit
        }
        
        # Store initial state to detect mixed fields
        self.mixed_fields = set()
        
        for attr, widget in fields.items():
            values = set()
            for d in docs:
                val = getattr(d, attr)
                # Normalize: None -> "" or stringify
                if val is None: val = ""
                else: val = str(val)
                values.add(val)
            
            if len(values) == 1:
                # All same
                if isinstance(widget, QDateEdit):
                    # Convert string "YYYY-MM-DD" back to QDate
                    val_str = values.pop() if isinstance(values, set) and len(values)==1 else ""
                    qdate = QDate.fromString(val_str, Qt.DateFormat.ISODate)
                    if not qdate.isValid():
                        qdate = QDate.currentDate()
                    
                    widget.setSpecialValueText("") # Clear any previous mixed state
                    widget.setDate(qdate)
                elif isinstance(widget, QLineEdit): widget.setText(val)
                elif isinstance(widget, QTextEdit): widget.setPlainText(val)
                elif isinstance(widget, QComboBox): widget.setCurrentText(val)
                
                if isinstance(widget, (QLineEdit, QTextEdit)):
                    widget.setPlaceholderText("")
            else:
                # Mixed
                self.mixed_fields.add(attr)
                if isinstance(widget, QLineEdit): 
                    widget.clear()
                    widget.setPlaceholderText("<Multiple Values>")
                elif isinstance(widget, QTextEdit): 
                    widget.clear()
                    widget.setPlaceholderText("<Multiple Values>")
                elif isinstance(widget, QDateEdit):
                    # Handle Mixed Date
                     widget.setSpecialValueText("<Multiple Values>")
                     widget.setDate(widget.minimumDate())
                elif isinstance(widget, QComboBox):
                     widget.setCurrentText("")
                     widget.lineEdit().setPlaceholderText("<Multiple Values>")

        # Info Labels (Special handling)
        self.uuid_lbl.setText("<Multiple Selected>")
        self.created_at_lbl.setText("-")
        self.updated_at_lbl.setText("-")
        # Sum pages? Or range?
        pages = sum((d.page_count or 0) for d in docs)
        self.page_count_lbl.setText(f"Total: {pages}")
        
        # Extra Data - Batch editing not easily supported yet
        self.extra_table.setRowCount(0)
        # Maybe show common keys? For now clear to avoid confusion.

    def display_document(self, doc: Document):
        """Populate fields for single document."""
        print(f"[DEBUG] MetadataEditor.display_document called for {doc.uuid}")
        self.current_uuids = [doc.uuid]
        self.mixed_fields = set() # No mixed fields
        self.doc = doc
        
        # Reset Placeholders
        self._reset_placeholders()

        # General
        self.doc = doc # Ensure doc is set before toggling?? No matter.
        
        # Locking
        # Block signals to prevent auto-toggle if connected? 
        # But toggle_lock logic is purely visual update based on state.
        with QSignalBlocker(self.chk_locked):
             self.chk_locked.setChecked(doc.locked)
        self.toggle_lock(doc.locked)

        self.uuid_lbl.setText(doc.uuid)
        self.created_at_lbl.setText(format_datetime(doc.created_at) or "-")
        self.updated_at_lbl.setText(format_datetime(doc.last_processed_at) or "-")
        
        self.page_count_lbl.setText(str(doc.page_count) if doc.page_count is not None else "-")
        self.sender_edit.setText(doc.sender or "")
        
        # Set Date
        if doc.doc_date:
            if isinstance(doc.doc_date, str):
                try:
                    qdate = QDate.fromString(doc.doc_date, Qt.DateFormat.ISODate)
                except:
                    qdate = QDate.currentDate()
            else:
                # python date -> QDate
                qdate = QDate(doc.doc_date.year, doc.doc_date.month, doc.doc_date.day)
            self.date_edit.setDate(qdate)
        else:
            self.date_edit.setDate(QDate.currentDate())
            
        def fmt_money(val):
            if val is not None:
                try: return f"{float(val):.2f}"
                except: return str(val)
            return ""

        self.amount_edit.setText(fmt_money(doc.amount))
        self.gross_amount_edit.setText(fmt_money(doc.gross_amount))
        self.postage_edit.setText(fmt_money(doc.postage))
        self.packaging_edit.setText(fmt_money(doc.packaging))
        
        # Tax Rate might not be currency. e.g. 19.0.
        # Maybe fmt_decimal? But 2 decimals is fine. 19.00
        self.tax_rate_edit.setText(fmt_money(doc.tax_rate))
        
        self.currency_edit.setText(doc.currency or "")
        
        if isinstance(doc.doc_type, list) and doc.doc_type:
            # Multi Select: Set Checked Items
            self.type_edit.setCheckedItems(doc.doc_type)
        else:
            # Fallback for legacy single string or empty
            val = str(doc.doc_type or "")
            if val:
                self.type_edit.setCheckedItems([val])
            else:
                self.type_edit.setCheckedItems([])
        self.export_filename_edit.setText(doc.export_filename or "")
        self.iban_edit.setText(doc.iban or "")
        self.phone_edit.setText(doc.phone or "")
        self.tags_edit.setText(doc.tags or "")
        
        # Sender
        self.sender_company_edit.setText(doc.sender_company or "")
        self.sender_name_edit.setText(doc.sender_name or "")
        self.sender_street_edit.setText(doc.sender_street or "")
        self.sender_zip_edit.setText(doc.sender_zip or "")
        self.sender_city_edit.setText(doc.sender_city or "")
        self.sender_country_edit.setText(doc.sender_country or "")
        self.sender_address_raw.setPlainText(doc.sender_address or "")
        
        # Recipient
        self.recipient_company_edit.setText(doc.recipient_company or "")
        self.recipient_name_edit.setText(doc.recipient_name or "")
        self.recipient_street_edit.setText(doc.recipient_street or "")
        self.recipient_zip_edit.setText(doc.recipient_zip or "")
        # Extra Data - Batch Logic
        self.extra_table.setRowCount(0)
        self.extra_table.setSortingEnabled(False)
        
        # 1. Collect all extra_data dicts
        all_extras = []
        docs = [doc]
        for d in docs:
            all_extras.append(d.extra_data or {})
            
        if all_extras:
            # 2. Find all unique keys (Union) or Intersection?
            # User wants "common keys" -> Intersection is implied for safe batch editing.
            # But Union allows seeing what exists.
            # Usually: Show Intersection + maybe others?
            # Let's start with Union but mark mixed?
            # User: "gemeinsame Keys" (common keys).
            # Let's use Intersection for editable fields.
            # Or Union to allow adding missing keys to others?
            # Standard approach: Union of keys. If a key is missing in some, treat as empty value.
            
            keys = set()
            for e in all_extras:
                keys.update(e.keys())
            sorted_keys = sorted(list(keys))
            
            for k in sorted_keys:
                row = self.extra_table.rowCount()
                self.extra_table.insertRow(row)
                
                # Check values
                values = []
                for e in all_extras:
                    val = e.get(k, None)
                    # Serialize for comparison
                    try:
                        if isinstance(val, (dict, list)):
                            s = json.dumps(val, sort_keys=True, ensure_ascii=False)
                        else:
                            s = str(val) if val is not None else ""
                    except:
                        s = str(val)
                    values.append(s)
                
                unique_values = set(values)
                display_val = ""
                if len(unique_values) == 1:
                    display_val = values[0]
                else:
                    display_val = "<Multiple Values>"
                    
                key_item = QTableWidgetItem(k)
                self.extra_table.setItem(row, 0, key_item)
                
                val_item = QTableWidgetItem(display_val)
                if display_val == "<Multiple Values>":
                    val_item.setForeground(Qt.GlobalColor.gray)
                    # Store special flag? Or just rely on text.
                    val_item.setData(Qt.ItemDataRole.UserRole, "MIXED")
                
                self.extra_table.setItem(row, 1, val_item)

        self.extra_table.setSortingEnabled(True)
        
        # --- Formatted Metadata ---
        self._populate_normalized_metadata(doc)
        
        # --- Canonical Entities (CDM) ---
        self._load_semantic_entities(doc.uuid)

    def _populate_normalized_metadata(self, doc: Document):
        # Clear previous layout
        while self.normalized_layout.count():
            child = self.normalized_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        config = MetadataNormalizer.get_config()
        # Resolve type
        doc_type = doc.doc_type
        if not doc_type and doc.semantic_data:
             doc_type = doc.semantic_data.get("summary", {}).get("doc_type", "Other")
        if isinstance(doc_type, list): 
            doc_type = doc_type[0] if doc_type else "Other"
        
        if not doc_type:
            doc_type = "Other"
        
        type_def = config.get("types", {}).get(doc_type)
        
        if not type_def:
            lbl = QLabel(self.tr(f"No type definition for '{doc_type}'"))
            self.normalized_layout.addWidget(lbl)
            self.normalized_layout.addStretch()
            return

        # Get values
        try:
            values = MetadataNormalizer.normalize_metadata(doc)
        except Exception as e:
            print(f"Error normalizing metadata: {e}")
            values = {}

        # Render Fields
        translator = SemanticTranslator.instance()
        
        # Translate the type label
        type_label_key = type_def.get("label_key", doc_type)
        grp_label = translator.translate(type_label_key) if type_label_key != doc_type else doc_type
        
        grp = QGroupBox(grp_label)
        form = QFormLayout()
        grp.setLayout(form)
        
        for field in type_def.get("fields", []):
            label_key = field.get("label_key", field["id"])
            label_text = translator.translate(label_key)
            
            val = values.get(field["id"])
            
            # Display widget
            # We use QLineEdits, now enabled for editing (Phase 85)
            edit = QLineEdit()
            edit.setText(str(val) if val is not None else "")
            # edit.setReadOnly(False) # Editable by default
            edit.setCursorPosition(0)
            
            # Store field ID in widget for lookup
            edit.setProperty("field_id", field["id"])

            
            # Add tooltip?
            strategies = field.get("strategies", [])
            tooltip = f"ID: {field['id']}\nStrategies: {len(strategies)}"
            edit.setToolTip(tooltip)
            
            form.addRow(label_text + ":", edit)
            
        self.normalized_layout.addWidget(grp)
        self.normalized_layout.addStretch()
        
        # Semantic Data
        if doc.semantic_data:
            try:
                self.semantic_viewer.setPlainText(json.dumps(doc.semantic_data, indent=2, ensure_ascii=False))
            except:
                self.semantic_viewer.setPlainText(str(doc.semantic_data))
        else:
             self.semantic_viewer.setPlainText("No semantic data available.")
        
    def _reset_placeholders(self):
        """Reset standard placeholders."""
        # self.date_edit.setPlaceholderText("YYYY-MM-DD") # QDateEdit doesn't supports this easily
        self.tags_edit.setPlaceholderText("Tag1, Tag2...")
        self.sender_edit.setPlaceholderText("")
        self.amount_edit.setPlaceholderText("") # etc.
        # Ideally iterate all and clear

    def clear(self):
        """Clear fields."""
        self.current_uuids = []
        self.doc = None
        self.mixed_fields = set()
        
        # General
        self.uuid_lbl.clear()
        self.created_at_lbl.clear()
        self.updated_at_lbl.clear()
        self.page_count_lbl.clear()
        self.sender_edit.clear()
        self.date_edit.setDate(QDate.currentDate()) # Or some default
        self.amount_edit.clear()
        self.type_edit.setCurrentText("")
        self.export_filename_edit.clear()
        self.iban_edit.clear()
        self.phone_edit.clear()
        self.tags_edit.clear()
        
        # Sender
        self.sender_company_edit.clear()
        self.sender_name_edit.clear()
        self.sender_street_edit.clear()
        self.sender_zip_edit.clear()
        self.sender_city_edit.clear()
        self.sender_country_edit.clear()
        self.sender_address_raw.clear()
        
        # Recipient
        self.recipient_company_edit.clear()
        self.recipient_name_edit.clear()
        self.recipient_street_edit.clear()
        self.recipient_zip_edit.clear()
        self.recipient_city_edit.clear()
        self.recipient_country_edit.clear()
        
        self.extra_table.setRowCount(0)
        
        self._reset_placeholders()
        self.semantic_viewer.clear()
        self.setEnabled(False) 

    def save_changes(self):
        if not self.current_uuids or not self.db_manager:
            return
            
        # Collect updates
        # Need to know which fields to update.
        # Map: attr -> widget
        fields = {
            "sender": self.sender_edit,
            "doc_date": self.date_edit,
            "amount": self.amount_edit,
            "gross_amount": self.gross_amount_edit,
            "postage": self.postage_edit,
            "packaging": self.packaging_edit,
            "tax_rate": self.tax_rate_edit,
            "currency": self.currency_edit,
            
            "doc_type": self.type_edit,
            "export_filename": self.export_filename_edit,
            "iban": self.iban_edit,
            "phone": self.phone_edit,
            "tags": self.tags_edit,
            
            "sender_company": self.sender_company_edit,
            "sender_name": self.sender_name_edit,
            "sender_street": self.sender_street_edit,
            "sender_zip": self.sender_zip_edit,
            "sender_city": self.sender_city_edit,
            "sender_country": self.sender_country_edit,
            "sender_address": self.sender_address_raw,
            
            "recipient_company": self.recipient_company_edit,
            "recipient_name": self.recipient_name_edit,
            "recipient_street": self.recipient_street_edit,
            "recipient_zip": self.recipient_zip_edit,
            "recipient_city": self.recipient_city_edit,
            "recipient_country": self.recipient_country_edit
        }
        
        updates = {}
        
        for attr, widget in fields.items():
            text = None
            if isinstance(widget, QDateEdit):
                # QDateEdit logic:
                # If mixed field AND value == minimumDate (which holds our special text), ignore it.
                current_qdate = widget.date()
                if attr in self.mixed_fields and current_qdate == widget.minimumDate():
                    continue # User didn't change the mixed value placeholder
                
                text = current_qdate.toString(Qt.DateFormat.ISODate)
            elif isinstance(widget, QLineEdit):
                text = widget.text().strip()
            elif isinstance(widget, QTextEdit):
                text = widget.toPlainText().strip()
            elif isinstance(widget, MultiSelectComboBox):
                # Special Multi-Select Logic
                checked = widget.getCheckedItems()
                if checked:
                    text = checked # Pass list directly
                else:
                     # Check if user typed something manually?
                     raw = widget.currentText().strip()
                     if raw:
                         # Split by comma
                         text = [t.strip() for t in raw.split(',') if t.strip()]
                     else:
                         text = []
            elif isinstance(widget, QComboBox):
                text = widget.currentText().strip()
                
            # Logic:
            # 1. If field was mixed (in self.mixed_fields):
            #    - Update ONLY if text is NOT empty.
            # 2. If field was common (not in mixed):
            #    - Update always (even if empty, meaning user cleared it).
            
            if attr in self.mixed_fields:
                if text: # User entered something
                    # Special case for Amount/Date conversion logic?
                    # The update_document_metadata handles conversion if passed as string?
                    # Actually update_document_metadata expects primitives usually?
                    # Let's clean it up.
                    if text == "<Multiple Values>": continue # Should not happen if cleared/placeholder
                    updates[attr] = text
            else:
                # Common value. Update to text (empty or not).
                updates[attr] = text if text else None
                
        # Clean up specific types based on model needs (Date, Amount)
        # Assuming db_manager.update_document_metadata handles string->type conversion?
        # Let's check update_document_metadata implementation or handle here.
        # It's safer to handle here or trust manager. 
        # For efficiency, let's assume strings are passed and manager/model handles it 
        # OR we need to be careful.
        
        # Actually `update_document_metadata` iterates keys and setattr.
        # Document (Pydantic) will coerce types? Yes, if valid.
        # But text "" for Date might fail.
        
        # Validation / Cleanup
        financial_fields = ["amount", "gross_amount", "postage", "packaging", "tax_rate", "currency"]
        for f in financial_fields:
            if f in updates and updates[f] == "":
                updates[f] = None
                
        if "doc_date" in updates and updates["doc_date"] == "": updates["doc_date"] = None
        
        # Locked State handled immediately via on_lock_clicked
        # We do NOT save it here to avoid overwriting if user didn't touch it?
        # Or should we?
        # If we remove it here, locking via checkbox is isolated.
        # This is what user requested ("Verzichten wir auf Änderungen speichern").
        
        # Extra Data (Batch + Single)
        # Strategy:
        # 1. Gather all keys from table.
        # 2. Identify if value is "MIXED" (unchanged) or new value.
        # 3. For each doc, update ONLY keys present in table? 
        #    Or merge?
        #    If Table has row "K", Value "V", we should set K=V for all docs.
        #    If Table has row "K", Value "<Multiple Values>", we skip K (no change).
        #    If Table is missing a key found in doc? 
        #       - If user deleted it explicitly? (Using Remove button)
        #       - We need to track deletion vs just not showing.
        #       - With Union display, if row is gone, it means DELETE from all docs?
        #       - Yes, "Remove" button should mean "Remove Key from All".
        
        # --- Phase 87: Sync Logic (General -> Semantic) ---
        # When user edits Sender/Date/Amount in General Tab, we MUST sync to semantic_data
        # to ensure Virtual Columns (v_sender, v_doc_date, v_amount) are correct.
        
        # We process each document
        for uuid in self.current_uuids:
            doc_updates = updates.copy() # Base updates
            
            # Fetch doc to get current semantic_data
            # If batch, we might modify multiple.
            # We can't easily modify semantic_data without the object.
            # Let's use db_manager.get_document_by_uuid(uuid) if needed?
            # Or use self.doc if single.
            
            target_doc = None
            if self.doc and self.doc.uuid == uuid:
                target_doc = self.doc
            elif self.current_uuids:
                 # In batch, we really should have cached docs or fetch them.
                 # Let's trust self.db_manager to handle this if we pass "semantic_updates"?
                 # No, db manager is generic.
                 # We must fetch.
                 target_doc = self.db_manager.get_document_by_uuid(uuid)
            
            if target_doc:
                # Prepare semantic_data if missing
                if not target_doc.semantic_data:
                    target_doc.semantic_data = {"summary": {}}
                if "summary" not in target_doc.semantic_data:
                    target_doc.semantic_data["summary"] = {}
                
                summary = target_doc.semantic_data["summary"]
                modified_semantic = False
                
                # Sync Sender
                if "sender" in doc_updates and doc_updates["sender"] is not None:
                    summary["sender_name"] = doc_updates["sender"]
                    modified_semantic = True
                    
                # Sync Date
                if "doc_date" in doc_updates and doc_updates["doc_date"] is not None:
                     summary["main_date"] = str(doc_updates["doc_date"])
                     modified_semantic = True
                     
                # Sync Amount
                if "amount" in doc_updates:
                    # Amount can be None or string
                    amt = doc_updates["amount"]
                    if amt is not None:
                         summary["amount"] = str(amt) # JSON schema wants string
                    else:
                         summary["amount"] = None
                    modified_semantic = True
                
                if modified_semantic:
                    doc_updates["semantic_data"] = target_doc.semantic_data

            # Apply Updates
            self.db_manager.update_document_metadata(uuid, doc_updates)

            # Capture Type Data Updates (Phase 85) - Only for single doc currently supported in UI logic
            # These are ALREADY in semantic_data if we sync'd above? 
            # No, these are EXTRA edits from the Type Tab.
            # We must be careful not to overwrite if we merge.
            # The Type Tab edits call MetadataNormalizer.update_field which modifies doc.semantic_data in place.
            # So if we use target_doc above, we are safe.
            
            # Re-apply Type Tab edits if single doc (overwriting what we just prepared?)
            # Actually, "Type Data" tab writes directly to doc.semantic_data via update_field.
            # If we call update_document_metadata with semantic_data, we are good.
            # BUT: update_field logic in save_changes (below) iterates widgets.
            
        # Capture Type Data Updates (Phase 85) - REVISED
        if self.doc and len(self.current_uuids) == 1:
             # Iterate widgets in Normalized Layout
             doc_modified = False
             for i in range(self.normalized_layout.count()):
                item = self.normalized_layout.itemAt(i)
                if not item: continue
                
                widget = item.widget()
                if isinstance(widget, QGroupBox):
                    form_layout = widget.layout()
                    if form_layout:
                        for r in range(form_layout.rowCount()):
                            field_item = form_layout.itemAt(r, QFormLayout.ItemRole.FieldRole)
                            if field_item and field_item.widget():
                                w = field_item.widget()
                                if isinstance(w, QLineEdit):
                                    field_id = w.property("field_id")
                                    if field_id:
                                        new_val = w.text().strip()
                                        if MetadataNormalizer.update_field(self.doc, field_id, new_val):
                                           doc_modified = True
             
             if doc_modified:
                 self.db_manager.update_document_metadata(self.doc.uuid, {"semantic_data": self.doc.semantic_data})

        self.metadata_saved.emit()

        # Capture current table state
        table_keys = set()
        table_updates = {} # Key -> Value (or MIXED_MARKER)
        
        for row in range(self.extra_table.rowCount()):
            key_item = self.extra_table.item(row, 0)
            val_item = self.extra_table.item(row, 1)
            
            if key_item and key_item.text().strip():
                k = key_item.text().strip()
                table_keys.add(k)
                
                # Check for Mixed
                is_mixed = False
                if val_item:
                    # Check UserRole first
                    if val_item.data(Qt.ItemDataRole.UserRole) == "MIXED":
                         # Verify text wasn't changed by user
                         if val_item.text() == "<Multiple Values>":
                             is_mixed = True
                
                if not is_mixed:
                    val_raw = val_item.text().strip() if val_item else ""
                    try:
                        val = json.loads(val_raw)
                    except:
                        val = val_raw
                    table_updates[k] = val
                    
        # Apply to each doc
        # We need to fetch current doc extra_data to merge? 
        # Or does update_document_metadata support partials? 
        # DatabaseManager.update replaces the column value. So we must merge and Write Full.
        # This is expensive for Batch... we need to fetch, merge, update.
        # self.current_uuids are known.
        
        count = 0 
        for uuid in self.current_uuids:
             # Fetch current extra_data? 
             # We assume db_manager.get_document_by_uuid is fast enough or we check self.doc but that's only for single.
             # Batch save is heavy.
             
             # Optimization: We already fetched docs in display_documents?
             # But they might be stale if we edit.
             # Let's fetch fresh to be safe.
             
             current_doc = self.db_manager.get_document_by_uuid(uuid)
             if not current_doc: continue
             
             current_extra = current_doc.extra_data or {}
             dirty_extra = False
             
             # 1. Updates
             for k, v in table_updates.items():
                 if current_extra.get(k) != v:
                     current_extra[k] = v
                     dirty_extra = True
                     
             # 2. Deletions 
             # If a key exists in current_extra but NOT in table_keys:
             # It means user removed it (since we showed Union of keys).
             # So we delete it.
             keys_to_remove = [k for k in current_extra.keys() if k not in table_keys]
             for k in keys_to_remove:
                 del current_extra[k]
                 dirty_extra = True
                 
             # Prepare individual update
             doc_updates = updates.copy()
             if dirty_extra:
                 doc_updates["extra_data"] = current_extra
             
             if not doc_updates and not dirty_extra:
                 continue
                 
             if self.db_manager.update_document_metadata(uuid, doc_updates):
                 count += 1
                 
        if count > 0:
            QMessageBox.information(self, self.tr("Success"), self.tr(f"Metadata saved for {count} documents."))
            self.metadata_saved.emit()
        else:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to save changes."))

    def regenerate_export_filename(self):
        import re
        # Gather data from widgets
        sender = self.sender_company_edit.text() or self.sender_name_edit.text() or self.sender_edit.text() or "Unknown"
        doc_type = self.type_edit.text() or "Document"
        date_part = self.date_edit.text() or "UnknownDate"
        
        def clean(s):
             s = str(s).strip()
             s = re.sub(r'[^\w\s-]', '', s)
             s = re.sub(r'[\s]+', '_', s)
             return s
             
        base = f"{clean(sender)}_{clean(doc_type)}_{clean(date_part)}"
        self.export_filename_edit.setText(base)

    def add_extra_field(self):
        row = self.extra_table.rowCount()
        self.extra_table.insertRow(row)
        self.extra_table.setItem(row, 0, QTableWidgetItem("new_key"))
        self.extra_table.setItem(row, 1, QTableWidgetItem(""))
        
    def remove_extra_field(self):
        row = self.extra_table.currentRow()
        if row >= 0:
            self.extra_table.removeRow(row)

    def _clear_ui(self):
        """Reset all fields."""
        self.doc = None
        self.uuid_lbl.setText("-")
        self.created_at_lbl.setText("-")
        self.updated_at_lbl.setText("-")
        self.page_count_lbl.setText("-")
        self.sender_edit.clear()
        self.date_edit.setDate(QDate.currentDate())
        self.amount_edit.clear()
        self.gross_amount_edit.clear()
        self.postage_edit.clear()
        self.packaging_edit.clear()
        self.tax_rate_edit.clear()
        self.currency_edit.clear()
        self.type_edit.setCheckedItems([])
        self.export_filename_edit.clear()
        self.iban_edit.clear()
        self.phone_edit.clear()
        self.tags_edit.clear()
        self.sender_company_edit.clear()
        self.sender_name_edit.clear()
        self.sender_street_edit.clear()
        self.sender_zip_edit.clear()
        self.sender_city_edit.clear()
        self.sender_country_edit.clear()
        self.sender_address_raw.clear()
        self.recipient_company_edit.clear()
        self.recipient_name_edit.clear()
        self.recipient_street_edit.clear()
        self.recipient_zip_edit.clear()
        self.recipient_city_edit.clear()
        self.recipient_country_edit.clear()
        self.extra_table.setRowCount(0)
        self.json_edit.clear()
        self.semantic_viewer.clear()
        self.entities_table.setRowCount(0)
        self.entity_detail.clear()
        # Clear normalized tab
        while self.normalized_layout.count():
            child = self.normalized_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            
    def _load_semantic_entities(self, uuid: str):
        """Fetch and display CDM entities."""
        print(f"[DEBUG] Loading CDM entities for {uuid}")
        if not self.db_manager: return
        
        entities = self.db_manager.get_semantic_entities(uuid)
        self.entities_data = entities # Store for detail view
        
        self.entities_table.setRowCount(0)
        self.entities_table.setRowCount(len(entities))
        
        for i, ent in enumerate(entities):
            type_item = QTableWidgetItem(str(ent.get("doc_type", "Unknown")))
            id_item = QTableWidgetItem(str(ent.get("doc_id", "-")))
            date_item = QTableWidgetItem(str(ent.get("doc_date", "-")))
            status_item = QTableWidgetItem(str(ent.get("status", "NEW")))
            
            self.entities_table.setItem(i, 0, type_item)
            self.entities_table.setItem(i, 1, id_item)
            self.entities_table.setItem(i, 2, date_item)
            self.entities_table.setItem(i, 3, status_item)
            
    def _on_entity_selected(self):
        """Show JSON details for selected entity."""
        rows = self.entities_table.selectionModel().selectedRows()
        if not rows:
            self.entity_detail.clear()
            return
            
        row = rows[0].row()
        if hasattr(self, 'entities_data') and row < len(self.entities_data):
            ent = self.entities_data[row]
            self.entity_detail.setText(json.dumps(ent, indent=2, ensure_ascii=False))
