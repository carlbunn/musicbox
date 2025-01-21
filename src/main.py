import sys
import os

# Add the project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.audio_player import AudioPlayer
from src.core.file_manager import FileManager
from src.core.learning_mode import LearningMode
from src.core.mapping_manager import MappingManager
from src.config.settings import Settings
from src.api.server import APIServer
from src.utils.logger import get_logger
import time
import signal
from pathlib import Path
from typing import Dict

# Change to the project root directory
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = get_logger(__name__)
logger.info("Main module loading...")

class MusicBox:
    def __init__(self):
        self.settings = Settings()
        
        # Use RC522Reader on Pi, MockRFIDReader for development
        if self._is_running_on_pi():
            logger.info("Running an rfc522 rfid reader...")
            from src.core.rc522_reader import RC522Reader
            self.rfid_reader = RC522Reader()
        else:
            logger.info("Running a mock rfid reader...")
            from src.core.mock_rfid_reader import MockRFIDReader
            self.rfid_reader = MockRFIDReader()
        
        self.mapping_manager = MappingManager()
        self.audio_player = AudioPlayer(self.mapping_manager)
        
        # Initialise file manager with music directory
        music_dir = self.settings.get('music_directory', 'music')
        self.file_manager = FileManager(music_dir)

        # Initialise Spotify downloader if enabled
        if self.settings.get('spotify', {}).get('enabled', True):
            from src.core.spotify_downloader import SpotifyDownloader
            self.spotify_downloader = SpotifyDownloader(self.mapping_manager)
            logger.info("Spotify downloader initialised")

        # Initialise API server
        self.api_server = APIServer(self)
        
        logger.info("MusicBox initialised")

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
            if not self.mapping_manager.get_music_file(tag):  # Only add if not already mapped
                self.mapping_manager.add_mapping(tag, song)
                logger.info(f"Added test mapping: {tag} -> {song}")

    def handle_tag(self, tag_id: str) -> bool:
        """Handle a scanned RFID tag."""
        try:
            music_file = self.mapping_manager.get_music_file(tag_id)
            
            if not music_file:
                logger.info(f"No mapping found for tag: {tag_id}")
                return False
                
            logger.info(f"Found mapping for {tag_id}: {music_file}")
            if self.audio_player.play(str(music_file)):
                info = self.audio_player.get_display_info()
                logger.info(f"Playing: {info['title']} by {info['artist']}")
                return True
            else:
                logger.error(f"Failed to play file: {music_file}")
                return False
            
        except Exception as e:
            logger.error(f"Error handling tag {tag_id}: {str(e)}")
            return False

    def handle_learning_mode(self) -> None:
        """Handle learning mode in the main loop."""
        self.learning_mode = LearningMode(self.mapping_manager, self.audio_player)

        try:
            if self.learning_mode.enter_mode():
                logger.info("Learning mode activated. Controls:")
                logger.info("  RIGHT: Next song")
                logger.info("  LEFT: Previous song")
                logger.info("  L: Exit learning mode")
                logger.info("  Tap RFID card to map current song")
                
                while self.learning_mode.is_active:
                    tag_id = self.rfid_reader.read_tag()
                    
                    if tag_id == 'QUIT' or tag_id == 'L':  # 'L' key exits
                        break
                        
                    if tag_id == 'RIGHT':  # Right arrow
                        self.learning_mode.next_song()
                    elif tag_id == 'LEFT':  # Left arrow
                        self.learning_mode.previous_song()
                    elif tag_id:  # RFID card detected
                        if self.learning_mode.map_current_song(tag_id):
                            logger.info(f"Successfully mapped card {tag_id}")
                        
                    time.sleep(0.1)
                    
            self.learning_mode.exit_mode()
            logger.info("Learning mode deactivated")
            
        except Exception as e:
            logger.error(f"Error in learning mode: {str(e)}")
            self.learning_mode.exit_mode()

    def run(self):
        """Main program loop."""
        try:
            if not self.rfid_reader.initialise():
                logger.error("Failed to initialise RFID reader")
                return
            
            self.api_server.start()
            logger.info("API server started")

            # Validate mappings before starting
            issues = self.mapping_manager.validate_mappings()
            if any(issues.values()):
                logger.warning("Mapping validation found issues:")
                for category, items in issues.items():
                    if items:
                        logger.warning(f"{category}: {items}")

            logger.info("Starting main loop - waiting for cards...")

            # Show some additional information about options if playing in dev
            if not self._is_running_on_pi():
                logger.info("\nAvailable mappings:")
                for tag in ['MOCK_TAG_1', 'MOCK_TAG_2', 'MOCK_TAG_3', 'MOCK_TAG_4']:
                    music_file = self.mapping_manager.get_music_file(tag)
                    if music_file:
                        logger.info(f"Key {tag[-1]}: {music_file.name}")
            
            # Add this flag
            track_end_logged = False

            while True:
                tag_id = self.rfid_reader.read_tag()
                
                if tag_id == 'QUIT':
                    logger.info("Received quit command")
                    break
                elif tag_id == 'L':
                    self.handle_learning_mode()
                elif tag_id:
                    self.handle_tag(tag_id)
                    track_end_logged = False
                
                if self.audio_player.has_ended and not track_end_logged:
                    logger.info("Track finished playing")
                    track_end_logged = True 
                
                time.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources."""
        self.audio_player.stop()
        self.rfid_reader.cleanup()
        logger.info("MusicBox cleaned up")

class GracefulShutdown:
    def __init__(self, music_box):
        self.music_box = music_box
        self.shutdown = False
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        signal.signal(signal.SIGINT, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown = True
        
        try:
            # Stop RFID reading
            if hasattr(self.music_box, 'rfid_reader'):
                logger.info("Stopping RFID reader...")
                self.music_box.rfid_reader.cleanup()

            # Save current playback position and stop audio
            if hasattr(self.music_box, 'audio_player'):
                logger.info("Stopping audio playback...")
                self.music_box.audio_player._save_current_position()
                self.music_box.audio_player.stop()
            
            # Save any pending mappings
            if hasattr(self.music_box, 'mapping_manager'):
                logger.info("Saving mappings...")
                self.music_box.mapping_manager._save_mappings()
            
            # Stop the API server
            if hasattr(self.music_box, 'api_server'):
                logger.info("Stopping API server...")
                self.music_box.api_server.stop()
            
            # Stop Spotify downloader if running
            if hasattr(self.music_box, 'spotify_downloader'):
                logger.info("Stopping Spotify downloader...")
                self.music_box.spotify_downloader.stop()
            
            logger.info("Graceful shutdown completed")
            sys.exit(0)
            
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    music_box = MusicBox()
    music_box.run()