
import unittest
from core.ai.client import AIClient
from core.config import AppConfig

class TestAIClientDispatch(unittest.TestCase):
    def test_provider_selection(self):
        config = AppConfig()
        original_provider = config.get_ai_provider()
        
        try:
            # Test Gemini Selection
            config.set_ai_provider("gemini")
            client_gemini = AIClient()
            from core.ai.gemini_provider import GeminiProvider
            self.assertIsInstance(client_gemini.provider, GeminiProvider)
            
            # Test Ollama Selection
            config.set_ai_provider("ollama")
            client_ollama = AIClient()
            from core.ai.ollama_provider import OllamaProvider
            self.assertIsInstance(client_ollama.provider, OllamaProvider)
            
        finally:
            config.set_ai_provider(original_provider)

if __name__ == "__main__":
    unittest.main()
