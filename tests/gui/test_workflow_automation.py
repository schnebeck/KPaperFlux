import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from gui.metadata_editor import MetadataEditorWidget
from core.models.virtual import VirtualDocument
from core.models.semantic import SemanticExtraction, WorkflowInfo
from core.workflow import WorkflowRegistry, WorkflowPlaybook

@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def editor(qtbot):
    widget = MetadataEditorWidget(db_manager=MagicMock())
    qtbot.addWidget(widget)
    return widget

def test_auto_playbook_assignment_on_display(qtbot, editor):
    """
    Test that if a document has 'INVOICE' tag but no playbook_id, 
    the editor automatically assigns the matching playbook.
    """
    # 1. Setup Registry with a mock playbook for INVOICE
    registry = WorkflowRegistry()
    registry.playbooks.clear()
    
    pb = WorkflowPlaybook(
        id="test_invoice_pb",
        name="Test Invoice Agent",
        triggers={"type_tags": ["INVOICE"]},
        states={"NEW": {"label": "New"}}
    )
    registry.playbooks["test_invoice_pb"] = pb
    
    # 2. Create Doc with INVOICE tag but no workflow info
    doc = VirtualDocument(uuid="doc1")
    doc.type_tags = ["INVOICE"]
    doc.semantic_data = SemanticExtraction() 
    # workflow is None by default in SemanticExtraction if not initialized
    
    # 3. Display Doc
    editor.display_document(doc)
    
    # 4. Verify that playbook_id was assigned
    # We check the internal doc state or the UI
    assert doc.semantic_data.workflow is not None
    assert doc.semantic_data.workflow.playbook_id == "test_invoice_pb"
    
    # Verify UI updated
    assert editor.workflow_controls.playbook_id == "test_invoice_pb"

def test_no_auto_reassignment_if_already_set(qtbot, editor):
    """
    If a playbook is already set (e.g. manually), don't override it on display.
    """
    registry = WorkflowRegistry()
    registry.playbooks.clear()
    
    pb_invoice = WorkflowPlaybook(id="pb_invoice", triggers={"type_tags": ["INVOICE"]})
    pb_other = WorkflowPlaybook(id="pb_other", triggers={"type_tags": ["OTHER"]})
    registry.playbooks["pb_invoice"] = pb_invoice
    registry.playbooks["pb_other"] = pb_other
    
    doc = VirtualDocument(uuid="doc1")
    doc.type_tags = ["INVOICE"]
    doc.semantic_data = SemanticExtraction(
        workflow=WorkflowInfo(playbook_id="manual_pb", current_step="SOME_STEP")
    )
    
    editor.display_document(doc)
    
    # Should NOT be changed to pb_invoice
    assert doc.semantic_data.workflow.playbook_id == "manual_pb"
