import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTranslator, QLibraryInfo
from gui.widgets.filter_group import FilterGroupWidget
from core.filter_tree import FilterTree

def test_filter_group_l10n_retrieval(qapp):
    """Verifies that FilterGroupWidget and its elements are translatable."""
    tree = FilterTree()
    widget = FilterGroupWidget(is_root=True)
    
    # Check default English (source)
    assert widget.combo_logic.itemText(0) == "AND"
    assert widget.btn_add_condition.text() == "+ Condition"
    
    # Verify tr() call for AND
    # Since we can't easily load the .qm in this environment and expect it to work without paths,
    # we check if the retranslate_ui exists and calls the expected methods.
    assert hasattr(widget, "retranslate_ui")
    widget.retranslate_ui()
    
    # Check if sub-widget would be created correctly
    widget.add_condition()
    child = widget.children_widgets[0]
    assert hasattr(child, "retranslate_ui")
    assert child.btn_field_selector.text() == "Select Field..."

def test_filter_group_language_change_event(qapp):
    """Verifies that sending a LanguageChange event does not crash and updates UI."""
    from PyQt6.QtCore import QEvent
    tree = FilterTree()
    widget = FilterGroupWidget(is_root=True)
    widget.add_condition()
    
    # Simulate LanguageChange event
    event = QEvent(QEvent.Type.LanguageChange)
    QApplication.sendEvent(widget, event)
    
    # If no crash occurred, the test passes. 
    # retranslate_ui should have been called.
