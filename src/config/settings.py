from pathlib import Path
from typing import Dict, Any
import json
from src.utils.logger import get_logger 

logger = get_logger(__name__)

class Settings:
    """
    Manages application settings with lazy loading.
    Only loads configuration when needed.
    """
    _instance = None
    _settings: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._settings:
            self.load_settings()

    def load_settings(self, config_path: str = "config.json") -> None:
        """Load settings from configuration file."""
        try:
            with open(config_path, 'r') as f:
                self._settings = json.load(f)
            logger.info("Settings loaded successfully")
        except Exception as e:
            logger.error(f"Error loading settings: {str(e)}")
            self._settings = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value with default fallback."""
        return self._settings.get(key, default)