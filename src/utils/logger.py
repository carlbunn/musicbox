import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional
from pathlib import Path

def get_logger(
    name: str,
    log_level: Optional[str] = None,
    max_bytes: int = 10_485_760,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Creates a logger instance with proper formatting and rotation.
    
    Args:
        name: Logger name
        log_level: Optional override for log level (defaults to env var or INFO)
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup files to keep
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        try:
            # Determine log level
            level = (
                log_level 
                or os.getenv('MUSICBOX_LOG_LEVEL', 'INFO')
            ).upper()
            logger.setLevel(getattr(logging, level))

            # Configure log directory
            is_prod = os.getenv('MUSICBOX_ENV') == 'production'
            log_dir = Path("/opt/musicbox/log") if is_prod else Path.cwd() / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)

            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

            # Set up file handler
            log_file = log_dir / os.getenv('MUSICBOX_LOG_FILE', 'musicbox.log')
            file_handler = RotatingFileHandler(
                str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            # Add console handler only in development
            if not is_prod:
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)

        except Exception as e:
            # Fallback to basic console logging if setup fails
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(console_handler)
            logger.error(f"Failed to initialize logger: {e}")
            logger.setLevel(logging.INFO)

    return logger