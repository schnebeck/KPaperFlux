"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/base.py
Version:        2.1.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Abstract AI provider interface plus the shared logical retry
                loop (re-prompting with error feedback) used by all backends.
------------------------------------------------------------------------------
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, Tuple

from core.logger import get_logger, log_ai_interaction

logger = get_logger("ai")

RawCall = Callable[[str, str, Optional[Any]], Tuple[Optional[Any], Optional[str]]]


class AIConnectionError(Exception):
    """
    Raised by a provider's raw call when the backend could not be reached or
    refused the request (as opposed to returning unparsable content).

    Attributes:
        retryable: True if repeating the identical request may succeed
                   (e.g. connection refused, model still loading).
    """

    def __init__(self, message: str, retryable: bool = False) -> None:
        """
        Initializes the error.

        Args:
            message: Human readable description.
            retryable: Whether an identical retry is meaningful.
        """
        super().__init__(message)
        self.retryable: bool = retryable


class AIProvider(ABC):
    """Abstract base class for all AI backends (Gemini, Ollama, etc.)."""

    @abstractmethod
    def list_models(self) -> List[str]:
        """Returns available models."""

    @abstractmethod
    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """Executes a structured JSON request."""

    def get_adaptive_delay(self) -> float:
        """Returns current rate-limit delay. Subclasses may override."""
        return getattr(self, '_delay', 0.0)

    def _generate_with_feedback(
        self,
        prompt: str,
        stage_label: str,
        images: Optional[Any],
        raw_call: RawCall,
        max_attempts: int = 3,
        retry_delay: float = 1.0,
    ) -> Optional[Any]:
        """
        Shared logical retry loop. Calls ``raw_call`` and, if the response could
        not be parsed, re-prompts the model with the error message appended.
        Retryable connection errors are repeated without feedback using
        exponential backoff; non-retryable ones abort immediately.

        Args:
            prompt: The original prompt.
            stage_label: Label for logging.
            images: Optional image payload passed through to ``raw_call``.
            raw_call: Callable(prompt, stage_label, images) -> (json, error).
            max_attempts: Maximum number of attempts (at least 1).
            retry_delay: Base delay between attempts in seconds.

        Returns:
            The parsed JSON result, or None if all attempts failed.
        """
        attempts = max(1, int(max_attempts))
        working_prompt = prompt

        for attempt in range(1, attempts + 1):
            try:
                res_json, error_msg = raw_call(working_prompt, stage_label, images)
            except AIConnectionError as e:
                if not e.retryable or attempt == attempts:
                    logger.error(f"{stage_label}: backend request failed: {e}")
                    return None
                backoff = retry_delay * (2 ** attempt)
                logger.warning(f"{stage_label}: backend unavailable ({e}). Retry {attempt}/{attempts - 1} in {backoff:.0f}s.")
                time.sleep(backoff)
                continue

            if res_json is not None:
                log_ai_interaction(working_prompt, str(res_json), res_json if isinstance(res_json, dict) else None)
                return res_json

            if attempt == attempts:
                logger.error(f"{stage_label}: giving up after {attempts} attempts. Last error: {error_msg}")
                break

            logger.info(f"Logical Retry {attempt}/{attempts - 1} for {stage_label} due to: {error_msg}")
            working_prompt = prompt + f"\n\n### PREVIOUS ATTEMPT FAILED WITH ERROR:\n{error_msg}\n\nPLEASE FIX THE JSON STRUCTURE!"
            time.sleep(retry_delay)
        return None
