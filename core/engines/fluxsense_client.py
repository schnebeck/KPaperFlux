"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/engines/fluxsense_client.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Clients for the FluxSense analysis engine: in-process library
                (the 'fluxsense' package) or the FluxSense REST service.
                Both return the AnalysisResult as a JSON dict and map every
                failure onto FluxSenseError so callers can keep documents in
                a retryable state.
------------------------------------------------------------------------------
"""

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from core.logger import get_logger
from core.models.identity import IdentityProfile

logger = get_logger("ai.fluxsense")

CONNECT_TIMEOUT_S: float = 10.0
HEALTH_TIMEOUT_S: float = 15.0
UNAVAILABLE_STATUS: frozenset = frozenset({502, 503, 504})


class FluxSenseError(Exception):
    """
    Raised when FluxSense could not deliver a result.

    Attributes:
        retryable: True if the same request may succeed later (service or
            LLM backend temporarily unreachable).
        unreachable: True if the server could not be reached at all.
    """

    def __init__(self, message: str, retryable: bool = False, unreachable: bool = False) -> None:
        """
        Initializes the error.

        Args:
            message: Human readable description.
            retryable: Whether a later retry is meaningful.
            unreachable: Whether the server could not be reached at all.
        """
        super().__init__(message)
        self.retryable: bool = retryable
        self.unreachable: bool = unreachable


@dataclass
class FluxSenseOutput:
    """
    One analysis run.

    Attributes:
        result: The FluxSense AnalysisResult as JSON dict.
        page_texts: Best text per page of the analyzed PDF (index i = page i + 1),
            or None if the connection cannot deliver the text layer (REST).
    """

    result: Dict[str, Any]
    page_texts: Optional[List[str]] = None


class FluxSenseClient(ABC):
    """Interface of a FluxSense engine connection."""

    mode: str = ""
    #: True if analyze() returns the engine's text layer (Stage 0 then needs no OCR).
    supplies_page_texts: bool = False

    @abstractmethod
    def analyze(self, pdf_path: Path) -> FluxSenseOutput:
        """
        Analyzes one PDF (never modified). Safe to call from several threads.

        Args:
            pdf_path: PDF file.

        Returns:
            The analysis output.

        Raises:
            FluxSenseError: If no result could be produced.
        """

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """
        Checks engine and LLM backend availability without analyzing anything.

        Returns:
            Dict with at least 'status' ('ok' | 'degraded') and 'llm_backend' (bool).

        Raises:
            FluxSenseError: If the engine itself is not reachable or not installed.
        """

    @abstractmethod
    def server_url(self) -> Optional[str]:
        """
        The address of the server this connection depends on, for messages:
        the AI (LLM) server in library mode, the FluxSense service in REST mode.

        Returns:
            The URL, or None if it cannot be determined.
        """

    @abstractmethod
    def complete_json(self, prompt: str, label: str) -> Optional[Any]:
        """
        Sends a free JSON prompt to the engine's primary LLM (application
        helpers such as identity signature parsing).

        Args:
            prompt: The complete prompt.
            label: Short label for logs.

        Returns:
            The parsed JSON answer, or None if the model gave no valid answer.

        Raises:
            FluxSenseError: If the mode does not support free prompts or the backend failed.
        """


# --------------------------------------------------------------------- library

AnalyzerFactory = Callable[[], Any]


def _profile_to_fluxsense(profile: Optional[IdentityProfile], target_cls: Any) -> Any:
    """Converts a KPaperFlux IdentityProfile into FluxSense's field-identical model."""
    return target_cls.model_validate(profile.model_dump()) if profile else None


def default_analyzer_factory(private_id: Optional[IdentityProfile] = None,
                             business_id: Optional[IdentityProfile] = None,
                             llm_url: Optional[str] = None) -> AnalyzerFactory:
    """
    Builds a factory for an in-process FluxSense Analyzer.

    Settings come from FluxSense's own configuration (TOML + environment).
    KPaperFlux only overrides what the user explicitly set in KPaperFlux:
    the identity profiles (the application owns the user's identities) and
    the AI server URL. Empty values keep FluxSense's configuration.

    Args:
        private_id: Private identity profile.
        business_id: Business identity profile.
        llm_url: AI server (OpenAI-compatible) base URL; empty keeps FluxSense's setting.

    Returns:
        Callable that creates the Analyzer.
    """

    def create() -> Any:
        """Imports FluxSense lazily and creates the Analyzer."""
        try:
            from fluxsense.config import load_settings
            from fluxsense.models.identity import IdentityProfile as FluxIdentity
            from fluxsense.pipeline import Analyzer
        except ImportError as e:
            raise FluxSenseError(f"FluxSense library is not installed in this Python environment: {e}") from e
        settings = load_settings()
        if private_id:
            settings.identity.private = _profile_to_fluxsense(private_id, FluxIdentity)
        if business_id:
            settings.identity.business = _profile_to_fluxsense(business_id, FluxIdentity)
        if llm_url and llm_url.strip():
            settings.llm.base_url = llm_url.strip()
        return Analyzer(settings)

    return create


