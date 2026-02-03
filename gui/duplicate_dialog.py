
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, 
    QLabel, QPushButton, QWidget, QSplitter, QTextEdit, QMessageBox,
    QMenu
)
from PyQt6.QtCore import Qt, QPoint
from core.models.virtual import VirtualDocument as Document
from core.database import DatabaseManager

class DuplicateFinderDialog(QDialog):
    """
    Dialog to review and resolve potential duplicates.
    Enhanced with sorting (Accuracy), age-based ordering (Young=Left, Old=Right),
    and batch processing via context menu.
    """
    def __init__(self, duplicates: list, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Duplicate Finder"))
        self.resize(1000, 700)
        self.db_manager = db_manager
        self.duplicates = duplicates # List of (doc_a, doc_b, score)
        
        self._init_ui()
        self._load_duplicates()
        
    def _init_ui(self):
        layout = QHBoxLayout(self)
        
        # Left: List of pairs
        left_layout = QVBoxLayout()
        self.pair_list = QListWidget()
        
        # Enable Multi-Selection
        self.pair_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.pair_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pair_list.customContextMenuRequested.connect(self._show_context_menu)
        
        self.pair_list.itemSelectionChanged.connect(self._on_pair_selected)
        
        left_layout.addWidget(QLabel(self.tr("Potential Duplicates (Sorted by Accuracy):")))
        left_layout.addWidget(self.pair_list)
        
        hint = QLabel(self.tr("<i>Left: Younger | Right: Older</i>"))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(hint)
        
        layout.addLayout(left_layout, 1)
        
        # Right: Detail & Actions
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Comparison Area
        compare_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Doc A (Left - Younger)
        self.doc_a_info = QTextEdit()
        self.doc_a_info.setReadOnly(True)
        compare_splitter.addWidget(self.doc_a_info)
        
        # Doc B (Right - Older)
        self.doc_b_info = QTextEdit()
        self.doc_b_info.setReadOnly(True)
        compare_splitter.addWidget(self.doc_b_info)
        
        right_layout.addWidget(compare_splitter, 1)
        
        # Single Pair Actions
        btn_layout = QHBoxLayout()
        self.btn_keep_a = QPushButton(self.tr("Keep Left (Delete Old)"))
        self.btn_keep_a.clicked.connect(self.keep_a)
        self.btn_keep_a.setEnabled(False)
        
        self.btn_keep_b = QPushButton(self.tr("Keep Right (Delete Young)"))
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
        
        processed_pairs = []
        for doc_a, doc_b, score in self.duplicates:
            # 1. Ensure doc_a is Younger (Later timestamp), doc_b is Older
            # compare created_at (ISO strings)
            # If a is older than b, swap
            time_a = doc_a.created_at or ""
            time_b = doc_b.created_at or ""
            
            if time_a < time_b:
                doc_left, doc_right = doc_b, doc_a
            else:
                doc_left, doc_right = doc_a, doc_b
                
            processed_pairs.append((doc_left, doc_right, score))
            
        # 2. Sort by Accuracy (Score) descending
        processed_pairs.sort(key=lambda x: x[2], reverse=True)
        
        for doc_left, doc_right, score in processed_pairs:
            label = f"[{score:.0%} Match] {doc_left.original_filename} (Y) vs {doc_right.original_filename} (O)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, (doc_left, doc_right))
            self.pair_list.addItem(item)
            
        if self.pair_list.count() == 0:
            show_selectable_message_box(self, self.tr("No Duplicates"), self.tr("No duplicates found with current threshold."), icon=QMessageBox.Icon.Information)
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
            
        # Preview first selected pair
        doc_a, doc_b = items[0].data(Qt.ItemDataRole.UserRole)
        
        self.doc_a_info.setHtml(f"<b style='color: #4CAF50'>YOUNGER (LEFT):</b><br>{self._format_doc_info(doc_a)}")
        self.doc_b_info.setHtml(f"<b style='color: #FF5722'>OLDER (RIGHT):</b><br>{self._format_doc_info(doc_b)}")
        
        self.btn_keep_a.setEnabled(True)
        self.btn_keep_b.setEnabled(True)
        self.btn_ignore.setEnabled(True)
        
    def _format_doc_info(self, doc: Document) -> str:
        text_preview = (doc.text_content or "")[:200]
        sd = doc.semantic_data or {}
        return (
            f"<b>Filename:</b> {doc.original_filename}<br>"
            f"<b>Date:</b> {doc.doc_date or '-'}<br>"
            f"<b>Sender:</b> {doc.sender_name or '-'}<br>"

            f"<b>UUID:</b> <small>{doc.uuid}</small><br>"
            f"<b>Created:</b> {doc.created_at}<br>"
            f"<b>Pages:</b> {doc.page_count}<br>"
            f"<br><i>Text Preview:</i><br><pre>{text_preview}...</pre>"
        )

    def _show_context_menu(self, pos: QPoint):
        items = self.pair_list.selectedItems()
        if not items: return
        
        menu = QMenu()
        keep_younger = menu.addAction(self.tr(f"Jüngere Dubletten behalten ({len(items)})"))
        keep_older = menu.addAction(self.tr(f"Ältere Dubletten behalten ({len(items)})"))
        menu.addSeparator()
        ignore = menu.addAction(self.tr("Aus Liste entfernen (Ignorieren)"))
        
        action = menu.exec(self.pair_list.mapToGlobal(pos))
        
        if action == keep_younger:
            self._resolve_batch(keep_left=True)
        elif action == keep_older:
            self._resolve_batch(keep_left=False)
        elif action == ignore:
            for item in items:
                self.pair_list.takeItem(self.pair_list.row(item))

    def keep_a(self):
        self._resolve_pair(keep_left=True)

    def keep_b(self):
        self._resolve_pair(keep_left=False)

    def ignore_pair(self):
        row = self.pair_list.currentRow()
        self.pair_list.takeItem(row)
        
    def _resolve_pair(self, keep_left: bool):
        items = self.pair_list.selectedItems()
        if not items: return
        self._resolve_batch(keep_left, items=[items[0]])

    def _resolve_batch(self, keep_left: bool, items=None):
        if items is None:
            items = self.pair_list.selectedItems()
        
        if not items: return
        
        msg = self.tr(f"Wirklich {len(items)} Dubletten löschen?")
        if show_selectable_message_box(self, self.tr("Bestätigen"), msg, icon=QMessageBox.Icon.Question, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
            
        success_count = 0
        error_count = 0
        
        # Iterate in reverse to avoid index shifts if we were using indices, 
        # but takeItem is safe with item references.
        for item in items:
            doc_left, doc_right = item.data(Qt.ItemDataRole.UserRole)
            doc_to_delete = doc_right if keep_left else doc_left
            
            if self.db_manager.delete_document(doc_to_delete.uuid):
                success_count += 1
                self.pair_list.takeItem(self.pair_list.row(item))
            else:
                error_count += 1
                
        if error_count > 0:
            show_selectable_message_box(self, self.tr("Fehler"), self.tr(f"{error_count} Dokumente konnten nicht gelöscht werden."), icon=QMessageBox.Icon.Warning)
        
        if self.pair_list.count() == 0:
            self.close()
