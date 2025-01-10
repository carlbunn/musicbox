import vlc
from typing import Optional, Dict
from src.utils.logger import get_logger
import time
from pathlib import Path

logger = get_logger(__name__)

class AudioPlayer:
    """
    Enhanced audio player implementation using VLC.
    Provides playback status and metadata information.
    """
    def __init__(self):
        self._current_player: Optional[vlc.MediaPlayer] = None
        self._current_media: Optional[vlc.Media] = None
        self._is_playing = False
        self._metadata: Dict = {}
        logger.info("AudioPlayer initialized")

    def play(self, file_path: str) -> bool:
        """Play audio file from given path."""
        try:
            if self._current_player:
                self._current_player.stop()
                self._current_player = None
                self._current_media = None

            # Create new instances
            self._current_player = vlc.MediaPlayer(file_path)
            self._current_media = self._current_player.get_media()
            
            # Parse media information and metadata
            if self._current_media:
                self._current_media.parse()
                self._metadata = self._extract_metadata(file_path)
            
            self._current_player.play()
            self._is_playing = True
            logger.info(f"Playing: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error playing file {file_path}: {str(e)}")
            return False

    def _extract_metadata(self, file_path: str) -> Dict:
        """Extract metadata from the media file."""
        metadata = {
            'title': None,
            'artist': None,
            'album': None,
            'duration': None,
            'filename': Path(file_path).stem  # Fallback to filename without extension
        }
        
        try:
            if self._current_media:
                # Try to get metadata from media
                metadata.update({
                    'title': self._current_media.get_meta(vlc.Meta.Title),
                    'artist': self._current_media.get_meta(vlc.Meta.Artist),
                    'album': self._current_media.get_meta(vlc.Meta.Album),
                    'duration': self._current_media.get_duration() // 1000  # Convert to seconds
                })
                
                # If no title found, use filename
                if not metadata['title']:
                    metadata['title'] = metadata['filename']
                
                logger.info(f"Metadata extracted: {metadata}")
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
        
        return metadata

    def stop(self) -> None:
        """Stop current playback."""
        if self._current_player:
            self._current_player.stop()
            self._is_playing = False
            logger.info("Playback stopped")

    def pause(self) -> None:
        """Pause current playback."""
        if self._current_player:
            self._current_player.pause()
            self._is_playing = False
            logger.info("Playback paused")

    def resume(self) -> None:
        """Resume paused playback."""
        if self._current_player:
            self._current_player.play()
            self._is_playing = True
            logger.info("Playback resumed")

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        if self._current_player:
            state = self._current_player.get_state()
            self._is_playing = state == vlc.State.Playing
        return self._is_playing

    @property
    def has_ended(self) -> bool:
        """Check if the current track has ended."""
        if self._current_player:
            return self._current_player.get_state() == vlc.State.Ended
        return False

    def get_status(self) -> Dict:
        """Get current playback status and track information."""
        status = {
            'is_playing': self.is_playing,
            'has_ended': self.has_ended,
            'position': 0,
            'length': 0,
            'position_percent': 0,
            'volume': 0,
            'metadata': self._metadata
        }

        if self._current_player:
            length = self._current_player.get_length() / 1000
            position = self._current_player.get_time() / 1000
            
            status.update({
                'position': int(position),
                'length': int(length),
                'position_percent': int((position / length * 100) if length > 0 else 0),
                'volume': self._current_player.audio_get_volume(),
            })

        return status

    def set_volume(self, volume: int) -> None:
        """Set volume level (0-100)."""
        if self._current_player:
            self._current_player.audio_set_volume(max(0, min(100, volume)))
            logger.info(f"Volume set to {volume}")

    def format_time(self, seconds: int) -> str:
        """Format time in seconds to MM:SS format."""
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def get_display_info(self) -> Dict:
        """
        Get formatted display information suitable for small screens.
        Returns minimal information in an easy-to-display format.
        """
        status = self.get_status()
        metadata = status['metadata']
        
        display_info = {
            'title': metadata.get('title', 'Unknown Title'),
            'artist': metadata.get('artist', 'Unknown Artist'),
            'time': f"{self.format_time(status['position'])}/{self.format_time(status['length'])}",
            'progress': f"{status['position_percent']}%",
            'state': "Playing" if self.is_playing else "Stopped",
            'volume': f"{status['volume']}%"
        }
        
        # Create a compact representation for small displays
        display_info['compact'] = {
            'line1': display_info['title'][:20],  # Limit to 20 characters
            'line2': f"{display_info['artist'][:12]} {display_info['time']}"  # Combine artist and time
        }
        
        return display_info