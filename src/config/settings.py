import json
import os
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from src.utils.logger import get_logger 

logger = get_logger(__name__)

@dataclass
class ConfigurationError(Exception):
    """Custom exception for configuration-related errors."""
    message: str
    details: Optional[Dict[str, Any]] = None

class Settings:
    """
    Thread-safe settings manager with environment support and validation.
    """
    _instance = None
    _settings: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            cls._instance._lock = threading.Lock()
        return cls._instance

    def __init__(self):
        if not self._settings:
            self.load_settings()

    def _sanitize_for_logging(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Create a safe copy of settings for logging."""
        sensitive_keys = {'api_key', 'password', 'secret', 'token'}
        return {
            k: '***' if any(s in k.lower() for s in sensitive_keys) else v
            for k, v in settings.items()
        }

    def load_settings(self, config_path: Optional[str] = None) -> None:
        """
        Load settings from configuration file with environment overrides.
        
        Args:
            config_path: Optional path to config file. If not provided,
                        uses default based on environment.
        """
        with self._lock:
            try:
                # Determine config path based on environment
                env = os.getenv('MUSICBOX_ENV', 'production')
                if not config_path:
                    base_path = Path.cwd()
                    config_path = str(base_path / f"config/config.{env}.json")

                config_path = Path(config_path)
                if not Path(config_path).is_absolute():
                    config_path = Path.cwd() / config_path

                logger.info(f"Loading settings from: {config_path}")

                # Load base configuration
                if not config_path.exists():
                    raise ConfigurationError(
                        f"Configuration file not found: {config_path}"
                    )

                with open(config_path, 'r') as f:
                    settings = json.load(f)

                # Override with environment variables
                env_prefix = 'MUSICBOX_'
                for key, value in os.environ.items():
                    if key.startswith(env_prefix):
                        setting_key = key[len(env_prefix):].lower()
                        settings[setting_key] = value

                # Validate required settings
                self._validate_settings(settings)
                
                self._settings = settings
                
                # Log sanitized settings
                safe_settings = self._sanitize_for_logging(settings)
                
                logger.info(f"Settings loaded successfully")
                logger.debug(f"Settings: {safe_settings}")

            except json.JSONDecodeError as e:
                raise ConfigurationError(
                    "Invalid JSON configuration",
                    {"error": str(e)}
                )

            except Exception as e:
                raise ConfigurationError(
                    f"Failed to load settings: {str(e)}"
                )

    def _validate_settings(self, settings: Dict[str, Any]) -> None:
        """
        Validate required settings and their types.
        """
        required_settings = {
            'music_directory': str
        }

        for key, expected_type in required_settings.items():
            if key not in settings:
                raise ConfigurationError(
                    f"Missing required setting: {key}"
                )
            if not isinstance(settings[key], expected_type):
                raise ConfigurationError(
                    f"Invalid type for setting {key}",
                    {
                        "expected": expected_type.__name__,
                        "received": type(settings[key]).__name__
                    }
                )

    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value with default fallback."""
        with self._lock:
            return self._settings.get(key, default)

    def reload(self) -> None:
        """Reload settings from configuration file."""
        self.load_settings()

    def update(self, key: str, value: Any) -> None:
        """
        Update a setting value at runtime.
        Use with caution as changes are not persistent.
        """
        with self._lock:
            self._settings[key] = value
            logger.info(f"Updated setting: {key}")