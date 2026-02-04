from PyQt6.QtWidgets import QComboBox, QLineEdit, QStylePainter, QStyleOptionComboBox, QStyle
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QPalette
from PyQt6.QtCore import Qt, pyqtSignal, QRect

class MultiSelectComboBox(QComboBox):
    """
    A QComboBox that allows selecting multiple items via checkboxes.
    Uses custom painting to show selected items as a comma-separated list.
    """
    selectionChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(False) # Paint manually instead
        
        self.model = QStandardItemModel(self)
        self.setModel(self.model)
        self.model.itemChanged.connect(self.on_item_changed)
        self.activated.connect(self._on_activated)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        painter.setPen(self.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Text))
        
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        
        # Determine text to show (Labels)
        checked_labels = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_labels.append(item.text())
        
        if checked_labels:
            opt.currentText = ", ".join(checked_labels)
        else:
            opt.currentText = "" # Or placeholder
            
        # Draw the combo box frame and arrow
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        # Draw the text
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, opt)

    def addItem(self, text, data=None):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        if data is not None:
            item.setData(data, Qt.ItemDataRole.UserRole)
        self.model.appendRow(item)
        self.update()

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)

    def on_item_changed(self, item):
        self.update() # Trigger repaint
        self.selectionChanged.emit(self.getCheckedItems())

    def _on_activated(self, index):
        item = self.model.item(index)
        if item:
            new_state = Qt.CheckState.Checked if item.checkState() == Qt.CheckState.Unchecked else Qt.CheckState.Unchecked
            item.setCheckState(new_state)
        self.showPopup()

    def getCheckedItems(self) -> list[str]:
        """Returns the list of technical values (UserData) for checked items."""
        items = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                val = item.data(Qt.ItemDataRole.UserRole)
                if val is None: val = item.text()
                items.append(str(val))
        return items

    def setCheckedItems(self, items: list[str]):
        """Sets check states based on technical values (UserData)."""
        self.model.blockSignals(True)
        items = [str(i) for i in items]
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            val = item.data(Qt.ItemDataRole.UserRole)
            if val is None: val = item.text()
            
            state = Qt.CheckState.Checked if str(val) in items else Qt.CheckState.Unchecked
            item.setCheckState(state)
        self.model.blockSignals(False)
        self.update()

    def currentText(self):
        return ", ".join(self.getCheckedItems())

    def clear(self):
        super().clear()
        self.update()
