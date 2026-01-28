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
        
        # Determine text to show
        checked = self.getCheckedItems()
        if checked:
            opt.currentText = ", ".join(checked)
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
        items = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                items.append(item.text())
        return items

    def setCheckedItems(self, items: list[str]):
        self.model.blockSignals(True)
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            state = Qt.CheckState.Checked if item.text() in items else Qt.CheckState.Unchecked
            item.setCheckState(state)
        self.model.blockSignals(False)
        self.update()

    def currentText(self):
        return ", ".join(self.getCheckedItems())

    def clear(self):
        super().clear()
        self.update()
