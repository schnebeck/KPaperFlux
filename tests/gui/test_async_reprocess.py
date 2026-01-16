
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from gui.main_window import MainWindow
from core.document import Document

@pytest.fixture
def mock_pipeline():
    pipeline = MagicMock()
    # Mock methods
    pipeline.reprocess_document.return_value = Document(uuid="123", original_filename="a.pdf")
    pipeline.process_document.return_value = Document(uuid="456", original_filename="b.pdf")
    return pipeline

@pytest.fixture
def main_window(qtbot, mock_pipeline):
    # Mock dependencies inside MainWindow
    # Only patch AIQueueWorker which is instantiated in __init__
    with patch('gui.main_window.AIQueueWorker') as MockAIWorker, \
         patch('gui.main_window.DocumentListWidget'):
        
        mw = MainWindow()
        mw.pipeline = mock_pipeline
        mw.db_manager = MagicMock()
        mw.list_widget = MagicMock()
        
        # Setup AI Worker mock instance
        mw.ai_worker = MockAIWorker.return_value
        
        qtbot.addWidget(mw)
        yield mw

def test_async_reprocess_flow(main_window, mock_pipeline):
    """
    Test that reprocessing documents correctly:
    1. Calls pipeline.reprocess_document with skip_ai=True (via Worker).
    2. Adds task to AIQueueWorker upon completion.
    """
    from gui.workers import ReprocessWorker
    
    uuids = ["1", "2"]
    
    # 1. Create worker manually to test logic (skip slow GUI integration test)
    worker = ReprocessWorker(mock_pipeline, uuids)
    worker.run() # Sync run
    
    # Verify Pipeline called with skip_ai=True
    assert mock_pipeline.reprocess_document.call_count == 2
    mock_pipeline.reprocess_document.assert_any_call("1", skip_ai=True)
    
    # 2. Verify MainWindow Integration (on_reprocess_finished)
    # Simulate signal
    main_window._on_reprocess_finished(2, 2, uuids)
    
    # Verify AI Queue
    assert main_window.ai_worker.add_task.call_count == 2
    main_window.ai_worker.add_task.assert_any_call("1")
    main_window.ai_worker.add_task.assert_any_call("2")

def test_pipeline_signature():
    """Verify Pipeline signature accepts skip_ai."""
    from core.pipeline import PipelineProcessor
    import inspect
    sig = inspect.signature(PipelineProcessor.reprocess_document)
    assert "skip_ai" in sig.parameters
    assert sig.parameters["skip_ai"].default is False
