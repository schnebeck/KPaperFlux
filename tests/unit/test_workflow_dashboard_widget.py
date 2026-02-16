import pytest
from PyQt6.QtWidgets import QApplication
from gui.workflow_manager import WorkflowDashboardWidget
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo
import uuid

@pytest.fixture
def db_manager():
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

def test_workflow_dashboard_refresh(qtbot, db_manager):
    """Verify that WorkflowDashboardWidget correctly counts documents."""
    repo = LogicalRepository(db_manager)
    
    # Add some docs
    for _ in range(5):
        u = str(uuid.uuid4())
        v = VirtualDocument(uuid=u, semantic_data=SemanticExtraction(workflow=WorkflowInfo(current_step="URGENT")))
        repo.save(v)
        
    for _ in range(3):
        u = str(uuid.uuid4())
        v = VirtualDocument(uuid=u, semantic_data=SemanticExtraction(workflow=WorkflowInfo(current_step="NEW")))
        repo.save(v)

    widget = WorkflowDashboardWidget(db_manager)
    qtbot.addWidget(widget)
    
    widget.refresh()
    
    # We should have 3 StatCards
    assert widget.stats_layout.count() == 3
    
    # Find the 'Urgent' card
    urgent_card = None
    for i in range(widget.stats_layout.count()):
        c = widget.stats_layout.itemAt(i).widget()
        # Find labels
        labels = c.findChildren(pytest.importorskip("PyQt6.QtWidgets").QLabel)
        if any("Urgent" in l.text() for l in labels):
            urgent_card = c
            break
            
    assert urgent_card is not None
    assert urgent_card.lbl_count.text() == "5"
