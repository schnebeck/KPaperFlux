"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_local_ai_providers.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Unit tests (mocked HTTP, no network) for the self-hosted AI
                providers (Ollama, llama.cpp), shared image normalization,
                logical retries and provider/model selection.
------------------------------------------------------------------------------
"""

import base64
import io
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
import requests
from PIL import Image

from core.ai.image_payload import normalize_payload
from core.ai.llamacpp_provider import LlamaCppProvider
from core.ai.ollama_provider import OllamaProvider

FAKE_KEY = "test-token-not-real"


def _png_b64(width: int, height: int) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _decoded_size(b64: str) -> tuple:
    with Image.open(io.BytesIO(base64.b64decode(b64))) as img:
        return img.size


def _response(status: int, body: Dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    resp.text = str(body)
    return resp


def _ollama_ok(content: str) -> MagicMock:
    return _response(200, {"message": {"role": "assistant", "content": content}, "prompt_eval_count": 100, "eval_count": 20, "done_reason": "stop"})


def _llama_ok(content: str, finish: str = "stop") -> MagicMock:
    return _response(200, {
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    })


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("core.ai.base.time.sleep"):
        yield


@pytest.fixture(autouse=True)
def reset_warm_models():
    LlamaCppProvider._warm_models = set()
    yield
    LlamaCppProvider._warm_models = set()


# --- Image normalization -----------------------------------------------------

def test_normalize_mixed_payload_preserves_order_and_downscales() -> None:
    big = Image.new("RGB", (3000, 1500), "white")
    parts = normalize_payload(["\n[IMAGE CONTEXT: FIRST_PAGE]\n", big], max_px=1600)
    assert [p.kind for p in parts] == ["text", "image"]
    assert "FIRST_PAGE" in parts[0].value
    assert _decoded_size(parts[1].value) == (1600, 800)


def test_normalize_dict_bytes_and_single_item() -> None:
    small_b64 = _png_b64(100, 50)
    parts = normalize_payload({"base64": small_b64, "label": "P1"}, max_px=1600)
    assert len(parts) == 1 and parts[0].value == small_b64  # fits -> unchanged

    big_dict = normalize_payload([{"base64": _png_b64(2000, 4000)}], max_px=1000)
    assert _decoded_size(big_dict[0].value) == (500, 1000)

    raw = base64.b64decode(_png_b64(10, 10))
    parts = normalize_payload([raw], max_px=1600)
    assert parts[0].kind == "image" and _decoded_size(parts[0].value) == (10, 10)


def test_normalize_skips_garbage() -> None:
    assert normalize_payload([b"not an image", 42, None], max_px=1600) == []


# --- Ollama ------------------------------------------------------------------

@patch("core.ai.local_http.requests.post")
def test_ollama_chat_payload_shape(mock_post: MagicMock) -> None:
    mock_post.return_value = _ollama_ok('{"ok": true}')
    provider = OllamaProvider("http://host:11434/", "qwen3-vl:8b", num_ctx=16384, num_predict=4096, timeout=321, keep_alive="10m")
    pil = Image.new("RGB", (400, 200), "white")

    result = provider.generate_json("PROMPT", images=["[IMAGE CONTEXT: FIRST_PAGE]", pil, {"base64": _png_b64(20, 20)}])

    assert result == {"ok": True}
    args, kwargs = mock_post.call_args
    assert args[0] == "http://host:11434/api/chat"
    assert kwargs["timeout"] == (10.0, 321)
    payload = kwargs["json"]
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["format"] == "json"
    assert payload["keep_alive"] == "10m"
    assert payload["options"] == {"temperature": 0.1, "seed": 42, "num_ctx": 16384, "num_predict": 4096}
    message = payload["messages"][0]
    assert message["role"] == "user"
    assert message["content"].startswith("PROMPT")
    assert "[IMAGE CONTEXT: FIRST_PAGE]" in message["content"]
    assert len(message["images"]) == 2
    assert all(isinstance(i, str) for i in message["images"])


@patch("core.ai.local_http.requests.post")
def test_ollama_json_schema_and_no_images(mock_post: MagicMock) -> None:
    mock_post.return_value = _ollama_ok('{"a": 1}')
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    provider = OllamaProvider("http://host:11434", "m")
    assert provider.generate_json("P", json_schema=schema) == {"a": 1}
    payload = mock_post.call_args[1]["json"]
    assert payload["format"] == schema
    assert "images" not in payload["messages"][0]


@patch("core.ai.local_http.requests.post")
def test_ollama_retry_with_error_feedback(mock_post: MagicMock) -> None:
    mock_post.side_effect = [_ollama_ok("totally not json"), _ollama_ok('<think>hmm</think>{"fixed": 1}')]
    provider = OllamaProvider("http://host:11434", "m", max_attempts=3)
    assert provider.generate_json("ORIGINAL") == {"fixed": 1}
    assert mock_post.call_count == 2
    second_prompt = mock_post.call_args_list[1][1]["json"]["messages"][0]["content"]
    assert second_prompt.startswith("ORIGINAL")
    assert "PREVIOUS ATTEMPT FAILED WITH ERROR" in second_prompt


@patch("core.ai.local_http.requests.post")
def test_ollama_read_timeout_aborts_without_retry(mock_post: MagicMock) -> None:
    mock_post.side_effect = requests.exceptions.ReadTimeout("slow")
    provider = OllamaProvider("http://host:11434", "m", max_attempts=3)
    assert provider.generate_json("P") is None
    assert mock_post.call_count == 1


@patch("core.ai.local_http.requests.post")
def test_ollama_connection_refused_is_retried(mock_post: MagicMock) -> None:
    mock_post.side_effect = [requests.exceptions.ConnectionError("refused"), _ollama_ok('{"a": 1}')]
    provider = OllamaProvider("http://host:11434", "m", max_attempts=3)
    assert provider.generate_json("P") == {"a": 1}
    # Connection retries do not add JSON feedback
    assert mock_post.call_args_list[1][1]["json"]["messages"][0]["content"] == "P"


@patch("core.ai.local_http.requests.post")
def test_ollama_warns_on_context_overflow(mock_post: MagicMock) -> None:
    resp = _ollama_ok('{"a": 1}')
    resp.json.return_value["prompt_eval_count"] = 4096
    mock_post.return_value = resp
    provider = OllamaProvider("http://host:11434", "m", num_ctx=4096)
    with patch("core.ai.ollama_provider.logger") as mock_logger:
        provider.generate_json("P")
    assert any("num_ctx" in str(c) for c in mock_logger.warning.call_args_list)


# --- llama.cpp -----------------------------------------------------------------

@patch("core.ai.local_http.requests.post")
def test_llamacpp_vision_payload_shape(mock_post: MagicMock) -> None:
    mock_post.return_value = _llama_ok('{"ok": 1}')
    provider = LlamaCppProvider("http://host:8090/v1/", "qwen3.6-35b-a3b", api_key=FAKE_KEY, max_tokens=1234)

    result = provider.generate_json("PROMPT", images=["[IMAGE CONTEXT: FIRST_PAGE]", Image.new("RGB", (50, 50))])

    assert result == {"ok": 1}
    args, kwargs = mock_post.call_args
    assert args[0] == "http://host:8090/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    payload = kwargs["json"]
    assert payload["model"] == "qwen3.6-35b-a3b"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 1234
    assert payload["stream"] is False
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    content = payload["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "PROMPT"}
    assert content[1] == {"type": "text", "text": "[IMAGE CONTEXT: FIRST_PAGE]"}
    assert content[2]["type"] == "image_url"
    assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")


@patch("core.ai.local_http.requests.post")
def test_llamacpp_text_only_drops_images(mock_post: MagicMock) -> None:
    mock_post.return_value = _llama_ok('{"ok": 1}')
    provider = LlamaCppProvider("http://host:8090", "qwen3.8-flash-next-strata", vision=False)
    with patch("core.ai.llamacpp_provider.logger") as mock_logger:
        provider.generate_json("PROMPT", images=[{"base64": _png_b64(10, 10)}])
    assert mock_logger.warning.called
    payload = mock_post.call_args[1]["json"]
    assert payload["messages"][1]["content"] == "PROMPT"
    assert "Authorization" not in mock_post.call_args[1]["headers"]


@patch("core.ai.local_http.requests.post")
def test_llamacpp_json_schema_and_first_request_timeout(mock_post: MagicMock) -> None:
    mock_post.return_value = _llama_ok('{"a": 1}')
    schema = {"title": "Preflight", "type": "object"}
    provider = LlamaCppProvider("http://host:8090", "m", timeout=100, first_request_timeout=900)

    provider.generate_json("P", json_schema=schema)
    provider.generate_json("P", json_schema=schema)

    first, second = mock_post.call_args_list
    assert first[1]["timeout"] == (10.0, 900)
    assert second[1]["timeout"] == (10.0, 100)
    assert first[1]["json"]["response_format"] == {"type": "json_schema", "json_schema": {"name": "Preflight", "schema": schema}}


@patch("core.ai.local_http.requests.post")
def test_llamacpp_unauthorized_aborts(mock_post: MagicMock) -> None:
    mock_post.return_value = _response(401, {"error": "unauthorized"})
    provider = LlamaCppProvider("http://host:8090", "m", max_attempts=3)
    assert provider.generate_json("P") is None
    assert mock_post.call_count == 1


@patch("core.ai.local_http.requests.post")
def test_llamacpp_503_retried_then_repaired(mock_post: MagicMock) -> None:
    mock_post.side_effect = [_response(503, {"error": "loading"}), _llama_ok('```json\n{"a": [1, 2,]}\n```')]
    provider = LlamaCppProvider("http://host:8090", "m", max_attempts=3)
    assert provider.generate_json("P") == {"a": [1, 2]}


@patch("core.ai.llamacpp_provider.requests.get")
def test_llamacpp_list_models(mock_get: MagicMock) -> None:
    mock_get.return_value = _response(200, {"data": [{"id": "qwen3.6-35b-a3b"}, {"id": "qwen3.8-flash-next-strata"}]})
    provider = LlamaCppProvider("http://host:8090/v1", "m", api_key=FAKE_KEY)
    assert provider.list_models() == ["qwen3.6-35b-a3b", "qwen3.8-flash-next-strata"]
    assert mock_get.call_args[0][0] == "http://host:8090/v1/models"


# --- Provider / model selection ---------------------------------------------------

def _mock_config(provider: str) -> MagicMock:
    cfg = MagicMock()
    cfg.get_ai_provider.return_value = provider
    cfg.get_ai_retries.return_value = 2
    cfg.get_ollama_url.return_value = "http://ollama:11434"
    cfg.get_ollama_model.return_value = "qwen3-vl:8b"
    cfg.get_ollama_num_ctx.return_value = 32768
    cfg.get_ollama_num_predict.return_value = 8192
    cfg.get_ollama_timeout.return_value = 600
    cfg.get_ollama_keep_alive.return_value = "30m"
    cfg.get_ollama_max_image_px.return_value = 1600
    cfg.get_llamacpp_url.return_value = "http://llama:8090"
    cfg.get_llamacpp_model.return_value = "qwen3.6-35b-a3b"
    cfg.get_llamacpp_api_key.return_value = FAKE_KEY
    cfg.get_llamacpp_vision.return_value = True
    cfg.get_llamacpp_timeout.return_value = 600
    cfg.get_llamacpp_first_request_timeout.return_value = 1800
    cfg.get_llamacpp_max_tokens.return_value = 8192
    cfg.get_llamacpp_max_image_px.return_value = 1600
    cfg.get_openai_key.return_value = "openai-key"
    cfg.get_openai_model.return_value = "gpt-4o"
    cfg.get_anthropic_key.return_value = "anthropic-key"
    cfg.get_anthropic_model.return_value = "claude-sonnet-4-6"
    cfg.get_api_key.return_value = ""
    cfg.get_gemini_model.return_value = "gemini-2.5-flash"
    return cfg


@pytest.mark.parametrize(
    "provider, attr, expected",
    [
        ("ollama", "model_name", "qwen3-vl:8b"),
        ("llamacpp", "model_name", "qwen3.6-35b-a3b"),
        ("openai", "model_name", "gpt-4o"),
        ("anthropic", "model_name", "claude-sonnet-4-6"),
    ],
)
def test_gemini_overrides_do_not_leak_into_other_providers(provider: str, attr: str, expected: str) -> None:
    from core.ai.client import AIClient
    with patch("core.ai.client.AppConfig", return_value=_mock_config(provider)):
        client = AIClient("gemini-key", "gemini-2.5-flash")
    assert getattr(client.provider, attr) == expected
    if provider in ("openai", "anthropic"):
        assert client.provider.api_key == f"{provider}-key"


def test_llamacpp_client_wiring() -> None:
    from core.ai.client import AIClient
    with patch("core.ai.client.AppConfig", return_value=_mock_config("llamacpp")):
        client = AIClient()
    assert isinstance(client.provider, LlamaCppProvider)
    assert client.provider.api_key == FAKE_KEY
    assert client.provider.max_attempts == 2


def test_gemini_override_still_applies_to_gemini() -> None:
    from core.ai.client import AIClient
    with patch("core.ai.client.AppConfig", return_value=_mock_config("gemini")), \
         patch("core.ai.client.GeminiProvider") as mock_gemini:
        AIClient("override-key", "gemini-x")
    mock_gemini.assert_called_once_with("override-key", "gemini-x")


# --- Config defaults -------------------------------------------------------------

def test_config_defaults_for_local_backends() -> None:
    from core.config import AppConfig
    with patch.object(AppConfig, "_get_setting", lambda self, group, key, default=None: default), \
         patch.dict("os.environ", {"LLAMACPP_API_KEY": ""}):
        cfg = AppConfig.__new__(AppConfig)
        assert cfg.get_ollama_num_ctx() == 32768
        assert cfg.get_ollama_num_predict() == 8192
        assert cfg.get_ollama_timeout() == 600
        assert cfg.get_ollama_keep_alive() == "30m"
        assert cfg.get_ollama_max_image_px() == 1600
        assert cfg.get_llamacpp_url() == "http://localhost:8090"
        assert cfg.get_llamacpp_model() == "qwen3.6-35b-a3b"
        assert cfg.get_llamacpp_api_key() == ""
        assert cfg.get_llamacpp_vision() is True
        assert cfg.get_ocr_engine() == "ocrmypdf"
        assert cfg.get_docling_url() == "http://localhost:5001"
        assert cfg.get_docling_pipeline() == "standard"
        assert cfg.get_docling_timeout() == 900


def test_config_parses_ini_strings() -> None:
    from core.config import AppConfig
    values = {"llamacpp_vision": "false", "ollama_num_ctx": "not-a-number", "ocr_engine": "DOCLING"}
    with patch.object(AppConfig, "_get_setting", lambda self, group, key, default=None: values.get(key, default)):
        cfg = AppConfig.__new__(AppConfig)
        assert cfg.get_llamacpp_vision() is False
        assert cfg.get_ollama_num_ctx() == 32768
        assert cfg.get_ocr_engine() == "docling"
