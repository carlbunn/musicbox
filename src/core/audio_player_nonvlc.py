import sounddevice as sd
import numpy as np
import threading
from typing import Optional
from pydub import AudioSegment
from src.utils.logger import get_logger
import io
import wave

logger = get_logger(__name__)

class AudioPlayer:
    """
    Audio player implementation using pydub for format handling and sounddevice for playback.
    Converts audio to WAV format in memory before streaming.
    """
    def __init__(self, buffer_size: int = 4096):
        self._is_playing = False
        self._stop_flag = False
        self._buffer_size = buffer_size
        self._play_thread: Optional[threading.Thread] = None
        logger.info("AudioPlayer initialized")

    def _stream_audio(self, file_path: str) -> None:
        """Stream audio file in chunks to minimize memory usage."""
        try:
            # Load and convert audio file using pydub
            audio = AudioSegment.from_file(file_path)
            
            # Convert to WAV format in memory
            buffer = io.BytesIO()
            audio.export(buffer, format='wav')
            buffer.seek(0)
            
            # Open WAV file from buffer
            with wave.open(buffer, 'rb') as wav_file:
                # Set up audio stream
                stream = sd.OutputStream(
                    samplerate=wav_file.getframerate(),
                    channels=wav_file.getnchannels(),
                    dtype=np.int16  # WAV files use 16-bit PCM
                )
                
                with stream:
                    while not self._stop_flag:
                        data = wav_file.readframes(self._buffer_size)
                        if not len(data):  # End of file
                            break
                        audio_data = np.frombuffer(data, dtype=np.int16)
                        stream.write(audio_data)
                    
            self._is_playing = False
            logger.info("Finished playing audio file")
            
        except Exception as e:
            logger.error(f"Error streaming audio: {str(e)}")
            self._is_playing = False

    def play(self, file_path: str) -> bool:
        """Play audio file from given path."""
        try:
            # Stop any current playback
            self.stop()
            
            # Start new playback
            self._stop_flag = False
            self._is_playing = True
            self._play_thread = threading.Thread(
                target=self._stream_audio,
                args=(file_path,)
            )
            self._play_thread.start()
            logger.info(f"Playing: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error playing file {file_path}: {str(e)}")
            self._is_playing = False
            return False

    def stop(self) -> None:
        """Stop current playback."""
        if self._is_playing:
            self._stop_flag = True
            if self._play_thread and self._play_thread.is_alive():
                self._play_thread.join(timeout=1.0)
            self._is_playing = False
            logger.info("Playback stopped")

    @property
    def is_playing(self) -> bool:
        return self._is_playing