"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/widgets/group_membership_chips.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    GroupMembershipWidget — tag-cloud-style chip display for the
                group memberships of a single document. Shown in the General
                tab of MetadataEditor. Each chip shows the full breadcrumb
                path (Parent / Child) and has an × remove button.
                A '+' button opens GroupPickerDialog to add memberships.
------------------------------------------------------------------------------
"""
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from core.database import DatabaseManager
from core.models.group import DocumentGroup
from core.repositories.group_repo import GroupRepository
from core.logger import get_logger

logger = get_logger("gui.widgets.group_membership_chips")

_ALL_DOCS_ID = "__ALL__"


class _GroupPickerDialog(QDialog):
    """Simple tree dialog to pick a group for adding membership."""

    def __init__(self, repo: GroupRepository, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Add to Group"))
        self.resize(320, 400)
        self._repo = repo
        self._selected_id: Optional[str] = None

        layout = QVBoxLayout(self)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._populate()
        layout.addWidget(self._tree)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate(self) -> None:
        self._tree.clear()
        self._add_children(self._tree.invisibleRootItem(), None)
        self._tree.expandAll()

    def _add_children(self, parent_item: QTreeWidgetItem, parent_id: Optional[str]) -> None:
        for group in self._repo.get_children(parent_id):
            item = QTreeWidgetItem(parent_item)
            item.setText(0, f"{group.icon or '📁'} {group.name}")
            item.setData(0, Qt.ItemDataRole.UserRole, group.id)
            self._add_children(item, group.id)

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        self._selected_id = item.data(0, Qt.ItemDataRole.UserRole)

    def selected_group_id(self) -> Optional[str]:
        return self._selected_id


class GroupMembershipWidget(QWidget):
    """
    Horizontal flow of group-membership chips for a single document.

    Signals:
        membership_changed — emitted after any add or remove operation
    """

    membership_changed = pyqtSignal()

    def __init__(self, db_manager: DatabaseManager,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._repo = GroupRepository(db_manager)
        self._document_uuid: Optional[str] = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.addStretch()

        self._btn_add = QPushButton("+")
        self._btn_add.setFixedSize(22, 22)
        self._btn_add.setToolTip(self.tr("Add to group"))
        self._btn_add.clicked.connect(self._on_add)
        self._layout.addWidget(self._btn_add)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_document(self, document_uuid: Optional[str]) -> None:
        """Load groups for the given document UUID and refresh chips."""
        self._document_uuid = document_uuid
        self._refresh()

    def clear_document(self) -> None:
        """Clear all chips (no document selected)."""
        self._document_uuid = None
        self._refresh()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Rebuild chip row from current membership data."""
        # Remove all chips (keep stretch + add-button at the end)
        while self._layout.count() > 2:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._document_uuid:
            return

        groups = self._repo.get_groups_for_document(self._document_uuid)
        for group in groups:
            chip = self._make_chip(group)
            self._layout.insertWidget(self._layout.count() - 2, chip)

    def _make_chip(self, group: DocumentGroup) -> QFrame:
        """Build a single pill-shaped chip for the given group."""
        breadcrumb = self._breadcrumb(group)
        icon = group.icon or "📁"
        color = group.color or "#4b5563"

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {color}22; border: 1px solid {color}; "
            f"border-radius: 10px; padding: 1px 4px; }}"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(4, 1, 2, 1)
        h.setSpacing(2)

        lbl = QLabel(f"{icon} {breadcrumb}")
        lbl.setStyleSheet(f"color: {color}; font-size: 11px; border: none; background: transparent;")
        h.addWidget(lbl)

        btn_x = QPushButton("×")
        btn_x.setFixedSize(16, 16)
        btn_x.setStyleSheet(
            f"QPushButton {{ color: {color}; font-weight: bold; border: none; "
            f"background: transparent; padding: 0; }}"
            f"QPushButton:hover {{ color: #dc2626; }}"
        )
        btn_x.setToolTip(self.tr("Remove from group"))
        btn_x.clicked.connect(lambda _checked, gid=group.id: self._on_remove(gid))
        h.addWidget(btn_x)

        return frame

    def _breadcrumb(self, group: DocumentGroup) -> str:
        """Build a Parent / Child breadcrumb string for display."""
        if group.parent_id:
            parent = self._repo.get_by_id(group.parent_id)
            if parent:
                return f"{parent.name} / {group.name}"
        return group.name

    def _on_add(self) -> None:
        if not self._document_uuid:
            return
        dlg = _GroupPickerDialog(self._repo, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_group_id():
            self._repo.add_membership(self._document_uuid, dlg.selected_group_id())
            self._refresh()
            self.membership_changed.emit()

    def _on_remove(self, group_id: str) -> None:
        if not self._document_uuid:
            return
        self._repo.remove_membership(self._document_uuid, group_id)
        self._refresh()
        self.membership_changed.emit()

    def changeEvent(self, event: QEvent) -> None:
        if event and event.type() == QEvent.Type.LanguageChange:
            self._btn_add.setToolTip(self.tr("Add to group"))
        super().changeEvent(event)
