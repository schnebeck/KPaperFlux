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
import os
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
    KEY_GEMINI_MODEL: str = "gemini_model"
    KEY_LANGUAGE: str = "language"
    KEY_API_KEY: str = "api_key"
    KEY_API_VERIFIED: str = "api_verified"
    KEY_AI_RETRIES: str = "ai_retries"
    KEY_TRANSFER_PATH: str = "transfer_path"
    KEY_AI_PROVIDER: str = "ai_provider" # "gemini" | "ollama" | "llamacpp" | "openai" | "anthropic"
    KEY_OLLAMA_URL: str = "ollama_url"
    KEY_OLLAMA_MODEL: str = "ollama_model"
    KEY_OPENAI_KEY: str = "openai_key"
    KEY_OPENAI_MODEL: str = "openai_model"
    KEY_ANTHROPIC_KEY: str = "anthropic_key"
    KEY_ANTHROPIC_MODEL: str = "anthropic_model"
    KEY_LOG_LEVEL: str = "log_level"
    KEY_LOG_COMPONENTS: str = "log_components"
    KEY_PDF_PAGE_SIZE: str = "pdf_page_size"
    KEY_OLLAMA_NUM_CTX: str = "ollama_num_ctx"
    KEY_OLLAMA_NUM_PREDICT: str = "ollama_num_predict"
    KEY_OLLAMA_TIMEOUT: str = "ollama_timeout"
    KEY_OLLAMA_KEEP_ALIVE: str = "ollama_keep_alive"
    KEY_OLLAMA_MAX_IMAGE_PX: str = "ollama_max_image_px"
    KEY_LLAMACPP_URL: str = "llamacpp_url"
    KEY_LLAMACPP_MODEL: str = "llamacpp_model"
    KEY_LLAMACPP_API_KEY: str = "llamacpp_api_key"
    KEY_LLAMACPP_VISION: str = "llamacpp_vision"
    KEY_LLAMACPP_TIMEOUT: str = "llamacpp_timeout"
    KEY_LLAMACPP_FIRST_TIMEOUT: str = "llamacpp_first_request_timeout"
    KEY_LLAMACPP_MAX_TOKENS: str = "llamacpp_max_tokens"
    KEY_LLAMACPP_MAX_IMAGE_PX: str = "llamacpp_max_image_px"
    KEY_OCR_ENGINE: str = "ocr_engine"
    KEY_DOCLING_URL: str = "docling_url"
    KEY_DOCLING_PIPELINE: str = "docling_pipeline"
    KEY_DOCLING_TIMEOUT: str = "docling_timeout"

    # Defaults
    DEFAULT_LANGUAGE: str = "en"
    DEFAULT_MODEL: str = "gemini-2.5-flash"
    DEFAULT_AI_RETRIES: int = 3
    DEFAULT_OLLAMA_NUM_CTX: int = 32768
    DEFAULT_OLLAMA_NUM_PREDICT: int = 8192
    DEFAULT_OLLAMA_TIMEOUT: int = 600
    DEFAULT_OLLAMA_KEEP_ALIVE: str = "30m"
    DEFAULT_MAX_IMAGE_PX: int = 1600
    DEFAULT_LLAMACPP_URL: str = "http://localhost:8090"
    DEFAULT_LLAMACPP_MODEL: str = "qwen3.6-35b-a3b"
    DEFAULT_LLAMACPP_TIMEOUT: int = 600
    DEFAULT_LLAMACPP_FIRST_TIMEOUT: int = 1800
    DEFAULT_LLAMACPP_MAX_TOKENS: int = 8192
    OCR_ENGINES: tuple = ("ocrmypdf", "docling")
    DOCLING_PIPELINES: tuple = ("standard", "vlm")
    DEFAULT_OCR_ENGINE: str = "ocrmypdf"
    DEFAULT_DOCLING_URL: str = "http://localhost:5001"
    DEFAULT_DOCLING_PIPELINE: str = "standard"
    DEFAULT_DOCLING_TIMEOUT: int = 900

    APP_ID: str = "kpaperflux"
    _active_profile: Optional[str] = None
    _cached_models: list[str] = []

    @classmethod
    def get_cached_models(cls) -> list[str]:
        """Returns the cached list of available AI models."""
        return cls._cached_models

    @classmethod
    def set_cached_models(cls, models: list[str]) -> None:
        """Stores the discovered AI model list in the class-level cache."""
        cls._cached_models = list(models)

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
        
        # Run migrations
        self.migrate_config()

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

    def _get_bool(self, group: str, key: str, default: bool) -> bool:
        """
        Retrieves a boolean setting (QSettings INI stores booleans as strings).

        Args:
            group: Settings group.
            key: Settings key.
            default: Fallback value.

        Returns:
            The boolean value.
        """
        raw = self._get_setting(group, key, default)
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")

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

    def get_gemini_model(self) -> str:
        """
        Retrieves the configured Gemini AI model name.

        Returns:
            The model name string.
        """
        return str(self._get_setting("AI", self.KEY_GEMINI_MODEL, self.DEFAULT_MODEL))

    def set_gemini_model(self, model: str) -> None:
        """
        Saves the Gemini AI model name.
        Also handles basic validation to prevent empty strings.

        Args:
            model: The model name string.
        """
        if not model or str(model).strip() == "":
             model = self.DEFAULT_MODEL
        self._set_setting("AI", self.KEY_GEMINI_MODEL, model)

    def migrate_config(self) -> None:
        """
        Handles automatic migration of configuration values across versions.
        For example, upgrades legacy AI models to current defaults.
        """
        logger = get_logger("core.config")
        
        # 1. AI Model Migration (Upgrade < 2.5 to 2.5-flash)
        current_model = self.get_gemini_model()
        legacy_models = [
            "gemini-1.5-flash", "gemini-1.5-pro", 
            "gemini-2.0-flash", "gemini-2.0-pro-experimental",
            "gemini-exp-1206", "gemini-exp-1114"
        ]
        
        if any(legacy in current_model.lower() for legacy in legacy_models):
            logger.info(f"Migrating legacy AI model '{current_model}' to current default '{self.DEFAULT_MODEL}'")
            self.set_gemini_model(self.DEFAULT_MODEL)

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

    def get_api_key(self) -> str:
        """
        Retrieves the Gemini API key, falling back to environment variables.

        Returns:
            The API key string.
        """
        env_key = os.environ.get("GEMINI_API_KEY", "")
        val = self._get_setting("AI", self.KEY_API_KEY)

        if val is None or str(val).strip() == "":
            return env_key
        return str(val)

    def set_api_key(self, key: str) -> None:
        """
        Saves the Gemini API key.

        Args:
            key: The API key string.
        """
        self._set_setting("AI", self.KEY_API_KEY, key)

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

    def get_ai_retries(self) -> int:
        """
        Retrieves the max number of AI validation correction loops.

        Returns:
            The number of retries.
        """
        return int(self._get_setting("AI", self.KEY_AI_RETRIES, self.DEFAULT_AI_RETRIES))

    def set_ai_retries(self, retries: int) -> None:
        """
        Saves the max number of AI validation correction loops.

        Args:
            retries: The number of retries.
        """
        self._set_setting("AI", self.KEY_AI_RETRIES, retries)

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

    def get_ai_provider(self) -> str:
        """Retrieves the active AI provider ('gemini', 'ollama', 'llamacpp', 'openai', 'anthropic')."""
        return str(self._get_setting("AI", self.KEY_AI_PROVIDER, "gemini"))

    def set_ai_provider(self, provider: str) -> None:
        """Saves the active AI provider."""
        self._set_setting("AI", self.KEY_AI_PROVIDER, provider)

    def get_ollama_url(self) -> str:
        """Retrieves the Ollama API URL."""
        return str(self._get_setting("AI", self.KEY_OLLAMA_URL, "http://localhost:11434"))

    def set_ollama_url(self, url: str) -> None:
        """Saves the Ollama API URL."""
        self._set_setting("AI", self.KEY_OLLAMA_URL, url)

    def get_ollama_model(self) -> str:
        """Retrieves the Ollama model name."""
        return str(self._get_setting("AI", self.KEY_OLLAMA_MODEL, "llama3"))

    def set_ollama_model(self, model: str) -> None:
        """Saves the Ollama model name."""
        self._set_setting("AI", self.KEY_OLLAMA_MODEL, model)

    def get_openai_key(self) -> str:
        """Retrieves the OpenAI API key."""
        return str(self._get_setting("AI", self.KEY_OPENAI_KEY, ""))

    def set_openai_key(self, key: str) -> None:
        """Saves the OpenAI API key."""
        self._set_setting("AI", self.KEY_OPENAI_KEY, key)

    def get_openai_model(self) -> str:
        """Retrieves the OpenAI model name."""
        return str(self._get_setting("AI", self.KEY_OPENAI_MODEL, "gpt-4o"))

    def set_openai_model(self, model: str) -> None:
        """Saves the OpenAI model name."""
        self._set_setting("AI", self.KEY_OPENAI_MODEL, model)

    def get_anthropic_key(self) -> str:
        """Retrieves the Anthropic API key."""
        return str(self._get_setting("AI", self.KEY_ANTHROPIC_KEY, ""))

    def set_anthropic_key(self, key: str) -> None:
        """Saves the Anthropic API key."""
        self._set_setting("AI", self.KEY_ANTHROPIC_KEY, key)

    def get_anthropic_model(self) -> str:
        """Retrieves the Anthropic model name."""
        return str(self._get_setting("AI", self.KEY_ANTHROPIC_MODEL, "claude-sonnet-4-6"))

    def set_anthropic_model(self, model: str) -> None:
        """Saves the Anthropic model name."""
        self._set_setting("AI", self.KEY_ANTHROPIC_MODEL, model)

    def get_ollama_num_ctx(self) -> int:
        """Retrieves the Ollama context window size (options.num_ctx)."""
        return self._get_int("AI", self.KEY_OLLAMA_NUM_CTX, self.DEFAULT_OLLAMA_NUM_CTX)

    def set_ollama_num_ctx(self, value: int) -> None:
        """Saves the Ollama context window size."""
        self._set_setting("AI", self.KEY_OLLAMA_NUM_CTX, int(value))

    def get_ollama_num_predict(self) -> int:
        """Retrieves the Ollama max output tokens (options.num_predict)."""
        return self._get_int("AI", self.KEY_OLLAMA_NUM_PREDICT, self.DEFAULT_OLLAMA_NUM_PREDICT)

    def set_ollama_num_predict(self, value: int) -> None:
        """Saves the Ollama max output tokens."""
        self._set_setting("AI", self.KEY_OLLAMA_NUM_PREDICT, int(value))

    def get_ollama_timeout(self) -> int:
        """Retrieves the Ollama request timeout in seconds."""
        return self._get_int("AI", self.KEY_OLLAMA_TIMEOUT, self.DEFAULT_OLLAMA_TIMEOUT)

    def set_ollama_timeout(self, seconds: int) -> None:
        """Saves the Ollama request timeout in seconds."""
        self._set_setting("AI", self.KEY_OLLAMA_TIMEOUT, int(seconds))

    def get_ollama_keep_alive(self) -> str:
        """Retrieves the Ollama keep_alive duration (e.g. '30m')."""
        return str(self._get_setting("AI", self.KEY_OLLAMA_KEEP_ALIVE, self.DEFAULT_OLLAMA_KEEP_ALIVE))

    def set_ollama_keep_alive(self, value: str) -> None:
        """Saves the Ollama keep_alive duration."""
        self._set_setting("AI", self.KEY_OLLAMA_KEEP_ALIVE, value)

    def get_ollama_max_image_px(self) -> int:
        """Retrieves the maximum long-side pixel size of images sent to Ollama."""
        return self._get_int("AI", self.KEY_OLLAMA_MAX_IMAGE_PX, self.DEFAULT_MAX_IMAGE_PX)

    def set_ollama_max_image_px(self, value: int) -> None:
        """Saves the maximum long-side pixel size of images sent to Ollama."""
        self._set_setting("AI", self.KEY_OLLAMA_MAX_IMAGE_PX, int(value))

    def get_llamacpp_url(self) -> str:
        """Retrieves the base URL of the OpenAI-compatible llama.cpp / llama-swap server."""
        return str(self._get_setting("AI", self.KEY_LLAMACPP_URL, self.DEFAULT_LLAMACPP_URL))

    def set_llamacpp_url(self, url: str) -> None:
        """Saves the llama.cpp server base URL."""
        self._set_setting("AI", self.KEY_LLAMACPP_URL, url)

    def get_llamacpp_model(self) -> str:
        """Retrieves the llama.cpp model id."""
        return str(self._get_setting("AI", self.KEY_LLAMACPP_MODEL, self.DEFAULT_LLAMACPP_MODEL))

    def set_llamacpp_model(self, model: str) -> None:
        """Saves the llama.cpp model id."""
        self._set_setting("AI", self.KEY_LLAMACPP_MODEL, model)

    def get_llamacpp_api_key(self) -> str:
        """
        Retrieves the optional llama.cpp bearer token, falling back to the
        LLAMACPP_API_KEY environment variable.
        """
        val = self._get_setting("AI", self.KEY_LLAMACPP_API_KEY, "")
        if val is None or str(val).strip() == "":
            return os.environ.get("LLAMACPP_API_KEY", "")
        return str(val)

    def set_llamacpp_api_key(self, key: str) -> None:
        """Saves the llama.cpp bearer token."""
        self._set_setting("AI", self.KEY_LLAMACPP_API_KEY, key)

    def get_llamacpp_vision(self) -> bool:
        """Retrieves whether the llama.cpp model accepts images (False = text-only)."""
        return self._get_bool("AI", self.KEY_LLAMACPP_VISION, True)

    def set_llamacpp_vision(self, enabled: bool) -> None:
        """Saves whether the llama.cpp model accepts images."""
        self._set_setting("AI", self.KEY_LLAMACPP_VISION, bool(enabled))

    def get_llamacpp_timeout(self) -> int:
        """Retrieves the llama.cpp request timeout in seconds."""
        return self._get_int("AI", self.KEY_LLAMACPP_TIMEOUT, self.DEFAULT_LLAMACPP_TIMEOUT)

    def set_llamacpp_timeout(self, seconds: int) -> None:
        """Saves the llama.cpp request timeout in seconds."""
        self._set_setting("AI", self.KEY_LLAMACPP_TIMEOUT, int(seconds))

    def get_llamacpp_first_request_timeout(self) -> int:
        """Retrieves the timeout for the first request per model (llama-swap model load)."""
        return self._get_int("AI", self.KEY_LLAMACPP_FIRST_TIMEOUT, self.DEFAULT_LLAMACPP_FIRST_TIMEOUT)

    def set_llamacpp_first_request_timeout(self, seconds: int) -> None:
        """Saves the timeout for the first request per model."""
        self._set_setting("AI", self.KEY_LLAMACPP_FIRST_TIMEOUT, int(seconds))

    def get_llamacpp_max_tokens(self) -> int:
        """Retrieves the llama.cpp max output tokens."""
        return self._get_int("AI", self.KEY_LLAMACPP_MAX_TOKENS, self.DEFAULT_LLAMACPP_MAX_TOKENS)

    def set_llamacpp_max_tokens(self, value: int) -> None:
        """Saves the llama.cpp max output tokens."""
        self._set_setting("AI", self.KEY_LLAMACPP_MAX_TOKENS, int(value))

    def get_llamacpp_max_image_px(self) -> int:
        """Retrieves the maximum long-side pixel size of images sent to llama.cpp."""
        return self._get_int("AI", self.KEY_LLAMACPP_MAX_IMAGE_PX, self.DEFAULT_MAX_IMAGE_PX)

    def set_llamacpp_max_image_px(self, value: int) -> None:
        """Saves the maximum long-side pixel size of images sent to llama.cpp."""
        self._set_setting("AI", self.KEY_LLAMACPP_MAX_IMAGE_PX, int(value))

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
