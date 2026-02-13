import pytest
from unittest.mock import MagicMock, patch
import datetime
import time
from core.ai.client import AIClient

@pytest.fixture
def mock_genai_client():
    with patch("core.ai.client.genai") as mock:
        yield mock

def test_ai_client_cooldown(mock_genai_client):
    """Test that _wait_for_cooldown in AIClient sleeps if cooldown is active."""
    client = AIClient(api_key="test")
    
    # Set cooldown in future
    future = datetime.datetime.now() + datetime.timedelta(seconds=0.5)
    AIClient._cooldown_until = future
    
    start = time.time()
    client._wait_for_cooldown()
    end = time.time()
    
    # Should have slept at least 0.5s (approx)
    assert (end - start) >= 0.4
    
    # Cooldown should be cleared
    assert AIClient._cooldown_until is None

def test_ai_client_backoff_on_429(mock_genai_client):
    """Test that 429 triggers retry and sets cooldown in AIClient."""
    client = AIClient(api_key="test")
    
    # Mock Response
    success_response = MagicMock()
    success_response.text = '{"status": "ok"}'
    
    # Mock Client models
    mock_model = MagicMock()
    client_instance = mock_genai_client.Client.return_value
    client_instance.models = mock_model
    
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
        result = client.generate("test prompt")
        
        assert result is not None
        assert mock_model.generate_content.call_count == 3
        assert mock_sleep.called
        # Cooldown should be None as it's cleared after waiting in the successful attempt
        assert AIClient._cooldown_until is None
