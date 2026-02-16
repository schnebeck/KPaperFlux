import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6 import QtCore
from gui.advanced_filter import AdvancedFilterWidget
from core.database import DatabaseManager
from core.filter_tree import FilterTree

@pytest.fixture
def db_ft():
    db = DatabaseManager(":memory:")
    ft = FilterTree(db)
    return db, ft

def test_advanced_filter_layout_stability(qtbot, db_ft):
    db, ft = db_ft
    widget = AdvancedFilterWidget(db_manager=db, filter_tree=ft)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    
    # 1. State: No selection
    for b in widget.sub_mode_group.buttons():
        b.setChecked(False)
    widget._update_stack_visibility()
    
    btn = widget.sub_mode_group.button(0)
    
    def get_gap():
        global_btn_y = btn.mapToGlobal(QtCore.QPoint(0,0)).y()
        global_widget_y = widget.mapToGlobal(QtCore.QPoint(0,0)).y()
        return global_btn_y - global_widget_y

    gap_none = get_gap()
    print(f"Gap (None): {gap_none}")
    
    # Toggle each button and check gap
    for i in range(3):
        btn_to_click = widget.sub_mode_group.button(i)
        qtbot.mouseClick(btn_to_click, QtCore.Qt.MouseButton.LeftButton)
        
        gap_active = get_gap()
        print(f"Gap (Active {i}): {gap_active}")
        assert gap_active == gap_none, f"Layout shifted by {gap_active - gap_none}px when selecting button {i}!"
        
        # Click again to unselect
        qtbot.mouseClick(btn_to_click, QtCore.Qt.MouseButton.LeftButton)
        assert not any(b.isChecked() for b in widget.sub_mode_group.buttons())
        
        gap_unselected = get_gap()
        assert gap_unselected == gap_none, f"Layout shifted by {gap_unselected - gap_none}px when unselecting button {i}!"
