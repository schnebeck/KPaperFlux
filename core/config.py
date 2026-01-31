from pathlib import Path
from PyQt6.QtCore import QSettings, QStandardPaths

class AppConfig:
    """
    Manages application configuration using QSettings.
    Singleton-like usage via class methods or single instance.
    """
    
    # Keys (Simple names now, groups handled in methods)
    KEY_VAULT_PATH = "vault_path"
    KEY_OCR_BINARY = "binary_path"
    KEY_GEMINI_MODEL = "gemini_model"
    KEY_LANGUAGE = "language"
    KEY_API_KEY = "api_key"
    
    # Defaults
    DEFAULT_LANGUAGE = "en"
    DEFAULT_MODEL = "gemini-1.5-flash"
    
    def __init__(self):
        # On Linux, this stores at ~/.config/kpaperflux/kpaperflux.conf
        # Organization="kpaperflux", Application="kpaperflux"
        self.settings = QSettings("kpaperflux", "kpaperflux")

    def get_config_dir(self) -> Path:
        """
        Returns the path to the application configuration directory.
        Ensures the directory exists.
        Default on Linux: ~/.config/kpaperflux/
        """
        base_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ConfigLocation)
        config_dir = Path(base_path) / "kpaperflux"
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def get_data_dir(self) -> Path:
        """
        Returns the path to the application data directory.
        Ensures the directory exists.
        Default on Linux: ~/.local/share/kpaperflux/
        """
        base_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        # Note: AppDataLocation usually includes Organization/Appname automatically or generically.
        # But QStandardPaths behavior varies. 
        # On Linux AppDataLocation usually -> ~/.local/share/kpaperflux if initialized with correct org/app names.
        # However, to be safe and consistent with previous manually joined paths, we check.
        data_dir = Path(base_path)
        if not data_dir.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
        
    def _get_setting(self, group: str, key: str, default=None):
        if group:
            self.settings.beginGroup(group)
        val = self.settings.value(key, default)
        if group:
            self.settings.endGroup()
        return val

    def _set_setting(self, group: str, key: str, value):
        # Ensure we strip whitespace to avoid \n inside keys
        if isinstance(value, str):
            value = value.strip()
            
        if group:
            self.settings.beginGroup(group)
        self.settings.setValue(key, value)
        if group:
            self.settings.endGroup()

    def get_vault_path(self) -> str:
        # Check standard location XDG_DOCUMENTS_DIR/KPaperFlux if not set?
        # For now, return empty string or home dir
        return str(self._get_setting("Storage", self.KEY_VAULT_PATH, ""))
        
    def set_vault_path(self, path: str):
        self._set_setting("Storage", self.KEY_VAULT_PATH, path)
        
    def get_ocr_binary(self) -> str:
        val = str(self._get_setting("OCR", self.KEY_OCR_BINARY, ""))
        if not val:
            return "ocrmypdf"
        return val
        
    def set_ocr_binary(self, path: str):
        self._set_setting("OCR", self.KEY_OCR_BINARY, path)
        
    def get_gemini_model(self) -> str:
        return str(self._get_setting("AI", self.KEY_GEMINI_MODEL, self.DEFAULT_MODEL))
        
    def set_gemini_model(self, model: str):
        self._set_setting("AI", self.KEY_GEMINI_MODEL, model)
        
    def get_language(self) -> str:
        # Use root scope (which maps to [General] in INI by default)
        return str(self._get_setting("", self.KEY_LANGUAGE, self.DEFAULT_LANGUAGE))
        
    def set_language(self, lang: str):
        self._set_setting("", self.KEY_LANGUAGE, lang)

    def get_api_key(self) -> str:
        # Fallback to env var if not set in config (migration path)
        import os
        env_key = os.environ.get("GEMINI_API_KEY", "")
        
        self.settings.beginGroup("AI")
        val = self.settings.value(self.KEY_API_KEY)
        self.settings.endGroup()
        
        # If val is None, it returns None (if no default provided) or we could provide default.
        # But here we want to fallback if val is None OR val is empty string
        if val is None or str(val).strip() == "":
            return env_key
        return str(val)
        
    def set_api_key(self, key: str):
        self._set_setting("AI", self.KEY_API_KEY, key)

    # --- Phase 100: Identity ---
    def get_private_signature(self) -> str:
        return str(self._get_setting("Identity", "private_signature", ""))
        
    def set_private_signature(self, sig: str):
        self._set_setting("Identity", "private_signature", sig)
        
    def get_business_signature(self) -> str:
        return str(self._get_setting("Identity", "business_signature", ""))
        
    def set_business_signature(self, sig: str):
        self._set_setting("Identity", "business_signature", sig)

    def get_private_profile_json(self) -> str:
        return str(self._get_setting("Identity", "private_profile", "{}"))

    def set_private_profile_json(self, json_str: str):
        self._set_setting("Identity", "private_profile", json_str)

    def get_business_profile_json(self) -> str:
        return str(self._get_setting("Identity", "business_profile", "{}"))

    def set_business_profile_json(self, json_str: str):
        self._set_setting("Identity", "business_profile", json_str)
