import threading
import time
import sys
import subprocess
import re
from queue import Queue, Empty
from pathlib import Path
from urllib.parse import urlparse
from src.utils.logger import get_logger

logger = get_logger(__name__)

class SpotifyDownloader:
    VALID_SPOTIFY_PATHS = {
        'track': r'^/track/[a-zA-Z0-9]{22}(?:\?.*)?$',
        'album': r'^/album/[a-zA-Z0-9]{22}(?:\?.*)?$',
        'playlist': r'^/playlist/[a-zA-Z0-9]{22}(?:\?.*)?$'
    }

    def __init__(self,
                 output_directory: str | Path,
                 spotdl_path: str | Path = None,
                 download_timeout: int = 300):
        """Initialize the downloader with specified output directory
        
        Args:
            output_directory: Directory where downloaded music will be stored
            spotdl_path: Optional custom path to spotdl executable
            download_timeout: Timeout in seconds for each download (default 300)
        """
        self.output_dir = Path(output_directory).resolve()

        if spotdl_path is not None:
            # Use the provided path
            self.spotdl_path = spotdl_path
        else:
            # Try to find spotdl in the virtual environment
            if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
                # We're in a virtual environment
                if sys.platform.startswith('win'):
                    self.spotdl_path = str(Path(sys.prefix) / 'Scripts' / 'spotdl.exe')
                else:
                    self.spotdl_path = str(Path(sys.prefix) / 'bin' / 'spotdl')

        # Just confirm that the path exists before we continue
        if not Path(self.spotdl_path).exists():
            raise RuntimeError(f"spotdl executable not found at: {self.spotdl_path}")

        logger.info(f"Using spotdl path: {self.spotdl_path}")

        # Initialize thread-safe components
        self.download_queue = Queue(maxsize=1000)
        self._running = threading.Event()
        self._running.set() # Start in a running state
        self._current_download = None
        self._download_lock = threading.Lock()
        self._download_timeout = download_timeout

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Start download thread
        self.download_thread = threading.Thread(target=self._download_worker)
        self.download_thread.daemon = False
        self.download_thread.start()
        logger.info(f"SpotifyDownloader initialised with output directory: {self.output_dir}")

    @classmethod
    def _validate_spotify_url(cls, url: str) -> tuple[bool, str]:
        """
        Validate if a URL is a valid Spotify URL
        
        Args:
            url: URL to validate
            
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        try:
            # Basic URL validation
            if not url.startswith(('http://', 'https://')):
                return False, "URL must start with http:// or https://"

            # Parse URL
            parsed = urlparse(url)
            
            # Check domain
            if parsed.netloc not in ['open.spotify.com', 'spotify.com']:
                return False, "URL must be from open.spotify.com or spotify.com"

            # Check path format for different content types
            path = parsed.path
            for content_type, pattern in cls.VALID_SPOTIFY_PATHS.items():
                if re.match(pattern, path):
                    return True, ""

            return False, "Invalid Spotify URL format - must be a track, album, or playlist URL"

        except Exception as e:
            return False, f"URL validation error: {str(e)}"

    def add_track(self, spotify_url: str) -> bool:
        """
        Add a track to the download queue
        
        Args:
            spotify_url: Spotify URL of the track to download
            
        Returns:
            bool: True if track was added to queue, False otherwise
        """
        try:
            # Validate URL format
            is_valid, error_message = self._validate_spotify_url(spotify_url)
            if not is_valid:
                logger.error(f"Invalid Spotify URL ({error_message}): {spotify_url}")
                return False

            if not self._running.is_set():
                logger.error("Cannot add track - downloader is stopping or stopped")
                return False

            self.download_queue.put(spotify_url)
            logger.info(f"Added track to queue: {spotify_url}")
            return True

        except Exception as e:
            logger.error(f"Error adding track to queue: {str(e)}")
            return False
        
    def _download_worker(self):
        """Background worker that processes the download queue"""
        while self._running.is_set() or not self.download_queue.empty():
            try:
                try:
                    # Get next URL from queue, wait up to 1 second
                    spotify_url = self.download_queue.get(timeout=1.0)
                except Empty:
                    continue

                with self._download_lock:
                    self._current_download = spotify_url

                logger.info(f"Starting download: {spotify_url}")

                # Prepare command
                cmd = [
                    self.spotdl_path,
                    "--output", str(self.output_dir),
                    spotify_url
                ]

                # Run spotdl
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=self._download_timeout # 5 minute timeout per download
                    )
                    logger.info(f"Download completed: {spotify_url}")

                except subprocess.TimeoutExpired:
                    logger.error(f"Download timed out after {self._download_timeout} seconds: {spotify_url}")

                except subprocess.CalledProcessError as e:
                    logger.error(f"Download failed: {spotify_url}")
                    logger.error(f"Error output: {e.stderr}")

                finally:
                    with self._download_lock:
                        self._current_download = None
                    self.download_queue.task_done()

            except Exception as e:
                logger.error(f"Error in download worker: {str(e)}")
                time.sleep(1)  # Prevent tight loop on persistent errors

    def stop(self, timeout: float = None) -> bool:
        """
        Stop the download thread gracefully
        
        Args:
            timeout: Maximum time to wait for current downloads to complete (None = wait forever)
            
        Returns:
            bool: True if stopped cleanly, False if timeout occurred
        """
        logger.info("Stopping downloader...")
        self._running.clear()

        # Wait for download thread to finish
        if timeout is not None:
            self.download_thread.join(timeout=timeout)
            clean_stop = not self.download_thread.is_alive()
        else:
            self.download_thread.join()
            clean_stop = True

        if clean_stop:
            logger.info("SpotifyDownloader stopped cleanly")
        else:
            logger.warning("SpotifyDownloader stop timed out")

        return clean_stop
        
    def get_queue_size(self) -> int:
        """Get number of pending downloads"""
        return self.download_queue.qsize()
        
    def get_status(self) -> dict:
        """Get current downloader status"""
        with self._download_lock:
            return {
                'queue_size': self.download_queue.qsize(),
                'is_running': self._running.is_set(),
                'output_directory': str(self.output_dir),
                'current_download': self._current_download
            }

    def cleanup(self) -> None:
        """Clean up resources"""
        logger.info("Starting spotify downloader cleanup...")

        try:
            # Stop with 60 second timeout
            clean_stop = self.stop(timeout=60)
            if not clean_stop:
                logger.warning("Force stopping downloader after timeout")

        except Exception as e:
            logger.exception(f"Error during spotify downloader cleanup: {e}")
            raise  # Re-raise to ensure calling code knows cleanup failed

        finally:
            logger.info("Spotify downloader cleanup complete")
