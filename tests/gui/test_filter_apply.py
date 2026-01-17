import pytest
from PyQt6.QtWidgets import QComboBox, QLineEdit
from gui.advanced_filter import AdvancedFilterWidget
from unittest.mock import MagicMock

@pytest.fixture
def filter_widget(qapp):
    widget = AdvancedFilterWidget(db_manager=None)
    widget.filter_changed = MagicMock() # Mock signal
    return widget

def test_apply_workflow(filter_widget):
    # 1. Add Condition
    filter_widget.add_condition()
    assert len(filter_widget.rows) == 1
    row = filter_widget.rows[0]
    
    # Check initial state of Apply button
    # If implemented, it should be Disabled initially?
    # Or enabled if we just added a condition that makes it dirty?
    # Adding condition -> is it dirty? Yes, query changed from {} to {conditions: empty}.
    # Let's assume implementation will handle it.
    
    # 2. Modify value
    # Trigger change
    row.current_input.setText("123")
    
    # Assert Signal NOT emitted yet (Manual Apply policy)
    filter_widget.filter_changed.emit.assert_not_called()
    
    # Assert Apply Button is ENABLED
    assert filter_widget.btn_apply.isEnabled()
    
    # 3. Click Apply
    filter_widget.btn_apply.click()
    
    # Assert Signal EMITTED
    filter_widget.filter_changed.emit.assert_called()
    args = filter_widget.filter_changed.emit.call_args[0][0]
    assert args['conditions'][0]['value'] == "123"
    
    # Assert Apply Button DISABLED (Clean state)
    assert not filter_widget.btn_apply.isEnabled()