class FluxSenseLibraryClient(FluxSenseClient):
    """
    Runs FluxSense in-process (blocking; call from worker threads).

    The analysis result itself carries no page texts, so the client captures
    the text layer FluxSense builds in Analyzer.prepare() (per thread, so
    concurrent analyses on the shared Analyzer stay apart).
    """

    mode = "library"
    supplies_page_texts = True

    def __init__(self, analyzer_factory: AnalyzerFactory) -> None:
        """
        Args:
            analyzer_factory: Creates the FluxSense Analyzer on first use.
        """
        self._factory = analyzer_factory
        self._analyzer: Optional[Any] = None
        self._lock = threading.Lock()
        self._captured = threading.local()

    def _get_analyzer(self) -> Any:
        """Creates the Analyzer once (thread-safe) and hooks the text layer capture."""
        with self._lock:
            if self._analyzer is None:
                try:
                    analyzer = self._factory()
                except FluxSenseError:
                    raise
                except Exception as e:  # invalid FluxSense configuration and similar
                    raise FluxSenseError(f"FluxSense could not be initialized: {e}") from e
                self._install_capture(analyzer)
                self._analyzer = analyzer
            return self._analyzer

    def _install_capture(self, analyzer: Any) -> None:
        """Wraps Analyzer.prepare() so analyze() keeps its own flow (deferred mode, reviews)."""
        original = analyzer.prepare
        captured = self._captured

        def prepare(pdf_path: Path, engine: Optional[str] = None) -> Any:
            """Delegates to FluxSense and remembers the text layer for this thread."""
            prepared = original(pdf_path, engine)
            captured.layer = getattr(prepared, "layer", None)
            return prepared

        analyzer.prepare = prepare

    def analyze(self, pdf_path: Path) -> FluxSenseOutput:
        """Analyzes a PDF in-process. See FluxSenseClient.analyze()."""
        analyzer = self._get_analyzer()
        self._captured.layer = None
        try:
            result = analyzer.analyze(Path(pdf_path))
        except Exception as e:  # FluxSense is an external engine: never let it crash the worker
            logger.error(f"[FluxSense] Library analysis failed for {Path(pdf_path).name}: {e}")
            raise FluxSenseError(f"FluxSense analysis failed: {e}", retryable=True) from e
        layer, self._captured.layer = self._captured.layer, None
        texts = [str(t or "") for t in layer.texts()] if layer is not None else None
        return FluxSenseOutput(result=result.model_dump(mode="json"), page_texts=texts)

    def health(self) -> Dict[str, Any]:
        """Lists the backend models (no wake-up, no analysis). See FluxSenseClient.health()."""
        analyzer = self._get_analyzer()
        try:
            from fluxsense import __version__
        except ImportError as e:
            raise FluxSenseError(f"FluxSense library is not installed: {e}") from e
        try:
            models = analyzer.backend.list_models()
            backend_ok = True
        except Exception as e:  # httpx/OS errors of the external backend
            logger.info(f"[FluxSense] LLM backend unreachable: {e}")
            models, backend_ok = [], False
        return {"status": "ok" if backend_ok else "degraded", "version": __version__,
                "llm_backend": backend_ok, "models": list(models), "server_url": self.server_url()}

    def server_url(self) -> Optional[str]:
        """The AI server FluxSense talks to (after KPaperFlux's override). See FluxSenseClient.server_url()."""
        try:
            return str(self._get_analyzer().settings.llm.base_url)
        except FluxSenseError as e:
            logger.info(f"[FluxSense] AI server URL unknown: {e}")
            return None

    def complete_json(self, prompt: str, label: str) -> Optional[Any]:
        """Sends the prompt through FluxSense's LLM backend (primary model)."""
        analyzer = self._get_analyzer()
        try:
            from fluxsense.llm.base import LLMRequest
        except ImportError as e:
            raise FluxSenseError(f"FluxSense library is not installed: {e}") from e
        request = LLMRequest(prompt=prompt, label=label, model=analyzer.settings.models.primary)
        try:
            return analyzer.backend.generate_json(request)
        except Exception as e:  # httpx/OS errors of the external backend
            raise FluxSenseError(f"FluxSense LLM request failed: {e}", retryable=True) from e


# --------------------------------------------------------------------- REST

