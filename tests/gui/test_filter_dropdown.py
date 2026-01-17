import pytest
from PyQt6.QtWidgets import QApplication
from gui.advanced_filter import AdvancedFilterWidget
from unittest.mock import MagicMock

@pytest.fixture
def filter_widget(qapp):
    widget = AdvancedFilterWidget(db_manager=None)
    # Bypass persistence loading which overwrites map
    widget.saved_filters_map = {
        "Test Filter A": {"operator": "AND", "conditions": [{"field": "amount", "op": "equals", "value": 100}]},
        "Test Filter B": {"operator": "OR", "conditions": []}
    }
    
    # Reload combo from map manually (bypassing settings read)
    widget.combo_filters.clear()
    widget.combo_filters.addItem(widget.tr("- Select -"), None)
    for name in sorted(widget.saved_filters_map.keys()):
        widget.combo_filters.addItem(name, name)
        
    return widget

def test_dropdown_retains_selection_on_load(filter_widget):
    # Initial state
    assert filter_widget.combo_filters.currentText() == "- Select -"
    
    # Select "Test Filter A"
    # Find index
    print(f"DEBUG: Items in combo: {[filter_widget.combo_filters.itemText(i) for i in range(filter_widget.combo_filters.count())]}")
    index = filter_widget.combo_filters.findText("Test Filter A")
    assert index >= 0
    
    # Act: Trigger selection (simulate user click)
    filter_widget.combo_filters.setCurrentIndex(index)
    # Note: connect(self._on_saved_filter_selected) was commented out in code:
    # "self.combo_filters.currentIndexChanged.connect(self._on_saved_filter_selected) # Removed auto-trigger..."
    # User said: "Drücke ich dann 'Load' springt der Name zurück"
    # So I must click "Load" button.
    
    # So select dropdown...
    filter_widget.combo_filters.setCurrentIndex(index)
    assert filter_widget.combo_filters.currentText() == "Test Filter A"
    
    # ... Then click Load
    filter_widget.btn_load.click()
    
    # Assert: Dropdown should STILL equal "Test Filter A"
    # Bug Expectation: It reverts to "- Select -" because load calls clear_all() which resets combo.
    assert filter_widget.combo_filters.currentText() == "Test Filter A"
