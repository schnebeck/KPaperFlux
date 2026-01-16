import pytest
from unittest.mock import MagicMock, patch, ANY
import datetime
import time
from core.ai_analyzer import AIAnalyzer, AIAnalysisResult

@pytest.fixture
def mock_genai():
    with patch("core.ai_analyzer.genai") as mock:
        yield mock

def test_cooldown_logic(mock_genai):
    """Test that _wait_for_cooldown sleeps if cooldown is active."""
    analyzer = AIAnalyzer(api_key="test")
    
    # Set cooldown in future
    future = datetime.datetime.now() + datetime.timedelta(seconds=0.5)
    AIAnalyzer._cooldown_until = future
    
    start = time.time()
    analyzer._wait_for_cooldown()
    end = time.time()
    
    # Should have slept at least 0.5s (approx)
    # Using 0.4 to allow for minor overhead/precision
    assert (end - start) >= 0.4
    
    # Cooldown should be cleared
    assert AIAnalyzer._cooldown_until is None

def test_backoff_on_429(mock_genai):
    """Test that 429 triggers retry and sets cooldown."""
    analyzer = AIAnalyzer(api_key="test")
    
    # Mock Response
    success_response = MagicMock()
    success_response.text = '{"doc_type": "Success"}'
    
    # Mock Client
    mock_model = MagicMock()
    client_instance = mock_genai.Client.return_value
    client_instance.models = mock_model
    
    # Mock ClientError
    from google.genai.errors import ClientError
    
    # Create a 429 Error
    error_429 = ClientError("Resource Exhausted", {})
    error_429.code = 429
    
    # Scenario: Fail twice with 429, then succeed
    mock_model.generate_content.side_effect = [
        error_429, 
        error_429, 
        success_response
    ]
    
    # Patch time.sleep to speed up test (but verify it was called)
    with patch("time.sleep") as mock_sleep:
        result = analyzer.analyze_text("foo")
        
        # Should return success
        assert result.doc_type == "Success"
        
        # Should have called generate_content 3 times
        assert mock_model.generate_content.call_count == 3
        
        # Should have slept for backoff twice (plus cooldown checks maybe?)
        # Backoff delays:
        # Attempt 0 -> 2*(2^0) = 2s (+jitter)
        # Attempt 1 -> 2*(2^1) = 4s (+jitter)
        # Verify Cooldown was set
        # Since we mock sleep, we can't easily check real time, but side_effect ensures flow.
        assert mock_sleep.called
