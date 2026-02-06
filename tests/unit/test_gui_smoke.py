import pytest
from PyQt6.QtWidgets import QApplication
from unittest.mock import MagicMock, patch

from gui.workflow_manager import WorkflowManagerWidget, WorkflowFormEditor, AgentManagerDialog
from gui.document_list import DocumentListWidget
from gui.main_window import MainWindow

# Ensure a QApplication exists for widget tests
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
    # Patch Gemini/AI at the start of the session to avoid API key errors
    # during widget instantiation in smoke tests.
    with patch("google.genai.Client"), \
         patch("core.ai_analyzer.AIAnalyzer._fetch_model_limits"):
        yield app

def test_workflow_manager_instantiation(qapp):
    """Smoke test to ensure the widget can be created without NameErrors/AttributeErrors."""
    widget = WorkflowManagerWidget()
    assert widget is not None
    assert widget.combo_agents is not None

def test_workflow_form_editor_instantiation(qapp):
    widget = WorkflowFormEditor()
    assert widget is not None

def test_agent_manager_dialog_instantiation(qapp):
    # Dialogs usually need a parent or at least a QApp
    dialog = AgentManagerDialog()
    assert dialog is not None

def test_document_list_debug_signal(qapp):
    """Test that DocumentListWidget has the debug signal and it can be emitted."""
    mock_db = MagicMock()
    widget = DocumentListWidget(db_manager=mock_db)
    
    spy = MagicMock()
    widget.show_generic_requested.connect(spy)
    
    # Simulate signal emission
    test_uuid = "test-uuid-123"
    widget.show_generic_requested.emit(test_uuid)
    
    spy.assert_called_once_with(test_uuid)

def test_main_window_smoke(qapp):
    """Test if MainWindow can be instantiated with mocked dependencies."""
    mock_pipeline = MagicMock()
    mock_db = MagicMock()
    
    # Mock some expected DB calls to avoid init crashes
    mock_db.get_available_extra_keys.return_value = []
    mock_db.get_available_tags.return_value = []
    mock_db.get_all_entities_view.return_value = []
    mock_db.get_document_by_uuid.return_value = None
    mock_db.get_available_stamps.return_value = []
    
    window = MainWindow(pipeline=mock_pipeline, db_manager=mock_db)
    assert window is not None
    assert window.workflow_manager is not None
