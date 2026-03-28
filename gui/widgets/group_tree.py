"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/group_tree.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Collapsible sidebar GroupTreeWidget that displays document
                groups in a hierarchy. Selecting a group emits a signal that
                the main window uses to filter the document list. Supports
                right-click CRUD (new, rename, delete) and drag-and-drop
                membership assignment from DocumentListWidget.
------------------------------------------------------------------------------
"""
from typing import Optional, List

from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QEvent
from PyQt6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMenu, QPushButton, QSizePolicy, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from core.database import DatabaseManager
from core.repositories.group_repo import GroupRepository
from core.models.group import DocumentGroup
from core.logger import get_logger

logger = get_logger("gui.widgets.group_tree")

_ALL_DOCS_ID = "__ALL__"


class GroupTreeWidget(QWidget):
    """
    Collapsible sidebar panel showing the document group hierarchy.

    Signals:
        group_selected(group_id)  — emitted when user clicks a group;
                                    group_id == _ALL_DOCS_ID means no filter
        membership_dropped(document_uuid, group_id) — drag-drop assignment
    """

    group_selected = pyqtSignal(str)
    membership_dropped = pyqtSignal(str, str)

    def __init__(self, db_manager: DatabaseManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._repo = GroupRepository(db_manager)
        self._current_group_id: Optional[str] = None

        self.setMinimumWidth(30)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)

        self._init_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QFrame()
        header.setFixedHeight(32)
        header.setFrameShape(QFrame.Shape.StyledPanel)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(6, 2, 4, 2)
        h_layout.setSpacing(4)

        self._lbl_title = QLabel()
        self._lbl_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        h_layout.addWidget(self._lbl_title)
        h_layout.addStretch()

        self._btn_new = QPushButton("+")
        self._btn_new.setFixedSize(22, 22)
        self._btn_new.setToolTip(self.tr("New top-level group"))
        self._btn_new.clicked.connect(lambda: self._create_group(parent_id=None))
        h_layout.addWidget(self._btn_new)

        layout.addWidget(header)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.setDragDropMode(QTreeWidget.DragDropMode.DropOnly)
        self._tree.setAcceptDrops(True)
        layout.addWidget(self._tree)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self._lbl_title.setText(self.tr("Groups"))
        self._btn_new.setToolTip(self.tr("New top-level group"))

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the tree from the repository."""
        self._tree.clear()

        # "All Documents" root item
        all_item = QTreeWidgetItem(self._tree)
        all_item.setText(0, self.tr("All Documents"))
        all_item.setData(0, Qt.ItemDataRole.UserRole, _ALL_DOCS_ID)
        all_item.setIcon(0, self.style().standardIcon(
            self.style().StandardPixmap.SP_DirHomeIcon
        ))
        font = all_item.font(0)
        font.setBold(True)
        all_item.setFont(0, font)

        # Recursive group population
        self._populate_children(parent_item=self._tree.invisibleRootItem(),
                                 parent_id=None,
                                 skip_root_item=all_item)
        self._tree.expandAll()

        # Restore selection
        self._restore_selection()

    def _populate_children(self, parent_item: QTreeWidgetItem,
                            parent_id: Optional[str],
                            skip_root_item: Optional[QTreeWidgetItem] = None) -> None:
        """Recursively add group items under parent_item."""
        groups = self._repo.get_children(parent_id)
        target = parent_item
        if skip_root_item is not None:
            target = skip_root_item  # top-level groups go under "All Documents"

        for group in groups:
            count = self._repo.get_document_count(group.id)
            item = QTreeWidgetItem(target)
            item.setText(0, self._item_label(group, count))
            item.setData(0, Qt.ItemDataRole.UserRole, group.id)
            if group.color:
                item.setForeground(0, QColor(group.color))
            self._populate_children(parent_item=item, parent_id=group.id)

    @staticmethod
    def _item_label(group: DocumentGroup, count: int) -> str:
        icon = group.icon or "📁"
        suffix = f"  ({count})" if count > 0 else ""
        return f"{icon} {group.name}{suffix}"

    def _restore_selection(self) -> None:
        if self._current_group_id is None:
            return
        it = self._find_item(self._current_group_id)
        if it:
            self._tree.setCurrentItem(it)

    def _find_item(self, group_id: str) -> Optional[QTreeWidgetItem]:
        """Search tree for item with matching group_id UserRole data."""
        iterator = QTreeWidgetItem
        def _search(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            if item.data(0, Qt.ItemDataRole.UserRole) == group_id:
                return item
            for i in range(item.childCount()):
                result = _search(item.child(i))
                if result:
                    return result
            return None
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            result = _search(root.child(i))
            if result:
                return result
        return None

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        group_id = item.data(0, Qt.ItemDataRole.UserRole)
        self._current_group_id = group_id if group_id != _ALL_DOCS_ID else None
        self.group_selected.emit(group_id)

    # ------------------------------------------------------------------
    # Context menu (CRUD)
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        menu = QMenu(self)

        act_new_top = QAction(self.tr("New Group"), self)
        act_new_top.triggered.connect(lambda: self._create_group(parent_id=None))
        menu.addAction(act_new_top)

        if item:
            group_id = item.data(0, Qt.ItemDataRole.UserRole)
            if group_id != _ALL_DOCS_ID:
                act_sub = QAction(self.tr("New Subgroup"), self)
                act_sub.triggered.connect(lambda: self._create_group(parent_id=group_id))
                menu.addAction(act_sub)

                menu.addSeparator()

                act_rename = QAction(self.tr("Rename…"), self)
                act_rename.triggered.connect(lambda: self._rename_group(group_id, item))
                menu.addAction(act_rename)

                act_delete = QAction(self.tr("Delete…"), self)
                act_delete.triggered.connect(lambda: self._delete_group(group_id))
                menu.addAction(act_delete)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def _create_group(self, parent_id: Optional[str]) -> None:
        name, ok = QInputDialog.getText(
            self, self.tr("New Group"), self.tr("Group name:")
        )
        if ok and name.strip():
            self._repo.create(name=name.strip(), parent_id=parent_id)
            self.refresh()

    def _rename_group(self, group_id: str, item: QTreeWidgetItem) -> None:
        group = self._repo.get_by_id(group_id)
        if not group:
            return
        name, ok = QInputDialog.getText(
            self, self.tr("Rename Group"), self.tr("New name:"),
            QLineEdit.EchoMode.Normal, group.name
        )
        if ok and name.strip():
            self._repo.rename(group_id, name.strip())
            self.refresh()

    def _delete_group(self, group_id: str) -> None:
        from PyQt6.QtWidgets import QMessageBox
        group = self._repo.get_by_id(group_id)
        if not group:
            return
        reply = QMessageBox.question(
            self,
            self.tr("Delete Group"),
            self.tr("Delete group '%s'? Documents will not be deleted.") % group.name,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._current_group_id == group_id:
                self._current_group_id = None
            self._repo.delete(group_id)
            self.refresh()
            if self._current_group_id is None:
                self.group_selected.emit(_ALL_DOCS_ID)

    # ------------------------------------------------------------------
    # Drag & drop — accept document UUIDs from DocumentList
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        item = self._tree.itemAt(self._tree.mapFrom(self, event.position().toPoint()))
        if not item:
            event.ignore()
            return
        group_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not group_id or group_id == _ALL_DOCS_ID:
            event.ignore()
            return
        for uuid in event.mimeData().text().splitlines():
            uuid = uuid.strip()
            if uuid:
                self._repo.add_membership(uuid, group_id)
                self.membership_dropped.emit(uuid, group_id)
        self.refresh()
        event.acceptProposedAction()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def current_group_id(self) -> Optional[str]:
        """Returns the currently selected group ID, or None for 'all'."""
        return self._current_group_id

    def changeEvent(self, event: QEvent) -> None:
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
            self.refresh()
        super().changeEvent(event)
