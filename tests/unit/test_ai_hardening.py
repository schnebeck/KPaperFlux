import pytest
from unittest.mock import MagicMock, patch
from core.ai_analyzer import AIAnalyzer
from core.models.canonical_entity import DocType, InvoiceData
import json

@pytest.fixture
def mock_genai():
    with patch("core.ai_analyzer.genai") as mock:
        yield mock

def test_pydantic_validation_correction(mock_genai):
    """Test that coercible types are corrected (e.g. string numbers)."""
    analyzer = AIAnalyzer(api_key="test")
    
    # Coercible
    # InvoiceData does NOT have total_amount, it has net_amount/gross_amount.
    coercible_json = {
        "classification": "INVOICE",
        "specific_data": {
            "net_amount": "123.45" # String, should be float
        }
    }
    
    mock_response = MagicMock()
    mock_response.text = json.dumps(coercible_json)
    analyzer.client.models.generate_content.return_value = mock_response
    
    result = analyzer.extract_canonical_data(DocType.INVOICE, "some text")
    
    # Check that validation/coercion happened inside specific_data
    assert "specific_data" in result
    assert result["specific_data"]["net_amount"] == 123.45 # Should be float
