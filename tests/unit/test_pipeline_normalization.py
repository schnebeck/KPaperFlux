import pytest
from unittest.mock import MagicMock, patch
from core.pipeline import PipelineProcessor
from core.document import Document
from core.ai_analyzer import AIAnalysisResult

@pytest.fixture
def mock_pipeline():
    # Mock Vault and DB to avoid file conflicts
    # We only care about _run_ai_analysis logic
    with patch("core.pipeline.DocumentVault"), patch("core.pipeline.DatabaseManager"):
        p = PipelineProcessor(base_path="test_vault", db_path=":memory:")
        # Seed Vocabulary for test
        p.vocabulary.add_type("Invoice")
        p.vocabulary.add_type_alias("Rechnung", "Invoice")
        p.vocabulary.add_tag("Urgent")
        p.vocabulary.add_tag_alias("Wichtig", "Urgent")
        return p

def test_ai_normalization(mock_pipeline):
    """Test that _run_ai_analysis normalizes types and tags."""
    
    # Mock AI Analyzer to return specific result
    mock_result = AIAnalysisResult(
        sender="TestSender",
        doc_type="Rechnung", # Should become "Invoice"
        tags="Wichtig, Paid, unknown", # Should become "Urgent, Paid, unknown"
    )
    
    with patch("core.pipeline.AIAnalyzer") as MockAnalyzer:
        instance = MockAnalyzer.return_value
        instance.analyze_text.return_value = mock_result
        
        # Also patch Config/API Key check if needed, or just force API key
        with patch.object(mock_pipeline.config, "get_api_key", return_value="fake_key"):
            with patch("core.pipeline.convert_from_path", return_value=None): # Skip image gen
                
                doc = Document(original_filename="test.pdf")
                doc.text_content = "Some text"
                
                mock_pipeline._run_ai_analysis(doc)
                
                # Verify Normalization
                assert doc.doc_type == "Invoice", f"Expected 'Invoice', got '{doc.doc_type}'"
                
                # Tags: "Wichtig" -> "Urgent", "Paid" (assume passed if simple), "unknown" (passed)
                # "Paid" and "unknown" are not strictly in vocab unless added or unknown allowed.
                # VocabularyManager returns original if unknown.
                # Wichtig -> Urgent.
                # Paid -> Paid.
                # unknown -> unknown.
                assert "Urgent" in doc.tags
                assert "Wichtig" not in doc.tags
                assert "unknown" in doc.tags
