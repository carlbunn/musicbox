import RPi.GPIO as GPIO
import time
from mfrc522 import MFRC522
from typing import Optional
from dataclasses import dataclass
from src.core.rfid_reader import RFIDReader
from src.utils.logger import get_logger
import traceback
import os
from dotenv import load_dotenv

logger = get_logger(__name__)

class RC522Reader(RFIDReader):
    def __init__(self, removal_timeout: float = 0.2):
        """Initialise the RC522 RFID reader with optional configuration."""
        super().__init__()

        self._removal_timeout = max(0.1, removal_timeout) # Minimum 0.1s delay between reads
        self._raw_reader = None
        self._last_card_id = None
        self._last_read_time = 0

        logger.info("RC522Reader: Initialising...")

    def initialise(self) -> bool:
        """Initialise the GPIO and RFID reader hardware."""
        try:
            # First make sure GPIO is properly reset
            try:
                GPIO.cleanup()
                logger.info("RC522Reader: Cleaned up any existing GPIO configurations")
            except Exception as e:
                # This is ok if GPIO wasn't set up yet
                logger.debug(f"RC522Reader: No GPIO cleanup needed - {str(e)}")
            
            # Set GPIO mode explicitly before creating the MFRC522 instance
            GPIO.setmode(GPIO.BOARD)  # or GPIO.BCM depending on your mfrc522 library implementation
            logger.info("RC522Reader: GPIO mode set to BOARD")
            
            # Disable warnings before MFRC522 initialisation
            GPIO.setwarnings(False)
            
            # Create MFRC522 instance with error handling
            try:
                self._raw_reader = MFRC522()
                logger.info("RC522Reader: Successfully initialised")
                return True
            except Exception as e:
                logger.error(f"RC522Reader: MFRC522 initialisation failed - {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return False
            
        except Exception as e:
            logger.error(f"RC522Reader: Failed to initialise - {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def read_tag(self) -> Optional[str]:
        """
        Non-blocking read of RFID card.
        Returns:
            - None if no new card is detected
            - TAG_<hex_id> if a new card is detected after sufficient delay
        """
        try:
            # This is a bit of a hack
            # to avoid errors between reads, we
            # recreate the reader on every iteration
            self._raw_reader = MFRC522()
            
            # Request
            current_time = time.time()
            status, _ = self._raw_reader.MFRC522_Request(self._raw_reader.PICC_REQIDL)
            
            # No card present
            if status != self._raw_reader.MI_OK:
                self._last_card_id = None
                #logger.debug(f"RC522Reader: No card present - resetting reader")
                return None

            # Try to get card ID (anticollision)
            status, uid = self._raw_reader.MFRC522_Anticoll()
            if status != self._raw_reader.MI_OK:
                logger.debug(f"RC522Reader: Couldn't read the card id")
                return None

            # Convert UID bytes directly to hex string
            current_card = ''.join(format(x, '02X') for x in uid[:4])
            card_id = f"TAG_{current_card}"

            # If it's the same card we last saw, ignore it
            if card_id == self._last_card_id:
                logger.debug(f"RC522Reader: Ignoring the same card id [{card_id}]")
                return None

            # If we haven't waited long enough since last detection, ignore it
            #if (current_time - self._last_read_time) < self._removal_timeout:
            #    logger.debug(f"RC522Reader: Not enough time [{current_time - self._last_read_time}] against timeout [{self._removal_timeout}]")
            #    return None

            # New card detected after sufficient delay
            self._last_card_id = card_id
            self._last_read_time = current_time
            logger.info(f"RC522Reader: New card detected: {card_id}")

            # This is a bit of a hack
            # to avoid errors between reads, we
            # recreate the reader on every iteration
            # and this is the cleanup
            self._raw_reader.MFRC522_StopCrypto1()
            self._raw_reader = None
            GPIO.cleanup()

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
