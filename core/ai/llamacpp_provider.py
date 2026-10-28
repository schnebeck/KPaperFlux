"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/llamacpp_provider.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    AI provider for self-hosted OpenAI-compatible servers
                (llama.cpp llama-server, llama-swap). Supports vision models
                via image_url content parts, JSON mode / JSON schema output,
                text-only models, logical retries and JSON repair.
------------------------------------------------------------------------------
"""

import time
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from core.ai.base import AIProvider
from core.ai.image_payload import DEFAULT_MAX_IMAGE_PX, PayloadPart, normalize_payload
from core.ai.json_repair import parse_json_response
from core.ai.local_http import CONNECT_TIMEOUT_S, post_json, strip_reasoning
from core.logger import get_logger

logger = get_logger("ai.llamacpp")

SYSTEM_PROMPT: str = "You are a specialized document analyzer. Always respond with valid JSON and nothing else."


class LlamaCppProvider(AIProvider):
    """Client for an OpenAI-compatible llama.cpp / llama-swap endpoint."""

    # Models that already answered once in this process (llama-swap loads a
    # model on first use, which can take minutes).
    _warm_models: Set[str] = set()

    def __init__(
        self,
        url: str,
        model_name: str,
        api_key: str = "",
        vision: bool = True,
        timeout: int = 600,
        first_request_timeout: int = 1800,
        max_tokens: int = 8192,
        max_image_px: int = DEFAULT_MAX_IMAGE_PX,
        max_attempts: int = 3,
    ) -> None:
        """
        Initializes the provider.

        Args:
            url: Server base URL, with or without trailing '/v1'.
            model_name: Model id (as listed by /v1/models).
            api_key: Optional bearer token.
            vision: False for text-only models (images are dropped).
            timeout: Read timeout per request in seconds.
            first_request_timeout: Read timeout for the first request per model.
            max_tokens: Maximum completion tokens.
            max_image_px: Maximum long side of images in pixels.
            max_attempts: Logical attempts (with error feedback) per request.
        """
        base = url.strip().rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        self.base_url: str = base
        self.model_name: str = model_name
        self.api_key: str = api_key or ""
        self.vision: bool = vision
        self.timeout: int = int(timeout)
        self.first_request_timeout: int = max(int(first_request_timeout), self.timeout)
        self.max_tokens: int = int(max_tokens)
        self.max_image_px: int = int(max_image_px)
        self.max_attempts: int = max(1, int(max_attempts))
        self._delay: float = 0.0

    @property
    def chat_url(self) -> str:
        """Returns the chat completions endpoint URL."""
        return f"{self.base_url}/v1/chat/completions"

    def _headers(self) -> Dict[str, str]:
        """Builds request headers (bearer auth only when a key is configured)."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def list_models(self) -> List[str]:
        """Fetches model ids from GET /v1/models."""
        try:
            resp = requests.get(f"{self.base_url}/v1/models", headers=self._headers(), timeout=CONNECT_TIMEOUT_S)
            if resp.status_code == 200:
                return sorted(m.get("id", "") for m in resp.json().get("data", []) if m.get("id"))
            logger.error(f"Listing models at {self.base_url} failed: HTTP {resp.status_code}")
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Failed to list models at {self.base_url}: {e}")
        return []

    def build_payload(self, prompt: str, images: Optional[Any] = None, json_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Builds the chat completions request body.

        Args:
            prompt: Prompt text.
            images: Optional image payload (see image_payload.normalize_payload).
            json_schema: Optional JSON schema to enforce instead of plain JSON mode.

        Returns:
            The request body dict.
        """
        parts: List[PayloadPart] = []
        if images:
            if self.vision:
                parts = normalize_payload(images, self.max_image_px)
            else:
                logger.warning(f"Model '{self.model_name}' is configured as text-only. Dropping image payload.")

        user_content: Any
        if any(p.kind == "image" for p in parts):
            user_content = [{"type": "text", "text": prompt}]
            for part in parts:
                if part.kind == "image":
                    user_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{part.value}"}})
                else:
                    user_content.append({"type": "text", "text": part.value})
        else:
            extra_text = "\n".join(p.value for p in parts if p.kind == "text")
            user_content = f"{prompt}\n{extra_text}" if extra_text else prompt

        if json_schema:
            response_format: Dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {"name": str(json_schema.get("title", "response")), "schema": json_schema},
            }
        else:
            response_format = {"type": "json_object"}

        return {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": response_format,
            "temperature": 0.1,
            "seed": 42,
            "max_tokens": self.max_tokens,
            "stream": False,
            # Qwen3-style hybrid models: disable thinking for structured output.
            "chat_template_kwargs": {"enable_thinking": False},
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
        is_first = self.model_name not in LlamaCppProvider._warm_models
        read_timeout = self.first_request_timeout if is_first else self.timeout
        user_content = payload["messages"][1]["content"]
        n_images = 0
        if isinstance(user_content, list):
            n_images = sum(1 for part in user_content if part.get("type") == "image_url")

        logger.info(f"llama.cpp Request [{stage_label}] model={self.model_name} images={n_images} timeout={read_timeout}s")
        started = time.monotonic()
        data = post_json(self.chat_url, payload, read_timeout, self._headers())
        elapsed = time.monotonic() - started
        LlamaCppProvider._warm_models.add(self.model_name)

        usage = data.get("usage") or {}
        choices = data.get("choices") or []
        finish_reason = choices[0].get("finish_reason") if choices else None
        logger.info(
            f"llama.cpp Response [{stage_label}] in {elapsed:.1f}s: "
            f"prompt_tokens={usage.get('prompt_tokens')} completion_tokens={usage.get('completion_tokens')} "
            f"finish_reason={finish_reason}"
        )
        if finish_reason == "length":
            logger.warning(f"Response for {stage_label} was TRUNCATED (max_tokens={self.max_tokens}).")

        if not choices:
            return None, "No choices in response"
        content = (choices[0].get("message") or {}).get("content") or ""
        return parse_json_response(strip_reasoning(content))
