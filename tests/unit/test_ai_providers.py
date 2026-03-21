
import unittest
from unittest.mock import patch, MagicMock
import json
import requests
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

    def test_anthropic_no_api_key_returns_none(self):
        provider = AnthropicProvider(api_key="")
        result = provider.generate_json("test prompt")
        self.assertIsNone(result)

    @patch("requests.post")
    def test_anthropic_http_error_returns_none(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_post.return_value = mock_resp

        provider = AnthropicProvider(api_key="bad-key")
        result = provider.generate_json("test")
        self.assertIsNone(result)

    @patch("requests.post")
    def test_anthropic_connection_error_returns_none(self, mock_post):
        mock_post.side_effect = requests.RequestException("timeout")

        provider = AnthropicProvider(api_key="fake-key")
        result = provider.generate_json("test")
        self.assertIsNone(result)

    @patch("requests.post")
    def test_anthropic_vision_sends_image_parts(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": [{"text": "\"label\": \"stamp\"}"}]}
        mock_post.return_value = mock_resp

        provider = AnthropicProvider(api_key="fake-key")
        images = [{"base64": "AAAA", "label": "page_0", "page_index": 0}]
        result = provider.generate_json("describe this", images=images)

        self.assertIsNotNone(result)
        payload = mock_post.call_args[1]["json"]
        user_content = payload["messages"][0]["content"]
        # Must be a list with text part + image part
        self.assertIsInstance(user_content, list)
        types = [p["type"] for p in user_content]
        self.assertIn("text", types)
        self.assertIn("image", types)
        image_part = next(p for p in user_content if p["type"] == "image")
        self.assertEqual(image_part["source"]["type"], "base64")
        self.assertEqual(image_part["source"]["data"], "AAAA")

    @patch("requests.get")
    def test_anthropic_list_models_from_api(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "claude-sonnet-4-6"},
                {"id": "claude-opus-4-6"},
            ]
        }
        mock_get.return_value = mock_resp

        provider = AnthropicProvider(api_key="fake-key")
        models = provider.list_models()
        self.assertIn("claude-sonnet-4-6", models)
        self.assertIn("claude-opus-4-6", models)

    @patch("requests.get")
    def test_anthropic_list_models_fallback_on_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("network down")

        provider = AnthropicProvider(api_key="fake-key")
        models = provider.list_models()
        # Must return static fallback list
        self.assertGreater(len(models), 0)
        self.assertIn("claude-sonnet-4-6", models)

    def test_anthropic_list_models_no_key_returns_empty(self):
        provider = AnthropicProvider(api_key="")
        models = provider.list_models()
        self.assertEqual(models, [])

    @patch("requests.post")
    def test_anthropic_markdown_strip(self, mock_post):
        """Model wraps output in ```json despite pre-fill — must be stripped.
        The model returns full JSON including opening brace inside the markdown block,
        so the pre-filled '{' combines with the markdown wrapper text.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # The model's continuation text after the pre-filled '{':
        # It wraps the full JSON in a code block, so text starts with '`\`\`json'
        # and contains the full object including '{'.
        mock_resp.json.return_value = {
            "content": [{"text": "```json\n{\"key\": \"val\"}\n```"}]
        }
        mock_post.return_value = mock_resp

        provider = AnthropicProvider(api_key="fake-key")
        result = provider.generate_json("test")
        self.assertEqual(result, {"key": "val"})

if __name__ == "__main__":
    unittest.main()
