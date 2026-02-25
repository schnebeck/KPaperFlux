import pytest
import os
from PyQt6.QtCore import Qt
from gui.advanced_filter import AdvancedFilterWidget
from core.filter_tree import FilterTree, NodeType

@pytest.fixture
def filter_widget(qtbot):
    # Setup Tree with mixed items
    tree = FilterTree()
    
    # User Filters
    f_apple = tree.add_filter(tree.root, "Apple Filter", {"operator": "AND", "conditions": []})
    f_banana = tree.add_filter(tree.root, "Banana Filter", {"operator": "AND", "conditions": []})
    f_cherry = tree.add_filter(tree.root, "Cherry Filter", {"operator": "AND", "conditions": []})
    
    # System Nodes
    tree.add_archive(tree.root)
    tree.add_trash(tree.root)
    
    # Seeds for Top 3
    f_banana.usage_count = 10
    f_apple.usage_count = 5
    
    widget = AdvancedFilterWidget(filter_tree=tree)
    qtbot.addWidget(widget)
    return widget, tree, f_apple, f_banana, f_cherry

def test_filter_categorization_and_promotion(qtbot, filter_widget):
    widget, tree, f_apple, f_banana, f_cherry = filter_widget
    widget.show()
    
    combo = widget.combo_filters
    
    # 1. Initial Categorization Check
    # Expected: 0: --- Saved Filter ---, 1: ⭐ Banana, 2: ⭐ Apple, 3: Separator, 4: [ Archive ], 5: [ Trash ], 6: Separator, 7: Apple, 8: Banana, 9: Cherry...
    items = [combo.itemText(i) for i in range(combo.count())]
    
    assert "⭐ Banana Filter" in items[1]
    assert "⭐ Apple Filter" in items[2]
    assert "[ Archive ]" in items[4]
    assert "[ Trash ]" in items[5]
    
    # 2. Promotion Check (Pushing to Top 3)
    # Target: Cherry Filter
    cherry_idx = combo.findText("Cherry Filter")
    assert cherry_idx >= 0
    combo.setCurrentIndex(cherry_idx)
    
    # Each "Load" click should increment usage and refresh combo
    for _ in range(6):
        widget.btn_load.click()
        
    assert f_cherry.usage_count == 6
    
    # Refresh logic should have promoted it to ⭐ section
    new_items = [combo.itemText(i) for i in range(combo.count())]
    assert any("⭐ Cherry Filter" in txt for txt in new_items)

def test_rules_categorization_and_ui_alignment(qtbot, filter_widget):
    widget, tree, _, _, _ = filter_widget
    widget.show()
    
    # Switch to Rules Tab
    widget.btn_mode_rules.click()
    
    combo = widget.combo_rules
    # Rules list includes all filters that can be rules
    items = [combo.itemText(i) for i in range(combo.count())]
    
    # Categorization check for rules
    assert any("⭐ Banana Filter" in txt for txt in items)
    assert any("⭐ Apple Filter" in txt for txt in items)
    
    # UI Alignment Check (110px Labels)
    assert widget.lbl_rule_select.width() == 110
    assert widget.lbl_tags_add.width() == 110
    assert widget.lbl_tags_rem.width() == 110
    assert widget.lbl_assign_wf.width() == 110
    
    # Toggle Visibility Check
    assert widget.rules_scroll.isVisible() is False
    
    # "Laden" should show editor
    # Find a valid entry (not the header)
    valid_idx = -1
    for i in range(combo.count()):
        if combo.itemData(i) is not None:
            valid_idx = i
            break
            
    assert valid_idx >= 0
    combo.setCurrentIndex(valid_idx)
    widget.btn_load_rule.click()
    
    # Using waitUntil because visibility might depend on layout cycle
    qtbot.waitUntil(lambda: widget.rules_scroll.isVisible(), timeout=2000)
    assert widget.rules_editor_widget.isVisible()
    assert widget.btn_toggle_rules.text() == "🔼"

def test_layout_elasticity(qtbot, filter_widget):
    widget, _, _, _, _ = filter_widget
    widget.show()
    
    # 1. Height in Rules mode, editor collapsed
    widget.btn_mode_rules.click()
    collapsed_height = widget.sizeHint().height()
    
    # Selection and Loading should show editor and increase sizeHint
    combo = widget.combo_rules
    # Find a valid entry (not the header)
    valid_idx = -1
    for i in range(combo.count()):
        if combo.itemData(i) is not None:
            valid_idx = i
            break
    combo.setCurrentIndex(valid_idx)
    widget.btn_load_rule.click()
    
    qtbot.waitUntil(lambda: widget.rules_scroll.isVisible())
    expanded_height = widget.sizeHint().height()
    
    assert expanded_height > collapsed_height + 100 # Editor is at least 100px tall
    
    # 2. Toggle editor off
    widget.btn_toggle_rules.click()
    qtbot.waitUntil(lambda: not widget.rules_scroll.isVisible())
    
    # sizeHint should have decreased again
    final_height = widget.sizeHint().height()
    assert final_height < expanded_height
    assert abs(final_height - collapsed_height) < 20 # Should be back to original (+/- margin diff)
