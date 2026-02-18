import pytest
from PyQt6.QtWidgets import QApplication, QToolButton
from PyQt6.QtCore import Qt, QEvent
from gui.advanced_filter import AdvancedFilterWidget
from core.filter_tree import FilterTree

def test_navigation_buttons_localized(qapp):
    """
    Integration test to verify that navigation buttons in AdvancedFilterWidget
    use literal tr() calls that we can intercept.
    """
    tree = FilterTree()
    widget = AdvancedFilterWidget(filter_tree=tree)
    
    # Check if buttons are named correctly and have text placeholders
    assert widget.btn_mode_search is not None
    assert widget.btn_mode_filter is not None
    assert widget.btn_mode_rules is not None
    
    # In a real L10n test with translator, these would be German.
    # Here we just verify the names exist.
    assert "Search" in widget.btn_mode_search.text()
    assert "Filter" in widget.btn_mode_filter.text()
    assert "Rules" in widget.btn_mode_rules.text()

def test_filter_manager_persistence(qapp):
    """
    Verify that FilterManagerDialog has settings and geometry persistence.
    """
    from gui.filter_manager import FilterManagerDialog
    tree = FilterTree()
    dialog = FilterManagerDialog(tree)
    
    assert hasattr(dialog, "settings")
    assert hasattr(dialog, "restore_geometry")
    assert hasattr(dialog, "save_settings")
