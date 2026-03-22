"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/anthropic_provider.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    AI provider implementation for Anthropic Claude API.
                Supports text and vision (base64 image) requests.
------------------------------------------------------------------------------
"""

import json
import requests
from typing import Any, Dict, List, Optional

from core.ai.base import AIProvider
from core.logger import get_logger

logger = get_logger("ai.anthropic")


class AnthropicProvider(AIProvider):
    """Client for Anthropic Claude API."""

    API_URL: str = "https://api.anthropic.com/v1/messages"
    API_VERSION: str = "2023-06-01"

    def __init__(self, api_key: str, model_name: str = "claude-sonnet-4-6") -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._delay: float = 0.0
        if not self.api_key:
            logger.warning("Missing API key. Anthropic Provider will be inactive.")

    def list_models(self) -> List[str]:
        """Returns known Claude models. Anthropic's /v1/models endpoint requires a key."""
        if not self.api_key:
            return []
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": self.API_VERSION,
            }
            resp = requests.get("https://api.anthropic.com/v1/models", headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return sorted([m["id"] for m in data.get("data", [])], reverse=True)
        except requests.RequestException as e:
            logger.warning(f"Could not fetch Anthropic model list: {e}")
        # Fallback static list (current as of 2026-03)
        return [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ]

    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """Executes a JSON request to Anthropic Claude, with optional vision context."""
        if not self.api_key:
            return None

        logger.info(f"Anthropic Request [{stage_label}] using {self.model_name}")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

        # Build user message content — text + optional images
        user_content: Any
        if images:
            image_list = images if isinstance(images, list) else [images]
            content_parts: List[Dict] = [{"type": "text", "text": prompt}]
            for img in image_list:
                if isinstance(img, dict) and "base64" in img:
                    content_parts.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img["base64"],
                        },
                    })
            user_content = content_parts
        else:
            user_content = prompt

        # Pre-filling the assistant turn with '{' forces JSON output without markdown wrapping.
        payload = {
            "model": self.model_name,
            "system": "You are a specialized document analyzer. Always respond with valid JSON and nothing else.",
            "messages": [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": "{"},
            ],
            "max_tokens": 8192,
            "temperature": 0.1,
        }

        try:
            resp = requests.post(self.API_URL, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                result = resp.json()
                content = "{" + result["content"][0]["text"]

                # Safety strip in case the model wrapped output despite the pre-fill
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                return json.loads(content)
            else:
                logger.error(f"Anthropic error {resp.status_code}: {resp.text[:500]}")
        except json.JSONDecodeError as e:
            logger.error(f"Anthropic JSON parse failed: {e}")
        except requests.RequestException as e:
            logger.error(f"Anthropic connection failed: {e}")

        return None

