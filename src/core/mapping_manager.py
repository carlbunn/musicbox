from pathlib import Path
import json
import vlc
import threading
from typing import Dict, Optional, List, Union
from src.utils.logger import get_logger

logger = get_logger(__name__)

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg'}

class MappingManager:
    def __init__(self,
                 mapping_file: Union[str, Path] = "config/mappings.json",
                 music_dir: Union[str, Path] = "music",
                 save_timer: int = 30.0):
        """
        Initialize the MappingManager with absolute paths for mapping file and music directory.
        
        Args:
            mapping_file: Path to the mapping database file
            music_dir: Path to the root music directory
        """
        self._save_database_timer = None
        try:
            # Convert paths to absolute
            self.mapping_file = Path(mapping_file).resolve()
            self.music_dir = Path(music_dir).resolve()

            if not self.music_dir.is_dir():
                logger.info(f"Music directory does not exist, will create a new directory: {self.music_dir}")
                self.music_dir.mkdir(parents=True, exist_ok=True)

            if not self.mapping_file.exists():
                logger.info(f"Mapping file doesn't exist, will create a new file: {self.mapping_file}")
                self.mapping_file.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"Initialising MappingManager with music directory: {self.music_dir}")
            logger.info(f"Initialising MappingManager with mapping file: {self.mapping_file}")

            # Initialize storage
            self.files: Dict[str, Dict] = {}        # relative_path -> file metadata
            self.mappings: Dict[str, str] = {}      # rfid_tag -> relative_path

            # Set the save database timer
            self._save_timer_interval = save_timer
            self._database_changed = False

            # Load existing data
            self._load_database()
            self.scan_directory()

        except Exception:
            self.cleanup()  # Ensure cleanup happens if initialization fails
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def _mark_database_changed(self) -> None:
        """Mark database as changed and ensure timer is running."""
        self._database_changed = True

        # Ensure timer is running if not already
        if (not self._save_database_timer or not self._save_database_timer.is_alive()):
            self._save_database_timer = threading.Timer(self._save_timer_interval, self._save_database_to_disk)
            self._save_database_timer.start()

    def to_absolute_path(self, relative_path: Union[str, Path]) -> Path:
        """Convert a relative path to an absolute path within music_dir."""
        return (self.music_dir / Path(relative_path)).resolve()

    def to_relative_path(self, path: Union[str, Path]) -> str:
        """
        Convert any path (absolute or relative) to a path relative to music_dir.
        Raises ValueError if path is outside music_dir.
        """
        try:
            path = Path(path)
            if not path.is_absolute():
                path = (self.music_dir / path).resolve()

            rel_path = path.relative_to(self.music_dir)
            return str(rel_path)
        except ValueError:
            raise ValueError(f"Path {path} is not within music directory {self.music_dir}")

    def _load_database(self) -> None:
        """Load the mapping database from disk."""
        if not self.mapping_file.exists():
            logger.info(f"Creating new empty database at {self.mapping_file}")
            self._save_database_to_disk(force_save=True)
            return

        try:
            with open(self.mapping_file, 'r') as f:
                data = json.load(f)
                self.files = data.get('files', {})
                self.mappings = data.get('mappings', {})

            logger.info(f"Loaded {len(self.mappings)} mappings and {len(self.files)} files")
            self._database_changed = False

        except Exception as e:
            logger.error(f"Error loading database: {e}")
            self.files = {}
            self.mappings = {}
            self._save_database_to_disk(force_save=True)

    def save_database(self) -> bool:
        """Save the mapping database."""
        return self._save_database_to_disk()

    def _save_database_to_disk(self, force_save: bool = False) -> bool:
        """Save the mapping database to disk.
        
        Args:
            set_timer: Whether to reset the auto-save timer
            force_save: Whether to save even if no changes detected
        """
        try:
            # Cancel any existing timers
            if (self._save_database_timer and self._save_database_timer.is_alive()):
                self._save_database_timer.cancel()

            if not self._database_changed and not force_save:
                return True

            # Write to temporary file first
            temp_file = self.mapping_file.with_suffix('.tmp')
            data = {
                'files': self.files,
                'mappings': self.mappings
            }

            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)

            # Atomic replace
            temp_file.replace(self.mapping_file)
            logger.info("Database saved successfully")
            self._database_changed = False

            return True

        except Exception as e:
            logger.error(f"Error saving database: {e}")
            return False

    def _extract_metadata(self, file_path: Union[str, Path]) -> Dict:
        """Extract metadata from an audio file."""
        media = None

        try:
            media = vlc.Media(str(file_path))
            media.parse()
            
            metadata = {
                'title': media.get_meta(vlc.Meta.Title) or file_path.stem,
                'artist': media.get_meta(vlc.Meta.Artist) or 'Unknown Artist',
                'album': media.get_meta(vlc.Meta.Album) or 'Unknown Album',
                'filename': file_path.name,
                'size': file_path.stat().st_size,
                'modified': file_path.stat().st_mtime,
                'last_position': 0
            }
            return metadata

        except Exception as e:
            logger.error(f"Error extracting metadata from {file_path}: {e}")
            return {
                'title': file_path.stem,
                'artist': 'Unknown Artist',
                'album': 'Unknown Album',
                'filename': file_path.name,
                'size': 0,
                'modified': 0,
                'last_position': 0
            }

        finally:
            if media:
                media.release()

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
            for tag, rel_path in self.mappings.items():
                abs_path = self.to_absolute_path(rel_path)
                if not abs_path.exists():
                    issues['missing_files'].append(f"{tag}: {rel_path}")

            # Check for duplicate mappings to the same file
            path_counts = {}
            for rel_path in self.mappings.values():
                path_counts[rel_path] = path_counts.get(rel_path, 0) + 1
                
            for rel_path, count in path_counts.items():
                if count > 1:
                    issues['duplicate_files'].append(rel_path)

            if any(issues.values()):
                logger.warning(f"Found mapping issues: {issues}")

            return issues

        except Exception as e:
            logger.error(f"Error validating mappings: {e}")
            return issues

    def scan_directory(self) -> bool:
        """Scan music directory and update file database."""
        try:
            # Find all music files
            current_files = []
            
            for file_path in self.music_dir.rglob('*'):
                if file_path.suffix.lower() in AUDIO_EXTENSIONS and not file_path.name.startswith('.'):
                    current_files.append(file_path)

            # Convert to relative paths
            current_files = {str(f.relative_to(self.music_dir)): f for f in current_files}

            # Remove entries for files that no longer exist
            self.files = {path: data for path, data in self.files.items() 
                         if path in current_files}

            # Add new files
            for rel_path, abs_path in current_files.items():
                if rel_path not in self.files:
                    self.files[rel_path] = {
                        'metadata': self._extract_metadata(abs_path),
                        'last_position': 0
                    }

            # Clean up mappings for missing files
            self.mappings = {tag: path for tag, path in self.mappings.items()
                           if path in self.files}

            self._mark_database_changed()
            logger.info(f"Scan complete. Found {len(current_files)} files")

            return True

        except Exception as e:
            logger.error(f"Error scanning directory: {e}")
            return False

    def add_mapping(self, rfid_tag: str, file_path: Union[str, Path]) -> bool:
        """
        Add or update mapping. file_path can be absolute or relative.
        Returns True if mapping was successful.
        """
        try:
            # Convert to Path and resolve
            rel_path = self.to_relative_path(file_path)
            
            # If file not in database, rescan directory
            if rel_path not in self.files:
                self.scan_directory()

            # Check again after potential rescan
            if rel_path in self.files:
                self.mappings[rfid_tag] = rel_path
                self._mark_database_changed()
                return True
            return False

        except Exception as e:
            logger.error(f"Error adding mapping: {e}")
            return False

    def remove_mapping(self, rfid_tag: str) -> bool:
        """Remove RFID mapping."""
        try:
            if rfid_tag in self.mappings:
                del self.mappings[rfid_tag]
                self._mark_database_changed()
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing mapping: {e}")
            return False

    def get_mapped_file(self, rfid_tag: str) -> Optional[Path]:
        """Get absolute path for RFID-mapped file."""
        try:
            if rfid_tag in self.mappings:
                rel_path = self.mappings[rfid_tag]
                return self.to_absolute_path(rel_path)
            return None
        except Exception as e:
            logger.error(f"Error getting mapped file: {e}")
            return None

    def update_position(self, file_path: Union[str, Path], position_ms: int) -> None:
        """Update last played position for a file."""
        try:
            # Convert absolute path to relative
            rel_path = self.to_relative_path(file_path)

            if rel_path in self.files:
                self.files[rel_path]['last_position'] = position_ms
                self._mark_database_changed()
        except Exception as e:
            logger.error(f"Error updating position: {e}")

    def get_metadata(self, file_path: Union[str, Path]) -> Optional[Dict]:
        """Get metadata for a file."""
        try:
            rel_path = self.to_relative_path(file_path)
            file_info = self.files.get(rel_path)
            return file_info.get('metadata') if file_info else None
        except Exception as e:
            logger.error(f"Error getting metadata: {e}")
            return None

    def get_unmapped_files(self) -> List[Path]:
        """Get list of music files that aren't mapped to any RFID tag."""
        try:
            # Get set of all currently mapped relative paths
            mapped_paths = set(self.mappings.values())

            # Get all files that are in our database but not mapped
            unmapped = [self.to_absolute_path(rel_path) 
                    for rel_path in self.files.keys() 
                    if rel_path not in mapped_paths]

            logger.info(f"Found {len(unmapped)} unmapped files")
            return sorted(unmapped)

        except Exception as e:
            logger.error(f"Error getting unmapped files: {e}")
            return []

    def cleanup(self) -> None:
        """Clean up resources"""
        logger.info("Starting mapping manager cleanup...")

        try:
            # Cancel any pending save timer
            if self._save_database_timer and self._save_database_timer.is_alive():
                logger.info("Cancelling pending save timer")
                self._save_database_timer.cancel()
                self._save_database_timer = None

            # Force final save to disk
            logger.info("Performing final database save")
            save_success = self._save_database_to_disk(force_save=True)
            if not save_success:
                logger.error("Failed to save database during cleanup")

        except Exception as e:
            logger.error(f"Error during mapping manager cleanup: {e}")
            raise  # Re-raise to ensure calling code knows cleanup failed

        finally:
            logger.info("Mapping manager cleanup complete")