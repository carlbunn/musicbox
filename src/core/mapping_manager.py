from pathlib import Path
import os
import json
import vlc
from typing import Dict, Optional, List
from src.utils.logger import get_logger

logger = get_logger(__name__)

class MappingManager:
    """
    Manages mappings between RFID tags and music files.
    Handles persistence and validation of mappings.
    """
    def __init__(self, mapping_file: str = "config/mappings.json", music_dir: str = "music"):
        # Convert paths to absolute using Path
        if not Path(mapping_file).is_absolute():
            self.mapping_file = Path(__file__).parent.parent.parent / mapping_file
        else:
            self.mapping_file = Path(mapping_file)
            
        if not Path(music_dir).is_absolute():
            self.music_dir = Path(__file__).parent.parent.parent / music_dir
        else:
            self.music_dir = Path(music_dir)
            
        logger.info(f"Initialising MappingManager with music directory: {self.music_dir}")
        self.mappings: Dict[str, str] = {}
        
        # Ensure music directory exists
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self._load_mappings()
        self._scan_music_directory()

    def _load_mappings(self) -> None:
        """Load mappings from file, create if doesn't exist."""
        try:
            logger.info(f"Attempting to load mappings from: {self.mapping_file}")
            
            if self.mapping_file.exists():
                logger.info("Mappings file exists, loading content...")
                with open(self.mapping_file, 'r') as f:
                    data = json.load(f)
                    self.mappings = data.get('rfid_mappings', {})
                    self.files = data.get('files', {})
                logger.info(f"Loaded {len(self.mappings)} mappings and {len(self.files)} file records")
            else:
                logger.info("Mappings file does not exist, creating new one")
                self.mappings = {}
                self.files = {}
                self._save_mappings()
                logger.info("Created new mappings file")
                
        except Exception as e:
            logger.error(f"Error loading mappings: {str(e)}")
            self.mappings = {}
            self.files = {}

    def _save_mappings(self) -> None:
        """Save current mappings to file using atomic write."""
        try:
            # Create temp file in same directory
            temp_file = self.mapping_file.with_suffix('.tmp')
            data = {
                'rfid_mappings': self.mappings,
                'files': self.files
            }
            
            # Write to temp file first
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()  # Ensure all data is written
                os.fsync(f.fileno())  # Force write to disk
                
            # Atomic replace
            os.replace(temp_file, self.mapping_file)
            logger.info("Mappings saved successfully")
            
        except Exception as e:
            logger.error(f"Error saving mappings: {str(e)}")
            if temp_file.exists():
                temp_file.unlink()  # Clean up temp file

    def _extract_metadata(self, file_path: Path) -> Dict:
        """Extract metadata from audio file."""
        try:
            media = vlc.Media(str(file_path))
            media.parse()
            
            metadata = {
                'title': media.get_meta(vlc.Meta.Title),
                'artist': media.get_meta(vlc.Meta.Artist),
                'album': media.get_meta(vlc.Meta.Album),
                'filename': file_path.name,
                'last_position': 0,  # Initialise position tracking
            }
            
            # Use filename as title if no metadata found
            if not metadata['title']:
                metadata['title'] = file_path.stem
                
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting metadata from {file_path}: {str(e)}")
            return {
                'title': file_path.stem,
                'filename': file_path.name,
                'last_position': 0
            }

    def _scan_music_directory(self) -> None:
        """Scan music directory and update file records."""
        try:
            # Get all music files
            music_files = []
            for ext in ['.mp3', '.wav', '.flac', '.ogg']:
                music_files.extend([f for f in self.music_dir.glob(f"*{ext}") 
                    if not f.name.startswith('.')])

            # Convert to relative paths for storage
            current_files = {str(f.relative_to(self.music_dir)): f for f in music_files}
            
            # Remove entries for files that no longer exist
            self.files = {path: data for path, data in self.files.items() 
                    if path in current_files}

            # Add or update entries for current files
            for rel_path, abs_path in current_files.items():
                if rel_path not in self.files:
                    metadata = self._extract_metadata(abs_path)
                    self.files[rel_path] = {
                        'metadata': metadata,
                        'last_position': 0,
                        'last_played': None
                    }
            
            # Clean up mappings for missing files
            self.mappings = {tag: mapping for tag, mapping in self.mappings.items()
                           if mapping['path'] in self.files}
            
            self._save_mappings()
            logger.info(f"Music directory scan complete. Found {len(current_files)} files")
            
        except Exception as e:
            logger.error(f"Error scanning music directory: {str(e)}")

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
        """Add or update an RFID mapping."""
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

            # Get relative path
            relative_path = str(music_path.relative_to(self.music_dir))
            
            # Ensure file is in our files dict
            if relative_path not in self.files:
                self._scan_music_directory()
            
            self.mappings[rfid_tag] = {
                'path': relative_path
            }
            
            self._save_mappings()
            logger.info(f"Added mapping: {rfid_tag} -> {relative_path}")
            return True

        except Exception as e:
            logger.error(f"Error adding mapping: {str(e)}")
            return False

    def get_music_file(self, rfid_tag: str) -> Optional[Dict]:
        """Get file info for an RFID-mapped file."""
        try:
            if rfid_tag in self.mappings:
                mapping = self.mappings[rfid_tag]
                return self.get_file_info(mapping['path'])
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
    
    def update_position(self, file_path: str, position_ms: int) -> None:
        """Update the last played position for a file."""
        try:
            # Find the mapping entry for this file
            file_path = Path(file_path).resolve()
            relative_path = str(Path(file_path).relative_to(self.music_dir))

            if relative_path in self.files:
                self.files[relative_path]['last_position'] = position_ms
                self._save_mappings()

        except Exception as e:
            logger.error(f"Error updating position: {str(e)}")
    
    def get_file_info(self, file_path: str) -> Optional[Dict]:
        """Get file info for any file, mapped or not."""
        try:
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = self.music_dir / file_path
            
            relative_path = str(file_path.relative_to(self.music_dir))
            
            if relative_path in self.files:
                return {
                    'path': file_path,
                    **self.files[relative_path]
                }
            return None
            
        except Exception as e:
            logger.error(f"Error getting file info: {str(e)}")
            return None