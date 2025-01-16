from mfrc522 import SimpleMFRC522, MFRC522
import RPi.GPIO as GPIO
from typing import Optional
from src.core.rfid_reader import RFIDReader
from src.utils.logger import get_logger

logger = get_logger(__name__)

class RC522Reader(RFIDReader):
    def __init__(self):
        self._reader = None
        self._raw_reader = None
        logger.info("RC522Reader: Initializing...")

    def initialize(self) -> bool:
        try:
            GPIO.setwarnings(False)
            self._reader = SimpleMFRC522()
            self._raw_reader = MFRC522()
            logger.info("RC522Reader: Successfully initialized")
            return True
        except Exception as e:
            logger.error(f"RC522Reader: Failed to initialize - {str(e)}")
            return False

    def read_tag(self) -> Optional[str]:
        """Non-blocking read implementation using lower-level MFRC522 commands."""
        try:
            if not self._raw_reader:
                return None

            # Step 1: Request
            (status, _) = self._raw_reader.MFRC522_Request(self._raw_reader.PICC_REQIDL)
            if status != self._raw_reader.MI_OK:
                return None

            logger.debug("RC522Reader: Card detected in request phase")
                
            # Step 2: Anticollision
            (status, uid) = self._raw_reader.MFRC522_Anticoll()
            if status != self._raw_reader.MI_OK:
                return None

            logger.debug(f"RC522Reader: Raw UID bytes: {uid}")
                
            # Convert UID bytes to ID number
            card_id = 0
            for i in range(4):  # Use first 4 bytes of UID
                card_id = card_id * 256 + uid[i]
                
            tag_id = f"TAG_{card_id}"
            logger.info(f"RC522Reader: Successfully read card with ID: {tag_id}")
            return tag_id
                
        except Exception as e:
            logger.error(f"RC522Reader: Error reading card - {str(e)}")
            return None

    def cleanup(self) -> None:
        try:
            GPIO.cleanup()
            logger.info("RC522Reader: Cleaned up GPIO")
        except Exception as e:
            logger.error(f"RC522Reader: Error during cleanup - {str(e)}")