# src/core/learning_mode.py
from pathlib import Path
from typing import List, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

class LearningMode:
    """Handles the learning mode for mapping new RFID cards to songs."""
    def __init__(self, mapping_manager, audio_player):
        self.mapping_manager = mapping_manager
        self.audio_player = audio_player
        self.is_active = False
        self.current_song_index = 0
        self.unmapped_songs: List[Path] = []
        
    def enter_mode(self) -> bool:
        """Enter learning mode and prepare unmapped songs list."""
        try:
            self.unmapped_songs = self.mapping_manager.get_unmapped_files()
            if not self.unmapped_songs:
                logger.info("No unmapped songs available")
                return False
                
            self.is_active = True
            self.current_song_index = 0
            logger.info("Entered learning mode")
            self._announce_current_song()
            return True
            
        except Exception as e:
            logger.error(f"Error entering learning mode: {str(e)}")
            return False
            
    def exit_mode(self) -> None:
        """Exit learning mode."""
        self.is_active = False
        self.audio_player.stop()
        logger.info("Exited learning mode")
        
    def next_song(self) -> bool:
        """Move to next unmapped song."""
        if not self.is_active or not self.unmapped_songs:
            return False
            
        self.current_song_index = (self.current_song_index + 1) % len(self.unmapped_songs)
        self._announce_current_song()
        return True
        
    def previous_song(self) -> bool:
        """Move to previous unmapped song."""
        if not self.is_active or not self.unmapped_songs:
            return False
            
        self.current_song_index = (self.current_song_index - 1) % len(self.unmapped_songs)
        self._announce_current_song()
        return True
        
    def _announce_current_song(self) -> None:
        """Play the current song for preview."""
        if self.unmapped_songs:
            current_song = self.unmapped_songs[self.current_song_index]
            logger.info(f"Current song: {current_song}")
            self.audio_player.play(str(current_song))
            
    def map_current_song(self, rfid_tag: str) -> bool:
        """Map the current song to the provided RFID tag."""
        if not self.is_active or not self.unmapped_songs:
            return False
            
        try:
            current_song = self.unmapped_songs[self.current_song_index]
            if self.mapping_manager.add_mapping(rfid_tag, str(current_song)):
                logger.info(f"Mapped {rfid_tag} to {current_song}")
                # Remove the mapped song from our list
                self.unmapped_songs.pop(self.current_song_index)
                if self.unmapped_songs:
                    self.current_song_index = self.current_song_index % len(self.unmapped_songs)
                    self._announce_current_song()
                else:
                    self.exit_mode()
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error mapping song: {str(e)}")
            return False