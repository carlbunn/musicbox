# src/main.py
import sys
import os

# Add the project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.audio_player import AudioPlayer
import time
from pathlib import Path

def test_player(file_path: str):
    """Test audio player functionality with detailed output."""
    print("Testing Audio Player with:", file_path)
    print("-" * 50)

    player = AudioPlayer()
    
    # Start playback
    if player.play(file_path):
        print("\nInitial metadata:")
        info = player.get_display_info()
        for key, value in info.items():
            if key != 'compact':
                print(f"{key}: {value}")
        
        print("\nCompact display format:")
        print(f"Line 1: {info['compact']['line1']}")
        print(f"Line 2: {info['compact']['line2']}")
        
        # Monitor playback for a few seconds
        print("\nMonitoring playback:")
        for _ in range(5):
            status = player.get_status()
            print(f"\rPosition: {status['position_percent']}% - "
                  f"Time: {player.format_time(status['position'])}/"
                  f"{player.format_time(status['length'])}", end='')
            time.sleep(1)
            
        # Test volume control
        print("\n\nTesting volume control:")
        player.set_volume(50)
        time.sleep(1)
        status = player.get_status()
        print(f"Volume set to: {status['volume']}%")
        
        # Stop playback
        print("\nStopping playback...")
        player.stop()
        
    print("\nTest complete")

if __name__ == "__main__":
    # You can change this to the path of your test MP3 file
    test_file = "music/song1.mp3"
    if Path(test_file).exists():
        test_player(test_file)
    else:
        print(f"Error: Test file not found: {test_file}")
        print("Please place an MP3 file at:", test_file)