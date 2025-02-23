from typing import Optional, List, Dict
import vlc
import time
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)

class VLCManager:
    """
    Manages VLC instance lifecycle and audio device selection.
    Implements fallback mechanisms and proper resource cleanup.
    """
    def __init__(self):
        self._instance: Optional[vlc.Instance] = None
        self._current_player: Optional[vlc.MediaPlayer] = None
        self._current_media: Optional[vlc.Media] = None
        self._audio_output = None
        self._retry_count = 0
        self._max_retries = 3
        self.initialize()

    def initialize(self) -> bool:
        """Initialize VLC with fallback options for audio output."""
        # Audio configuration options in order of preference
        audio_configs = [
            ['--aout=alsa', '--alsa-audio-device=bluetooth'],  # Bluetooth
            ['--aout=alsa', '--alsa-audio-device=default'],    # Default ALSA
            #['--aout=pulse'],                                  # PulseAudio
            ['--aout=alsa']                                    # Basic ALSA
        ]

        for config in audio_configs:
            try:
                logger.info(f"Attempting VLC initialization with config: {config}")
                if self._try_initialize(config):
                    self._audio_output = config
                    return True
            except Exception as e:
                logger.warning(f"Failed to initialize VLC with config {config}: {str(e)}")
                continue

        logger.error("Failed to initialize VLC with any audio configuration")
        return False

    def _try_initialize(self, config: List[str]) -> bool:
        """Attempt to initialize VLC with specific config."""
        try:
            # Cleanup any existing instance
            self.cleanup()

            # Create new instance
            self._instance = vlc.Instance(*config)
            
            # Test instance by creating a dummy player
            test_player = self._instance.media_player_new()
            
            # Try to set up audio output
            test_player.audio_output_device_enum()
            
            # Cleanup test player
            test_player.release()
            
            logger.info(f"Successfully initialized VLC with config: {config}")
            return True

        except Exception as e:
            logger.error(f"VLC initialization failed: {str(e)}")
            self.cleanup()
            return False

    def create_player(self, file_path: str) -> Optional[Dict]:
        """
        Create a new media player for the given file.
        Returns a dict containing player, media, and success status.
        """
        self._retry_count = 0
        while self._retry_count < self._max_retries:
            try:
                if not self._instance:
                    if not self.initialize():
                        return None

                # Clean up existing player/media
                if self._current_player:
                    self._current_player.stop()
                    self._current_player.release()
                if self._current_media:
                    self._current_media.release()

                # Create new player and media
                self._current_player = self._instance.media_player_new()
                self._current_media = self._instance.media_new(str(file_path))
                self._current_player.set_media(self._current_media)

                # Test audio output
                if not self._test_audio_output():
                    raise Exception("Audio output test failed")

                return {
                    'player': self._current_player,
                    'media': self._current_media,
                    'success': True
                }

            except Exception as e:
                logger.error(f"Error creating player (attempt {self._retry_count + 1}): {str(e)}")
                self._retry_count += 1
                time.sleep(1)  # Wait before retry
                
                # Try to reinitialize VLC on failure
                self.initialize()

        logger.error("Failed to create player after all retries")
        return None

    def _test_audio_output(self) -> bool:
        """Test if audio output is working."""
        try:
            if self._current_player:
                devices = self._current_player.audio_output_device_enum()
                if devices:
                    devices.release()
                return True
            return False
        except Exception as e:
            logger.error(f"Audio output test failed: {str(e)}")
            return False

    def cleanup(self) -> None:
        """Clean up VLC resources."""
        try:
            if self._current_player:
                self._current_player.stop()
                self._current_player.release()
                self._current_player = None

            if self._current_media:
                self._current_media.release()
                self._current_media = None

            if self._instance:
                self._instance.release()
                self._instance = None

        except Exception as e:
            logger.error(f"Error during VLC cleanup: {str(e)}")

    def __del__(self):
        """Ensure cleanup on object destruction."""
        self.cleanup()