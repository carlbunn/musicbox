from mfrc522 import SimpleMFRC522
import RPi.GPIO as GPIO
from typing import Optional
from src.core.rfid_reader import RFIDReader
from src.utils.logger import get_logger

logger = get_logger(__name__)

class RC522Reader(RFIDReader):
    """
    Concrete implementation of RFIDReader for RC522 module.
    Uses the SimpleMFRC522 library for easy interfacing.
    """
    def __init__(self):
        self._reader = None
        logger.info("RC522 Reader initialized")

    def initialize(self) -> bool:
        """Initialize the RFID reader hardware."""
        try:
            GPIO.setwarnings(False)
            self._reader = SimpleMFRC522()
            logger.info("RC522 Reader initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Error initializing RC522 Reader: {str(e)}")
            return False

    def read_tag(self) -> Optional[str]:
        """
        Read RFID tag and return its ID if present.
        Non-blocking implementation that returns None if no card is present.
        """
        try:
            # SimpleMFRC522.read() is blocking, so we need to implement
            # our own non-blocking read using the raw MFRC522 interface
            if self._reader.READER.MFRC522_Request(self._reader.READER.PICC_REQIDL)[0] == self._reader.READER.MI_OK:
                # Card detected, get ID
                uid = self._reader.read_id_no_block()
                if uid:
                    tag_id = f"TAG_{uid}"
                    logger.info(f"Card read: {tag_id}")
                    return tag_id
            return None
            
        except Exception as e:
            logger.error(f"Error reading RC522: {str(e)}")
            return None

    def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        try:
            GPIO.cleanup()
            logger.info("RC522 Reader cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up RC522: {str(e)}")