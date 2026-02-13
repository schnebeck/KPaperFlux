
import unittest
from unittest.mock import patch, MagicMock
import json
from core.ai.openai_provider import OpenAIProvider
from core.ai.anthropic_provider import AnthropicProvider
from core.ai.ollama_provider import OllamaProvider

class TestAIProviders(unittest.TestCase):
    
    @patch("requests.post")
    def test_openai_provider_success(self, mock_post):
        # Setup mock response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "{\"key\": \"value\"}"}}]
        }
        mock_post.return_value = mock_resp
        
        provider = OpenAIProvider(api_key="fake-key")
        result = provider.generate_json("test prompt")
        
        self.assertEqual(result, {"key": "value"})
        self.assertTrue(mock_post.called)
        # Verify headers and payload
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-key")
        self.assertEqual(kwargs["json"]["response_format"], {"type": "json_object"})

    @patch("requests.post")
    def test_anthropic_provider_success(self, mock_post):
        # Setup mock response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"text": "\"key\": \"value\"}"}] # Pre-fill { was sent
        }
        mock_post.return_value = mock_resp
        
        provider = AnthropicProvider(api_key="fake-key")
        result = provider.generate_json("test prompt")
        
        self.assertEqual(result, {"key": "value"})
        self.assertTrue(mock_post.called)
        # Verify pre-fill in messages
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["messages"][1]["content"], "{")

    @patch("requests.post")
    def test_ollama_provider_success(self, mock_post):
        # Setup mock response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": "{\"status\": \"ok\"}"
        }
        mock_post.return_value = mock_resp
        
        provider = OllamaProvider(url="http://localhost:11434")
        result = provider.generate_json("test prompt")
        
        self.assertEqual(result, {"status": "ok"})
        self.assertTrue(mock_post.called)
        self.assertEqual(kwargs := mock_post.call_args[1], kwargs)
        self.assertEqual(kwargs["json"]["format"], "json")

    @patch("requests.post")
    def test_openai_api_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp
        
        provider = OpenAIProvider(api_key="fake-key")
        result = provider.generate_json("test")
        self.assertIsNone(result)

    @patch("requests.post")
    def test_anthropic_invalid_json(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": [{"text": "not json"}]}
        mock_post.return_value = mock_resp
        
        provider = AnthropicProvider(api_key="fake-key")
        result = provider.generate_json("test")
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
