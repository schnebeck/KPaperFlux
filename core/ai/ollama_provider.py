"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/ollama_provider.py
Version:        2.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    AI provider for a local Ollama server (>= 0.12) using
                /api/chat with vision support, JSON mode / schema output,
                thinking disabled, configurable context, logical retries
                and JSON repair.
------------------------------------------------------------------------------
"""

import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.ai.base import AIProvider
from core.ai.image_payload import DEFAULT_MAX_IMAGE_PX, normalize_payload, split_payload
from core.ai.json_repair import parse_json_response
from core.ai.local_http import CONNECT_TIMEOUT_S, post_json, strip_reasoning
from core.logger import get_logger

logger = get_logger("ai.ollama")


class OllamaProvider(AIProvider):
    """Client for local Ollama API (Sovereign AI)."""

    def __init__(
        self,
        url: str,
        model_name: str = "llama3",
        num_ctx: int = 32768,
        num_predict: int = 8192,
        timeout: int = 600,
        keep_alive: str = "30m",
        max_image_px: int = DEFAULT_MAX_IMAGE_PX,
        max_attempts: int = 3,
    ) -> None:
        """
        Initializes the provider.

        Args:
            url: Ollama base URL.
            model_name: Model tag (e.g. 'qwen3-vl:8b').
            num_ctx: Context window size (options.num_ctx).
            num_predict: Maximum output tokens (options.num_predict).
            timeout: Read timeout per request in seconds.
            keep_alive: How long Ollama keeps the model loaded.
            max_image_px: Maximum long side of images in pixels.
            max_attempts: Logical attempts (with error feedback) per request.
        """
        self.url: str = url.rstrip("/")
        self.model_name: str = model_name
        self.num_ctx: int = int(num_ctx)
        self.num_predict: int = int(num_predict)
        self.timeout: int = int(timeout)
        self.keep_alive: str = keep_alive
        self.max_image_px: int = int(max_image_px)
        self.max_attempts: int = max(1, int(max_attempts))
        self._delay: float = 0.0

    def list_models(self) -> List[str]:
        """Fetches models from local Ollama instance."""
        try:
            resp = requests.get(f"{self.url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
            logger.error(f"Listing Ollama models failed: HTTP {resp.status_code}")
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.error(f"Failed to list Ollama models at {self.url}: {e}")
        return []

    def build_payload(self, prompt: str, images: Optional[Any] = None, json_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Builds the /api/chat request body.

        Args:
            prompt: Prompt text.
            images: Optional image payload (see image_payload.normalize_payload).
            json_schema: Optional JSON schema passed as 'format'.

        Returns:
            The request body dict.
        """
        texts, b64_images = split_payload(normalize_payload(images, self.max_image_px))
        content = "\n".join([prompt] + texts) if texts else prompt
        message: Dict[str, Any] = {"role": "user", "content": content}
        if b64_images:
            message["images"] = b64_images

        return {
            "model": self.model_name,
            "messages": [message],
            "stream": False,
            "format": json_schema if json_schema else "json",
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.1,
                "seed": 42,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }

    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None, json_schema: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """
        Executes a JSON request with logical retries and JSON repair.

        Args:
            prompt: Prompt text.
            stage_label: Label for logging.
            images: Optional image payload.
            json_schema: Optional JSON schema for constrained output.

        Returns:
            Parsed JSON (dict or list) or None.
        """
        def raw_call(p: str, label: str, imgs: Optional[Any]) -> Tuple[Optional[Any], Optional[str]]:
            return self._generate_json_raw(p, label, imgs, json_schema)

        return self._generate_with_feedback(prompt, stage_label, images, raw_call, max_attempts=self.max_attempts)

    def _generate_json_raw(self, prompt: str, stage_label: str, images: Optional[Any], json_schema: Optional[Dict[str, Any]]) -> Tuple[Optional[Any], Optional[str]]:
        """
        Executes one request and parses the result.

        Raises:
            AIConnectionError: On transport or HTTP failures.
        """
        payload = self.build_payload(prompt, images, json_schema)
        n_images = len(payload["messages"][0].get("images", []))
        logger.info(f"Ollama Request [{stage_label}] model={self.model_name} images={n_images} num_ctx={self.num_ctx}")

        started = time.monotonic()
        data = post_json(f"{self.url}/api/chat", payload, self.timeout)
        elapsed = time.monotonic() - started

        prompt_tokens = data.get("prompt_eval_count")
        logger.info(
            f"Ollama Response [{stage_label}] in {elapsed:.1f}s: prompt_eval_count={prompt_tokens} "
            f"eval_count={data.get('eval_count')} done_reason={data.get('done_reason')}"
        )
        if isinstance(prompt_tokens, int) and prompt_tokens >= self.num_ctx:
            logger.warning(f"[{stage_label}] prompt_eval_count {prompt_tokens} >= num_ctx {self.num_ctx}: prompt was likely truncated. Increase ollama_num_ctx.")
        if data.get("done_reason") == "length":
            logger.warning(f"Response for {stage_label} was TRUNCATED (num_predict={self.num_predict}).")

        content = (data.get("message") or {}).get("content") or ""
        return parse_json_response(strip_reasoning(content))
