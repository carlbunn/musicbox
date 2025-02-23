import RPi.GPIO as GPIO
import time
from mfrc522 import MFRC522
from typing import Optional
from dataclasses import dataclass
from src.core.rfid_reader import RFIDReader
from src.utils.logger import get_logger

logger = get_logger(__name__)

class RC522Reader(RFIDReader):
    def __init__(self, removal_timeout: float = 0.2):
        """Initialize the RC522 RFID reader with optional configuration."""
        super().__init__()

        self._removal_timeout = max(0.1, removal_timeout) # Minimum 0.1s delay between reads
        self._raw_reader = None
        self._last_card_id = None
        self._last_read_time = 0

        logger.info("RC522Reader: Initialising...")

    def initialise(self) -> bool:
        """Initialize the GPIO and RFID reader hardware."""
        try:
            # Check if GPIO is already in use
            if GPIO.getmode() is not None:
                logger.warning("RC522Reader: GPIO is already initialized, may conflict with other processes")

            # Enable warnings to catch conflicts
            import warnings
            warnings.filterwarnings('error')
            GPIO.setwarnings(True)

            try:
                self._raw_reader = MFRC522()
                GPIO.setwarnings(False)
                warnings.filterwarnings('default') # Reset warnings to default
                logger.info("RC522Reader: Successfully initialised")
                return True

            except RuntimeWarning as w:
                logger.error(f"RC522Reader: GPIO conflict detected - {str(w)}")
                warnings.filterwarnings('default') # Reset warnings to default
                return False
            
        except Exception as e:
            logger.error(f"RC522Reader: Failed to initialise - {str(e)}")
            return False

    def read_tag(self) -> Optional[str]:
        """
        Non-blocking read of RFID card.
        Returns:
            - None if no new card is detected
            - TAG_<hex_id> if a new card is detected after sufficient delay
        """
        try:
            if not self._raw_reader:
                logger.error("RC522Reader: Reader not initialized")
                return None

            # Step 1: Request
            current_time = time.time()
            status, _ = self._raw_reader.MFRC522_Request(self._raw_reader.PICC_REQIDL)

            # No card present
            if status != self._raw_reader.MI_OK:
                self._last_card_id = None
                return None
            
            # Try to get card ID (anticollision)
            status, uid = self._raw_reader.MFRC522_Anticoll()
            if status != self._raw_reader.MI_OK:
                return None
            
            # Convert UID bytes directly to hex string
            current_card = ''.join(format(x, '02X') for x in uid[:4])
            card_id = f"TAG_{current_card}"
            
            # If it's the same card we last saw, ignore it
            if card_id == self._last_card_id:
                return None
            
            # If we haven't waited long enough since last detection, ignore it
            if (current_time - self._last_read_time) < self._removal_timeout:
                return None

            # New card detected after sufficient delay
            self._last_card_id = card_id
            self._last_read_time = current_time
            logger.info(f"RC522Reader: New card detected: {card_id}")

            return card_id

        except Exception as e:
            logger.error(f"RC522Reader: Error reading card - {str(e)}")
            return None

    def cleanup(self) -> None:
        """Clean up RFID reader and GPIO resources. 
        Ensures proper shutdown of MFRC522 reader and GPIO pins.
        
        Raises:
            Exception: If any cleanup operation fails
        """
        logger.info("RC522Reader: Starting cleanup...")
        cleanup_error = None

        # First, cleanup the MFRC522 reader
        if self._raw_reader:
            try:
                # Stop any ongoing operations
                self._raw_reader.MFRC522_StopCrypto1()
                # Safely close SPI if available
                if hasattr(self._raw_reader, 'spi') and self._raw_reader.spi:
                    self._raw_reader.spi.close()
                self._raw_reader = None
                logger.info("RC522Reader: Cleaned up MFRC522 reader")

            except Exception as e:
                cleanup_error = e
                logger.error(f"RC522Reader: Error cleaning up MFRC522 - {str(e)}")

        # Then cleanup GPIO
        try:
            GPIO.cleanup()
            logger.info("RC522Reader: Cleaned up GPIO")

        except Exception as e:
            # If we already had an error, log this one but keep the original
            if not cleanup_error:
                cleanup_error = e
            logger.error(f"RC522Reader: Error cleaning up GPIO - {str(e)}")

        # Log final status and propagate any error
        if cleanup_error:
            logger.error("RC522Reader: Cleanup failed")
            raise cleanup_error
        else:
            logger.info("RC522Reader: Cleanup completed successfully")
