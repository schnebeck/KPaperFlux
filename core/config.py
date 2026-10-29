"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/config.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Manages application configuration using QSettings. Standardizes
                paths for configuration and data across different platforms
                (XDG standards on Linux).
------------------------------------------------------------------------------
"""

import json
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import QSettings, QStandardPaths

from core.logger import get_logger


class AppConfig:
    """
    Manages application configuration using QSettings.
    Singleton-like usage via class methods or single instance.
    """

    # Keys (Simple names now, groups handled in methods)
    KEY_VAULT_PATH: str = "vault_path"
    KEY_OCR_BINARY: str = "binary_path"
    KEY_LANGUAGE: str = "language"
    KEY_TRANSFER_PATH: str = "transfer_path"
    KEY_LOG_LEVEL: str = "log_level"
    KEY_LOG_COMPONENTS: str = "log_components"
    KEY_PDF_PAGE_SIZE: str = "pdf_page_size"
    KEY_OCR_ENGINE: str = "ocr_engine"
    KEY_DOCLING_URL: str = "docling_url"
    KEY_DOCLING_PIPELINE: str = "docling_pipeline"
    KEY_DOCLING_TIMEOUT: str = "docling_timeout"
    KEY_FLUXSENSE_MODE: str = "fluxsense_mode"
    KEY_FLUXSENSE_URL: str = "fluxsense_url"
    KEY_FLUXSENSE_TIMEOUT: str = "fluxsense_timeout"
    KEY_FLUXSENSE_LLM_URL: str = "fluxsense_llm_url"
    KEY_FLUXSENSE_WOL_URL: str = "fluxsense_wol_url"
    KEY_FLUXSENSE_WOL_DEVICE: str = "fluxsense_wol_device"
    KEY_FLUXSENSE_WOL_TOKEN_COMMAND: str = "fluxsense_wol_token_command"

    # Defaults
    DEFAULT_LANGUAGE: str = "en"
    OCR_ENGINES: tuple = ("ocrmypdf", "docling")
    DOCLING_PIPELINES: tuple = ("standard", "vlm")
    DEFAULT_OCR_ENGINE: str = "ocrmypdf"
    DEFAULT_DOCLING_URL: str = "http://localhost:5001"
    DEFAULT_DOCLING_PIPELINE: str = "standard"
    DEFAULT_DOCLING_TIMEOUT: int = 900
    FLUXSENSE_MODE_LIBRARY: str = "library"
    FLUXSENSE_MODE_REST: str = "rest"
    FLUXSENSE_MODES: tuple = (FLUXSENSE_MODE_LIBRARY, FLUXSENSE_MODE_REST)
    DEFAULT_FLUXSENSE_MODE: str = FLUXSENSE_MODE_LIBRARY
    DEFAULT_FLUXSENSE_URL: str = "http://127.0.0.1:8765"
    DEFAULT_FLUXSENSE_TIMEOUT: int = 1800

    APP_ID: str = "kpaperflux"
    _active_profile: Optional[str] = None

    def __init__(self, profile: Optional[str] = None) -> None:
        """
        Initializes the configuration manager.
        Ensures a flat structure by explicitly naming the application and organization.
        
        Args:
            profile: Optional profile name (e.g. 'dev', 'test').
                    If provided, all paths and settings will be isolated (e.g. kpaperflux-dev).
        """
        # If no profile provided, use the last active one (Global Singleton-like)
        if profile is None:
            profile = AppConfig._active_profile
        else:
            AppConfig._active_profile = profile

        self.profile = profile
        self.active_id = self.APP_ID
        if profile:
            self.active_id = f"{self.APP_ID}-{profile}"
            
        self.settings = QSettings(self.active_id, self.active_id)
        get_logger("core").debug(f"[Config] Initialized settings from: {self.settings.fileName()} (Profile: {self.profile or 'default'})")

    def get_config_dir(self) -> Path:
        """
        Returns the path to the application configuration directory.
        Forces a flat structure: ~/.config/kpaperflux[-profile]/
        """
        base_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ConfigLocation)
        config_dir = Path(base_path) / self.active_id
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def get_data_dir(self) -> Path:
        """
        Returns the path to the application data directory.
        Forces a flat structure: ~/.local/share/kpaperflux[-profile]/
        """
        base_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
        data_dir = Path(base_path) / self.active_id
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def get_plugins_dir(self) -> Path:
        """
        Returns the path to the plugins directory.
        Located within the data folder: ~/.local/share/kpaperflux/plugins/
        """
        plugins_dir = self.get_data_dir() / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        return plugins_dir

    def _get_setting(self, group: str, key: str, default: Any = None) -> Any:
        """
        Helper to retrieve a setting value using a full path key.
        This is thread-safe as it doesn't use beginGroup/endGroup state.
        """
        full_key = f"{group}/{key}" if group else key
        val = self.settings.value(full_key, default)
        
        # Fallback for root keys being in [General] (common in INI files)
        if val is None and not group:
            val = self.settings.value(f"General/{key}", default)
            
        return val

    def _set_setting(self, group: str, key: str, value: Any) -> None:
        """
        Helper to save a setting value using a full path key.
        """
        if isinstance(value, str):
            value = value.strip()

        full_key = f"{group}/{key}" if group else key
        self.settings.setValue(full_key, value)

    def _get_int(self, group: str, key: str, default: int) -> int:
        """
        Retrieves an integer setting, falling back to the default on invalid values.

        Args:
            group: Settings group.
            key: Settings key.
            default: Fallback value.

        Returns:
            The integer value.
        """
        raw = self._get_setting(group, key, default)
        try:
            return int(raw)
        except (TypeError, ValueError):
            get_logger("core.config").warning(f"[Config] Invalid integer for {group}/{key}: {raw!r}. Using {default}.")
            return default

    def get_vault_path(self) -> str:
        """
        Retrieves the path to the document vault.

        Returns:
            The vault path string.
        """
        return str(self._get_setting("Storage", self.KEY_VAULT_PATH, "vault"))

    def set_vault_path(self, path: str) -> None:
        """
        Saves the path to the document vault.

        Args:
            path: The vault path string.
        """
        self._set_setting("Storage", self.KEY_VAULT_PATH, path)

    def get_ocr_binary(self) -> str:
        """
        Retrieves the path or command for the OCR binary.

        Returns:
            The OCR binary command string.
        """
        val = str(self._get_setting("OCR", self.KEY_OCR_BINARY, ""))
        return val if val else "ocrmypdf"

    def set_ocr_binary(self, path: str) -> None:
        """
        Saves the path or command for the OCR binary.

        Args:
            path: The OCR binary command string.
        """
        self._set_setting("OCR", self.KEY_OCR_BINARY, path)

    def get_language(self) -> str:
        """
        Retrieves the configured application language.

        Returns:
            The ISO language code string.
        """
        return str(self._get_setting("", self.KEY_LANGUAGE, self.DEFAULT_LANGUAGE))

    def set_language(self, lang: str) -> None:
        """
        Saves the application language.

        Args:
            lang: The ISO language code string.
        """
        self._set_setting("", self.KEY_LANGUAGE, lang)

    def get_private_signature(self) -> str:
        """
        Retrieves the private identity signature.

        Returns:
            The private signature string.
        """
        return str(self._get_setting("Identity", "private_signature", ""))

    def set_private_signature(self, sig: str) -> None:
        """
        Saves the private identity signature.

        Args:
            sig: The private signature string.
        """
        self._set_setting("Identity", "private_signature", sig)

    def get_business_signature(self) -> str:
        """
        Retrieves the business identity signature.

        Returns:
            The business signature string.
        """
        return str(self._get_setting("Identity", "business_signature", ""))

    def set_business_signature(self, sig: str) -> None:
        """
        Saves the business identity signature.

        Args:
            sig: The business signature string.
        """
        self._set_setting("Identity", "business_signature", sig)

    def get_private_profile_json(self) -> str:
        """
        Retrieves the private profile data as a JSON string.

        Returns:
            The JSON profile string.
        """
        return str(self._get_setting("Identity", "private_profile", "{}"))

    def set_private_profile_json(self, json_str: str) -> None:
        """
        Saves the private profile data as a JSON string.

        Args:
            json_str: The JSON profile string.
        """
        self._set_setting("Identity", "private_profile", json_str)

    def get_business_profile_json(self) -> str:
        """
        Retrieves the business profile data as a JSON string.

        Returns:
            The JSON profile string.
        """
        return str(self._get_setting("Identity", "business_profile", "{}"))

    def set_business_profile_json(self, json_str: str) -> None:
        """
        Saves the business profile data as a JSON string.

        Args:
            json_str: The JSON profile string.
        """
        self._set_setting("Identity", "business_profile", json_str)

    def get_transfer_path(self) -> str:
        """
        Retrieves the path to the transfer folder.

        Returns:
            The transfer path string.
        """
        return str(self._get_setting("Storage", self.KEY_TRANSFER_PATH, ""))

    def set_transfer_path(self, path: str) -> None:
        """
        Saves the path to the transfer folder.

        Args:
            path: The transfer path string.
        """
        self._set_setting("Storage", self.KEY_TRANSFER_PATH, path)

    def get_ocr_engine(self) -> str:
        """Retrieves the text extraction engine ('ocrmypdf' or 'docling')."""
        val = str(self._get_setting("OCR", self.KEY_OCR_ENGINE, self.DEFAULT_OCR_ENGINE)).lower()
        return val if val in self.OCR_ENGINES else self.DEFAULT_OCR_ENGINE

    def set_ocr_engine(self, engine: str) -> None:
        """Saves the text extraction engine."""
        if engine not in self.OCR_ENGINES:
            raise ValueError(f"Unknown OCR engine: {engine}")
        self._set_setting("OCR", self.KEY_OCR_ENGINE, engine)

    def get_docling_url(self) -> str:
        """Retrieves the docling-serve base URL."""
        return str(self._get_setting("OCR", self.KEY_DOCLING_URL, self.DEFAULT_DOCLING_URL))

    def set_docling_url(self, url: str) -> None:
        """Saves the docling-serve base URL."""
        self._set_setting("OCR", self.KEY_DOCLING_URL, url)

    def get_docling_pipeline(self) -> str:
        """Retrieves the docling pipeline ('standard' or 'vlm')."""
        val = str(self._get_setting("OCR", self.KEY_DOCLING_PIPELINE, self.DEFAULT_DOCLING_PIPELINE)).lower()
        return val if val in self.DOCLING_PIPELINES else self.DEFAULT_DOCLING_PIPELINE

    def set_docling_pipeline(self, pipeline: str) -> None:
        """Saves the docling pipeline."""
        if pipeline not in self.DOCLING_PIPELINES:
            raise ValueError(f"Unknown docling pipeline: {pipeline}")
        self._set_setting("OCR", self.KEY_DOCLING_PIPELINE, pipeline)

    def get_docling_timeout(self) -> int:
        """Retrieves the docling-serve request timeout in seconds."""
        return self._get_int("OCR", self.KEY_DOCLING_TIMEOUT, self.DEFAULT_DOCLING_TIMEOUT)

    def set_docling_timeout(self, seconds: int) -> None:
        """Saves the docling-serve request timeout in seconds."""
        self._set_setting("OCR", self.KEY_DOCLING_TIMEOUT, int(seconds))

    def get_fluxsense_mode(self) -> str:
        """Retrieves how FluxSense is called ('library' in-process or 'rest' service)."""
        val = str(self._get_setting("AI", self.KEY_FLUXSENSE_MODE, self.DEFAULT_FLUXSENSE_MODE)).lower()
        return val if val in self.FLUXSENSE_MODES else self.DEFAULT_FLUXSENSE_MODE

    def set_fluxsense_mode(self, mode: str) -> None:
        """
        Saves how FluxSense is called.

        Args:
            mode: One of FLUXSENSE_MODES.

        Raises:
            ValueError: If the mode is unknown.
        """
        if mode not in self.FLUXSENSE_MODES:
            raise ValueError(f"Unknown FluxSense mode: {mode}")
        self._set_setting("AI", self.KEY_FLUXSENSE_MODE, mode)

    def get_fluxsense_url(self) -> str:
        """Retrieves the base URL of the FluxSense REST service (mode 'rest')."""
        return str(self._get_setting("AI", self.KEY_FLUXSENSE_URL, self.DEFAULT_FLUXSENSE_URL))

    def set_fluxsense_url(self, url: str) -> None:
        """Saves the base URL of the FluxSense REST service."""
        self._set_setting("AI", self.KEY_FLUXSENSE_URL, url)

    def get_fluxsense_llm_url(self) -> str:
        """
        Retrieves the AI server URL override for FluxSense (library mode).

        Returns:
            The URL, or "" to use FluxSense's own configuration (default).
        """
        return str(self._get_setting("AI", self.KEY_FLUXSENSE_LLM_URL, "") or "").strip()

    def set_fluxsense_llm_url(self, url: str) -> None:
        """Saves the AI server URL override ("" = use FluxSense's configuration)."""
        self._set_setting("AI", self.KEY_FLUXSENSE_LLM_URL, url or "")

    def get_fluxsense_wol(self) -> dict:
        """
        Retrieves the optional energy-management settings (WOL-Server device
        requests for an AI server that sleeps). All empty by default = off.
        The token is never stored, only a command that prints it.

        Returns:
            {"url": ..., "device": ..., "token_command": ...}
        """
        return {
            "url": str(self._get_setting("AI", self.KEY_FLUXSENSE_WOL_URL, "") or "").strip(),
            "device": str(self._get_setting("AI", self.KEY_FLUXSENSE_WOL_DEVICE, "") or "").strip(),
            "token_command": str(self._get_setting("AI", self.KEY_FLUXSENSE_WOL_TOKEN_COMMAND, "") or "").strip(),
        }

    def set_fluxsense_wol(self, url: str, device: str, token_command: str) -> None:
        """
        Saves the energy-management settings ("" = off / keep FluxSense's configuration).

        Args:
            url: WOL-Server base URL.
            device: Device id or name of the AI server.
            token_command: Command printing the API token (e.g. a keyring lookup), never the token itself.
        """
        self._set_setting("AI", self.KEY_FLUXSENSE_WOL_URL, url or "")
        self._set_setting("AI", self.KEY_FLUXSENSE_WOL_DEVICE, device or "")
        self._set_setting("AI", self.KEY_FLUXSENSE_WOL_TOKEN_COMMAND, token_command or "")

    def get_fluxsense_hooks(self) -> dict:
        """
        FluxSense hook overrides from the energy-management settings (only set values).

        Returns:
            Mapping of FluxSense hooks.* names to values.
        """
        wol = self.get_fluxsense_wol()
        hooks = {"wol_url": wol["url"], "wol_device": wol["device"], "wol_token_command": wol["token_command"]}
        return {key: value for key, value in hooks.items() if value}

    def get_fluxsense_timeout(self) -> int:
        """Retrieves the FluxSense request timeout in seconds (whole-document analysis)."""
        return self._get_int("AI", self.KEY_FLUXSENSE_TIMEOUT, self.DEFAULT_FLUXSENSE_TIMEOUT)

    def set_fluxsense_timeout(self, seconds: int) -> None:
        """Saves the FluxSense request timeout in seconds."""
        self._set_setting("AI", self.KEY_FLUXSENSE_TIMEOUT, int(seconds))

    def get_log_level(self) -> str:
        """Retrieves the global log level."""
        return str(self._get_setting("Logging", self.KEY_LOG_LEVEL, "WARNING"))

    def set_log_level(self, level: str) -> None:
        """Saves the global log level."""
        self._set_setting("Logging", self.KEY_LOG_LEVEL, level.upper())

    def get_log_components(self) -> dict:
        """Retrieves a dictionary of component-specific log levels."""
        raw = str(self._get_setting("Logging", self.KEY_LOG_COMPONENTS, "{}"))
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_log_components(self, components: dict) -> None:
        """Saves a dictionary of component-specific log levels."""
        self._set_setting("Logging", self.KEY_LOG_COMPONENTS, json.dumps(components))

    def get_log_file_path(self) -> Path:
        """Returns the absolute path to the log file."""
        return self.get_data_dir() / "app.log"

    def get_pdf_page_size(self) -> Optional[str]:
        """Retrieves the preferred PDF page size (e.g. 'A4', 'LETTER')."""
        val = self._get_setting("General", self.KEY_PDF_PAGE_SIZE, None)
        return str(val) if val else None

    def set_pdf_page_size(self, size: str) -> None:
        """Saves the preferred PDF page size."""
        self._set_setting("General", self.KEY_PDF_PAGE_SIZE, size)
