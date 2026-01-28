
import sys
import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.advanced_filter import FilterConditionWidget
from gui.widgets.multi_select_combo import MultiSelectComboBox

# We need a QApplication for widget tests
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

class TestFilterUI(unittest.TestCase):
    def test_multi_select_combo(self):
        combo = MultiSelectComboBox()
        combo.addItems(["A", "B", "C"])
        
        # Initially empty
        self.assertEqual(combo.getCheckedItems(), [])
        self.assertEqual(combo.currentText(), "")
        
        # Check an item
        item = combo.model.item(0)
        item.setCheckState(Qt.CheckState.Checked)
        
        # Verify state
        self.assertEqual(combo.getCheckedItems(), ["A"])
        self.assertEqual(combo.currentText(), "A")
        
        # Check another
        item2 = combo.model.item(1)
        item2.setCheckState(Qt.CheckState.Checked)
        self.assertEqual(combo.getCheckedItems(), ["A", "B"])
        self.assertEqual(combo.currentText(), "A, B")

    def test_filter_condition_widget_audit_mode(self):
        widget = FilterConditionWidget()
        
        # Change to Visual Audit
        # Find index for "Visual Audit"
        idx = widget.combo_field.findText("Visual Audit")
        self.assertNotEqual(idx, -1)
        widget.combo_field.setCurrentIndex(idx)
        
        # Verify stack index is 1 (MultiSelect)
        self.assertEqual(widget.input_stack.currentIndex(), 1)
        
        # Verify items are added
        items = [widget.input_multi.model.item(i).text() for i in range(widget.input_multi.model.rowCount())]
        self.assertIn("STAMP_ONLY", items)
        
        # Simulate checking an item
        combo = widget.input_multi
        item = combo.model.item(0)
        item.setCheckState(Qt.CheckState.Checked)
        
        # Verify line edit shows it
        self.assertEqual(combo.currentText(), item.text())
        
        # Verify get_condition returns it
        cond = widget.get_condition()
        self.assertEqual(cond["field"], "visual_audit_mode")
        self.assertEqual(cond["value"], [item.text()])

if __name__ == "__main__":
    unittest.main()
