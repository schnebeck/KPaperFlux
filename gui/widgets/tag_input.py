from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLineEdit, QLabel, 
                             QPushButton, QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QKeyEvent

class TagBadge(QFrame):
    """A small pill/badge representing a single tag."""
    deleted = pyqtSignal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.setObjectName("TagBadge")
        self.setStyleSheet("""
            #TagBadge {
                background-color: #e3f2fd;
                border: 1px solid #bbdefb;
                border-radius: 4px;
                padding-left: 4px;
            }
            QLabel {
                color: #1976d2;
                font-weight: bold;
                font-size: 11px;
            }
            #CloseBtn {
                border: none;
                background: transparent;
                color: #1976d2;
                font-weight: bold;
                padding: 0 4px;
            }
            #CloseBtn:hover {
                color: #d32f2f;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        lbl = QLabel(text)
        layout.addWidget(lbl)
        
        btn = QPushButton("×")
        btn.setObjectName("CloseBtn")
        btn.setFixedSize(16, 16)
        btn.clicked.connect(lambda: self.deleted.emit(self.text))
        layout.addWidget(btn)

class TagInputWidget(QFrame):
    """
    A premium tag input field that renders tags as badges.
    Supports comma and enter as separators.
    """
    tagsChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TagInputWidget")
        self.setStyleSheet("""
            #TagInputWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
            }
            QLineEdit {
                border: none;
                background: transparent;
                min-width: 50px;
            }
        """)
        
        self.tags = []
        
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(4, 2, 4, 2)
        self.main_layout.setSpacing(4)
        
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText("...")
        self.line_edit.textChanged.connect(self._on_text_changed)
        self.line_edit.returnPressed.connect(self._add_current_text)
        self.line_edit.installEventFilter(self)
        
        self.main_layout.addWidget(self.line_edit)
        self.main_layout.addStretch()

    def setTags(self, tags: list[str]):
        """Programmatically set the list of tags."""
        self.clear()
        for t in tags:
            self._add_tag_ui(t)
        self.tags = list(tags)

    def getTags(self) -> list[str]:
        return self.tags

    def clear(self):
        self.tags = []
        # Remove all widgets except line_edit and stretch
        for i in reversed(range(self.main_layout.count())):
            item = self.main_layout.itemAt(i)
            w = item.widget()
            if w and w != self.line_edit:
                w.deleteLater()
                self.main_layout.removeItem(item)
        self.line_edit.clear()

    def eventFilter(self, obj, event):
        if obj == self.line_edit and event.type() == QEvent.Type.KeyPress:
            # FIX: Do not re-wrap the event. In PyQt6 event IS the QKeyEvent.
            key_event = event 
            if key_event.key() == Qt.Key.Key_Backspace and not self.line_edit.text() and self.tags:
                self._remove_tag(self.tags[-1])
                return True
        return super().eventFilter(obj, event)

    def _on_text_changed(self, text):
        if text.endswith(",") or text.endswith(";"):
            self._add_current_text()

    def _add_current_text(self):
        text = self.line_edit.text().strip().strip(",").strip(";")
        if text and text not in self.tags:
            self.tags.append(text)
            self._add_tag_ui(text)
            self.line_edit.clear()
            self.tagsChanged.emit(self.tags)
        elif text in self.tags:
            self.line_edit.clear()

    def _add_tag_ui(self, text):
        badge = TagBadge(text)
        badge.deleted.connect(self._remove_tag)
        # Insert before line_edit
        self.main_layout.insertWidget(self.main_layout.count() - 2, badge)

    def _remove_tag(self, text):
        if text in self.tags:
            self.tags.remove(text)
            # Find and remove widget
            for i in range(self.main_layout.count()):
                item = self.main_layout.itemAt(i)
                w = item.widget()
                if isinstance(w, TagBadge) and w.text == text:
                    w.deleteLater()
                    break
            self.tagsChanged.emit(self.tags)

    def setText(self, text: str):
        """Standard compatibility for loading comma separated strings."""
        tags = [t.strip() for t in text.split(",") if t.strip()]
        self.setTags(tags)

    def text(self) -> str:
        """Standard compatibility for getting comma separated strings."""
        return ", ".join(self.tags)
