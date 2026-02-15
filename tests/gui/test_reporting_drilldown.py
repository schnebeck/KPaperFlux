import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QTableWidget
from gui.reporting import ReportingWidget
from core.models.reporting import ReportDefinition, ReportComponent

@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def reporting_widget(qtbot):
    widget = ReportingWidget(db_manager=MagicMock())
    qtbot.addWidget(widget)
    return widget

def test_table_drill_down_filtering(qtbot, reporting_widget):
    """
    Verify that clicking a row in a reporting table emits filter_requested.
    """
    # 1. Setup a report definition with a table
    comp = ReportComponent(type="table")
    definition = ReportDefinition(
        id="test_report",
        name="Test Report",
        group_by="sender",
        components=[comp]
    )
    
    # 2. Mock results
    results = {
        "title": "Test Results",
        "table_rows": [
            {"Sender": "Telekom", "Count": 5, "Total": 100.0},
            {"Sender": "Amazon", "Count": 2, "Total": 50.0}
        ]
    }
    
    # Manually trigger rendering/setup to inject our components
    reporting_widget.render_report(results, definition)
    
    # Find the table widget
    table = reporting_widget.findChild(QTableWidget)
    assert table is not None
    
    # 3. Setup signal spy
    with qtbot.waitSignal(reporting_widget.filter_requested) as blocker:
        # Click on "Telekom" (Row 0, Col 0)
        qtbot.mouseClick(table.viewport(), 
                         Qt.MouseButton.LeftButton,
                         pos=table.visualItemRect(table.item(0, 0)).center())
        
    # Phase 115: Handle New Payload Structure
    payload = blocker.args[0]
    if "select_query" in payload:
        query = payload["select_query"]
    else:
        query = payload
        
    found_telekom = False
    for cond in query.get("conditions", []):
        if isinstance(cond, dict) and cond.get("value") == "Telekom":
            found_telekom = True
            break
    assert found_telekom, f"Filter query should contain 'Telekom': {payload}"
