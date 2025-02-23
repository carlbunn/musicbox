import vlc
from typing import Optional, Dict
from src.utils.logger import get_logger
import time
from pathlib import Path
from src.core.mapping_manager import MappingManager

logger = get_logger(__name__)

class AudioPlayer:
    """
    Enhanced audio player implementation using VLC.
    Provides playback status and metadata information.
    """
    def __init__(self,
                 mapping_manager: MappingManager,
                 near_end_threshold: float = 3.0,
                 playback_init_delay: float = 0.1,
                 player_args: list = None):
        self._current_instance: Optional[vlc.Instance] = None
        self._current_player: Optional[vlc.MediaPlayer] = None
        self._current_media: Optional[vlc.Media] = None
        self._player_args = player_args or []
        self._near_end_threshold = near_end_threshold
        self._playback_init_delay = playback_init_delay
        self._is_playing = False
        self._metadata: Dict = {}
        self._current_file: Optional[str] = None
        self._mapping_manager = mapping_manager

        logger.info("AudioPlayer initialized")
    
    def _create_new_player(self, file_path: str) -> None:
        """Create and store VLC player with appropriate configuration."""
        
        # Clean up existing instance if any
        self._cleanup_current_player()

        self._current_instance = vlc.Instance(*self._player_args)
    
        # Create new player and media
        self._current_player = self._current_instance.media_player_new()
        self._current_media = self._current_instance.media_new(str(file_path))
        self._current_player.set_media(self._current_media)

        self._current_file = file_path

        # Parse media information and metadata
        self._metadata = self._mapping_manager.get_metadata(file_path)

        logger.debug("Created new VLC instance")

        """ return vlc.Instance(
            '--aout=alsa',
            '--alsa-audio-device=bluetooth',
            '--network-caching=1000',
            '--live-caching=1000',
            '--file-caching=1000',
            '--clock-jitter=0',
            '--clock-synchro=0'
        ) """

    def _save_current_position(self) -> bool:
        """
        Save the current position for later resumption.
        If track is at or near the end, reset position to start.
        """
        if not self._current_player or not self._current_file:
            return False
        
        position = self._current_player.get_time()
        duration = self._current_player.get_length()

        # If we're within 3 seconds of the end, reset to start
        if duration > 0 and (duration - position) <= (self._near_end_threshold * 1000):
            position = 0
            logger.debug(f"Track was near end, resetting position to start for {self._current_file}")

        self._mapping_manager.update_position(self._current_file, position)
        logger.debug(f"Saved position {position}ms for {self._current_file}")

    def seek_to_position(self, position_ms: int) -> bool:
        """
        Seek to a specific position in milliseconds.
        Handles potential VLC seeking errors by rebuilding player if necessary.
        """
        try:
            if not self._current_player or not self._current_file:
                return False

            # Ensure position is an integer and within bounds
            position_ms = int(position_ms)
            duration = self._current_player.get_length()
            position_ms = max(0, min(position_ms, duration))

            # Try normal seek first
            result = self._current_player.set_time(position_ms)

            # If seek failed or produced an error, try rebuilding the player
            if result != 0 or self._current_player.get_state() == vlc.State.Error:
                logger.warning("Seek failed, attempting to rebuild player")

                # Remember current state
                was_playing = self._is_playing

                # Create new instance and player
                self._create_new_player(self._current_file)

                # Start playback
                self._current_player.play()
                time.sleep(self._playback_init_delay)  # Brief wait for media to initialize

                # Seek in new player
                self._current_player.set_time(position_ms)

                # If we weren't playing before, pause the new player
                if not was_playing:
                    time.sleep(self._playback_init_delay)  # Wait for seek to complete
                    self._current_player.pause()

                logger.info("Player rebuilt successfully after seek error")
                return True

            return True

        except Exception as e:
            logger.error(f"Error seeking: {str(e)}")
            return False

    def seek_relative(self, offset_ms: int) -> bool:
        """Seek relative to current position with error handling."""
        try:
            if not self._current_player:
                return False

            current_pos = self._current_player.get_time()
            return self.seek_to_position(current_pos + offset_ms)
            
        except Exception as e:
            logger.error(f"Error in relative seek: {str(e)}")
            return False

    def skip_forward(self, ms: int = 15000) -> bool:
        """Skip forward by specified milliseconds (default 15s)."""
        return self.seek_relative(ms)

    def skip_backward(self, ms: int = 15000) -> bool:
        """Skip backward by specified milliseconds (default 15s)."""
        return self.seek_relative(-ms)

    def play(self, file_path: str) -> bool:
        """Play audio file from given path."""
        try:
            # Convert to Path and resolve to absolute
            file_path = Path(file_path).resolve()

            # Save position of current track before switching
            if self._current_file:
                self._save_current_position()

            logger.info(f"Creating new player for: {file_path}")

            # Create new player
            self._create_new_player(file_path)

            play_result = self._current_player.play()
            logger.info(f"VLC play() result: {play_result}")

            self._is_playing = True

            # Restore last position if available
            if self._metadata and self._metadata.get('last_position', 0) > 0:
                time.sleep(self._playback_init_delay)  # Brief wait for playback to start
                self._current_player.set_time(self._metadata.get('last_position', 0))

            logger.info(f"Playing: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error playing file {file_path}: {str(e)}")
            return False

    def stop(self) -> None:
        """Stop playback and save position."""
        try:
            self._save_current_position()
            
            if self._current_player:
                self._current_player.stop()
                self._is_playing = False
                self._current_file = None
                logger.info("Playback stopped")
        except Exception as e:
            logger.error(f"Error stopping playback: {str(e)}")

    def pause(self) -> None:
        """Pause current playback and save position."""
        try:
            self._save_current_position()
            
            if self._current_player:
                self._current_player.pause()
                self._is_playing = False
                logger.info("Playback paused")
        except Exception as e:
            logger.error(f"Error pausing playback: {str(e)}")

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
            # Consider a track ended if it's within 3 seconds of the end
            position = self._current_player.get_time()
            duration = self._current_player.get_length()
            return duration > 0 and (duration - position) <= (self._near_end_threshold * 1000)
        return False

    def get_status(self) -> Dict:
        """Get current playback status and track information."""
        status = {
            'is_playing': self.is_playing,
            'has_ended': self.has_ended,
            'position_ms': 0,
            'duration_ms': 0,
            'position_percent': 0,
            'progress': '0%',
            'time': '00:00/00:00',
            'volume': 0,
            'state': 'Stopped',
            'metadata': {},
            'can_seek': False,
            'compact': {}
        }

        if self._current_player:
            duration = self._current_player.get_length()
            position = self._current_player.get_time()
            position_percent = int((position / duration * 100) if duration > 0 else 0)

            status.update({
                'position_ms': position,
                'duration_ms': duration,
                'position_percent': position_percent,
                'progress': f"{position_percent}%",
                'time': f"{self.format_time(position)}/{self.format_time(duration)}",
                'volume': self._current_player.audio_get_volume(),
                'state': "Playing" if self.is_playing else "Stopped",
                'can_seek': True,
                'metadata': self._metadata or {}
            })

            status['compact'] = {
                'line1': self._metadata.get('title', '')[:20],  # Limit to 20 characters
                'line2': f"{self._metadata.get('artist', '')[:12]} {status['time']}"  # Combine artist and time
            }

        return status

    def set_volume(self, volume: int) -> None:
        """Set volume level (0-100)."""
        if self._current_player:
            self._current_player.audio_set_volume(max(0, min(100, volume)))
            logger.info(f"Volume set to {volume}")

    def format_time(self, milliseconds: int) -> str:
        """Format time in seconds to MM:SS format."""
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def _cleanup_current_player(self) -> None:
        """Clean up current player and media resources."""
        if self._current_player:
            self._current_player.stop()
            self._current_player.release()
            self._current_player = None

        if self._current_media:
            self._current_media.release()
            self._current_media = None

        if self._current_instance:
            self._current_instance.release()

        self._metadata = {}
        self._is_playing = False
        self._current_file = None

    def cleanup(self) -> None:
        """Clean up resources"""
        logger.info("Starting audio player cleanup...")
        
        try:
            # Save current position before cleanup
            if self._current_file:
                self._save_current_position()

            # Clean up player and media
            self._cleanup_current_player()
            
        except Exception as e:
            logger.error(f"Error during audio player cleanup: {e}")

        finally:
            logger.info("Audio player cleanup complete")