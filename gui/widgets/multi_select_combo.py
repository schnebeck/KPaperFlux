
from PyQt6.QtWidgets import QComboBox, QLineEdit
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt, pyqtSignal

class MultiSelectComboBox(QComboBox):
    """
    A QComboBox that allows selecting multiple items via checkboxes.
    The display text shows a comma-separated list of selected items.
    """
    selectionChanged = pyqtSignal(list) # Emits list of selected strings

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.current_items = []
        
        # Use QStandardItemModel to support checkable items
        self.model = QStandardItemModel(self)
        self.setModel(self.model)
        
        # Connect model item changed signal
        self.model.itemChanged.connect(self.on_item_changed)
        
        # Connect activated to toggle (allows clicking the text instead of just the checkbox)
        self.activated.connect(self._on_activated)
        
        # Connect line edit click to show popup (optional UX improvement)
        self.lineEdit().selectionChanged.connect(self.showPopup)

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)

    def clear(self):
        super().clear()
        self.update_line_edit()
        self.setCurrentIndex(-1)

    def addItem(self, text, data=None):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        if data is not None:
            item.setData(data, Qt.ItemDataRole.UserRole)
        self.model.appendRow(item)
        self.update_line_edit()

    def on_item_changed(self, item):
        self.update_line_edit()
        self.selectionChanged.emit(self.getCheckedItems())
        # If any item is checked, we don't really care about currentIndex, 
        # but if we want to avoid the 'first item ghost' we can keep it -1
        self.setCurrentIndex(-1)

    def _on_activated(self, index):
        item = self.model.item(index)
        if item:
            new_state = Qt.CheckState.Checked if item.checkState() == Qt.CheckState.Unchecked else Qt.CheckState.Unchecked
            item.setCheckState(new_state)
        
        # Hack to keep popup open for multi-selection
        # Standard QComboBox closes on activation.
        self.showPopup()

    def update_line_edit(self):
        checked = self.getCheckedItems()
        text = ", ".join(checked)
        self.lineEdit().setText(text)
        self.setCurrentIndex(-1)    
    def getCheckedItems(self) -> list[str]:
        items = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                items.append(item.text())
        return items

    def showPopup(self):
        super().showPopup()
        # Optionally adjust width to content
        
    def hidePopup(self):
        # Optional: check if we should stay open (e.g. if Shift is held?)
        # For now, let's keep standard behavior but maybe log.
        super().hidePopup()

    def setCheckedItems(self, items: list[str]):
        """
        Set the checked state for the given list of strings.
        Clears previous selection.
        """
        # Block signals to prevent multiple updates/signals
        self.model.blockSignals(True)
        
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.text() in items:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
                
        self.model.blockSignals(False)
        self.update_line_edit()
        
    def currentText(self):
        # Override to return the comma list
        return self.lineEdit().text()
        
    def setCurrentText(self, text):
        # Override behavior: Try to parse comma list or set individual?
        # Usually called by set data.
        # If text is single item, check it.
        # If text is "A, B", check both.
        items = [t.strip() for t in text.split(",") if t.strip()]
        self.setCheckedItems(items)

    def hidePopup(self):
        # Prevent hiding immediately when clicking inside (checkboxes)
        # But we need to allow hiding when clicking outside.
        # Standard QComboBox behavior usually hides on item click. 
        # With Checkboxes, we want to keep it open.
        # This is tricky. For now, let's accept standard behavior (closes on click)
        # because properly keeping it open requires installing event filter or re-implementing view.
        # However, standard QComboBox view click usually closes popup.
        super().hidePopup()
