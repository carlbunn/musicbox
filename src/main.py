import sys
import os

# Add the project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.audio_player import AudioPlayer
from src.core.mapping_manager import MappingManager
from src.config.settings import Settings
from src.api.server import APIServer
from src.utils.logger import get_logger
import time
import signal
import threading
from queue import Queue, Empty

# Change to the project root directory
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = get_logger(__name__)
logger.info("Main module loading...")

class MusicBox:
    def __init__(self):
        self.settings = Settings()

        # Initialise mapping manager with music directory
        music_dir = self.settings.get('music_directory', 'music')
        mapping_file = self.settings.get('mapping_file', 'music')
        self.mapping_manager = MappingManager(mapping_file  = mapping_file,
                                              music_dir     = music_dir)
        self.audio_player = AudioPlayer(mapping_manager     = self.mapping_manager,
                                        near_end_threshold  = self.settings.get('audio_player', {}).get('near_end_threshold', 0),
                                        playback_init_delay = self.settings.get('audio_player', {}).get('playback_init_delay', 0),
                                        player_args         = self.settings.get('audio_player', {}).get('player_args', 0))

        # Use RC522Reader on Pi, MockRFIDReader for development
        if self._is_running_on_pi():
            logger.info("Running an rfc522 rfid reader...")
            from src.core.rc522_reader import RC522Reader
            self.rfid_reader = RC522Reader()
        else:
            logger.info("Running a mock rfid reader...")
            from src.core.mock_rfid_reader import MockRFIDReader
            self.rfid_reader = MockRFIDReader()
            self._setup_test_mappings()

        # Initialise Spotify downloader if enabled
        if self.settings.get('spotify', {}).get('enabled', True):
            from src.core.spotify_downloader import SpotifyDownloader
            self.spotify_downloader = SpotifyDownloader(output_directory=music_dir)
            logger.info("Spotify downloader initialised")

        # Initialise API server
        self.api_server = APIServer(self,
                                    host=self.settings.get('api', {}).get('host', '0.0.0.0'),
                                    port=self.settings.get('api', {}).get('port', 8000),
                                    debug=self.settings.get('api', {}).get('debug', False))

        # Track currently playing tag and state
        self._current_playing_tag = None

        # RFID Thread and queue for tag handling
        self._tag_queue = Queue()
        self._polling_interval = max(0.5, min(5.0, self.settings.get('rfid', {}).get('slow_polling', 2.0)))            # Base interval for RFID polling
        self._busy_interval = max(0.1, min(1.0, self.settings.get('rfid', {}).get('fast_polling', 0.1)))               # Faster interval when activity detected
        self._activity_timeout = max(5.0, min(30.0, self.settings.get('rfid', {}).get('transition_polling', 10.0)))     # Transition time between fast & slow
        self._current_interval = self._polling_interval
        self._last_activity = 0
        self._reader_thread = None

        # Check main loop interval
        self._main_loop_interval = self.settings.get('main_loop_interval', '0.1')

        # Graceful shutdown handler
        self._shutdown_requested = False

        logger.info("MusicBox initialised")

    def _rfid_polling_loop(self) -> None:
        """Dedicated thread for RFID polling."""
        while not self._shutdown_requested:
            try:
                tag_id = self.rfid_reader.read_tag()
                if tag_id:
                    self._tag_queue.put(tag_id)
                    self._last_activity = time.time()
                    self._current_interval = self._busy_interval
                elif time.time() - self._last_activity > self._activity_timeout:
                    self._current_interval = self._polling_interval

                time.sleep(self._current_interval)

            except Exception as e:
                logger.error(f"Error in RFID polling loop: {str(e)}")
                time.sleep(1)  # Prevent tight error loop

    def _is_running_on_pi(self) -> bool:
        """Check if we're running on a Raspberry Pi."""
        try:
            with open('/sys/firmware/devicetree/base/model', 'r') as m:
                return 'raspberry pi' in m.read().lower()
        except:
            return False

    def _setup_test_mappings(self):
        """Set up some default mappings for keyboard-simulated RFID tags."""
        test_mappings = {
            'MOCK_TAG_1': 'song1.mp3',
            'MOCK_TAG_2': 'song2.mp3',
            'MOCK_TAG_3': 'song3.mp3',
            'MOCK_TAG_4': 'song4.mp3'
        }

        # Add each test mapping
        for tag, song in test_mappings.items():
            if not self.mapping_manager.get_mapped_file(tag):  # Only add if not already mapped
                self.mapping_manager.add_mapping(tag, song)
                logger.info(f"Added test mapping: {tag} -> {song}")

    def handle_tag(self, tag_id: str) -> bool:
        """
        Handle a scanned RFID tag with improved pause/play logic.
        
        Args:
            tag_id: The ID of the scanned tag
            
        Returns:
            bool: True if tag was handled successfully, False otherwise
        """
        try:
            # Get the mapped file for this tag
            file_path = self.mapping_manager.get_mapped_file(tag_id)
            if not file_path:
                logger.info(f"No mapping found for tag: {tag_id}")
                return False

            # Case 1: Same tag as currently playing/paused
            if tag_id == self._current_playing_tag:
                # Check if track has ended
                if self.audio_player.has_ended:
                    logger.info(f"Track ended, starting playback again for tag: {tag_id}")
                    if self.audio_player.play(file_path):
                        info = self.audio_player.get_status().get('metadata', {})
                        logger.info(f"Restarting: {info.get('title', '')} by {info.get('artist', '')}")
                        return True
                    return False

                # Track is still playing
                if self.audio_player.is_playing:
                    self.audio_player.pause()
                    info = self.audio_player.get_status().get('metadata', {})
                    logger.info(f"Pausing: {info.get('title', '')} by {info.get('artist', '')}")
                else:
                    self.audio_player.resume()
                    info = self.audio_player.get_status().get('metadata', {})
                    logger.info(f"Resuming: {info.get('title', '')} by {info.get('artist', '')}")

                return True

            # Case 2: Different tag or no current tag
            # Stop any current playback
            if self.audio_player.is_playing:
                self.audio_player.stop()

            # Start playing new tag
            logger.info(f"Playing new tag: {tag_id}, file: {file_path}")
            if self.audio_player.play(file_path):
                self._current_playing_tag = tag_id
                info = self.audio_player.get_status().get('metadata', {})
                logger.info(f"Now Playing: {info.get('title', '')} by {info.get('artist', '')}")
                return True

            logger.error(f"Failed to play file: {file_path}")
            self._current_playing_tag = None
            return False

        except Exception as e:
            logger.error(f"Error handling tag {tag_id}: {str(e)}")
            # Reset state on error
            self._current_playing_tag = None
            return False

    def handle_learning_mode(self) -> None:
        """Handle learning mode in the main loop."""
        logger.info("Learning mode not implemented")

    def run(self):
        """Main program loop."""
        try:
            if not self.rfid_reader.initialise():
                logger.error("Failed to initialise RFID reader")
                return
            
            # Start RFID polling thread
            self._reader_thread = threading.Thread(
                target=self._rfid_polling_loop,
                name="RFID-Polling",
                daemon=True
            )
            self._reader_thread.start()

            # Start API server (already threaded)
            self.api_server.start()
            logger.info("API server started")

            # Validate mappings before starting
            issues = self.mapping_manager.validate_mappings()
            if any(issues.values()):
                logger.warning("Mapping validation found issues:")
                for category, items in issues.items():
                    if items:
                        logger.warning(f"{category}: {items}")

            track_end_logged = True

            logger.info("Starting main loop - waiting for cards...")

            while not self._shutdown_requested:
                tag_id = None 

                try:
                    # Non-blocking check for new tags
                    try:
                        tag_id = self._tag_queue.get_nowait()

                        # Handle special commands first
                        if tag_id == 'QUIT':
                            logger.info("Received quit command")
                            self._shutdown_requested = True
                        elif tag_id == 'L':
                            self.handle_learning_mode()
                        # Only process regular tags if not a special command
                        elif tag_id:
                            if self.handle_tag(tag_id):
                                track_end_logged = False

                    except Empty:
                        pass

                    
                    if self.audio_player.has_ended and not track_end_logged:
                        info = self.audio_player.get_status().get('metadata', {})
                        logger.info(f"Track finished playing: {info.get('title', '')} by {info.get('artist', '')}")
                        self._current_playing_tag = None
                        track_end_logged = True

                    time.sleep(self._main_loop_interval)

                except Exception as e:
                    logger.error(f"Error in main loop iteration: {str(e)}")

        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Cleanup all resources in a specific order."""
        cleanup_errors = []
        
        # Stop RFID reading first to prevent new events
        if self._reader_thread and self._reader_thread.is_alive():
            try:
                logger.info("Stopping RFID polling thread...")
                self._shutdown_requested = True
                self._reader_thread.join(timeout=2.0)  # Wait up to 2 seconds for thread to finish
            except Exception as e:
                cleanup_errors.append(f"RFID reader cleanup failed: {str(e)}")

        # Stop API server
        if hasattr(self, 'api_server'):
            try:
                logger.info("Stopping API server...")
                self.api_server.cleanup()
            except Exception as e:
                cleanup_errors.append(f"API server cleanup failed: {str(e)}")

        # Stop audio playback
        if hasattr(self, 'audio_player'):
            try:
                logger.info("Stopping audio player...")
                self.audio_player.cleanup()
            except Exception as e:
                cleanup_errors.append(f"Audio player cleanup failed: {str(e)}")

        # Save any pending mappings
        if hasattr(self, 'mapping_manager'):
            try:
                logger.info("Stopping mapping manager...")
                self.mapping_manager.cleanup()
            except Exception as e:
                cleanup_errors.append(f"Mapping manager cleanup failed: {str(e)}")

        # Stop Spotify downloader last since it's not critical
        if hasattr(self, 'spotify_downloader'):
            try:
                logger.info("Stopping Spotify downloader...")
                self.spotify_downloader.cleanup()
            except Exception as e:
                cleanup_errors.append(f"Spotify downloader cleanup failed: {str(e)}")

        if cleanup_errors:
            error_msg = "\n".join(cleanup_errors)
            logger.error(f"Cleanup completed with errors:\n{error_msg}")
            raise Exception(f"Cleanup failed with multiple errors:\n{error_msg}")
        else:
            logger.info("MusicBox cleanup completed successfully")

class GracefulShutdown:
    def __init__(self, music_box):
        self.music_box = music_box
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        signal.signal(signal.SIGINT, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        """Set shutdown flag and let main loop handle cleanup."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.music_box._shutdown_requested = True

if __name__ == "__main__":
    try:
        logger.info("Creating MusicBox instance...")
        music_box = MusicBox()
        shutdown_handler = GracefulShutdown(music_box)
        logger.info("Starting MusicBox...")
        music_box.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
