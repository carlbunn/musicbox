from pathlib import Path
import json
from typing import Dict, Optional, List
from src.utils.logger import get_logger

logger = get_logger(__name__)

class MappingManager:
    """
    Manages mappings between RFID tags and music files.
    Handles persistence and validation of mappings.
    """
    def __init__(self, mapping_file: str = "config/mappings.json", music_dir: str = "music"):
        self.mapping_file = Path(mapping_file)
        self.music_dir = Path(music_dir).absolute()  # Get absolute path
        logger.info(f"Initializing MappingManager with music directory: {self.music_dir}")
        self.mappings: Dict[str, str] = {}
        
        # Ensure music directory exists
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self._load_mappings()

    def _load_mappings(self) -> None:
        """Load mappings from file, create if doesn't exist."""
        try:
            if self.mapping_file.exists():
                with open(self.mapping_file, 'r') as f:
                    self.mappings = json.load(f)
                logger.info(f"Loaded {len(self.mappings)} mappings")
            else:
                self._save_mappings()
                logger.info("Created new mappings file")
        except Exception as e:
            logger.error(f"Error loading mappings: {str(e)}")

    def _save_mappings(self) -> None:
        """Save current mappings to file."""
        try:
            # Ensure directory exists
            self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.mapping_file, 'w') as f:
                json.dump(self.mappings, f, indent=2)
            logger.info("Mappings saved successfully")
        except Exception as e:
            logger.error(f"Error saving mappings: {str(e)}")

    def remove_tag_mapping(self, rfid_tag: str) -> bool:
        """Remove mapping for a specific RFID tag."""
        try:
            if rfid_tag in self.mappings:
                del self.mappings[rfid_tag]
                self._save_mappings()
                logger.info(f"Removed mapping for tag: {rfid_tag}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing mapping: {str(e)}")
            return False

    def add_mapping(self, rfid_tag: str, music_file: str) -> bool:
        """
        Add or update a mapping between RFID tag and music file.
        If tag already exists, removes old mapping first.
        Returns True if successful.
        """
        try:
            # Convert to Path object
            music_path = Path(music_file)
            
            # If it's not absolute, assume it's relative to music_dir
            if not music_path.is_absolute():
                music_path = self.music_dir / music_path

            # Verify file exists
            if not music_path.exists():
                logger.error(f"Music file not found: {music_path}")
                return False

            # Remove existing mapping for this tag if it exists
            if rfid_tag in self.mappings:
                old_file = self.mappings[rfid_tag]
                logger.info(f"Removing existing mapping: {rfid_tag} -> {old_file}")
                self.remove_tag_mapping(rfid_tag)

            # Store path relative to music directory
            relative_path = music_path.relative_to(self.music_dir)
            self.mappings[rfid_tag] = str(relative_path)
            self._save_mappings()
            logger.info(f"Added mapping: {rfid_tag} -> {relative_path}")
            return True

        except Exception as e:
            logger.error(f"Error adding mapping: {str(e)}")
            return False

    def get_music_file(self, rfid_tag: str) -> Optional[Path]:
        """
        Get full path of music file for RFID tag.
        Returns None if tag isn't mapped or file doesn't exist.
        """
        try:
            if rfid_tag in self.mappings:
                music_path = self.music_dir / self.mappings[rfid_tag]
                if music_path.exists():
                    return music_path
                logger.warning(f"Mapped file not found: {music_path}")
            return None
        except Exception as e:
            logger.error(f"Error getting music file: {str(e)}")
            return None

    def get_unmapped_files(self) -> List[Path]:
        """Get list of music files that aren't mapped to any RFID tag."""
        try:
            # Get all music files
            all_files = set()
            for ext in ['.mp3', '.wav', '.flac', '.ogg']:
                all_files.update(self.music_dir.glob(f"*{ext}"))
            
            # Convert mapped files to absolute paths for comparison
            mapped_files = {(self.music_dir / Path(path)).resolve() 
                          for path in self.mappings.values()}
            
            # Return unmapped files (relative to music_dir)
            unmapped = sorted(list(all_files - mapped_files))
            logger.info(f"Found {len(unmapped)} unmapped files")
            return unmapped

        except Exception as e:
            logger.error(f"Error getting unmapped files: {str(e)}")
            return []

    def validate_mappings(self) -> Dict[str, List[str]]:
        """
        Validate all mappings and return any issues found.
        Returns dict with 'missing_files' and 'duplicate_files' lists.
        """
        issues = {
            'missing_files': [],
            'duplicate_files': []
        }

        try:
            # Check for missing files
            for tag, file_path in self.mappings.items():
                full_path = self.music_dir / file_path
                if not full_path.exists():
                    issues['missing_files'].append(f"{tag}: {file_path}")

            # Check for duplicate files
            file_counts = {}
            for file_path in self.mappings.values():
                file_counts[file_path] = file_counts.get(file_path, 0) + 1
                
            for file_path, count in file_counts.items():
                if count > 1:
                    issues['duplicate_files'].append(file_path)

            if any(issues.values()):
                logger.warning(f"Found mapping issues: {issues}")

        except Exception as e:
            logger.error(f"Error validating mappings: {str(e)}")

        return issues