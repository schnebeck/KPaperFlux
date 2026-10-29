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
import threading
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

def _fake_pipeline_module() -> MagicMock:
    """fluxsense.pipeline stand-in whose AnalyzeOptions records its keyword arguments."""
    return MagicMock(AnalyzeOptions=lambda **kw: kw)


def test_library_analyze_requests_page_text(pdf: Path) -> None:
    """analyze() passes include_page_text and returns the dumped result (text layer included)."""
    analyzer = MagicMock()
    analyzer.analyze.return_value.model_dump.return_value = {"status": "OK", "text_layer": {"pages": [{"page": 1, "text": "x"}]}}
    factory = MagicMock(return_value=analyzer)
    client = FluxSenseLibraryClient(factory)
    with patch.dict(sys.modules, {"fluxsense.pipeline": _fake_pipeline_module()}):
        result = client.analyze(pdf)
        client.analyze(pdf)
    assert result["text_layer"]["pages"][0]["text"] == "x"
    assert analyzer.analyze.call_args.args[1] == {"include_page_text": True}
    analyzer.analyze.return_value.model_dump.assert_called_with(mode="json")
    factory.assert_called_once()


def test_library_error_results_are_returned_not_raised(pdf: Path) -> None:
    """FluxSense reports engine failures as ERROR results with error_code; the client passes them on."""
    analyzer = MagicMock()
    analyzer.analyze.return_value.model_dump.return_value = {"status": "ERROR", "error_code": "BACKEND_UNREACHABLE"}
    with patch.dict(sys.modules, {"fluxsense.pipeline": _fake_pipeline_module()}):
        assert FluxSenseLibraryClient(lambda: analyzer).analyze(pdf)["error_code"] == "BACKEND_UNREACHABLE"


def test_library_unexpected_exceptions_are_wrapped(pdf: Path) -> None:
    """A defect inside FluxSense becomes an unclassified FluxSenseError (not retryable)."""
    analyzer = MagicMock()
    analyzer.analyze.side_effect = OSError("disk")
    with patch.dict(sys.modules, {"fluxsense.pipeline": _fake_pipeline_module()}):
        with pytest.raises(FluxSenseError) as info:
            FluxSenseLibraryClient(lambda: analyzer).analyze(pdf)
    assert info.value.error_code is None and info.value.retryable is False


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


def test_ai_server_url_override_only_when_set() -> None:
    """KPaperFlux overrides FluxSense's llm.base_url only if the user set it; empty keeps the TOML value."""
    for override, expected in (("http://my-ai:8080/v1", "http://my-ai:8080/v1"), ("", "from-fluxsense-config")):
        settings = MagicMock()
        settings.llm.base_url = "from-fluxsense-config"
        modules = {"fluxsense": MagicMock(), "fluxsense.config": MagicMock(load_settings=MagicMock(return_value=settings)),
                   "fluxsense.models": MagicMock(), "fluxsense.models.identity": MagicMock(), "fluxsense.pipeline": MagicMock()}
        with patch.dict(sys.modules, modules):
            default_analyzer_factory(None, None, override)()
        assert settings.llm.base_url == expected


def test_server_url_per_mode() -> None:
    """Library: the AI server from FluxSense's settings; REST: the service URL; unknown -> None."""
    analyzer = MagicMock()
    analyzer.settings.llm.base_url = "http://localhost:8080/v1"
    assert FluxSenseLibraryClient(lambda: analyzer).server_url() == "http://localhost:8080/v1"
    def broken() -> Any:
        raise FluxSenseError("not installed")
    assert FluxSenseLibraryClient(broken).server_url() is None
    assert FluxSenseRestClient("http://svc:8765/v1", 5).server_url() == "http://svc:8765"


