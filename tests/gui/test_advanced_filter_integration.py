
import pytest
from PyQt6.QtCore import Qt
from gui.advanced_filter import AdvancedFilterWidget, FilterConditionWidget

@pytest.fixture
def advanced_widget(qapp):
    widget = AdvancedFilterWidget()
    return widget

def test_add_remove_condition(advanced_widget, qtbot):
    qtbot.addWidget(advanced_widget)
    
    assert len(advanced_widget.root_group.children_widgets) == 0
    
    # Add condition
    advanced_widget.add_condition({"field": "sender", "op": "contains", "value": "Test"})
    assert len(advanced_widget.root_group.children_widgets) == 1
    
    # Remove
    row = advanced_widget.root_group.children_widgets[0]
    row.remove_requested.emit()
    assert len(advanced_widget.root_group.children_widgets) == 0

def test_query_generation(advanced_widget, qtbot):
    qtbot.addWidget(advanced_widget)
    
    advanced_widget.add_condition({"field": "doc_date", "op": "gt", "value": "2023-01-01"})
    advanced_widget.add_condition({"field": "amount", "op": "lt", "value": 100})
    
    # Set logic
    advanced_widget.root_group.combo_logic.setCurrentIndex(1) # OR
    
    query = advanced_widget.get_query()
    assert query["operator"] == "OR"
    assert len(query["conditions"]) == 2
    assert query["conditions"][0]["field"] == "doc_date"