def normalize_base_url(url: str) -> str:
    """Strips trailing slashes and a trailing '/v1' from a service URL."""
    base = (url or "").strip().rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


class FluxSenseRestClient(FluxSenseClient):
    """Calls a FluxSense REST service (``fluxsense serve``)."""

    mode = "rest"

    def __init__(self, base_url: str, timeout_s: float, session: Optional[requests.Session] = None) -> None:
        """
        Args:
            base_url: Service URL, e.g. http://127.0.0.1:8765.
            timeout_s: Read timeout of one analysis in seconds.
            session: Optional HTTP session shared by all threads (tests); by
                default every thread gets its own session.
        """
        self.base_url = normalize_base_url(base_url)
        self.timeout_s = float(timeout_s)
        self._shared_session = session
        self._local = threading.local()

    def _get_session(self) -> requests.Session:
        """Returns the injected session or one per thread (requests.Session is not thread-safe)."""
        if self._shared_session is not None:
            return self._shared_session
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._local.session = requests.Session()
        return session

    def _request(self, method: str, path: str, read_timeout: float, **kwargs: Any) -> Dict[str, Any]:
        """Executes a request and maps transport / HTTP failures onto FluxSenseError."""
        url = f"{self.base_url}{path}"
        try:
            resp = self._get_session().request(method, url, timeout=(CONNECT_TIMEOUT_S, read_timeout), **kwargs)
        except requests.exceptions.ReadTimeout as e:
            raise FluxSenseError(f"FluxSense timeout after {read_timeout:.0f}s at {url}", retryable=True) from e
        except requests.exceptions.ConnectionError as e:
            raise FluxSenseError(f"FluxSense service unreachable at {url}: {e}", retryable=True, unreachable=True) from e
        except requests.exceptions.RequestException as e:
            raise FluxSenseError(f"FluxSense request to {url} failed: {e}") from e
        if resp.status_code != 200:
            body = (resp.text or "")[:300]
            raise FluxSenseError(f"FluxSense HTTP {resp.status_code} at {url}: {body}",
                                 retryable=resp.status_code in UNAVAILABLE_STATUS)
        try:
            data = resp.json()
        except ValueError as e:
            raise FluxSenseError(f"FluxSense returned no JSON at {url}: {e}") from e
        if not isinstance(data, dict):
            raise FluxSenseError(f"FluxSense returned {type(data).__name__} instead of an object at {url}")
        return data

    def analyze(self, pdf_path: Path) -> FluxSenseOutput:
        """Uploads the PDF to POST /v1/analyze (no text layer in the response). See FluxSenseClient.analyze()."""
        path = Path(pdf_path)
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, "application/pdf")}
            return FluxSenseOutput(result=self._request("POST", "/v1/analyze", self.timeout_s, files=files))

    def health(self) -> Dict[str, Any]:
        """GET /v1/health. See FluxSenseClient.health()."""
        return self._request("GET", "/v1/health", HEALTH_TIMEOUT_S)

    def server_url(self) -> Optional[str]:
        """The FluxSense service URL. See FluxSenseClient.server_url()."""
        return self.base_url

    def complete_json(self, prompt: str, label: str) -> Optional[Any]:
        """The REST API has no free-prompt endpoint."""
        raise FluxSenseError("The FluxSense REST API does not offer free prompts; use library mode")


def mode_supplies_page_texts(mode: str) -> bool:
    """
    Tells whether a FluxSense mode delivers the text layer with each analysis.

    Args:
        mode: 'library' or 'rest'.

    Returns:
        True for the in-process library.
    """
    return mode == FluxSenseLibraryClient.mode


def create_fluxsense_client(mode: str, base_url: str, timeout_s: float,
                            private_id: Optional[IdentityProfile] = None,
                            business_id: Optional[IdentityProfile] = None,
                            llm_url: str = "") -> FluxSenseClient:
    """
    Creates the configured FluxSense client.

    Args:
        mode: 'library' or 'rest'.
        base_url: REST service URL (mode 'rest').
        timeout_s: REST read timeout per analysis.
        private_id: Private identity (mode 'library').
        business_id: Business identity (mode 'library').
        llm_url: AI server URL override (mode 'library'); empty keeps FluxSense's configuration.

    Returns:
        The client.

    Raises:
        ValueError: If the mode is unknown.
    """
    if mode == FluxSenseLibraryClient.mode:
        return FluxSenseLibraryClient(default_analyzer_factory(private_id, business_id, llm_url))
    if mode == FluxSenseRestClient.mode:
        return FluxSenseRestClient(base_url, timeout_s)
    raise ValueError(f"Unknown FluxSense mode: {mode}")
