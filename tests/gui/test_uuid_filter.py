import pytest
from PyQt6.QtWidgets import QApplication
from gui.advanced_filter import AdvancedFilterWidget, FilterConditionWidget
from PyQt6.QtCore import Qt

def test_uuid_filter_fields(qapp):
    widget = FilterConditionWidget()
    
    # Check if UUID is in FIELDS
    field_keys = widget.FIELDS.keys()
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
    # Field should show UUID
    assert widget.btn_field_selector.text() == "UUID"
    
    # Operator should be "In List"
    assert widget.combo_op.currentData() == "in"
    
    # Input should show CSV string
    assert widget.input_text.text() == "u1, u2, u3"
    
def test_get_condition_uuid_list(qapp):
    widget = FilterConditionWidget()
    
    # Set UI state manually
    # Select UUID
    widget._set_field("uuid", "UUID")
    
    # Select IN
    idx_op = widget.combo_op.findData("in")
    widget.combo_op.setCurrentIndex(idx_op)
    
    # Enter CSV
    widget.input_text.setText("u1, u2,   u3")
    
    # Get Data
    data = widget.get_condition()
    
    assert data['field'] == 'uuid'
    assert data['op'] == 'in'
    # Should be parsed list
    assert data['value'] == ["u1", "u2", "u3"]
