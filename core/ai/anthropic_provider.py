
import json
import logging
import requests
from typing import Any, List, Optional
from core.ai.base import AIProvider

logger = logging.getLogger("KPaperFlux.AI.Anthropic")

class AnthropicProvider(AIProvider):
    """Client for Anthropic (Claude) API."""

    def __init__(self, api_key: str, model_name: str = "claude-3-5-sonnet-20240620") -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._delay = 0.0

    def list_models(self) -> List[str]:
        """Anthropic doesn't have a public models list endpoint like OpenAI, so we return a static list."""
        return [
            "claude-3-5-sonnet-20240620",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ]

    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """Executes a JSON request to Anthropic."""
        if not self.api_key: return None
        
        logger.info(f"Anthropic Request [{stage_label}] using {self.model_name}")
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        # Claude is very good at following instructions. 
        # We can also pre-fill the assistant response with '{' to force JSON.
        payload = {
            "model": self.model_name,
            "system": "You are a specialized document analyzer. Always respond with valid JSON and nothing else.",
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "{"} 
            ],
            "max_tokens": 4096,
            "temperature": 0.1
        }

        try:
            resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                content = "{" + result["content"][0]["text"] # Pre-filled with {
                
                # Basic cleaning if Claude adds markdown blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                return json.loads(content)
            else:
                logger.error(f"Anthropic error {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Anthropic connection failed: {e}")
            
        return None

    def get_adaptive_delay(self) -> float:
        return self._delay
