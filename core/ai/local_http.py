"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/local_http.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Shared HTTP helpers for self-hosted AI backends (Ollama,
                llama.cpp): request execution with timeout handling and
                mapping of transport/HTTP failures to AIConnectionError.
------------------------------------------------------------------------------
"""

import re
from typing import Any, Dict, Optional

import requests

from core.ai.base import AIConnectionError

CONNECT_TIMEOUT_S: float = 10.0
RETRYABLE_STATUS: frozenset = frozenset({502, 503, 504})
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def post_json(url: str, payload: Dict[str, Any], read_timeout: float, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    POSTs a JSON payload and returns the decoded JSON body.

    Args:
        url: Endpoint URL.
        payload: JSON request body.
        read_timeout: Read timeout in seconds (generation time).
        headers: Optional HTTP headers.

    Returns:
        The decoded response body.

    Raises:
        AIConnectionError: On transport errors, HTTP errors or a non-JSON body.
            ``retryable`` is True for refused connections and 502/503/504.
    """
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=(CONNECT_TIMEOUT_S, read_timeout))
    except requests.exceptions.ReadTimeout as e:
        raise AIConnectionError(f"Read timeout after {read_timeout:.0f}s at {url}: {e}", retryable=False) from e
    except requests.exceptions.ConnectionError as e:
        raise AIConnectionError(f"Connection failed to {url}: {e}", retryable=True) from e
    except requests.exceptions.RequestException as e:
        raise AIConnectionError(f"Request to {url} failed: {e}", retryable=False) from e

    if resp.status_code in (401, 403):
        raise AIConnectionError(f"HTTP {resp.status_code} (unauthorized) at {url}. Check the configured API key.", retryable=False)
    if resp.status_code != 200:
        body = (resp.text or "")[:500]
        raise AIConnectionError(f"HTTP {resp.status_code} at {url}: {body}", retryable=resp.status_code in RETRYABLE_STATUS)

    try:
        data = resp.json()
    except ValueError as e:
        raise AIConnectionError(f"Non-JSON response body from {url}: {e}", retryable=False) from e
    if not isinstance(data, dict):
        raise AIConnectionError(f"Unexpected response body type from {url}: {type(data).__name__}", retryable=False)
    return data


def strip_reasoning(text: str) -> str:
    """
    Removes inline reasoning blocks (<think>...</think>) emitted by thinking
    models when reasoning is not separated by the server.

    Args:
        text: Raw message content.

    Returns:
        Content without reasoning blocks.
    """
    return _THINK_RE.sub("", text or "").strip()
