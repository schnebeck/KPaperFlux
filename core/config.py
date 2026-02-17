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

import os
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import QSettings, QStandardPaths


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
    KEY_AI_PROVIDER: str = "ai_provider" # "gemini" or "ollama"
    KEY_OLLAMA_URL: str = "ollama_url"
    KEY_OLLAMA_MODEL: str = "ollama_model"
    KEY_OPENAI_KEY: str = "openai_key"
    KEY_OPENAI_MODEL: str = "openai_model"
    KEY_ANTHROPIC_KEY: str = "anthropic_key"
    KEY_ANTHROPIC_MODEL: str = "anthropic_model"
    KEY_LOG_LEVEL: str = "log_level"
    KEY_LOG_COMPONENTS: str = "log_components"

    # Defaults
    DEFAULT_LANGUAGE: str = "en"
    DEFAULT_MODEL: str = "gemini-2.0-flash"
    DEFAULT_AI_RETRIES: int = 3

    APP_ID: str = "kpaperflux"
    _active_profile: Optional[str] = None
    _cached_models: list[str] = []

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
        Helper to retrieve a setting value from a specific group.

        Args:
            group: The configuration group name.
            key: The setting key.
            default: The default value if not found.

        Returns:
            The retrieved value or default.
        """
        if group:
            self.settings.beginGroup(group)
        val = self.settings.value(key, default)
        if group:
            self.settings.endGroup()
        return val

    def _set_setting(self, group: str, key: str, value: Any) -> None:
        """
        Helper to save a setting value into a specific group.

        Args:
            group: The configuration group name.
            key: The setting key.
            value: The value to save.
        """
        if isinstance(value, str):
            value = value.strip()

        if group:
            self.settings.beginGroup(group)
        self.settings.setValue(key, value)
        if group:
            self.settings.endGroup()

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

        Args:
            model: The model name string.
        """
        self._set_setting("AI", self.KEY_GEMINI_MODEL, model)

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

        self.settings.beginGroup("AI")
        val = self.settings.value(self.KEY_API_KEY)
        self.settings.endGroup()

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
        """Retrieves the active AI provider ('gemini' or 'ollama')."""
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
        return str(self._get_setting("AI", self.KEY_ANTHROPIC_MODEL, "claude-3-5-sonnet-20240620"))

    def set_anthropic_model(self, model: str) -> None:
        """Saves the Anthropic model name."""
        self._set_setting("AI", self.KEY_ANTHROPIC_MODEL, model)

    def get_log_level(self) -> str:
        """Retrieves the global log level."""
        return str(self._get_setting("Logging", self.KEY_LOG_LEVEL, "WARNING"))

    def set_log_level(self, level: str) -> None:
        """Saves the global log level."""
        self._set_setting("Logging", self.KEY_LOG_LEVEL, level.upper())

    def get_log_components(self) -> dict:
        """Retrieves a dictionary of component-specific log levels."""
        import json
        raw = str(self._get_setting("Logging", self.KEY_LOG_COMPONENTS, "{}"))
        try:
            return json.loads(raw)
        except:
            return {}

    def set_log_components(self, components: dict) -> None:
        """Saves a dictionary of component-specific log levels."""
        import json
        self._set_setting("Logging", self.KEY_LOG_COMPONENTS, json.dumps(components))

    def get_log_file_path(self) -> Path:
        """Returns the absolute path to the log file."""
        return self.get_data_dir() / "app.log"
