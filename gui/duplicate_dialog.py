
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, 
    QLabel, QPushButton, QWidget, QSplitter, QTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt
from core.document import Document
from core.database import DatabaseManager

class DuplicateFinderDialog(QDialog):
    """
    Dialog to review and resolve potential duplicates.
    """
    def __init__(self, duplicates: list, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Duplicate Finder"))
        self.resize(900, 600)
        self.db_manager = db_manager
        self.duplicates = duplicates # List of (doc_a, doc_b, score)
        
        self._init_ui()
        self._load_duplicates()
        
    def _init_ui(self):
        layout = QHBoxLayout(self)
        
        # Left: List of pairs
        left_layout = QVBoxLayout()
        self.pair_list = QListWidget()
        self.pair_list.itemSelectionChanged.connect(self._on_pair_selected)
        left_layout.addWidget(QLabel(self.tr("Potential Duplicates:")))
        left_layout.addWidget(self.pair_list)
        layout.addLayout(left_layout, 1)
        
        # Right: Detail & Actions
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Comparison Area
        compare_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Doc A
        self.doc_a_info = QTextEdit()
        self.doc_a_info.setReadOnly(True)
        compare_splitter.addWidget(self.doc_a_info)
        
        # Doc B
        self.doc_b_info = QTextEdit()
        self.doc_b_info.setReadOnly(True)
        compare_splitter.addWidget(self.doc_b_info)
        
        right_layout.addWidget(compare_splitter, 1)
        
        # Actions
        btn_layout = QHBoxLayout()
        self.btn_keep_a = QPushButton(self.tr("Keep Left (Delete Right)"))
        self.btn_keep_a.clicked.connect(self.keep_a)
        self.btn_keep_a.setEnabled(False)
        
        self.btn_keep_b = QPushButton(self.tr("Keep Right (Delete Left)"))
        self.btn_keep_b.clicked.connect(self.keep_b)
        self.btn_keep_b.setEnabled(False)
        
        self.btn_ignore = QPushButton(self.tr("Ignore / Next"))
        self.btn_ignore.clicked.connect(self.ignore_pair)
        self.btn_ignore.setEnabled(False)
        
        btn_layout.addWidget(self.btn_keep_a)
        btn_layout.addWidget(self.btn_keep_b)
        btn_layout.addWidget(self.btn_ignore)
        right_layout.addLayout(btn_layout)
        
        layout.addWidget(right_widget, 2)
        
    def _load_duplicates(self):
        self.pair_list.clear()
        for doc_a, doc_b, score in self.duplicates:
            label = f"{score:.0%} Match: {doc_a.original_filename} vs {doc_b.original_filename}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, (doc_a, doc_b))
            self.pair_list.addItem(item)
            
        if self.pair_list.count() == 0:
            QMessageBox.information(self, self.tr("No Duplicates"), self.tr("No duplicates found with current threshold."))
            self.close()
            
    def _on_pair_selected(self):
        items = self.pair_list.selectedItems()
        if not items:
            self.doc_a_info.clear()
            self.doc_b_info.clear()
            self.btn_keep_a.setEnabled(False)
            self.btn_keep_b.setEnabled(False)
            self.btn_ignore.setEnabled(False)
            return
            
        doc_a, doc_b = items[0].data(Qt.ItemDataRole.UserRole)
        
        self.doc_a_info.setPlainText(self._format_doc_info(doc_a))
        self.doc_b_info.setPlainText(self._format_doc_info(doc_b))
        
        self.btn_keep_a.setEnabled(True)
        self.btn_keep_b.setEnabled(True)
        self.btn_ignore.setEnabled(True)
        
    def _format_doc_info(self, doc: Document) -> str:
        return (
            f"Filename: {doc.original_filename}\n"
            f"Date: {doc.doc_date}\n"
            f"Sender: {doc.sender}\n"
            f"Amount: {doc.amount}\n"
            f"Type: {doc.doc_type}\n"
            f"UUID: {doc.uuid}\n"
            f"Created: {doc.created_at}\n"
            f"Pages: {doc.page_count}\n"
            f"\nText Preview:\n{doc.text_content[:200]}..."
        )

    def keep_a(self):
        self._resolve_pair(keep_left=True)

    def keep_b(self):
        self._resolve_pair(keep_left=False)

    def ignore_pair(self):
        # Just remove from list
        row = self.pair_list.currentRow()
        self.pair_list.takeItem(row)
        
    def _resolve_pair(self, keep_left: bool):
        items = self.pair_list.selectedItems()
        if not items: return
        
        doc_a, doc_b = items[0].data(Qt.ItemDataRole.UserRole)
        doc_to_delete = doc_b if keep_left else doc_a
        
        # Confirm?
        # ret = QMessageBox.question(self, "Confirm Delete", f"Delete {doc_to_delete.original_filename}?")
        # if ret != QMessageBox.StandardButton.Yes: return
        
        # Delete from DB
        # Note: This updates DB but main window list needs refresh.
        # We assume Main Window refreshes after dialog closes or we emit signal?
        # Dialog is modal.
        
        if self.db_manager.delete_document(doc_to_delete.uuid):
            # Success
            pass
        else:
            QMessageBox.warning(self, "Error", "Failed to delete document.")
            return
            
        # Remove item
        row = self.pair_list.currentRow()
        self.pair_list.takeItem(row)
