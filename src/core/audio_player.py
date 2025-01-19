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
    def __init__(self, mapping_manager):
        self._current_player: Optional[vlc.MediaPlayer] = None
        self._current_media: Optional[vlc.Media] = None
        self._is_playing = False
        self._metadata: Dict = {}
        self._current_file: Optional[str] = None
        self._mapping_manager = mapping_manager
        logger.info("AudioPlayer initialized")

    def _createVLCInstance():
        return vlc.Instance('--aout=alsa', '--alsa-audio-device=bluetooth')

    def _save_current_position(self) -> None:
        """
        Save the current position for later resumption.
        If track is at or near the end, reset position to start.
        """
        if self._current_player and self._current_file:
            position = self._current_player.get_time()
            duration = self._current_player.get_length()
            
            # If we're within 3 seconds of the end, reset to start
            if duration > 0 and (duration - position) <= 3000:
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
                instance = self._createVLCInstance()
                new_player = instance.media_player_new()
                new_media = instance.media_new(str(self._current_file))
                new_player.set_media(new_media)
                
                # Start playback
                new_player.play()
                time.sleep(0.1)  # Brief wait for media to initialize
                
                # Seek in new player
                new_player.set_time(position_ms)
                
                # If we weren't playing before, pause the new player
                if not was_playing:
                    time.sleep(0.1)  # Wait for seek to complete
                    new_player.pause()
                
                # Clean up old player
                if self._current_player:
                    self._current_player.stop()
                    self._current_player.release()
                
                # Update references
                self._current_player = new_player
                self._current_media = new_media
                
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

    def get_detailed_status(self) -> Dict:
        """Get detailed playback status including time information."""
        status = {
            'is_playing': self.is_playing,
            'has_ended': self.has_ended,
            'position_ms': 0,
            'duration_ms': 0,
            'position_percent': 0,
            'volume': 0,
            'metadata': self._metadata,
            'can_seek': False
        }

        if self._current_player:
            duration = self._current_player.get_length()
            position = self._current_player.get_time()
            
            status.update({
                'position_ms': position,
                'duration_ms': duration,
                'position_percent': int((position / duration * 100) if duration > 0 else 0),
                'volume': self._current_player.audio_get_volume(),
                'can_seek': True
            })

        return status

    def play(self, file_path: str) -> bool:
        """Play audio file from given path."""
        try:
            # Save position of current track before switching
            if self._current_file and self._current_file != file_path:
                self._save_current_position()
            
            if self._current_player:
                self._current_player.stop()
                self._current_player.release()
                self._current_player = None
                self._current_media = None

            # Create new instances
            instance = self._createVLCInstance()
            #self._current_player = vlc.MediaPlayer(file_path)
            self._current_player = instance.media_player_new()
            #self._current_media = self._current_player.get_media()
            self._current_media = instance.media_new(file_path)
            self._current_player.set_media(self._current_media)
            
            # Parse media information and metadata
            if self._current_media:
                self._current_media.parse()
                self._metadata = self._extract_metadata(file_path)
            
            self._current_player.play()
            self._is_playing = True
            self._current_file = file_path

            # Restore last position if available
            relative_path = str(Path(file_path).relative_to(self._mapping_manager.music_dir))
            for mapping in self._mapping_manager.mappings.values():
                if mapping.get('path') == relative_path:
                    last_position = mapping.get('metadata', {}).get('last_position', 0)
                    if last_position > 0:
                        # Wait briefly for playback to start before seeking
                        time.sleep(0.1)
                        self._current_player.set_time(last_position)
                    break

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
            return duration > 0 and (duration - position) <= 3000
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