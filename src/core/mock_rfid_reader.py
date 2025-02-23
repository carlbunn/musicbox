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
    Available commands:
    - Keys 1-4: Simulate RFID tags (MOCK_TAG_1 to MOCK_TAG_4)
    - 'q': Quit command
    - 'l': Learning mode
    - Left/Right arrows: Navigation (if supported)
    """
    def __init__(self):
        super().__init__()
        self._fd = sys.stdin.fileno()
        self._old_settings = None
        self._running = False
        logger.info("MockRFIDReader initialised")

    def _print_help(self):
        """Print available commands."""
        logger.info("\nMock RFID Reader Commands:")
        logger.info("  1-4 - Simulate RFID tags")
        logger.info("  q   - Quit application")
        logger.info("  l   - Enter learning mode")
        logger.info("  ←/→ - Navigation (if supported)")
        logger.info("  h   - Show this help\n")

    def initialise(self) -> bool:
        """Initialize the mock reader and save terminal settings."""
        try:
            # Save current terminal settings
            self._old_settings = termios.tcgetattr(self._fd)
            # Set raw mode
            tty.setraw(sys.stdin.fileno())
            self._running = True
            logger.info("MockRFIDReader initialised successfully")
            return True
        except Exception as e:
            logger.error(f"Error initialising mock RFID reader: {str(e)}")
            self.cleanup()
            return False

    def read_tag(self) -> Optional[str]:
        """
        Non-blocking read of a key press.
        Returns:
            - None if no key pressed
            - 'QUIT' for 'q'
            - 'LEFT' for left arrow
            - 'RIGHT' for right arrow
            - 'L' for 'l' (learning mode)
            - tag ID (MOCK_TAG_X) for number keys 1-4
        """
        if not self._running:
            return None

        try:
            if select.select([sys.stdin], [], [], 0)[0] != []:
                char = sys.stdin.read(1)

                # Show help
                if char == 'h':
                    self._print_help()
                    return None

                # Handle arrow keys
                if char == '\x1b':
                    next_chars = sys.stdin.read(2)
                    if next_chars == '[D':
                        logger.debug("Left arrow pressed")
                        return 'LEFT'
                    elif next_chars == '[C':
                        logger.debug("Right arrow pressed")
                        return 'RIGHT'
                    return None

                # Handle regular keys
                if char in ['1', '2', '3', '4']:
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
        """Restore terminal settings and stop reader."""
        try:
            self._running = False
            if self._old_settings:
                # Restore the old terminal settings
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
                self._old_settings = None
            logger.info("MockRFIDReader cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")