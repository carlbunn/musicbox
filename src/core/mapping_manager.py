from pathlib import Path
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
                'last_position': 0,  # Initialize position tracking
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

            # Extract metadata and create mapping
            metadata = self._extract_metadata(music_path)
            relative_path = str(music_path.relative_to(self.music_dir))
            
            self.mappings[rfid_tag] = {
                'path': relative_path,
                'metadata': metadata
            }
            
            self._save_mappings()
            logger.info(f"Added mapping with metadata: {rfid_tag} -> {relative_path}")
            return True

        except Exception as e:
            logger.error(f"Error adding mapping: {str(e)}")
            return False

    def get_music_file(self, rfid_tag: str) -> Optional[Dict]:
        """Get file info including path and metadata."""
        try:
            if rfid_tag in self.mappings:
                mapping = self.mappings[rfid_tag]
                music_path = self.music_dir / mapping['path']
                if music_path.exists():
                    return {
                        'path': music_path,
                        'metadata': mapping.get('metadata', {
                            'title': music_path.stem,
                            'last_position': 0
                        })
                    }
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
    
    def update_position(self, file_path: str, position_ms: int) -> None:
        """Update the last played position for a file."""
        try:
            # Find the mapping entry for this file
            relative_path = str(Path(file_path).relative_to(self.music_dir))
            for tag_id, mapping in self.mappings.items():
                if mapping.get('path') == relative_path:
                    if 'metadata' not in mapping:
                        mapping['metadata'] = {}
                    mapping['metadata']['last_position'] = position_ms
                    self._save_mappings()
                    break
        except Exception as e:
            logger.error(f"Error updating position: {str(e)}")
    
    def get_songs(self) -> List[Dict]:
        """Get all songs with their metadata and mapping status."""
        try:
            songs = []
            # Get all music files
            for ext in ['.mp3', '.wav', '.flac', '.ogg']:
                for file_path in self.music_dir.glob(f"*{ext}"):
                    relative_path = str(file_path.relative_to(self.music_dir))
                    
                    # Find if file is mapped
                    mapped_to = None
                    metadata = None
                    for tag_id, mapping in self.mappings.items():
                        if mapping.get('path') == relative_path:
                            mapped_to = tag_id
                            metadata = mapping.get('metadata', {})
                            break
                    
                    # If not mapped, extract metadata
                    if not metadata:
                        metadata = self._extract_metadata(file_path)
                    
                    songs.append({
                        'filename': file_path.name,
                        'path': relative_path,
                        'mapped_to': mapped_to,
                        'title': metadata.get('title', file_path.stem),
                        'artist': metadata.get('artist'),
                        'album': metadata.get('album'),
                        'last_position': metadata.get('last_position', 0),
                        'size': file_path.stat().st_size,
                        'modified': file_path.stat().st_mtime
                    })
            
            return sorted(songs, key=lambda x: x['filename'].lower())
            
        except Exception as e:
            logger.error(f"Error getting songs: {str(e)}")
            return []