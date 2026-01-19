
import pytest
from PyQt6.QtWidgets import QComboBox, QLineEdit
from gui.advanced_filter import AdvancedFilterWidget, FilterConditionWidget
from gui.widgets.multi_select_combo import MultiSelectComboBox
from gui.widgets.date_range_picker import DateRangePicker

class MockDBManager:
    def get_available_extra_keys(self):
        return ["semantic:invoice.total", "json:custom_field"]
        
    def get_available_tags(self):
        return ["tag1", "tag2", "urgent"]

@pytest.fixture
def filter_widget(qapp):
    db_manager = MockDBManager()
    widget = AdvancedFilterWidget(db_manager=db_manager)
    return widget

def test_add_condition_initial(filter_widget):
    filter_widget.add_condition()
    assert len(filter_widget.rows) == 1
    row = filter_widget.rows[0]
    # Default stack index 0 (Text)
    assert row.input_stack.currentIndex() == 0
    assert isinstance(row.input_stack.currentWidget(), QLineEdit)

def test_switch_to_tags(filter_widget):
    filter_widget.add_condition()
    row = filter_widget.rows[0]
    
    # Change field to 'Tags'
    # Find index for 'Tags'
    # The combo is populated with names, we need to find "Tags" text or data "tags"
    # Actually _on_field_changed handles text. 
    # But set_condition logic handles lookup. Let's use set_condition for easier testing.
    
    row.set_condition({"field": "tags", "op": "contains", "value": []})
    
    assert row.input_stack.currentIndex() == 1
    assert isinstance(row.input_stack.currentWidget(), MultiSelectComboBox)
    
    # Check population
    combo = row.input_stack.currentWidget()
    assert combo.count() == 3 # tag1, tag2, urgent
    
def test_switch_to_date(filter_widget):
    filter_widget.add_condition()
    row = filter_widget.rows[0]
    
    row.set_condition({"field": "doc_date", "op": "between", "value": "2023-01-01,2023-01-31"})
    
    assert row.input_stack.currentIndex() == 2
    assert isinstance(row.input_stack.currentWidget(), DateRangePicker)
    
    # Check value
    picker = row.input_stack.currentWidget()
    assert picker.get_value() == "2023-01-01,2023-01-31"

def test_get_condition_tags(filter_widget):
    filter_widget.add_condition()
    row = filter_widget.rows[0]
    
    # Set Up
    row.set_condition({"field": "tags", "op": "in", "value": ["urgent", "tag1"]})
    
    # Get Back
    cond = row.get_condition()
    assert cond["field"] == "tags"
    assert "urgent" in cond["value"]
    assert "tag1" in cond["value"]
    assert len(cond["value"]) == 2

