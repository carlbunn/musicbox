import pygame
import os
import time
from typing import Optional, Dict
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from src.utils.logger import get_logger

logger = get_logger(__name__)

class AudioPlayerPygame:
    """
    Audio player implementation using pygame.mixer.
    Provides playback status and metadata information.
    """
    def __init__(self, mapping_manager):
        self._mapping_manager = mapping_manager
        self._current_file: Optional[str] = None
        self._metadata: Dict = {}
        self._is_paused = False
        self._start_time = 0
        self._pause_time = 0
        self._duration = 0
        
        # Set SDL to use ALSA audio driver and bluetooth device
        os.environ['SDL_AUDIODRIVER'] = 'alsa'
        os.environ['AUDIODEV'] = 'bluetooth'
        
        # Initialize pygame mixer
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
            logger.info("PygameAudioPlayer initialized with ALSA/Bluetooth")
        except Exception as e:
            logger.error(f"Failed to initialize with Bluetooth, falling back to default: {e}")
            # Try again with default audio
            os.environ.pop('AUDIODEV', None)
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
            
        logger.info("PygameAudioPlayer initialized")

    def play(self, file_path: str) -> bool:
        """Play audio file from given path."""
        try:
            # Convert to Path and resolve to absolute
            file_path = Path(file_path).resolve()

            # Save position of current track before switching
            if self._current_file:
                self._save_current_position()

            # Load and play the new file
            try:
                pygame.mixer.music.load(str(file_path))
                pygame.mixer.music.play()
                self._is_paused = False
                self._start_time = time.time()
                self._current_file = file_path
                
                # Get audio duration and metadata
                audio = MP3(file_path)
                self._duration = int(audio.info.length * 1000)  # Convert to ms
                self._metadata = self._extract_metadata(file_path)

                # Restore last position if available
                metadata = self._mapping_manager.get_metadata(file_path)
                if metadata and metadata.get('last_position', 0) > 0:
                    position_seconds = metadata['last_position'] / 1000.0
                    pygame.mixer.music.set_pos(position_seconds)
                    self._start_time = time.time() - position_seconds

                logger.info(f"Playing: {file_path}")
                return True

            except Exception as e:
                logger.error(f"Error loading audio file: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"Error playing file {file_path}: {str(e)}")
            return False

    def pause(self) -> None:
        """Pause current playback."""
        if not self._is_paused and pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self._is_paused = True
            self._pause_time = time.time()
            self._save_current_position()
            logger.info("Playback paused")

    def resume(self) -> None:
        """Resume paused playback."""
        if self._is_paused:
            pygame.mixer.music.unpause()
            self._is_paused = False
            self._start_time += time.time() - self._pause_time
            logger.info("Playback resumed")

    def stop(self) -> None:
        """Stop playback."""
        self._save_current_position()
        pygame.mixer.music.stop()
        self._is_paused = False
        self._current_file = None
        logger.info("Playback stopped")

    def _save_current_position(self) -> None:
        """Save the current position for later resumption."""
        if self._current_file:
            position = self.get_position_ms()
            
            # If we're within 3 seconds of the end, reset to start
            if self._duration > 0 and (self._duration - position) <= 3000:
                position = 0
                logger.debug(f"Track was near end, resetting position to start")
            
            self._mapping_manager.update_position(self._current_file, position)
            logger.debug(f"Saved position {position}ms for {self._current_file}")

    def _extract_metadata(self, file_path: Path) -> Dict:
        """Extract metadata from the audio file."""
        logger.debug(f"Extracting metadata from {file_path}")
        try:
            metadata = {
                'title': Path(file_path).stem,
                'artist': 'Unknown Artist',
                'album': 'Unknown Album',
                'filename': Path(file_path).name
            }

            # Try to get ID3 tags
            try:
                tags = EasyID3(str(file_path))
                if 'title' in tags:
                    metadata['title'] = tags['title'][0]
                if 'artist' in tags:
                    metadata['artist'] = tags['artist'][0]
                if 'album' in tags:
                    metadata['album'] = tags['album'][0]
            except:
                logger.debug(f"No ID3 tags found for {file_path}")

            return metadata

        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return metadata

    def get_position_ms(self) -> int:
        """Get current position in milliseconds."""
        if self._is_paused:
            return int((self._pause_time - self._start_time) * 1000)
        elif pygame.mixer.music.get_busy():
            return int((time.time() - self._start_time) * 1000)
        return 0

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        return pygame.mixer.music.get_busy() and not self._is_paused

    @property
    def has_ended(self) -> bool:
        """Check if the current track has ended."""
        if not self._current_file:
            return True
        position = self.get_position_ms()
        return self._duration > 0 and (self._duration - position) <= 3000

    def get_detailed_status(self) -> Dict:
        """Get detailed playback status."""
        position = self.get_position_ms()
        return {
            'is_playing': self.is_playing,
            'has_ended': self.has_ended,
            'position_ms': position,
            'duration_ms': self._duration,
            'position_percent': int((position / self._duration * 100) if self._duration > 0 else 0),
            'volume': pygame.mixer.music.get_volume() * 100,
            'metadata': self._metadata,
            'can_seek': False  # pygame.mixer doesn't support seeking
        }

    def get_display_info(self) -> Dict:
        """Get formatted display information."""
        status = self.get_detailed_status()
        metadata = status['metadata']
        
        display_info = {
            'title': metadata.get('title', 'Unknown Title'),
            'artist': metadata.get('artist', 'Unknown Artist'),
            'time': f"{self.format_time(status['position_ms']//1000)}/{self.format_time(self._duration//1000)}",
            'progress': f"{status['position_percent']}%",
            'state': "Playing" if self.is_playing else "Stopped",
            'volume': f"{int(status['volume'])}%"
        }
        
        display_info['compact'] = {
            'line1': display_info['title'][:20],
            'line2': f"{display_info['artist'][:12]} {display_info['time']}"
        }
        
        return display_info

    def format_time(self, seconds: int) -> str:
        """Format time in seconds to MM:SS format."""
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def set_volume(self, volume: int) -> None:
        """Set volume level (0-100)."""
        pygame.mixer.music.set_volume(max(0, min(100, volume)) / 100.0)
        logger.info(f"Volume set to {volume}")

    def cleanup(self):
        """Clean up resources."""
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            pygame.mixer.quit()
            pygame.quit()

            logger.info("Audio player cleanup completed")
        except Exception as e:
            logger.error(f"Error during audio player cleanup: {e}")