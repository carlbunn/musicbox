import logging
from typing import Optional

def get_logger(name: str) -> logging.Logger:
    """
    Creates a logger instance with proper formatting.
    Minimizes memory usage by reusing existing loggers.
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger