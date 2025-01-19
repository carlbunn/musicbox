from flask import Flask, request, jsonify
import base64
from pathlib import Path
import threading
from src.utils.logger import get_logger

logger = get_logger(__name__)

class APIServer:
    def __init__(self, music_box):
        self.app = Flask(__name__)
        self.music_box = music_box  # Reference to main MusicBox instance
        self.server_thread = None
        self._setup_routes()
        
    def _setup_routes(self):
        @self.app.route('/play', methods=['POST'])
        def play_song():
            try:
                data = request.json
                filename = data['filename']
                
                # Construct full path
                music_path = Path(self.music_box.settings.get('music_directory')) / filename
                
                if not music_path.exists():
                    return jsonify({'status': 'error', 'message': 'File not found'}), 404
                    
                if self.music_box.audio_player.play(str(music_path)):
                    return jsonify({'status': 'success', 'message': 'Playing song'})
                else:
                    return jsonify({'status': 'error', 'message': 'Failed to play song'}), 500
                    
            except Exception as e:
                logger.error(f"Error playing song: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/pause', methods=['POST'])
        def pause_playback():
            """Pause current playback."""
            try:
                self.music_box.audio_player.pause()
                return jsonify({
                    'status': 'success',
                    'message': 'Playback paused'
                })
            except Exception as e:
                logger.error(f"Error in pause: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/resume', methods=['POST'])
        def resume_playback():
            """Resume paused playback."""
            try:
                self.music_box.audio_player.resume()
                return jsonify({
                    'status': 'success',
                    'message': 'Playback resumed'
                })
            except Exception as e:
                logger.error(f"Error in resume: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/seek', methods=['POST'])
        def seek_playback():
            """Seek to a specific position in milliseconds."""
            try:
                data = request.json
                position_ms = data.get('position_ms')
                
                if position_ms is None:
                    return jsonify({
                        'status': 'error',
                        'message': 'position_ms is required'
                    }), 400
                    
                if self.music_box.audio_player.seek_to_position(position_ms):
                    return jsonify({
                        'status': 'success',
                        'message': f'Seeked to position {position_ms}ms'
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Failed to seek'
                    }), 500
                    
            except Exception as e:
                logger.error(f"Error in seek: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/skip', methods=['POST'])
        def skip_playback():
            """Skip forward or backward by a specified amount."""
            try:
                data = request.json
                direction = data.get('direction', 'forward')
                amount_ms = data.get('amount_ms', 15000)  # Default 15 seconds
                
                if direction not in ['forward', 'backward']:
                    return jsonify({
                        'status': 'error',
                        'message': 'Invalid direction. Use "forward" or "backward".'
                    }), 400
                
                success = (self.music_box.audio_player.skip_forward(amount_ms) 
                        if direction == 'forward' 
                        else self.music_box.audio_player.skip_backward(amount_ms))
                
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': f'Skipped {direction} by {amount_ms}ms'
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': f'Failed to skip {direction}'
                    }), 500
                    
            except Exception as e:
                logger.error(f"Error in skip: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
            
        @self.app.route('/upload', methods=['POST'])
        def upload_music():
            try:
                data = request.json
                filename = data['filename']
                content = base64.b64decode(data['content'])
                
                # Save file to music directory
                music_path = Path(self.music_box.settings.get('music_directory')) / filename
                with open(music_path, 'wb') as f:
                    f.write(content)
                    
                return jsonify({'status': 'success', 'message': 'File uploaded successfully'})
            except Exception as e:
                logger.error(f"Error in upload: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/map', methods=['POST'])
        def map_tag():
            try:
                data = request.json
                tag_id = data['tagId']
                filename = data['filename']
                
                if self.music_box.mapping_manager.add_mapping(tag_id, filename):
                    return jsonify({'status': 'success', 'message': 'Tag mapped successfully'})
                else:
                    return jsonify({'status': 'error', 'message': 'Failed to map tag'}), 400
            except Exception as e:
                logger.error(f"Error in mapping: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/setup', methods=['POST'])
        def setup_wifi():
            try:
                data = request.json
                ssid = data['ssid']
                password = data['password']
                
                # Use the existing settings manager
                self.music_box.settings._settings.update({
                    'wifi_ssid': ssid,
                    'wifi_password': password
                })
                self.music_box.settings._save_settings()
                
                return jsonify({'status': 'success', 'message': 'WiFi configured successfully'})
            except Exception as e:
                logger.error(f"Error in WiFi setup: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/status', methods=['GET'])
        def get_detailed_status():
            """Get detailed playback status."""
            try:
                status = self.music_box.audio_player.get_detailed_status()
                return jsonify(status)
            except Exception as e:
                logger.error(f"Error getting status: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/songs', methods=['GET'])
        def get_songs():
            """Get all songs and their mapping status"""
            try:
                # Get all music files
                music_files = []
                for ext in ['.mp3', '.wav', '.flac', '.ogg']:
                    music_files.extend(Path(self.music_box.settings.get('music_directory')).glob(f"*{ext}"))
                
                # Get mappings
                mapped_files = {str(Path(path)): tag_id 
                                for tag_id, path in self.music_box.mapping_manager.mappings.items()}
                
                # Create response
                songs = []
                for file_path in music_files:
                    relative_path = str(file_path.relative_to(self.music_box.settings.get('music_directory')))
                    songs.append({
                        'filename': file_path.name,
                        'path': relative_path,
                        'mapped_to': mapped_files.get(relative_path, None),
                        'size': file_path.stat().st_size,
                        'modified': file_path.stat().st_mtime
                    })
                    
                return jsonify({
                    'status': 'success',
                    'songs': sorted(songs, key=lambda x: x['filename'])
                })
                
            except Exception as e:
                logger.error(f"Error getting songs: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/refresh', methods=['POST'])
        def refresh_songs():
            """Force a rescan of the music directory"""
            try:
                # Rescan directory and update mappings
                self.music_box.mapping_manager._load_mappings()
                return jsonify({'status': 'success', 'message': 'Music directory rescanned'})
            except Exception as e:
                logger.error(f"Error refreshing songs: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
            

        @self.app.route('/spotify/download', methods=['POST'])
        def download_spotify():
            """Download a track from Spotify."""
            try:
                data = request.json
                spotify_url = data.get('url')
                
                if not spotify_url:
                    return jsonify({
                        'status': 'error',
                        'message': 'Spotify URL is required'
                    }), 400
                    
                # Initialize downloader if not exists
                if not hasattr(self.music_box, 'spotify_downloader'):
                    self.music_box.spotify_downloader = SpotifyDownloader(self.music_box.mapping_manager)
                    
                if self.music_box.spotify_downloader.add_track(spotify_url):
                    return jsonify({
                        'status': 'success',
                        'message': 'Track added to download queue',
                        'queue_size': self.music_box.spotify_downloader.get_queue_size()
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Failed to add track to queue'
                    }), 400
                    
            except Exception as e:
                logger.error(f"Error in Spotify download: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/spotify/status', methods=['GET'])
        def spotify_status():
            """Get Spotify downloader status."""
            try:
                if not hasattr(self.music_box, 'spotify_downloader'):
                    return jsonify({
                        'status': 'error',
                        'message': 'Spotify downloader not initialized'
                    }), 404
                    
                status = self.music_box.spotify_downloader.get_status()
                return jsonify({
                    'status': 'success',
                    'data': status
                })
                
            except Exception as e:
                logger.error(f"Error getting Spotify status: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

    def start(self):
        """Start the API server in a separate thread"""
        def run_server():
            self.app.run(host='0.0.0.0', port=8000, debug=False)
            
        self.server_thread = threading.Thread(target=run_server)
        self.server_thread.daemon = True  # Thread will be terminated when main program exits
        self.server_thread.start()
        logger.info("API server started on port 8000")

    def stop(self):
        """Stop the API server"""
        # Implement if needed, though daemon thread will auto-terminate