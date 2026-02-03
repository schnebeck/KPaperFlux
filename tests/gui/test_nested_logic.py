
import pytest
from gui.advanced_filter import AdvancedFilterWidget
from gui.widgets.filter_group import FilterGroupWidget

class MockDBManager:
    def get_available_extra_keys(self): return []
    def get_available_tags(self, system: bool = False): return []

@pytest.fixture
def filter_widget(qapp):
    db = MockDBManager()
    return AdvancedFilterWidget(db_manager=db)

def test_root_group_exists(filter_widget):
    assert isinstance(filter_widget.root_group, FilterGroupWidget)
    assert filter_widget.root_group.is_root
    # Root should have logic combo accessible
    assert filter_widget.root_group.combo_logic is not None

def test_add_nested_group(filter_widget):
    root = filter_widget.root_group
    
    # Add simple condition
    root.add_condition({"field": "sender", "op": "contains", "value": "Alice"})
    
    # Add Group
    root.add_group()
    assert len(root.children_widgets) == 2
    
    group = root.children_widgets[1]
    assert isinstance(group, FilterGroupWidget)
    assert not group.is_root
    
    # Add condition to subgroup
    group.add_condition({"field": "tags", "op": "in", "value": ["urgent"]})
    
    # Verify Query Structure
    query = filter_widget.get_query()
    assert query["operator"] == "AND" # Default
    assert len(query["conditions"]) == 2
    
    cond1 = query["conditions"][0]
    assert cond1["field"] == "sender"
    assert cond1["value"] == "Alice"
    
    grp1 = query["conditions"][1]
    assert grp1["operator"] == "AND" # Default
    assert len(grp1["conditions"]) == 1
    assert grp1["conditions"][0]["field"] == "tags"

def test_load_nested_query(filter_widget):
    # Prepare nested data
    data = {
        "operator": "OR",
        "conditions": [
            {"field": "doc_date", "op": "gt", "value": "2023-01-01"},
            {
                "operator": "AND",
                "conditions": [
                    {"field": "tags", "op": "in", "value": ["invoice"]},
                    {"field": "amount", "op": "gt", "value": 100}
                ]
            }
        ]
    }
    
    # Load via set_query on root (simulated load_from_node logic)
    filter_widget.root_group.set_query(data)
    
    # Verify UI
    root = filter_widget.root_group
    assert root.combo_logic.currentText().startswith("OR")
    assert len(root.children_widgets) == 2
    
    # Child 1: Condition
    assert root.children_widgets[0].get_condition()["field"] == "doc_date"
    
    # Child 2: Group
    subgroup = root.children_widgets[1]
    assert isinstance(subgroup, FilterGroupWidget)
    assert subgroup.combo_logic.currentText().startswith("AND")
    assert len(subgroup.children_widgets) == 2

