import pytest
from PyQt6.QtWidgets import QApplication
from gui.advanced_filter import AdvancedFilterWidget, FilterConditionWidget
from PyQt6.QtCore import Qt

def test_uuid_filter_fields(qapp):
    widget = FilterConditionWidget()
    
    # Check if UUID is in FIELDS
    field_keys = widget.FIELDS.values()
    assert "uuid" in field_keys, "UUID field missing in FilterConditionWidget"
    
    # Check if IN is in OPERATORS
    op_keys = [k for n, k in widget.OPERATORS]
    assert "in" in op_keys, "IN operator missing in FilterConditionWidget"

def test_set_condition_uuid_list(qapp):
    widget = FilterConditionWidget()
    
    # Simulate loading a "Save as List" filter
    # Condition: {field: uuid, op: in, value: [u1, u2]}
    condition = {
        "field": "uuid",
        "op": "in",
        "value": ["u1", "u2", "u3"],
        "negate": False
    }
    
    widget.set_condition(condition)
    
    # Verify Display
    # Field Combo should show UUID
    assert widget.combo_field.currentText() == "UUID"
    
    # Operator should be "In List"
    assert widget.combo_op.currentData() == "in"
    
    # Input should show CSV string
    # We implemented ", ".join(...)
    assert widget.current_input.text() == "u1, u2, u3"
    
def test_get_condition_uuid_list(qapp):
    widget = FilterConditionWidget()
    
    # Set UI state manually
    # Select UUID
    idx = widget.combo_field.findText("UUID")
    widget.combo_field.setCurrentIndex(idx)
    
    # Select IN
    idx_op = widget.combo_op.findData("in")
    widget.combo_op.setCurrentIndex(idx_op)
    
    # Enter CSV
    widget.current_input.setText("u1, u2,   u3")
    
    # Get Data
    data = widget.get_condition()
    
    assert data['field'] == 'uuid'
    assert data['op'] == 'in'
    # Should be parsed list
    assert data['value'] == ["u1", "u2", "u3"]
