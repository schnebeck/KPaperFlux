import pytest
from PyQt6.QtWidgets import QApplication, QLabel
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

    # Add some docs with URGENT step
    for _ in range(5):
        u = str(uuid.uuid4())
        v = VirtualDocument(
            uuid=u,
            semantic_data=SemanticExtraction(
                workflows={"test_flow": WorkflowInfo(rule_id="test_flow", current_step="URGENT")}
            )
        )
        repo.save(v)

    for _ in range(3):
        u = str(uuid.uuid4())
        v = VirtualDocument(
            uuid=u,
            semantic_data=SemanticExtraction(
                workflows={"test_flow": WorkflowInfo(rule_id="test_flow", current_step="NEW")}
            )
        )
        repo.save(v)

    widget = WorkflowDashboardWidget(db_manager)
    qtbot.addWidget(widget)

    widget.refresh()

    # We should have 3 overview StatCards on the board
    assert len(widget._board._overview) == 3

    # Find the 'Urgent' card
    urgent_card = None
    for card in widget._board._overview:
        labels = card.findChildren(QLabel)
        if any("Urgent" in l.text() for l in labels):
            urgent_card = card
            break

    assert urgent_card is not None
    assert urgent_card.lbl_count.text() == "5"
