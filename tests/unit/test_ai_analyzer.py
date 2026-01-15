import pytest
from unittest.mock import MagicMock, patch
from core.ai_analyzer import AIAnalyzer, AIAnalysisResult
import datetime
from decimal import Decimal

@pytest.fixture
def mock_gen_client():
    with patch("core.ai_analyzer.genai.Client") as MockClient:
        yield MockClient

def test_analyze_text_success(mock_gen_client):
    """Test successful text analysis with valid JSON response."""
    # Setup mock
    mock_client_instance = mock_gen_client.return_value
    mock_models = mock_client_instance.models
    mock_response = MagicMock()
    # Simulate a JSON response block
    mock_response.text = """
    ```json
    {
        "sender": "Example Corp",
        "doc_date": "2023-10-25",
        "amount": 123.45,
        "doc_type": "Invoice"
    }
    ```
    """
    mock_models.generate_content.return_value = mock_response
    
    analyzer = AIAnalyzer(api_key="fake_key")
    result = analyzer.analyze_text("Some extracted invoice text")
    
    assert isinstance(result, AIAnalysisResult)
    assert result.sender == "Example Corp"
    assert result.doc_date == datetime.date(2023, 10, 25)
    assert result.amount == Decimal("123.45")
    assert result.doc_type == "Invoice"

def test_analyze_text_invalid_json(mock_gen_client):
    """Test handling of invalid JSON response."""
    mock_client_instance = mock_gen_client.return_value
    mock_models = mock_client_instance.models
    mock_response = MagicMock()
    mock_response.text = "Not a JSON"
    mock_models.generate_content.return_value = mock_response
    
    analyzer = AIAnalyzer(api_key="fake_key")
    result = analyzer.analyze_text("text")
    
    # Should return empty/default values
    assert result.sender is None
    assert result.amount is None

def test_analyze_text_api_error(mock_gen_client):
    """Test handling of API errors."""
    mock_client_instance = mock_gen_client.return_value
    mock_models = mock_client_instance.models
    mock_models.generate_content.side_effect = Exception("API fail")
    
    analyzer = AIAnalyzer(api_key="fake_key")
    result = analyzer.analyze_text("text")
    
    assert result.sender is None
