import pytest
import uuid
from PyQt6.QtCore import Qt
from gui.cockpit import CockpitWidget
from core.database import DatabaseManager
from core.repositories import LogicalRepository
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo

@pytest.fixture
def db_manager():
    db = DatabaseManager(":memory:")
    db.init_db()
    return db

@pytest.fixture
def cockpit(qtbot, db_manager):
    widget = CockpitWidget(db_manager)
    qtbot.addWidget(widget)
    return widget

def test_cockpit_displays_workflow_urgent_count(qtbot, db_manager, cockpit):
    """Verify that the Cockpit shows the correct count for URGENT workflow steps."""
    repo = LogicalRepository(db_manager)

    # Add 3 Urgent documents
    for _ in range(3):
        u = str(uuid.uuid4())
        v = VirtualDocument(
            uuid=u,
            semantic_data=SemanticExtraction(
                workflows={"test_flow": WorkflowInfo(rule_id="test_flow", current_step="URGENT")}
            )
        )
        repo.save(v)

    # Add 1 New document (not urgent)
    u_new = str(uuid.uuid4())
    v_new = VirtualDocument(
        uuid=u_new,
        semantic_data=SemanticExtraction(
            workflows={"test_flow": WorkflowInfo(rule_id="test_flow", current_step="NEW")}
        )
    )
    repo.save(v_new)

    cockpit.refresh_stats()

    # Find the 'Urgent' card
    urgent_card = None
    for card in cockpit.card_widgets:
        if getattr(card, "preset_id", None) == "WORKFLOW_URGENT":
            urgent_card = card
            break

    assert urgent_card is not None
    assert urgent_card.lbl_count.text() == "3"

def test_cockpit_navigation_on_workflow_click(qtbot, db_manager, cockpit):
    """Verify that clicking a workflow card emits the correct filter query."""
    repo = LogicalRepository(db_manager)
    u = str(uuid.uuid4())
    v = VirtualDocument(
        uuid=u,
        semantic_data=SemanticExtraction(
            workflows={"test_flow": WorkflowInfo(rule_id="test_flow", current_step="URGENT")}
        )
    )
    repo.save(v)

    cockpit.refresh_stats()

    urgent_card = next(c for c in cockpit.card_widgets if getattr(c, "preset_id", None) == "WORKFLOW_URGENT")

    with qtbot.waitSignal(cockpit.navigation_requested) as blocker:
        qtbot.mouseClick(urgent_card, Qt.MouseButton.LeftButton)

    expected_query = {"field": "workflow_step", "op": "equals", "value": "URGENT"}
    assert blocker.args[0]["query"] == expected_query
