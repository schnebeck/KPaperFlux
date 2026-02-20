
from typing import Any, List, Optional
from core.config import AppConfig
from core.ai.base import AIProvider
from core.ai.gemini_provider import GeminiProvider
from core.ai.ollama_provider import OllamaProvider
from core.ai.openai_provider import OpenAIProvider
from core.ai.anthropic_provider import AnthropicProvider

class AIClient:
    """
    Dispatcher client that selects the appropriate backend provider 
    (Gemini, Ollama, OpenAI, Anthropic) based on application configuration.
    """

    def __init__(self, api_key: str = None, model_name: str = None) -> None:
        self.config = AppConfig()
        provider_type = self.config.get_ai_provider()
        
        if provider_type == "ollama":
            url = self.config.get_ollama_url()
            model = model_name or self.config.get_ollama_model()
            from core.logger import get_logger
            get_logger("ai").info(f"Using AI Provider: Ollama ({model} @ {url})")
            self.provider: AIProvider = OllamaProvider(url, model)
        elif provider_type == "openai":
            key = api_key or self.config.get_openai_key()
            model = model_name or self.config.get_openai_model()
            from core.logger import get_logger
            get_logger("ai").info(f"Using AI Provider: OpenAI ({model})")
            self.provider: AIProvider = OpenAIProvider(key, model)
        elif provider_type == "anthropic":
            key = api_key or self.config.get_anthropic_key()
            model = model_name or self.config.get_anthropic_model()
            from core.logger import get_logger
            get_logger("ai").info(f"Using AI Provider: Anthropic ({model})")
            self.provider: AIProvider = AnthropicProvider(key, model)
        else: # Default Gemini
            key = api_key or self.config.get_api_key()
            model = model_name or self.config.get_gemini_model()
            from core.logger import get_logger
            get_logger("ai").info(f"Using AI Provider: Gemini ({model})")
            self.provider: AIProvider = GeminiProvider(key, model)

    def list_models(self) -> List[str]:
        return self.provider.list_models()

    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        return self.provider.generate_json(prompt, stage_label, images)

    @classmethod
    def get_adaptive_delay(cls) -> float:
        # Since delay is usually provider specific, we'd need an instance.
        # But AIAnalyzer calls this as a classmethod. 
        # For simplicity, we return 0.0 or we'd need to track global state.
        return GeminiProvider.get_adaptive_delay()
