from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, 
    QLabel, QGroupBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QInputDialog, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt
from core.vocabulary import VocabularyManager

class VocabularySettingsWidget(QWidget):
    """
    Widget to manage Types, Tags, and Aliases.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.vocab = VocabularyManager()
        self._setup_ui()
        self._refresh_data()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Types Section ---
        type_group = QGroupBox(self.tr("Document Types"))
        type_layout = QHBoxLayout(type_group)
        
        # Type List
        v_list = QVBoxLayout()
        v_list.addWidget(QLabel(self.tr("Approved Types")))
        self.type_list = QListWidget()
        v_list.addWidget(self.type_list)
        
        h_btn = QHBoxLayout()
        self.btn_add_type = QPushButton("+")
        self.btn_del_type = QPushButton("-")
        self.btn_add_type.clicked.connect(self._add_type)
        self.btn_del_type.clicked.connect(self._del_type)
        h_btn.addWidget(self.btn_add_type)
        h_btn.addWidget(self.btn_del_type)
        h_btn.addStretch()
        v_list.addLayout(h_btn)
        
        type_layout.addLayout(v_list, 1) # Stretch 1
        
        # Type Aliases Table
        v_alias = QVBoxLayout()
        v_alias.addWidget(QLabel(self.tr("Aliases (Synonyms)")))
        self.type_alias_table = QTableWidget()
        self.type_alias_table.setColumnCount(2)
        self.type_alias_table.setHorizontalHeaderLabels([self.tr("Alias"), self.tr("Target Type")])
        self.type_alias_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v_alias.addWidget(self.type_alias_table)
        
        h_btn_a = QHBoxLayout()
        self.btn_add_type_alias = QPushButton("+")
        self.btn_del_type_alias = QPushButton("-")
        self.btn_add_type_alias.clicked.connect(self._add_type_alias)
        self.btn_del_type_alias.clicked.connect(self._del_type_alias)
        h_btn_a.addWidget(self.btn_add_type_alias)
        h_btn_a.addWidget(self.btn_del_type_alias)
        h_btn_a.addStretch()
        v_alias.addLayout(h_btn_a)
        
        type_layout.addLayout(v_alias, 2) # Stretch 2 (Wider)
        
        layout.addWidget(type_group)
        
        # --- Tags Section ---
        tag_group = QGroupBox(self.tr("Tags"))
        tag_layout = QHBoxLayout(tag_group)
        
        # Tag List
        v_list_t = QVBoxLayout()
        v_list_t.addWidget(QLabel(self.tr("Approved Tags")))
        self.tag_list = QListWidget()
        v_list_t.addWidget(self.tag_list)
        
        h_btn_t = QHBoxLayout()
        self.btn_add_tag = QPushButton("+")
        self.btn_del_tag = QPushButton("-")
        self.btn_add_tag.clicked.connect(self._add_tag)
        self.btn_del_tag.clicked.connect(self._del_tag)
        h_btn_t.addWidget(self.btn_add_tag)
        h_btn_t.addWidget(self.btn_del_tag)
        h_btn_t.addStretch()
        v_list_t.addLayout(h_btn_t)
        
        tag_layout.addLayout(v_list_t, 1)
        
        # Tag Aliases
        v_alias_t = QVBoxLayout()
        v_alias_t.addWidget(QLabel(self.tr("Aliases")))
        self.tag_alias_table = QTableWidget()
        self.tag_alias_table.setColumnCount(2)
        self.tag_alias_table.setHorizontalHeaderLabels([self.tr("Alias"), self.tr("Target Tag")])
        self.tag_alias_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v_alias_t.addWidget(self.tag_alias_table)
        
        h_btn_at = QHBoxLayout()
        self.btn_add_tag_alias = QPushButton("+")
        self.btn_del_tag_alias = QPushButton("-")
        self.btn_add_tag_alias.clicked.connect(self._add_tag_alias)
        self.btn_del_tag_alias.clicked.connect(self._del_tag_alias)
        h_btn_at.addWidget(self.btn_add_tag_alias)
        h_btn_at.addWidget(self.btn_del_tag_alias)
        h_btn_at.addStretch()
        v_alias_t.addLayout(h_btn_at)
        
        tag_layout.addLayout(v_alias_t, 2)
        
        layout.addWidget(tag_group)
        
    def _refresh_data(self):
        # Types
        self.type_list.clear()
        self.type_list.addItems(self.vocab.get_all_types())
        
        # Type Aliases
        aliases = self.vocab.get_type_aliases()
        self.type_alias_table.setRowCount(0)
        for alias, target in aliases.items():
            r = self.type_alias_table.rowCount()
            self.type_alias_table.insertRow(r)
            self.type_alias_table.setItem(r, 0, QTableWidgetItem(alias))
            self.type_alias_table.setItem(r, 1, QTableWidgetItem(target))
            
        # Tags
        self.tag_list.clear()
        self.tag_list.addItems(self.vocab.get_all_tags())
        
        # Tag Aliases
        t_aliases = self.vocab.get_tag_aliases()
        self.tag_alias_table.setRowCount(0)
        for alias, target in t_aliases.items():
            r = self.tag_alias_table.rowCount()
            self.tag_alias_table.insertRow(r)
            self.tag_alias_table.setItem(r, 0, QTableWidgetItem(alias))
            self.tag_alias_table.setItem(r, 1, QTableWidgetItem(target))
            
    # --- Actions Types ---
    def _add_type(self):
        text, ok = QInputDialog.getText(self, self.tr("Add Type"), self.tr("Document Type:"))
        if ok and text:
            self.vocab.add_type(text)
            self._refresh_data()
            
    def _del_type(self):
        item = self.type_list.currentItem()
        if item:
            self.vocab.remove_type(item.text())
            self._refresh_data()
            
    def _add_type_alias(self):
        # Need alias and target
        # Target must be from types
        types = self.vocab.get_all_types()
        if not types:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Define types first."))
            return
            
        alias, ok = QInputDialog.getText(self, self.tr("Add Alias"), self.tr("Alias (e.g. Rechnung):"))
        if not ok or not alias: return
        
        target, ok2 = QInputDialog.getItem(self, self.tr("Select Target"), self.tr("Map to Type:"), types, 0, False)
        if ok2 and target:
            self.vocab.add_type_alias(alias, target)
            self._refresh_data()
            
    def _del_type_alias(self):
        row = self.type_alias_table.currentRow()
        if row >= 0:
            alias = self.type_alias_table.item(row, 0).text()
            self.vocab.remove_type_alias(alias)
            self._refresh_data()

    # --- Actions Tags ---
    def _add_tag(self):
        text, ok = QInputDialog.getText(self, self.tr("Add Tag"), self.tr("Tag:"))
        if ok and text:
            self.vocab.add_tag(text)
            self._refresh_data()
            
    def _del_tag(self):
        item = self.tag_list.currentItem()
        if item:
            self.vocab.remove_tag(item.text())
            self._refresh_data()
            
    def _add_tag_alias(self):
        tags = self.vocab.get_all_tags()
        if not tags:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Define tags first."))
            return
            
        alias, ok = QInputDialog.getText(self, self.tr("Add Alias"), self.tr("Alias (e.g. Wichtig):"))
        if not ok or not alias: return
        
        target, ok2 = QInputDialog.getItem(self, self.tr("Select Target"), self.tr("Map to Tag:"), tags, 0, False)
        if ok2 and target:
            self.vocab.add_tag_alias(alias, target)
            self._refresh_data()
            
    def _del_tag_alias(self):
        row = self.tag_alias_table.currentRow()
        if row >= 0:
            alias = self.tag_alias_table.item(row, 0).text()
            self.vocab.remove_tag_alias(alias)
            self._refresh_data()
