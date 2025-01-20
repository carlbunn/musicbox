from abc import ABC, abstractmethod
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

class RFIDReader(ABC):
    """
    Abstract base class for RFID reader implementation.
    Concrete implementation will be added once hardware details are known.
    """
    @abstractmethod
    def initialise(self) -> bool:
        """Initialise the RFID reader hardware."""
        pass

    @abstractmethod
    def read_tag(self) -> Optional[str]:
        """Read RFID tag and return its ID if present."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup resources."""
        pass