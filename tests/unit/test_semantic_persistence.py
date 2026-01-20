import pytest
from core.pipeline import PipelineProcessor
from core.document import Document
from core.ai_analyzer import AIAnalysisResult
from unittest.mock import MagicMock, patch

def test_semantic_data_persistence():
    # 1. Setup Mock Pipeline
    pipeline = PipelineProcessor(base_path="test_vault", db_path=":memory:")
    pipeline.db.init_db()
    
    # 2. Create Dummy Doc
    doc = Document(original_filename="test.pdf")
    doc.text_content = "Test Content"
    pipeline.db.insert_document(doc)
    
    # 3. Mock AI Analyzer to return semantic_data
    mock_semantic = {"summary": {"doc_type": "Invoice"}, "pages": []}
    
    with patch("core.pipeline.AIAnalyzer") as MockAnalyzer:
        mock_instance = MockAnalyzer.return_value
        # Mock analyze_text return value
        mock_instance.analyze_text.return_value = AIAnalysisResult(
            sender="Test Sender",
            semantic_data=mock_semantic
        )
        # Fix: pipeline calls consolidate_semantics, which returns a Mock by default.
        # We must configure it to return the input data (pass-through) or the same dict.
        mock_instance.consolidate_semantics.side_effect = lambda x: x
        
        # 4. Run Analysis (Simulation of _run_ai_analysis or reprocess)
        # We call _run_ai_analysis directly to test the mapping logic
        pipeline._run_ai_analysis(doc, file_path=None)
        
        # 5. Check In-Memory Doc Object
        assert doc.sender == "Test Sender"
        # This assertion is expected to FAIL before the fix
        if doc.semantic_data != mock_semantic:
            pytest.fail(f"Semantic Data not mapped to Document object! Got: {doc.semantic_data}")

        # 6. Save and Check DB Persistence
        pipeline.db.insert_document(doc)
        fetched_doc = pipeline.db.get_document_by_uuid(doc.uuid)
        
        assert fetched_doc.semantic_data == mock_semantic, "Semantic Data not persisted to DB"

if __name__ == "__main__":
    test_semantic_data_persistence()
