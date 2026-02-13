import pytest
from unittest.mock import MagicMock, patch
from core.ai_analyzer import AIAnalyzer
from google.genai.errors import ClientError

@pytest.fixture
def analyzer_and_mock():
    from core.ai.gemini_provider import GeminiProvider
    GeminiProvider._adaptive_delay = 0.0
    GeminiProvider._cooldown_until = None
    
    with patch("core.ai.gemini_provider.genai") as mock_genai:
        analyzer = AIAnalyzer(api_key="test")
        yield analyzer, mock_genai

def test_adaptive_delay_increase(analyzer_and_mock):
    """Test that adaptive delay doubles on 429."""
    analyzer, mock_genai = analyzer_and_mock
    
    mock_model = MagicMock()
    analyzer.client.provider.client.models = mock_model
    
    # Create 429 Error
    error_429 = ClientError("Resource Exhausted", {})
    error_429.code = 429
    
    # Fail twice with 429, then succeed
    success_response = MagicMock()
    success_response.text = "{}"
    mock_model.generate_content.side_effect = [
        error_429, 
        error_429, 
        success_response
    ]
    
    # Mock sleep to intercept calls
    with patch("time.sleep") as mock_sleep:
        analyzer._generate_json("foo")
        
        # Check delay progression
        # Start: 0.0
        # Attempt 1 (429): Increase -> max(2.0, 0*2) = 2.0
        # Attempt 2 (429): Increase -> max(2.0, 2.0*2) = 4.0
        # Attempt 3 (Success): Decrease -> max(0.0, 4.0*0.5) = 2.0
        
        from core.ai.gemini_provider import GeminiProvider
        assert GeminiProvider.get_adaptive_delay() == 2.0

def test_adaptive_delay_decrease(analyzer_and_mock):
    """Test that adaptive delay halves on success."""
    analyzer, mock_genai = analyzer_and_mock
    
    from core.ai.gemini_provider import GeminiProvider
    GeminiProvider._adaptive_delay = 4.0
    
    mock_model = MagicMock()
    analyzer.client.provider.client.models = mock_model
    
    success_response = MagicMock()
    success_response.text = "{}"
    mock_model.generate_content.return_value = success_response
    
    with patch("time.sleep") as mock_sleep:
        analyzer._generate_json("foo")
        
        from core.ai.gemini_provider import GeminiProvider
        # Verify result
        assert GeminiProvider.get_adaptive_delay() == 2.0

def test_adaptive_delay_snap_to_zero(analyzer_and_mock):
    """Test that small delay snaps to zero."""
    from core.ai.gemini_provider import GeminiProvider
    analyzer, mock_genai = analyzer_and_mock
    GeminiProvider._adaptive_delay = 0.15
    
    mock_model = MagicMock()
    analyzer.client.provider.client.models = mock_model
    mock_model.generate_content.return_value = MagicMock(text="{}")
    
    with patch("time.sleep"):
        analyzer._generate_json("foo") # Updated to use the new common entry point or delegate
        from core.ai.gemini_provider import GeminiProvider
        assert GeminiProvider.get_adaptive_delay() == 0.0
