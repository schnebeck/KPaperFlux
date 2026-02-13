
import pytest
from unittest.mock import MagicMock, patch
import datetime
import time
from core.ai.client import AIClient
from core.ai.gemini_provider import GeminiProvider

@pytest.fixture
def mock_genai_client():
    with patch("core.ai.gemini_provider.genai") as mock:
        yield mock

def test_ai_client_cooldown(mock_genai_client):
    """Test that _wait_for_cooldown in GeminiProvider sleeps if cooldown is active."""
    # Reset state
    GeminiProvider._cooldown_until = None
    client = AIClient(api_key="test")
    
    # Set cooldown in future
    future = datetime.datetime.now() + datetime.timedelta(seconds=0.5)
    GeminiProvider._cooldown_until = future
    
    start = time.time()
    client.provider._wait_for_cooldown()
    end = time.time()
    
    # Should have slept at least 0.5s (approx)
    assert (end - start) >= 0.4
    
    # Cooldown should be cleared
    assert GeminiProvider._cooldown_until is None

def test_ai_client_backoff_on_429(mock_genai_client):
    """Test that 429 triggers retry and sets cooldown in GeminiProvider."""
    # Reset state
    GeminiProvider._cooldown_until = None
    client = AIClient(api_key="test")
    
    # Mock Response
    success_response = MagicMock()
    success_response.text = '{"status": "ok"}'
    
    # Mock Client models
    mock_model = MagicMock()
    client.provider.client.models = mock_model
    
    # Mock 429 Error
    error_429 = Exception("429 Resource Exhausted")
    error_429.code = 429
    
    # Scenario: Fail twice with 429, then succeed
    mock_model.generate_content.side_effect = [
        error_429, 
        error_429, 
        success_response
    ]
    
    # Patch time.sleep to speed up test
    with patch("time.sleep") as mock_sleep:
        result = client.provider.generate_json("test prompt")
        
        assert result is not None
        assert mock_model.generate_content.call_count == 3
        assert mock_sleep.called
        # Cooldown should be None as it's cleared after waiting in the successful attempt
        assert GeminiProvider._cooldown_until is None
