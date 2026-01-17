import pytest
import os
import shutil
from PyQt6.QtCore import Qt
from gui.advanced_filter import AdvancedFilterWidget, FilterConditionWidget
from PyQt6.QtWidgets import QApplication

@pytest.fixture
def app(qapp):
    return qapp

@pytest.fixture
def advanced_widget(app):
    widget = AdvancedFilterWidget()
    return widget

def test_add_remove_condition(advanced_widget, qtbot):
    """Test adding and removing filter conditions."""
    qtbot.addWidget(advanced_widget)
    
    initial_count = len(advanced_widget.rows)
    assert initial_count == 0
    
    # Add Condition
    qtbot.mouseClick(advanced_widget.btn_add, Qt.MouseButton.LeftButton)
    assert len(advanced_widget.rows) == 1
    
    # Check Row content
    row = advanced_widget.rows[0]
    assert isinstance(row, FilterConditionWidget)
    assert row.combo_field.count() > 0
    
    # Remove
    qtbot.mouseClick(row.btn_remove, Qt.MouseButton.LeftButton)
    assert len(advanced_widget.rows) == 0

def test_query_generation(advanced_widget, qtbot):
    """Test generating query object from UI."""
    qtbot.addWidget(advanced_widget)
    
    # Add Row: Amount > 100
    qtbot.mouseClick(advanced_widget.btn_add, Qt.MouseButton.LeftButton)
    row = advanced_widget.rows[0]
    
    row.combo_field.setCurrentText("Amount")
    row.combo_op.setCurrentIndex(row.combo_op.findData("gt")) # Greater Than
    row.current_input.setText("100")
    
    query = advanced_widget.get_query_object()
    assert query["operator"] == "AND" # Default
    assert len(query["conditions"]) == 1
    
    cond = query["conditions"][0]
    assert cond["field"] == "amount"
    assert cond["op"] == "gt"
    assert cond["value"] == "100"

def test_persistence(advanced_widget, qtbot):
    """Test saving and loading filters (Mock QSettings?)."""
    # QSettings uses Organization Name. Test env might share.
    # We rely on QSettings being functional.
    
    qtbot.addWidget(advanced_widget)
    
    # Setup some state
    advanced_widget.load_from_object({
        "operator": "OR",
        "conditions": [{"field": "sender", "op": "contains", "value": "Test"}]
    })
    
    assert len(advanced_widget.rows) == 1
    assert advanced_widget.combo_logic.currentText().startswith("ANY")
    
    # Mocking QInputDialog is hard via qtbot.
    # We test load_from_object and get_query_object mainly.
    # To test save, we'd need to mock QInputDialog.getText.
    # Let's verify internal map update if we manually call save logic step.
    
    # Manually adding to saved_filters_map
    advanced_widget.saved_filters_map["TestFilter"] = {"conditions": []}
    advanced_widget._persist()
    
    # Create new widget to verify reload
    new_widget = AdvancedFilterWidget()
    assert "TestFilter" in new_widget.saved_filters_map