def test_energy_hooks_override_only_when_set() -> None:
    """WOL settings from KPaperFlux reach FluxSense's hooks only if set (empty = FluxSense's config)."""
    settings = MagicMock()
    settings.hooks.wol_url = ""
    settings.hooks.wol_device = "from-toml"
    modules = {"fluxsense": MagicMock(), "fluxsense.config": MagicMock(load_settings=MagicMock(return_value=settings)),
               "fluxsense.models": MagicMock(), "fluxsense.models.identity": MagicMock(), "fluxsense.pipeline": MagicMock()}
    with patch.dict(sys.modules, modules):
        default_analyzer_factory(None, None, "", {"wol_url": "https://wol.example.test", "wol_device": ""})()
    assert settings.hooks.wol_url == "https://wol.example.test"
    assert settings.hooks.wol_device == "from-toml"


def test_library_health_reports_backend_state() -> None:
    """health() lists models; an unreachable backend reports 'degraded'."""
    analyzer = MagicMock()
    analyzer.backend.list_models.return_value = ["m1"]
    with patch.dict(sys.modules, {"fluxsense": MagicMock(__version__="0.1.0")}):
        client = FluxSenseLibraryClient(lambda: analyzer)
        analyzer.settings.llm.base_url = "http://localhost:8080/v1"
        assert client.health() == {"status": "ok", "version": "0.1.0", "llm_backend": True, "models": ["m1"],
                                   "server_url": "http://localhost:8080/v1"}
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

def test_rest_analyze_uploads_pdf_with_page_text(pdf: Path) -> None:
    """POST /v1/analyze with the PDF as multipart file and include_page_text=true."""
    session = MagicMock()
    session.request.return_value = _response(200, {"status": "OK", "logical_documents": [], "text_layer": {"pages": []}})
    client = FluxSenseRestClient("http://svc:8765/v1/", 600, session=session)
    assert client.analyze(pdf)["status"] == "OK"
    method, url = session.request.call_args.args
    assert (method, url) == ("POST", "http://svc:8765/v1/analyze")
    assert session.request.call_args.kwargs["timeout"] == (10.0, 600.0)
    assert session.request.call_args.kwargs["files"]["file"][0] == "doc.pdf"
    assert session.request.call_args.kwargs["params"] == {"include_page_text": "true"}


@pytest.mark.parametrize("error, code", [
    (requests.exceptions.ConnectionError("refused"), "BACKEND_UNREACHABLE"),
    (requests.exceptions.ReadTimeout("slow"), "BACKEND_TIMEOUT"),
    (requests.exceptions.InvalidURL("bad"), None),
])
def test_rest_transport_errors(pdf: Path, error: Exception, code: Any) -> None:
    """Transport failures of the service map onto FluxSense's error codes."""
    session = MagicMock()
    session.request.side_effect = error
    with pytest.raises(FluxSenseError) as info:
        FluxSenseRestClient("http://svc", 5, session=session).analyze(pdf)
    assert info.value.error_code == code
    assert info.value.retryable is (code is not None)


@pytest.mark.parametrize("status, code", [(503, "BACKEND_UNREACHABLE"), (504, "BACKEND_TIMEOUT"), (422, "INPUT_INVALID")])
def test_rest_error_bodies_carry_the_error_code(pdf: Path, status: int, code: str) -> None:
    """503/504/422 bodies {detail: {error_code, message}} keep FluxSense's code and message."""
    session = MagicMock()
    session.request.return_value = _response(status, {"detail": {"error_code": code, "message": "details"}})
    with pytest.raises(FluxSenseError) as info:
        FluxSenseRestClient("http://svc", 5, session=session).analyze(pdf)
    assert info.value.error_code == code and "details" in str(info.value)


def test_rest_other_http_errors_are_unclassified(pdf: Path) -> None:
    """Other HTTP errors (no FluxSense error body) carry no code."""
    session = MagicMock()
    session.request.return_value = _response(500, "Internal Server Error")
    with pytest.raises(FluxSenseError) as info:
        FluxSenseRestClient("http://svc", 5, session=session).analyze(pdf)
    assert info.value.error_code is None


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


def test_rest_uses_one_session_per_thread() -> None:
    """requests.Session is not thread-safe: without an injected session each thread gets its own."""
    client = FluxSenseRestClient("http://svc", 5)
    sessions = []
    threads = [threading.Thread(target=lambda: sessions.append(client._get_session())) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sessions[0] is not sessions[1]
    assert client._get_session() is client._get_session()


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
