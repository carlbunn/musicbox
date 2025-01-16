import requests
import sys
import json
from pathlib import Path
import base64
import argparse

def upload_song(server_url: str, filepath: Path):
    """Upload a song file to the server."""
    try:
        with open(filepath, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')
            
        response = requests.post(f"{server_url}/upload", json={
            'filename': filepath.name,
            'content': content
        })
        
        if response.status_code == 200:
            print(f"Successfully uploaded {filepath.name}")
        else:
            print(f"Error uploading file: {response.json().get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"Error: {str(e)}")

def map_tag(server_url: str, tag_id: str, filename: str):
    """Map an RFID tag to a song file."""
    try:
        response = requests.post(f"{server_url}/map", json={
            'tagId': tag_id,
            'filename': filename
        })
        
        if response.status_code == 200:
            print(f"Successfully mapped {tag_id} to {filename}")
        else:
            print(f"Error mapping tag: {response.json().get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"Error: {str(e)}")

def get_status(server_url: str):
    """Get current playback status."""
    try:
        response = requests.get(f"{server_url}/status")
        if response.status_code == 200:
            status = response.json()
            metadata = status.get('metadata', {})
            print("\nCurrent Status:")
            print(f"Playing: {'Yes' if status.get('is_playing') else 'No'}")
            print(f"Title: {metadata.get('title', 'Unknown')}")
            print(f"Artist: {metadata.get('artist', 'Unknown')}")
            if status.get('is_playing'):
                print(f"Position: {status.get('position_percent', 0)}%")
                print(f"Volume: {status.get('volume', 0)}%")
        else:
            print("Error getting status")
            
    except Exception as e:
        print(f"Error: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='MusicBox Control Tool')
    parser.add_argument('--server', default='http://localhost:8000',
                      help='Server URL (default: http://localhost:8000)')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload a song file')
    upload_parser.add_argument('filepath', type=Path, help='Path to the song file')
    
    # Map command
    map_parser = subparsers.add_parser('map', help='Map RFID tag to song')
    map_parser.add_argument('tag_id', help='RFID tag ID')
    map_parser.add_argument('filename', help='Song filename')
    
    # Status command
    subparsers.add_parser('status', help='Get current playback status')
    
    args = parser.parse_args()
    
    if args.command == 'upload':
        upload_song(args.server, args.filepath)
    elif args.command == 'map':
        map_tag(args.server, args.tag_id, args.filename)
    elif args.command == 'status':
        get_status(args.server)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()