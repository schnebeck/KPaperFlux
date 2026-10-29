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
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests

from core.logger import get_logger
from core.models.identity import IdentityProfile

logger = get_logger("engines.fluxsense")

CONNECT_TIMEOUT_S: float = 10.0
HEALTH_TIMEOUT_S: float = 15.0
UNAVAILABLE_STATUS: frozenset = frozenset({502, 503, 504})


class FluxSenseError(Exception):
    """
    Raised when FluxSense could not deliver a result.

    Attributes:
        retryable: True if the same request may succeed later (service or
            LLM backend temporarily unreachable).
    """

    def __init__(self, message: str, retryable: bool = False) -> None:
        """
        Initializes the error.

        Args:
            message: Human readable description.
            retryable: Whether a later retry is meaningful.
        """
        super().__init__(message)
        self.retryable: bool = retryable


class FluxSenseClient(ABC):
    """Interface of a FluxSense engine connection."""

    mode: str = ""

    @abstractmethod
    def analyze(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Analyzes one PDF (never modified).

        Args:
            pdf_path: PDF file.

        Returns:
            The FluxSense AnalysisResult as JSON dict.

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
                             business_id: Optional[IdentityProfile] = None) -> AnalyzerFactory:
    """
    Builds a factory for an in-process FluxSense Analyzer.

    Settings come from FluxSense's own configuration (TOML + environment).
    KPaperFlux's identity profiles, when configured, replace the ones in the
    FluxSense config: the application owns the user's identities.

    Args:
        private_id: Private identity profile.
        business_id: Business identity profile.

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
        return Analyzer(settings)

    return create


class FluxSenseLibraryClient(FluxSenseClient):
    """Runs FluxSense in-process (blocking; call from a worker thread)."""

    mode = "library"

    def __init__(self, analyzer_factory: AnalyzerFactory) -> None:
        """
        Args:
            analyzer_factory: Creates the FluxSense Analyzer on first use.
        """
        self._factory = analyzer_factory
        self._analyzer: Optional[Any] = None
        self._lock = threading.Lock()

    def _get_analyzer(self) -> Any:
        """Creates the Analyzer once (thread-safe)."""
        with self._lock:
            if self._analyzer is None:
                try:
                    self._analyzer = self._factory()
                except FluxSenseError:
                    raise
                except Exception as e:  # invalid FluxSense configuration and similar
                    raise FluxSenseError(f"FluxSense could not be initialized: {e}") from e
            return self._analyzer

    def analyze(self, pdf_path: Path) -> Dict[str, Any]:
        """Analyzes a PDF in-process. See FluxSenseClient.analyze()."""
        analyzer = self._get_analyzer()
        try:
            result = analyzer.analyze(Path(pdf_path))
        except Exception as e:  # FluxSense is an external engine: never let it crash the worker
            logger.error(f"[FluxSense] Library analysis failed for {Path(pdf_path).name}: {e}")
            raise FluxSenseError(f"FluxSense analysis failed: {e}", retryable=True) from e
        return result.model_dump(mode="json")

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
                "llm_backend": backend_ok, "models": list(models)}

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
            session: Optional HTTP session (tests).
        """
        self.base_url = normalize_base_url(base_url)
        self.timeout_s = float(timeout_s)
        self._session = session or requests.Session()

    def _request(self, method: str, path: str, read_timeout: float, **kwargs: Any) -> Dict[str, Any]:
        """Executes a request and maps transport / HTTP failures onto FluxSenseError."""
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.request(method, url, timeout=(CONNECT_TIMEOUT_S, read_timeout), **kwargs)
        except requests.exceptions.ReadTimeout as e:
            raise FluxSenseError(f"FluxSense timeout after {read_timeout:.0f}s at {url}", retryable=True) from e
        except requests.exceptions.ConnectionError as e:
            raise FluxSenseError(f"FluxSense service unreachable at {url}: {e}", retryable=True) from e
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

    def analyze(self, pdf_path: Path) -> Dict[str, Any]:
        """Uploads the PDF to POST /v1/analyze. See FluxSenseClient.analyze()."""
        path = Path(pdf_path)
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, "application/pdf")}
            return self._request("POST", "/v1/analyze", self.timeout_s, files=files)

    def health(self) -> Dict[str, Any]:
        """GET /v1/health. See FluxSenseClient.health()."""
        return self._request("GET", "/v1/health", HEALTH_TIMEOUT_S)

    def complete_json(self, prompt: str, label: str) -> Optional[Any]:
        """The REST API has no free-prompt endpoint."""
        raise FluxSenseError("The FluxSense REST API does not offer free prompts; use library mode")


def create_fluxsense_client(mode: str, base_url: str, timeout_s: float,
                            private_id: Optional[IdentityProfile] = None,
                            business_id: Optional[IdentityProfile] = None) -> FluxSenseClient:
    """
    Creates the configured FluxSense client.

    Args:
        mode: 'library' or 'rest'.
        base_url: REST service URL (mode 'rest').
        timeout_s: REST read timeout per analysis.
        private_id: Private identity (mode 'library').
        business_id: Business identity (mode 'library').

    Returns:
        The client.

    Raises:
        ValueError: If the mode is unknown.
    """
    if mode == FluxSenseLibraryClient.mode:
        return FluxSenseLibraryClient(default_analyzer_factory(private_id, business_id))
    if mode == FluxSenseRestClient.mode:
        return FluxSenseRestClient(base_url, timeout_s)
    raise ValueError(f"Unknown FluxSense mode: {mode}")
