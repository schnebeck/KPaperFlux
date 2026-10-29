"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_fluxsense_client.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Tests for the FluxSense library and REST clients. FluxSense,
                its LLM backend and the HTTP service are always mocked.
------------------------------------------------------------------------------
"""

import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.engines.fluxsense_client import (
    FluxSenseError,
    FluxSenseLibraryClient,
    FluxSenseRestClient,
    create_fluxsense_client,
    default_analyzer_factory,
    normalize_base_url,
)
from core.models.identity import IdentityProfile


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    """A tiny file standing in for a PDF (never parsed by the mocked engine)."""
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4 test")
    return path


def _response(status: int, payload: Any) -> MagicMock:
    """Builds a fake requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.text = str(payload)
    return resp


# ------------------------------------------------------------------ library

def test_library_analyze_returns_json_dict(pdf: Path) -> None:
    """The in-process result model is dumped to a JSON dict."""
    analyzer = MagicMock()
    analyzer.analyze.return_value.model_dump.return_value = {"status": "OK", "logical_documents": []}
    factory = MagicMock(return_value=analyzer)
    client = FluxSenseLibraryClient(factory)
    assert client.analyze(pdf) == {"status": "OK", "logical_documents": []}
    assert client.analyze(pdf)["status"] == "OK"
    factory.assert_called_once()
    analyzer.analyze.return_value.model_dump.assert_called_with(mode="json")


def test_library_analyze_wraps_engine_exceptions(pdf: Path) -> None:
    """Any engine exception becomes a retryable FluxSenseError."""
    analyzer = MagicMock()
    analyzer.analyze.side_effect = OSError("disk")
    client = FluxSenseLibraryClient(lambda: analyzer)
    with pytest.raises(FluxSenseError) as info:
        client.analyze(pdf)
    assert info.value.retryable is True


def test_library_factory_errors_are_wrapped(pdf: Path) -> None:
    """A broken FluxSense configuration does not escape as a foreign exception."""
    def broken() -> Any:
        raise ValueError("bad toml")
    with pytest.raises(FluxSenseError, match="could not be initialized"):
        FluxSenseLibraryClient(broken).analyze(pdf)


def test_library_missing_package_raises_clear_error(pdf: Path) -> None:
    """Without the fluxsense package the error names the cause."""
    blocked = {name: None for name in ("fluxsense", "fluxsense.config", "fluxsense.pipeline", "fluxsense.models.identity")}
    with patch.dict(sys.modules, blocked):
        client = FluxSenseLibraryClient(default_analyzer_factory())
        with pytest.raises(FluxSenseError, match="not installed"):
            client.analyze(pdf)


def test_default_factory_injects_kpaperflux_identities() -> None:
    """KPaperFlux's identity profiles replace FluxSense's configured ones."""
    settings = MagicMock()
    fake_config = MagicMock(load_settings=MagicMock(return_value=settings))
    fake_identity = MagicMock(IdentityProfile=MagicMock(model_validate=lambda data: ("FLUX", data["name"])))
    fake_pipeline = MagicMock()
    modules = {"fluxsense": MagicMock(), "fluxsense.config": fake_config,
               "fluxsense.models": MagicMock(), "fluxsense.models.identity": fake_identity, "fluxsense.pipeline": fake_pipeline}
    with patch.dict(sys.modules, modules):
        default_analyzer_factory(IdentityProfile(name="Erika Mustermann"), None)()
    assert settings.identity.private == ("FLUX", "Erika Mustermann")
    fake_pipeline.Analyzer.assert_called_once_with(settings)


def test_library_health_reports_backend_state() -> None:
    """health() lists models; an unreachable backend reports 'degraded'."""
    analyzer = MagicMock()
    analyzer.backend.list_models.return_value = ["m1"]
    with patch.dict(sys.modules, {"fluxsense": MagicMock(__version__="0.1.0")}):
        client = FluxSenseLibraryClient(lambda: analyzer)
        assert client.health() == {"status": "ok", "version": "0.1.0", "llm_backend": True, "models": ["m1"]}
        analyzer.backend.list_models.side_effect = OSError("down")
        assert client.health()["status"] == "degraded"


