import pytest
from PyQt6.QtWidgets import QCheckBox, QComboBox
from gui.advanced_filter import AdvancedFilterWidget

def test_filter_toggle_logic(qtbot):
    widget = AdvancedFilterWidget()
    qtbot.addWidget(widget)
    
    # Add a condition
    widget.add_condition({"field": "sender", "op": "contains", "value": "Test"})
    
    # 1. Active (Default) -> Should match condition
    # catch signal
    with qtbot.waitSignal(widget.filter_changed) as blocker:
        widget._emit_change()
    assert blocker.args[0]["conditions"][0]["value"] == "Test"
    
    # 2. Toggle Off
    widget.chk_active.setChecked(False)
    # verify signal emitted is empty
    # Toggling emits signal automatically via connect
    # But to be sure, let's toggle programmatically
    
    # 3. Test Signal on Toggle
    with qtbot.waitSignal(widget.filter_changed) as blocker:
        widget.chk_active.setChecked(True) # Toggle ON
    # Should emit query
    assert len(blocker.args[0].get("conditions", [])) == 1

    with qtbot.waitSignal(widget.filter_changed) as blocker:
        widget.chk_active.setChecked(False) # Toggle OFF
    # Should emit empty query
    assert blocker.args[0] == {}

def test_clear_all_resets_combo(qtbot):
    widget = AdvancedFilterWidget()
    qtbot.addWidget(widget)
    
    # Mock saved filters
    widget.saved_filters_map = {"TestFilter": {"foo": "bar"}}
    
    # Clear persistence pollution
    widget.combo_filters.blockSignals(True)
    widget.combo_filters.clear()
    widget.combo_filters.addItem("- Select -", None)
    widget.combo_filters.addItem("TestFilter", "TestFilter")
    widget.combo_filters.blockSignals(False)
    
    # Select it
    widget.combo_filters.setCurrentIndex(1)
    assert widget.combo_filters.currentText() == "TestFilter"
    
    # Click Clear All
    widget.clear_all()
    
    # Should reset to index 0 ("- Select -")
    assert widget.combo_filters.currentIndex() == 0
