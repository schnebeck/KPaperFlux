"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/client.py
Version:        2.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Dispatcher that selects and instantiates the correct AI backend
                provider (Gemini, Ollama, llama.cpp, OpenAI, Anthropic) based
                on config. Every provider uses its own configured model/key.
------------------------------------------------------------------------------
"""

from typing import Any, List, Optional

from core.config import AppConfig
from core.ai.base import AIProvider
from core.ai.gemini_provider import GeminiProvider
from core.ai.llamacpp_provider import LlamaCppProvider
from core.ai.ollama_provider import OllamaProvider
from core.ai.openai_provider import OpenAIProvider
from core.ai.anthropic_provider import AnthropicProvider
from core.logger import get_logger

logger = get_logger("ai")


class AIClient:
    """
    Dispatcher client that selects the appropriate backend provider
    (Gemini, Ollama, llama.cpp, OpenAI, Anthropic) based on application configuration.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None) -> None:
        """
        Initializes the dispatcher.

        Args:
            api_key: Optional Gemini API key override (e.g. an unsaved key in the
                     settings dialog). Ignored by all other providers.
            model_name: Optional Gemini model override. Ignored by all other
                        providers, which always use their own configured model.
        """
        self.config = AppConfig()
        provider_type = self.config.get_ai_provider()
        self.provider: AIProvider = self._create_provider(provider_type, api_key, model_name)

    def _create_provider(self, provider_type: str, gemini_key: Optional[str], gemini_model: Optional[str]) -> AIProvider:
        """
        Instantiates the provider for the given type from configuration.

        Args:
            provider_type: Configured provider id.
            gemini_key: Optional Gemini key override.
            gemini_model: Optional Gemini model override.

        Returns:
            The provider instance.
        """
        cfg = self.config
        retries = cfg.get_ai_retries() or 3

        if provider_type == "ollama":
            url = cfg.get_ollama_url()
            model = cfg.get_ollama_model()
            logger.info(f"Using AI Provider: Ollama ({model} @ {url})")
            return OllamaProvider(
                url,
                model,
                num_ctx=cfg.get_ollama_num_ctx(),
                num_predict=cfg.get_ollama_num_predict(),
                timeout=cfg.get_ollama_timeout(),
                keep_alive=cfg.get_ollama_keep_alive(),
                max_image_px=cfg.get_ollama_max_image_px(),
                max_attempts=retries,
            )
        if provider_type == "llamacpp":
            url = cfg.get_llamacpp_url()
            model = cfg.get_llamacpp_model()
            vision = cfg.get_llamacpp_vision()
            logger.info(f"Using AI Provider: llama.cpp ({model} @ {url}, vision={vision})")
            return LlamaCppProvider(
                url,
                model,
                api_key=cfg.get_llamacpp_api_key(),
                vision=vision,
                timeout=cfg.get_llamacpp_timeout(),
                first_request_timeout=cfg.get_llamacpp_first_request_timeout(),
                max_tokens=cfg.get_llamacpp_max_tokens(),
                max_image_px=cfg.get_llamacpp_max_image_px(),
                max_attempts=retries,
            )
        if provider_type == "openai":
            model = cfg.get_openai_model()
            logger.info(f"Using AI Provider: OpenAI ({model})")
            return OpenAIProvider(cfg.get_openai_key(), model)
        if provider_type == "anthropic":
            model = cfg.get_anthropic_model()
            logger.info(f"Using AI Provider: Anthropic ({model})")
            return AnthropicProvider(cfg.get_anthropic_key(), model)

        # Default: Gemini
        key = gemini_key or cfg.get_api_key()
        model = gemini_model or cfg.get_gemini_model()
        logger.info(f"Using AI Provider: Gemini ({model})")
        return GeminiProvider(key, model)

    def list_models(self) -> List[str]:
        """Returns the models available on the active provider."""
        return self.provider.list_models()

    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """Delegates a JSON request to the active provider."""
        return self.provider.generate_json(prompt, stage_label, images)

    def get_adaptive_delay(self) -> float:
        """Returns the active provider's rate-limit delay."""
        return self.provider.get_adaptive_delay()
