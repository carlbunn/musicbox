from flask import Flask, request, jsonify
from functools import wraps
#import base64
from pathlib import Path
import threading
from src.utils.logger import get_logger
#from src.core.spotify_downloader import SpotifyDownloader

logger = get_logger(__name__)

def api_error_handler(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            return result
        except FileNotFoundError as e:
            logger.error(f"File not found in {f.__name__}: {str(e)}")
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
        except ValueError as e:
            logger.error(f"Invalid input in {f.__name__}: {str(e)}")
            return jsonify({'status': 'error', 'message': str(e)}), 400
        except Exception as e:
            logger.error(f"Error in {f.__name__}: {str(e)}")
            return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
    return decorated_function

def validate_json_input(**expected_fields):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            logger.info(request.json)
            data = request.json
            if not data:
                raise ValueError("No JSON data provided")
                
            for field_name, field_spec in expected_fields.items():
                if field_spec.get('required', False) and field_name not in data:
                    raise ValueError(f"{field_name} is required")
                    
                if field_name in data:
                    value = data[field_name]
                    
                    # Type validation
                    expected_type = field_spec.get('type')
                    if expected_type and not isinstance(value, expected_type):
                        raise ValueError(f"{field_name} must be of type {expected_type.__name__}")
                    
                    # Range validation for numbers
                    if isinstance(value, (int, float)):
                        min_val = field_spec.get('min')
                        max_val = field_spec.get('max')
                        if min_val is not None and value < min_val:
                            raise ValueError(f"{field_name} must be at least {min_val}")
                        if max_val is not None and value > max_val:
                            raise ValueError(f"{field_name} must be at most {max_val}")
                            
                    # Custom validation
                    validator = field_spec.get('validator')
                    if validator and not validator(value):
                        raise ValueError(f"Invalid value for {field_name}")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# For file operations, add path validation
def validate_filename(filename):
    # Prevent directory traversal
    clean_path = Path(filename).name  # Get just filename part
    return (
        clean_path == filename  # Must not contain path separators
        and len(clean_path) > 0  # Must not be empty
        and len(clean_path) < 255  # Reasonable length limit
        and not clean_path.startswith('.')  # No hidden files
    )

def validate_tag_id(tag_id):
    return tag_id.isalnum() and len(tag_id) <= 50

class APIServer:
    def __init__(self,
                 music_box,
                 port: int = 8000,
                 host: str = '0.0.0.0',
                 debug: bool = False):
        self.app = Flask(__name__)
        self._host = host
        self._port = port
        self._debug = debug
        self.music_box = music_box  # Reference to main MusicBox instance
        self.server_thread = None
        self._default_skip_forward_ms = 15000
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route('/play', methods=['POST'])
        @api_error_handler
        @validate_json_input(
            filename={
                'required': True,
                'type': str,
                'validator': validate_filename
            }
        )
        def play_song():
            data = request.json
            filename = data['filename']

            # Construct full path
            music_path = self.music_box.mapping_manager.to_absolute_path(filename)

            if not music_path.exists():
                raise FileNotFoundError(f'File not found: {filename}')

            if not self.music_box.audio_player.play(str(music_path)):
                raise Exception('Failed to play song')

            return jsonify({'status': 'success', 'message': 'Playing song'})

        @self.app.route('/pause', methods=['POST'])
        @api_error_handler
        def pause_playback():
            """Pause current playback."""
            if not self.music_box.audio_player.pause():
                raise Exception('Failed to pause playback')

            return jsonify({'status': 'success', 'message': 'Playback paused'})

        @self.app.route('/resume', methods=['POST'])
        @api_error_handler
        def resume_playback():
            """Resume paused playback."""
            if not self.music_box.audio_player.resume():
                raise Exception('Failed to resume playback')

            return jsonify({'status': 'success', 'message': 'Playback resumed'})

        @self.app.route('/seek', methods=['POST'])
        @api_error_handler
        @validate_json_input(
            position_ms={
                'required': True,
                'type': float,
                'min': 0,
                'max': 24 * 60 * 60 * 1000  # 24 hours in milliseconds
            }
        )
        def seek_playback():
            """Seek to a specific position in milliseconds."""
            data = request.json
            position_ms = data.get('position_ms', 0)

            if not self.music_box.audio_player.seek_to_position(position_ms):
                raise Exception('Failed to seek to position')

            return jsonify({'status': 'success', 'message': f'Seeked to position {position_ms}ms'})

        @self.app.route('/skip', methods=['POST'])
        @api_error_handler
        @validate_json_input(
            direction={
                'required': True,
                'type': str,
                'validator': lambda x: x in ['forward', 'backward']
            },
            amount_ms={
                'required': True,
                'type': int,
                'min': 0,
                'max': 300000
            }
        )
        def skip_playback():
            """Skip forward or backward by a specified amount."""
            data = request.json
            direction = data.get('direction', 'forward')
            amount_ms = data.get('amount_ms', self._default_skip_forward_ms)
            
            if direction not in ['forward', 'backward']:
                raise ValueError('Invalid direction. Use "forward" or "backward".')
                
            if not (self.music_box.audio_player.skip_forward(amount_ms) 
                    if direction == 'forward' 
                    else self.music_box.audio_player.skip_backward(amount_ms)):
                raise Exception(f'Failed to skip {direction}')
            
            return jsonify({'status': 'success', 'message': f'Skipped {direction} by {amount_ms}ms'})
            
        # @self.app.route('/upload', methods=['POST'])
        # def upload_music():
        #     try:
        #         data = request.json
        #         filename = data['filename']
        #         content = base64.b64decode(data['content'])
                
        #         # Save file to music directory
        #         music_path = Path(self.music_box.settings.get('music_directory')) / filename
        #         with open(music_path, 'wb') as f:
        #             f.write(content)
                    
        #         return jsonify({'status': 'success', 'message': 'File uploaded successfully'})
        #     except Exception as e:
        #         logger.error(f"Error in upload: {str(e)}")
        #         return jsonify({'status': 'error', 'message': str(e)}), 500
            
        @self.app.route('/map', methods=['POST'])
        @api_error_handler
        @validate_json_input(
            tag_id={
                'required': True,
                'type': str,
                'validator': validate_tag_id
            },
            filename={
                'required': True,
                'type': str,
                'validator': validate_filename
            }
        )
        def map_tag():
            data = request.json
            tag_id = data['tag_id']
            filename = data['filename']

            # Ensure tag has TAG_ prefix
            if not tag_id.startswith('TAG_'):
                tag_id = f'TAG_{tag_id}'
                
            if not self.music_box.mapping_manager.add_mapping(tag_id, filename):
                raise Exception('Failed to map tag')
            
            return jsonify({'status': 'success', 'message': 'Tag mapped successfully'})

        @self.app.route('/songs', methods=['GET'])
        @api_error_handler
        def get_songs():
            """Get all songs and their mapping status"""
            # Scan directory to ensure we have latest files
            if not self.music_box.mapping_manager.scan_directory():
                raise Exception('Failed to scan music directory')

            # Get all music files
            songs = []
            for rel_path, file_info in self.music_box.mapping_manager.files.items():
                # Find if file is mapped
                mapped_to = None
                for tag_id, mapped_path in self.music_box.mapping_manager.mappings.items():
                    if mapped_path == rel_path:
                        # Strip TAG_ prefix when sending to API for consistency
                        mapped_to = tag_id.replace('TAG_', '') if tag_id.startswith('TAG_') else tag_id
                        break
                
                # Get absolute path for file stats
                file_path = self.music_box.mapping_manager.to_absolute_path(rel_path)
                
                # Get metadata from file_info
                metadata = file_info.get('metadata', {})
                
                metadata.update({'mapped_to': mapped_to})

                songs.append(metadata)

            return jsonify({'status': 'success', 'songs': sorted(songs, key=lambda x: x['filename'])})

        # @self.app.route('/setup', methods=['POST'])
        # @api_error_handler
        # def setup_wifi():
        #     try:
        #         data = request.json
        #         ssid = data['ssid']
        #         password = data['password']
                
        #         # Use the existing settings manager
        #         self.music_box.settings._settings.update({
        #             'wifi_ssid': ssid,
        #             'wifi_password': password
        #         })
        #         self.music_box.settings._save_settings()
                
        #         return jsonify({'status': 'success', 'message': 'WiFi configured successfully'})
        #     except Exception as e:
        #         logger.error(f"Error in WiFi setup: {str(e)}")
        #         return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/status', methods=['GET'])
        @api_error_handler
        def get_status():
            """Get detailed playback status."""
            status = self.music_box.audio_player.get_status()
            return jsonify(status)

        @self.app.route('/refresh', methods=['POST'])
        @api_error_handler
        def refresh_songs():
            """Force a rescan of the music directory"""
            # Rescan directory and update mappings
            if not self.music_box.mapping_manager.scan_directory():
                raise Exception('Failed to rescan music directory')

            return jsonify({'status': 'success', 'message': 'Music directory rescanned'})

        @self.app.route('/spotify/download', methods=['POST'])
        @api_error_handler
        @validate_json_input(
            url={
                'required': True,
                'type': str
            }
        )
        def download_spotify():
            """Download a track from Spotify."""
            data = request.json
            spotify_url = data.get('url')

            # Check if downloader is enabled
            if not hasattr(self.music_box, 'spotify_downloader'):
                raise Exception('Spotify Downloader is not enabled')

            if not self.music_box.spotify_downloader.add_track(spotify_url):
                raise Exception('Failed to add track to download queue')

            return jsonify({
                'status': 'success',
                'message': 'Track added to download queue',
                'queue_size': self.music_box.spotify_downloader.get_queue_size()
            })

        @self.app.route('/spotify/status', methods=['GET'])
        @api_error_handler
        def spotify_status():
            """Get Spotify downloader status."""
            # Check if downloader is enabled
            if not hasattr(self.music_box, 'spotify_downloader'):
                raise Exception('Spotify Downloader is not enabled')
                    
            status = self.music_box.spotify_downloader.get_status()
            return jsonify({'status': 'success', 'data': status})

    def start(self):
        """Start the API server in a separate thread"""
        def run_server():
            self.app.run(host=self._host, port=self._port, debug=self._debug)

        self.server_thread = threading.Thread(target=run_server)
        self.server_thread.daemon = True  # Thread will be terminated when main program exits
        self.server_thread.start()

        logger.info(f'API server started on port {self._port}')

    def stop(self):
        """Stop the API server"""
        logger.info("Stopping API server...")
        try:
            # Signal the Flask app to shutdown
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')
            func()

            # Wait for server thread to end with timeout
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=5)  # 5 second timeout
                if self.server_thread.is_alive():
                    logger.warning("Server thread did not terminate within timeout")

        except RuntimeError as e:
            logger.warning(f"Server stop: {str(e)}")

        except Exception as e:
            logger.error(f"Error stopping server: {str(e)}")

    def cleanup(self):
        """Clean up resources"""
        logger.info("Starting api server cleanup...")
        
        try:
            # Stop running server
            self.stop()
            
        except Exception as e:
            logger.error(f"Error during api server cleanup: {e}")