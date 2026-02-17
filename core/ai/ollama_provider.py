
import json
import logging
import requests
from typing import Any, List, Optional
from core.ai.base import AIProvider
from core.logger import get_logger, log_ai_interaction

logger = get_logger("ai.ollama")

class OllamaProvider(AIProvider):
    """Client for local Ollama API (Sovereign AI)."""

    def __init__(self, url: str, model_name: str = "llama3") -> None:
        self.url = url.rstrip("/")
        self.model_name = model_name
        self._delay = 0.0

    def list_models(self) -> List[str]:
        """Fetches models from local Ollama instance."""
        try:
            resp = requests.get(f"{self.url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to list Ollama models at {self.url}: {e}")
        return []

    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """
        Calls Ollama with JSON output forcing.
        Note: images are currently not supported in standard Ollama generate without specialized multimodal models.
        """
        logger.info(f"Ollama Request [{stage_label}] using {self.model_name}")
        
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "seed": 42
            }
        }

        try:
            resp = requests.post(f"{self.url}/api/generate", json=payload, timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                response_text = result.get("response", "")
                if not response_text:
                    return None
                
                try:
                    res_json = json.loads(response_text)
                    log_ai_interaction(prompt, response_text, res_json)
                    return res_json
                except json.JSONDecodeError as je:
                    logger.error(f"Invalid JSON from Ollama: {je}\nResponse: {response_text[:200]}...")
                    return None
            else:
                logger.error(f"Ollama error {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Ollama connection failed: {e}")
            
        return None

    def get_adaptive_delay(self) -> float:
        return self._delay