def test_library_complete_json_uses_primary_model() -> None:
    """Free prompts go through FluxSense's backend with the primary model."""
    analyzer = MagicMock()
    analyzer.settings.models.primary = "primary-model"
    analyzer.backend.generate_json.return_value = {"name": "X"}
    request_cls = MagicMock(side_effect=lambda **kw: kw)
    with patch.dict(sys.modules, {"fluxsense.llm.base": MagicMock(LLMRequest=request_cls)}):
        assert FluxSenseLibraryClient(lambda: analyzer).complete_json("prompt", "IDENTITY") == {"name": "X"}
    analyzer.backend.generate_json.assert_called_once_with({"prompt": "prompt", "label": "IDENTITY", "model": "primary-model"})


# ------------------------------------------------------------------ REST

def test_rest_analyze_uploads_pdf(pdf: Path) -> None:
    """POST /v1/analyze with the PDF as multipart file."""
    session = MagicMock()
    session.request.return_value = _response(200, {"status": "OK", "logical_documents": []})
    client = FluxSenseRestClient("http://svc:8765/v1/", 600, session=session)
    assert client.analyze(pdf)["status"] == "OK"
    method, url = session.request.call_args.args
    assert (method, url) == ("POST", "http://svc:8765/v1/analyze")
    assert session.request.call_args.kwargs["timeout"] == (10.0, 600.0)
    assert session.request.call_args.kwargs["files"]["file"][0] == "doc.pdf"


@pytest.mark.parametrize("error, retryable", [
    (requests.exceptions.ConnectionError("refused"), True),
    (requests.exceptions.ReadTimeout("slow"), True),
    (requests.exceptions.InvalidURL("bad"), False),
])
def test_rest_transport_errors(pdf: Path, error: Exception, retryable: bool) -> None:
    """Unreachable service and timeouts are retryable, malformed requests not."""
    session = MagicMock()
    session.request.side_effect = error
    with pytest.raises(FluxSenseError) as info:
        FluxSenseRestClient("http://svc", 5, session=session).analyze(pdf)
    assert info.value.retryable is retryable


@pytest.mark.parametrize("status, retryable", [(503, True), (502, True), (422, False), (500, False)])
def test_rest_http_errors(pdf: Path, status: int, retryable: bool) -> None:
    """HTTP errors map onto FluxSenseError; gateway errors are retryable."""
    session = MagicMock()
    session.request.return_value = _response(status, {"detail": "x"})
    with pytest.raises(FluxSenseError) as info:
        FluxSenseRestClient("http://svc", 5, session=session).analyze(pdf)
    assert info.value.retryable is retryable


def test_rest_rejects_non_object_body(pdf: Path) -> None:
    """A JSON list or non-JSON body is an error, not a result."""
    session = MagicMock()
    session.request.return_value = _response(200, [1, 2])
    with pytest.raises(FluxSenseError):
        FluxSenseRestClient("http://svc", 5, session=session).analyze(pdf)
    bad = _response(200, None)
    bad.json.side_effect = ValueError("no json")
    session.request.return_value = bad
    with pytest.raises(FluxSenseError):
        FluxSenseRestClient("http://svc", 5, session=session).analyze(pdf)


def test_rest_health_and_no_free_prompts() -> None:
    """GET /v1/health is forwarded; free prompts are not supported over REST."""
    session = MagicMock()
    health: Dict[str, Any] = {"status": "ok", "llm_backend": True}
    session.request.return_value = _response(200, health)
    client = FluxSenseRestClient("http://svc", 5, session=session)
    assert client.health() == health
    assert session.request.call_args.args == ("GET", "http://svc/v1/health")
    with pytest.raises(FluxSenseError):
        client.complete_json("p", "l")


# ------------------------------------------------------------------ factory

def test_create_client_by_mode() -> None:
    """The mode setting selects the client implementation."""
    assert isinstance(create_fluxsense_client("library", "", 10), FluxSenseLibraryClient)
    rest = create_fluxsense_client("rest", "http://h:1/", 10)
    assert isinstance(rest, FluxSenseRestClient) and rest.base_url == "http://h:1"
    with pytest.raises(ValueError):
        create_fluxsense_client("cloud", "", 10)


@pytest.mark.parametrize("raw, expected", [
    ("http://h:8765", "http://h:8765"), ("http://h:8765/", "http://h:8765"),
    ("http://h:8765/v1", "http://h:8765"), (" http://h/v1/ ", "http://h"),
])
def test_normalize_base_url(raw: str, expected: str) -> None:
    """Base URLs accept an optional /v1 suffix and trailing slashes."""
    assert normalize_base_url(raw) == expected
