from pathlib import Path
from typing import Generator, List
import os
from src.utils.logger import get_logger

logger = get_logger(__name__)

class FileManager:
    """
    Manages audio files with efficient memory usage.
    Uses generators for file operations to minimize memory footprint.
    """
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        logger.info(f"FileManager initialized with base path: {base_path}")

    def get_audio_files(self) -> Generator[Path, None, None]:
        """
        Generator that yields audio file paths.
        Supports common audio formats.
        """
        AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg'}
        try:
            for file_path in self.base_path.rglob('*'):
                if file_path.suffix.lower() in AUDIO_EXTENSIONS:
                    yield file_path
        except Exception as e:
            logger.error(f"Error scanning audio files: {str(e)}")

    def get_file_size(self, file_path: Path) -> int:
        """Get file size without loading file into memory."""
        try:
            return os.path.getsize(file_path)
        except Exception as e:
            logger.error(f"Error getting file size for {file_path}: {str(e)}")
            return 0