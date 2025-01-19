import threading
from queue import Queue, Empty
import subprocess
from pathlib import Path
import time
import sys
import os
from src.utils.logger import get_logger
from src.config.settings import Settings

logger = get_logger(__name__)

class SpotifyDownloader:
    def __init__(self, mapping_manager=None):
        """Initialize the downloader using project settings"""
        self.mapping_manager = mapping_manager
        """Initialize the downloader using project settings"""
        self.settings = Settings()
        self.output_dir = Path(self.settings.get('music_directory', 'music'))
        # Try to find spotdl in the virtual environment
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            # We're in a virtual environment
            if sys.platform.startswith('win'):
                self.spotdl_path = str(Path(sys.prefix) / 'Scripts' / 'spotdl.exe')
            else:
                self.spotdl_path = str(Path(sys.prefix) / 'bin' / 'spotdl')
        else:
            # Fallback to settings or default
            self.spotdl_path = self.settings.get('spotdl_path', 'spotdl')
            
        logger.info(f"Using spotdl path: {self.spotdl_path}")
        self.download_queue = Queue()
        self.running = True
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Start download thread
        self.download_thread = threading.Thread(target=self._download_worker)
        self.download_thread.daemon = True
        self.download_thread.start()
        logger.info(f"SpotifyDownloader initialized with output directory: {self.output_dir}")
        
    def add_track(self, spotify_url: str) -> bool:
        """
        Add a track to the download queue
        
        Args:
            spotify_url: Spotify URL of the track to download
            
        Returns:
            bool: True if track was added to queue, False otherwise
        """
        try:
            if not spotify_url.startswith("https://open.spotify.com/"):
                logger.error(f"Invalid Spotify URL: {spotify_url}")
                return False
                
            self.download_queue.put(spotify_url)
            logger.info(f"Added track to queue: {spotify_url}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding track to queue: {str(e)}")
            return False
        
    def _download_worker(self):
        """Background worker that processes the download queue"""
        while self.running:
            try:
                # Get next URL from queue, wait up to 1 second
                spotify_url = self.download_queue.get(timeout=1.0)
                
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
                        check=True
                    )
                    logger.info(f"Download completed: {spotify_url}")
                    
                except subprocess.CalledProcessError as e:
                    logger.error(f"Download failed: {spotify_url}")
                    logger.error(f"Error output: {e.stderr}")
                    
            except Empty:
                # Queue timeout - this is normal
                continue
                
            except Exception as e:
                logger.error(f"Error in download worker: {str(e)}")
                time.sleep(1)  # Prevent tight loop on persistent errors
                
    def stop(self):
        """Stop the download thread"""
        self.running = False
        self.download_thread.join()
        logger.info("SpotifyDownloader stopped")
        
    def get_queue_size(self) -> int:
        """Get number of pending downloads"""
        return self.download_queue.qsize()
        
    def get_status(self) -> dict:
        """Get current downloader status"""
        return {
            'queue_size': self.get_queue_size(),
            'is_running': self.running,
            'output_directory': str(self.output_dir)
        }