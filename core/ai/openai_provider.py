
import json
import logging
import requests
from typing import Any, List, Optional
from core.ai.base import AIProvider

logger = logging.getLogger("KPaperFlux.AI.OpenAI")

class OpenAIProvider(AIProvider):
    """Client for OpenAI API."""

    def __init__(self, api_key: str, model_name: str = "gpt-4o") -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._delay = 0.0

    def list_models(self) -> List[str]:
        """Fetches models from OpenAI."""
        if not self.api_key: return []
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Filter for chat models
                return sorted([m["id"] for m in data.get("data", []) if "gpt" in m["id"]])
        except Exception as e:
            logger.error(f"Failed to list OpenAI models: {e}")
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]

    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """Executes a JSON request to OpenAI."""
        if not self.api_key: return None
        
        logger.info(f"OpenAI Request [{stage_label}] using {self.model_name}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # OpenAI supports response_format={"type": "json_object"}
        # Note: Prompt MUST contain 'json' for this to work.
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are a specialized document analyzer. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        try:
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                content = result["choices"][0]["message"]["content"]
                return json.loads(content)
            else:
                logger.error(f"OpenAI error {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"OpenAI connection failed: {e}")
            
        return None

    def get_adaptive_delay(self) -> float:
        return self._delay
