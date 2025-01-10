# src/main.py
import sys
import os

# Add the project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.mock_rfid_reader import MockRFIDReader
from src.core.rc522_reader import RC522Reader
from src.core.audio_player import AudioPlayer
from src.core.file_manager import FileManager
from src.core.learning_mode import LearningMode
from src.core.mapping_manager import MappingManager
from src.config.settings import Settings
from src.utils.logger import get_logger
import time
from pathlib import Path
from typing import Dict

logger = get_logger(__name__)

class MusicBox:
    def __init__(self):
        self.settings = Settings()
        self.audio_player = AudioPlayer()
        
        # Use RC522Reader on Pi, MockRFIDReader for development
        if self._is_running_on_pi():
            self.rfid_reader = RC522Reader()
        else:
            self.rfid_reader = MockRFIDReader()
        
        self.mapping_manager = MappingManager()
        
        # Initialize file manager with music directory
        music_dir = self.settings.get('music_directory', 'music')
        self.file_manager = FileManager(music_dir)
        
        logger.info("MusicBox initialized")

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
            # Get the mapped music file
            music_file = self.mapping_manager.get_music_file(tag_id)
            
            if music_file:
                logger.info(f"Playing music for tag {tag_id}: {music_file}")
                if self.audio_player.play(str(music_file)):
                    # Get and log the track info
                    info = self.audio_player.get_display_info()
                    logger.info(f"Now playing: {info['title']} by {info['artist']}")
                    return True
                else:
                    logger.error(f"Failed to play file: {music_file}")
            else:
                logger.warning(f"No music mapped for tag: {tag_id}")
            
            return False
            
        except Exception as e:
            logger.error(f"Error handling tag {tag_id}: {str(e)}")
            return False
        
    # Add to src/main.py in the MusicBox class:
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
            if not self.rfid_reader.initialize():
                logger.error("Failed to initialize RFID reader")
                return

            # Validate mappings before starting
            issues = self.mapping_manager.validate_mappings()
            if any(issues.values()):
                logger.warning("Mapping issues found:")
                for category, items in issues.items():
                    if items:
                        logger.warning(f"{category}: {items}")

            logger.info("Starting main loop")
            logger.info("Controls:")
            logger.info("  1-4: Play mapped songs")
            logger.info("  L: Enter learning mode")
            logger.info("  Q: Quit")
            
            logger.info("\nAvailable mappings:")
            for tag in ['MOCK_TAG_1', 'MOCK_TAG_2', 'MOCK_TAG_3', 'MOCK_TAG_4']:
                music_file = self.mapping_manager.get_music_file(tag)
                if music_file:
                    logger.info(f"Key {tag[-1]}: {music_file.name}")
            
            while True:
                tag_id = self.rfid_reader.read_tag()
                
                if tag_id == 'QUIT':
                    break
                elif tag_id == 'L':
                    self.handle_learning_mode()
                    # Refresh the display of available mappings after learning mode
                    logger.info("\nAvailable mappings:")
                    for tag in ['MOCK_TAG_1', 'MOCK_TAG_2', 'MOCK_TAG_3', 'MOCK_TAG_4']:
                        music_file = self.mapping_manager.get_music_file(tag)
                        if music_file:
                            logger.info(f"Key {tag[-1]}: {music_file.name}")
                elif tag_id:
                    self.handle_tag(tag_id)
                
                # If a track has ended, log it
                if self.audio_player.has_ended:
                    logger.info("Track finished playing")
                
                time.sleep(0.1)  # Prevent busy waiting

        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources."""
        self.audio_player.stop()
        self.rfid_reader.cleanup()
        logger.info("MusicBox cleaned up")

if __name__ == "__main__":
    music_box = MusicBox()
    music_box.run()