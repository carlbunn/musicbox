from src.core.rfid_reader import RFIDReader
from typing import Optional
import sys
import tty
import termios
import select
from src.utils.logger import get_logger

logger = get_logger(__name__)

class MockRFIDReader(RFIDReader):
    """
    Mock RFID reader that uses keyboard input.
    Keys 1-9 simulate different RFID tags.
    """
    def __init__(self):
        self._fd = sys.stdin.fileno()
        self._old_settings = termios.tcgetattr(self._fd)
        logger.info("MockRFIDReader initialized")

    def initialize(self) -> bool:
        try:
            tty.setraw(sys.stdin.fileno())
            return True
        except Exception as e:
            logger.error(f"Error initializing mock RFID reader: {str(e)}")
            return False

    # Update in src/core/mock_rfid_reader.py

    def read_tag(self) -> Optional[str]:
        """
        Non-blocking read of a key press.
        Returns:
            - None if no key pressed
            - 'QUIT' for 'q'
            - 'LEFT' for left arrow (typically '\x1b[D')
            - 'RIGHT' for right arrow (typically '\x1b[C')
            - 'L' for 'l' (learning mode)
            - tag ID (MOCK_TAG_X) for number keys 1-4
        """
        try:
            if select.select([sys.stdin], [], [], 0)[0] != []:
                char = sys.stdin.read(1)
                
                # Handle arrow keys (they start with escape sequence)
                if char == '\x1b':
                    next_chars = sys.stdin.read(2)
                    if next_chars == '[D':
                        return 'LEFT'
                    elif next_chars == '[C':
                        return 'RIGHT'
                    return None
                    
                # Handle regular keys
                if char.isdigit() and char != '0':
                    tag_id = f"MOCK_TAG_{char}"
                    logger.info(f"Mock tag read: {tag_id}")
                    return tag_id
                elif char == 'q':
                    logger.info("Quit signal received")
                    return 'QUIT'
                elif char == 'l':
                    logger.info("Learning mode signal received")
                    return 'L'
                    
            return None
        except Exception as e:
            logger.error(f"Error reading mock tag: {str(e)}")
            return None

    def cleanup(self) -> None:
        """Restore terminal settings."""
        try:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
            logger.info("MockRFIDReader cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")