import logging
import os
from typing import Optional
from pathlib import Path

def get_logger(name: str) -> logging.Logger:
    """
    Creates a logger instance with proper formatting.
    Minimizes memory usage by reusing existing loggers.
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        # Check if we're in development or production
        if os.getenv('MUSICBOX_ENV') == 'production':
            log_dir = Path("/opt/musicbox/log")
        else:
            # In development, use a local logs directory
            log_dir = Path(__file__).parent.parent.parent / 'logs'
        
        # Create log directory if it doesn't exist
        log_dir.mkdir(parents=True, exist_ok=True)

        # Set up file handler
        log_file = log_dir / 'musicbox.log'
        file_handler = logging.FileHandler(str(log_file))

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Also add console handler for development
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        logger.setLevel(logging.INFO)
    
    return logger