#!/usr/bin/env python3
import os
os.environ["PYTHONIOENCODING"] = "utf-8"

"""
Complete Music Telegram Bot - Single File Solution
Features:
- Download Spotify tracks, albums, playlists, and artists
- Send single tracks directly as MP3 files
- ZIP compression for multiple files or files larger than 50MB
- Cloud storage integration with PixelDrain
- Live progress updates with percentage and current track
- Robust error handling with detailed messages
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
import random
from pathlib import Path
from typing import Dict, List, Optional, Set
import json
import threading
import glob
import shlex
import pyzipper  # Make sure to install: pip install pyzipper
import unicodedata

import aiohttp
import requests
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class YouTubeAPIv3:
    """YouTube Data API v3 client for fetching video metadata"""
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"
    
    async def get_video_info(self, video_id: str) -> Optional[Dict]:
        """Fetch video metadata using YouTube API v3"""
        try:
            url = f"{self.base_url}/videos"
            params = {
                'part': 'snippet,contentDetails,statistics',
                'id': video_id,
                'key': self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'items' in data and len(data['items']) > 0:
                            item = data['items'][0]
                            snippet = item.get('snippet', {})
                            content_details = item.get('contentDetails', {})
                            statistics = item.get('statistics', {})
                            
                            return {
                                'title': snippet.get('title'),
                                'description': snippet.get('description'),
                                'channel': snippet.get('channelTitle'),
                                'duration': content_details.get('duration'),
                                'views': statistics.get('viewCount'),
                                'likes': statistics.get('likeCount'),
                                'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url')
                            }
                    logger.warning(f"YouTube API returned status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching YouTube metadata: {e}")
            return None
    
    async def get_playlist_info(self, playlist_id: str) -> Optional[Dict]:
        """Fetch playlist metadata using YouTube API v3"""
        try:
            url = f"{self.base_url}/playlists"
            params = {
                'part': 'snippet,contentDetails',
                'id': playlist_id,
                'key': self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'items' in data and len(data['items']) > 0:
                            item = data['items'][0]
                            snippet = item.get('snippet', {})
                            content_details = item.get('contentDetails', {})
                            
                            return {
                                'title': snippet.get('title'),
                                'description': snippet.get('description'),
                                'channel': snippet.get('channelTitle'),
                                'item_count': content_details.get('itemCount'),
                                'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url')
                            }
                    logger.warning(f"YouTube API returned status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching playlist metadata: {e}")
            return None

class CloudUploader:
    """Handle cloud storage uploads using GoFile"""
    def __init__(self):
        # GoFile API Token
        self.gofile_token = "9k87oUoh6ljjoTv6VblzLABCD8t07SIL"
        if not self.gofile_token:
            logger.error("GOFILE_API_TOKEN not set! Uploads will fail.")
        
        self.timeout = aiohttp.ClientTimeout(total=600)  # 10 minutes

    @staticmethod
    def safe_filename(filename: str, max_length: int = 240) -> str:
        """Normalize and truncate filename to max_length (including extension) for safety."""
        base, ext = os.path.splitext(filename)
        base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
        base = re.sub(r'[\s/\\:*?"<>|]+', '_', base)  # Clean up file name - include pipe and other invalid chars
        ext = ext[:10] if len(ext) > 10 else ext
        max_base_len = max_length - len(ext)
        if len(base) > max_base_len:
            base = base[:max_base_len]
        return base + ext

    async def get_best_server(self, session: aiohttp.ClientSession) -> Optional[str]:
        """Find the best GoFile server to upload to."""
        try:
            # This endpoint doesn't require a token
            async with session.get("https://api.gofile.io/servers", timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('status') == 'ok':
                        # Get the first server in the list, which is the recommended one
                        server = data['data']['servers'][0]['name']
                        return server
                
                logger.error(f"GoFile failed to get server: {response.status} {await response.text()}")
                return None
        except Exception as e:
            logger.error(f"GoFile get_best_server error: {e}")
            return None

    async def upload_to_gofile(self, file_path: Path, progress_callback=None) -> Optional[str]:
        """Uploads a file to GoFile and returns the download page link."""
        if not self.gofile_token:
            logger.error("GoFile token not set. Cannot upload.")
            return None
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                
                # --- Step 1: Get the best server ---
                if progress_callback:
                    # Support both async and sync callbacks
                    import inspect
                    if inspect.iscoroutinefunction(progress_callback):
                        await progress_callback(10, "Finding best upload server...")
                    else:
                        progress_callback(10, "Finding best upload server...")
                
                server = await self.get_best_server(session)
                if not server:
                    logger.error("Could not find a GoFile server.")
                    return None

                if progress_callback:
                    # Support both async and sync callbacks
                    if inspect.iscoroutinefunction(progress_callback):
                        await progress_callback(25, f"Uploading to GoFile server: {server}...")
                    else:
                        progress_callback(25, f"Uploading to GoFile server: {server}...")

                # --- Step 2: Upload the file ---
                with open(file_path, "rb") as f:
                    data = aiohttp.FormData()
                    # Add the file
                    data.add_field("file", 
                                   f, 
                                   filename=self.safe_filename(file_path.name),
                                   content_type='application/octet-stream')
                    
                    # Add the token to associate the file with your account
                    data.add_field("token", self.gofile_token)

                    upload_url = f"https://{server}.gofile.io/uploadFile"
                    
                    async with session.post(upload_url, data=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            if result.get('status') == 'ok':
                                if progress_callback:
                                    # Support both async and sync callbacks
                                    if inspect.iscoroutinefunction(progress_callback):
                                        await progress_callback(100, "Upload complete!")
                                    else:
                                        progress_callback(100, "Upload complete!")
                                # Return the download page URL
                                return result.get('data', {}).get('downloadPage')
                            else:
                                logger.error(f"GoFile upload failed: {result.get('data')}")
                                return None
                        else:
                            logger.error(f"GoFile upload error: {response.status} {await response.text()}")
                            return None
                            
        except Exception as e:
            logger.error(f"GoFile upload_to_gofile error: {e}", exc_info=True)
            return None

    async def upload_file(self, file_path: Path, progress_callback=None) -> Optional[str]:
        """Tries to upload the file to GoFile."""
        
        # This wrapper function calls the main upload function and passes the progress_callback
        result = await self.upload_to_gofile(file_path, progress_callback)
        
        if result:
            return result
        
        logger.warning("GoFile upload failed.")
        return None

class MusicTelegramBot:
    def __init__(self):
        # Telegram bot token
        self.telegram_token = "7671153442:AAFb4RQmmldypIYImtldATmSSRKdqJE7oAg"
        if not self.telegram_token:
            logger.error("TELEGRAM_BOT_TOKEN not set!")
            raise ValueError("TELEGRAM_BOT_TOKEN is not set.")
            
        self.api_url = f"https://api.telegram.org/bot{self.telegram_token}"
        
        # YouTube API v3 client
        self.youtube_api = YouTubeAPIv3("AIzaSyAnHq_a1HOrRanQAfTbXZww9Jo3ztM7tF8")
        
        # Track active downloads
        self.active_downloads: Set[int] = set()
        
        # File size threshold for cloud upload (50MB)
        self.file_size_threshold = 50 * 1024 * 1024
        
        # Create temporary directory
        self.temp_dir = Path(tempfile.gettempdir()) / "mbot"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Progress tracking
        self.download_progress: Dict[int, Dict] = {}
        
        # Last update ID for polling
        self.last_update_id = 0
        
        # Cloud uploader
        self.uploader = CloudUploader()
        
        # Initialize FFmpeg
        self._setup_ffmpeg()
        
        # User conversation state for YouTube downloads (state machine)
        self.user_state: Dict[int, Dict] = {}  # user_id -> {'url_info': ..., 'state': ...}
        
        # Track user-specific tasks for cancellation
        self.user_tasks: Dict[int, asyncio.Task] = {}
        
    def _setup_ffmpeg(self):
        """Setup FFmpeg for audio processing"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("FFmpeg is available and ready")
            else:
                logger.warning("FFmpeg check failed")
        except FileNotFoundError:
            logger.error("FFmpeg not found in PATH")
        # Check yt-dlp
        try:
            result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"yt-dlp version: {result.stdout.strip()}")
            else:
                logger.warning("yt-dlp check failed")
        except FileNotFoundError:
            logger.error("yt-dlp not found in PATH")
    
    async def get_youtube_resolutions(self, url: str) -> List[int]:
        """
        Use yt-dlp -j to get a list of available video heights (resolutions).
        """
        try:
            cmd = [
                'yt-dlp',
                '-j',  # Get JSON output
                '--no-playlist',  # Only get info for the single video
                '--extractor-args', 'youtube:player_client=android,web',
                '--user-agent', 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                url
            ]
            
            logger.info(f"Getting formats for: {url}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                resolutions = set()
                # stdout may contain multiple JSON objects (one per video info)
                # We only care about the first one.
                first_line = stdout.decode('utf-8', errors='ignore').splitlines()[0]
                info = json.loads(first_line)
                
                for fmt in info.get('formats', []):
                    # We only want mp4 videos that have video data
                    if fmt.get('vcodec') != 'none' and fmt.get('ext') == 'mp4' and fmt.get('height'):
                        resolutions.add(fmt['height'])
                
                if not resolutions:  # Fallback for some formats
                    for fmt in info.get('formats', []):
                        if fmt.get('vcodec') != 'none' and fmt.get('height'):
                            resolutions.add(fmt['height'])

                return sorted(list(resolutions))  # Return a sorted list, e.g., [144, 240, 360, 720, 1080]
            else:
                logger.error(f"yt-dlp failed to get formats: {stderr.decode()}")
                return []
        except Exception as e:
            logger.error(f"Error getting YouTube resolutions: {e}")
            return []
    
    async def get_youtube_playlist_title(self, url: str) -> Optional[str]:
        """
        Use yt-dlp --dump-single-json to get the title of a playlist.
        """
        try:
            cmd = [
                'yt-dlp',
                '--dump-single-json',  # Get all info in one JSON object
                '--yes-playlist',      # Ensure it treats it as a playlist
                '--no-warnings',
                '--extractor-args', 'youtube:player_client=android,web',
                '--user-agent', 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                url
            ]
            
            logger.info(f"Getting playlist title for: {url}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Set a timeout for safety (e.g., 30 seconds)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.error("Timeout getting playlist title.")
                process.kill()
                return None

            if process.returncode == 0:
                info = json.loads(stdout)
                # Check if it's a playlist (has 'entries') or a single video
                if info.get('_type') == 'playlist' or 'entries' in info:
                    return info.get('title', 'YouTube Playlist')
                else:
                    # It's a single video, return its title
                    return info.get('title', 'YouTube Video')
            else:
                logger.error(f"yt-dlp failed to get playlist title: {stderr.decode()}")
                return None
        except Exception as e:
            logger.error(f"Error getting YouTube playlist title: {e}")
            return None
    
    async def send_message(self, chat_id: int, text: str, parse_mode: str = None, reply_markup: dict = None) -> Optional[Dict]:
        """Send message to Telegram chat"""
        data = {
            'chat_id': chat_id,
            'text': text
        }
        if parse_mode:
            data['parse_mode'] = parse_mode
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.api_url}/sendMessage", json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get('result')
                    else:
                        logger.error(f"Failed to send message: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
    
    async def edit_message(self, chat_id: int, message_id: int, text: str, parse_mode: str = None) -> bool:
        """Edit existing message"""
        data = {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text
        }
        if parse_mode:
            data['parse_mode'] = parse_mode

        timeout = aiohttp.ClientTimeout(total=30)
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(f"{self.api_url}/editMessageText", json=data) as response:
                        return response.status == 200
            except Exception as e:
                logger.error(f"Error editing message (attempt {attempt+1}): {e}")
                await asyncio.sleep(2)
        return False
    
    async def edit_message_reply_markup(self, chat_id: int, message_id: int, reply_markup: dict) -> bool:
        """Edit message reply markup (buttons) only"""
        data = {
            'chat_id': chat_id,
            'message_id': message_id,
            'reply_markup': json.dumps(reply_markup)
        }

        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.api_url}/editMessageReplyMarkup", json=data) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Error editing message reply markup: {e}")
        return False
    
    async def send_audio(self, chat_id: int, file_path: Path, caption: str = None) -> bool:
        """Send audio file to Telegram chat"""
        try:
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('chat_id', str(chat_id))
                data.add_field('audio', f, filename=file_path.name)
                if caption:
                    data.add_field('caption', caption)
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{self.api_url}/sendAudio", data=data) as response:
                        return response.status == 200
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            return False
    
    async def get_updates(self) -> List[Dict]:
        """Get updates from Telegram"""
        try:
            params = {
                'offset': self.last_update_id + 1,
                'timeout': 10
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/getUpdates", params=params) as response:
                    if response.status == 409:
                        logger.error("409 Conflict: Another instance of the bot is running. Only one polling instance is allowed.")
                        return []
                    if response.status == 200:
                        result = await response.json()
                        updates = result.get('result', [])
                        if updates:
                            self.last_update_id = updates[-1]['update_id']
                        return updates
                    else:
                        logger.error(f"Failed to get updates: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
            return []
    
    def extract_spotify_url_info(self, url: str) -> Optional[Dict]:
        """Extract Spotify URL information"""
        spotify_pattern = r'https://open\.spotify\.com/(track|album|playlist|artist)/([a-zA-Z0-9]+)'
        match = re.search(spotify_pattern, url)
        
        if match:
            return {
                'platform': 'spotify',
                'type': match.group(1),
                'id': match.group(2),
                'url': url
            }
        return None
    
    def extract_youtube_url_info(self, url: str) -> Optional[Dict]:
        """Extract YouTube URL information"""
        youtube_pattern = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|playlist\?list=)?([a-zA-Z0-9_\-]+)'
        match = re.search(youtube_pattern, url)
        if match:
            # Determine type
            if 'playlist?list=' in url:
                yt_type = 'playlist'
                yt_id = re.search(r'list=([a-zA-Z0-9_\-]+)', url).group(1)
            else:
                yt_type = 'video'
                yt_id = re.search(r'(v=|youtu\.be/)([a-zA-Z0-9_\-]+)', url)
                yt_id = yt_id.group(2) if yt_id else 'unknown'
            return {
                'platform': 'youtube',
                'type': yt_type,
                'id': yt_id,
                'url': url
            }
        return None

    async def extract_spotify_metadata(self, spotify_url: str) -> Optional[Dict]:
        """Extract metadata from Spotify URL using SpotDL's list feature"""
        try:
            cmd = ['spotdl', 'list', spotify_url]
            logger.info(f"Extracting metadata with: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and stdout:
                output = stdout.decode('utf-8', errors='ignore').strip()
                logger.info(f"SpotDL metadata output: {output}")
                
                # Parse the output to extract track info
                lines = output.split('\n')
                for line in lines:
                    if ' - ' in line and not line.startswith('Found'):
                        # Format is usually "Artist - Track Name"
                        return {
                            'search_term': line.strip(),
                            'artist_song': line.strip()
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting Spotify metadata: {e}")
            return None

    async def _process_spotdl_output(self, process, user_id: int, chat_id: int, output_dir: Path, original_url: str = None, metadata: Dict = None) -> bool:
        """Process SpotDL output and handle progress tracking and error detection."""
        spotdl_failed = False
        lookup_error_detected = False
        fallback_called = False  # Track if we already called fallback
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line_str = line.decode(errors='ignore').strip()
            logger.info(f"SpotDL: {line_str}")
            if user_id is not None and user_id in self.download_progress:
                # Detect playlist info and send to user (only once)
                playlist_info_match = re.search(r'Found (\d+) songs? in (.+?) \((?:Playlist|Album|Artist)\)', line_str)
                if playlist_info_match and not self.download_progress[user_id].get('playlist_info_sent', False):
                    total_songs = int(playlist_info_match.group(1))
                    playlist_name = unicodedata.normalize("NFKD", playlist_info_match.group(2)).encode("ascii", "ignore").decode("ascii")
                    self.download_progress[user_id]['total_tracks'] = total_songs
                    self.download_progress[user_id]['playlist_name'] = playlist_name
                    self.download_progress[user_id]['playlist_info_sent'] = True  # Mark as sent
                    await self.send_message(
                        chat_id,
                        f"🎶 **Playlist:** {playlist_name}\n📀 **Total Songs:** {total_songs}",
                        parse_mode="Markdown"
                    )
                # Try to match progress line
                match = re.search(r'Downloading (\d+) of (\d+): (.+)', line_str)
                if match:
                    completed = int(match.group(1))
                    total = int(match.group(2))
                    current_track = match.group(3)
                    percentage = int((completed / total) * 100)
                    self.download_progress[user_id]['percentage'] = percentage
                    self.download_progress[user_id]['current_track'] = current_track
                    self.download_progress[user_id]['completed_tracks'] = completed
                    self.download_progress[user_id]['total_tracks'] = total
                else:
                    # Detect "Downloaded ..." lines and increment completed_tracks
                    match2 = re.search(r'Downloaded "(.*?)":', line_str)
                    if match2:
                        if self.download_progress[user_id]['completed_tracks'] < self.download_progress[user_id]['total_tracks']:
                            self.download_progress[user_id]['completed_tracks'] += 1
                        total = self.download_progress[user_id].get('total_tracks', 1)
                        percentage = int((self.download_progress[user_id]['completed_tracks'] / total) * 100)
                        self.download_progress[user_id]['percentage'] = min(percentage, 100)
                        self.download_progress[user_id]['current_track'] = match2.group(1)
                # Detect SpotDL errors and update status
                if any(error in line_str for error in ["AudioProviderError", "LookupError", "KeyError", "DownloaderError", "YT-DLP download error"]):
                    logger.warning(f"SpotDL error detected: {line_str}")
                    if "YT-DLP download error" in line_str or "AudioProviderError" in line_str:
                        # Mark as failed but continue to let the process finish
                        spotdl_failed = True
                        self.download_progress[user_id]['status'] = 'error'
                        # Extract error message for user feedback
                        error_msg = line_str.strip()
                        if len(error_msg) > 100:
                            error_msg = error_msg[:100] + "..."
                        self.download_progress[user_id]['current_track'] = f"Error: {error_msg}"
                    elif "LookupError" in line_str or "KeyError" in line_str:
                        if not fallback_called:  # Only call fallback once
                            lookup_error_detected = True
                            spotdl_failed = True
                            fallback_called = True
                            # Use extracted metadata for better search terms
                            search_term = "Unknown track"
                            
                            # Priority 1: Use metadata if available
                            if metadata and 'search_term' in metadata:
                                search_term = metadata['search_term']
                            # Priority 2: Extract from error message
                            elif 'No results found for song:' in line_str:
                                error_match = re.search(r'No results found for song: (.+)', line_str)
                                if error_match:
                                    search_term = error_match.group(1).strip()
                            # Priority 3: Use original URL if it's a Spotify track
                            elif original_url and 'spotify.com/track' in original_url:
                                search_term = original_url
                            # Priority 4: Fallback to current track name if available
                            else:
                                current_track = self.download_progress[user_id].get('current_track', 'Unknown track')
                                if current_track not in ['Initializing...', 'Extracting track info...', 'Found: ']:
                                    search_term = current_track
                                elif original_url:
                                    search_term = original_url
                            
                            # Silently fallback to yt-dlp without notifying user
                            await self.fallback_download_with_ytdlp(search_term, output_dir, user_id, chat_id, playlist_mode=False)
        
        return spotdl_failed

    async def run_spotdl_command(self, url: str, output_dir: str, user_id: int, chat_id: int, metadata: Dict = None) -> bool:
        """Run spotdl command with live progress bar. No fallback to yt-dlp. Only SpotDL is used."""
        try:
            # Convert output_dir to Path if it's a string
            if isinstance(output_dir, str):
                output_dir = Path(output_dir)
            cmd = [
                'spotdl',
                'download',
                url,
                '--output', str(output_dir),
                '--format', 'mp3',  # Use MP3 for better compatibility
                '--bitrate', '320k',  # Force 320kbps (highest MP3 quality)
                '--threads', '2',  # Reduce threads to avoid hanging
                '--max-retries', '2',  # Limit retries
                '--print-errors',  # Show errors clearly
                '--no-cache'  # Avoid cache-related issues
            ]
            ffmpeg_path = shutil.which('ffmpeg')
            if ffmpeg_path:
                cmd.extend(['--ffmpeg', ffmpeg_path])
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(output_dir)
            )
            progress_task = asyncio.create_task(self.update_progress_periodically(user_id))
            spotdl_failed = False
            lookup_error_detected = False
            
            # Add timeout for the entire SpotDL process (2 minutes - faster fallback)
            timeout_seconds = 120
            try:
                spotdl_failed = await asyncio.wait_for(self._process_spotdl_output(process, user_id, chat_id, output_dir, url, metadata), timeout_seconds)
            except asyncio.TimeoutError:
                logger.warning("SpotDL process timed out after %s seconds, switching to yt-dlp fallback", timeout_seconds)
                process.kill()
                # Silently switch to fallback without notifying user
                if user_id in self.download_progress:
                    self.download_progress[user_id]['status'] = 'downloading'
                    self.download_progress[user_id]['current_track'] = 'Processing...'
                    await self.update_progress_message(user_id)
                # Try yt-dlp fallback with metadata if available
                search_term = url
                if metadata and 'search_term' in metadata:
                    search_term = metadata['search_term']
                return await self.fallback_download_with_ytdlp(search_term, output_dir, user_id, chat_id, playlist_mode=True)
                
            progress_task.cancel()
            return_code = await process.wait()
            downloaded_files = list(output_dir.glob("*"))
            logger.info("Downloaded files: %s", [f.name for f in downloaded_files])

            if return_code != 0 and not downloaded_files:
                # Only call fallback if we don't already have downloaded files
                existing_files = list(output_dir.glob("*.mp3")) + list(output_dir.glob("*.m4a")) + list(output_dir.glob("*.flac"))
                if not existing_files:
                    logger.error("SpotDL failed with return code %s and no files were downloaded.", return_code)
                    spotdl_failed = True
                    # Send more helpful error message to user
                    if user_id in self.download_progress:
                        self.download_progress[user_id]['status'] = 'downloading'
                        self.download_progress[user_id]['current_track'] = 'Finding alternative download method...'
                        await self.update_progress_message(user_id)
                        # Try fallback with yt-dlp
                        search_term = url
                        if metadata and 'search_term' in metadata:
                            search_term = metadata['search_term']
                        # For individual tracks, don't use playlist mode
                        fallback_success = await self.fallback_download_with_ytdlp(search_term, Path(output_dir), user_id, chat_id, playlist_mode=False)
                        return fallback_success
                else:
                    logger.info("Files were downloaded despite SpotDL errors.")
            elif return_code != 0 and downloaded_files:
                logger.warning("SpotDL had partial errors (code %s), but some files were downloaded.", return_code)
                await self.send_message(chat_id, "⚠️ Some tracks were skipped, but the rest were downloaded.")
            else:
                logger.info("SpotDL finished cleanly.")

            logger.info(f"Downloaded: {len(downloaded_files)} tracks.")
            # Ensure completed_tracks == total_tracks
            if user_id is not None and user_id in self.download_progress:
                if self.download_progress[user_id]['completed_tracks'] < self.download_progress[user_id]['total_tracks']:
                    self.download_progress[user_id]['completed_tracks'] = self.download_progress[user_id]['total_tracks']
                self.download_progress[user_id]['percentage'] = 100
                self.download_progress[user_id]['status'] = 'completed'
                await self.update_progress_message(user_id)
            if user_id is not None and user_id in self.download_progress:
                if self.download_progress[user_id]['completed_tracks'] == 0:
                    await self.edit_message(
                        self.download_progress[user_id]['chat_id'],
                        self.download_progress[user_id]['message_id'],
                        "❌ Download failed for all tracks. Please check your link or try again later."
                    )
            return not spotdl_failed or len(list(output_dir.glob("*.mp3"))) > 0  # Success if SpotDL worked OR if we have downloaded files
        except Exception as e:
            logger.error(f"Error running spotdl: {e}")
            return False

    async def fallback_download_with_ytdlp(self, track_name_or_url: str, output_dir: Path, user_id: int, chat_id: int, playlist_mode: bool = False) -> bool:
        """Enhanced fallback: Download with yt-dlp using intelligent URL/search handling."""
        try:
            # Determine if this is a Spotify URL or search term
            is_spotify_url = 'spotify.com' in track_name_or_url
            # Track whether cookies were successfully added to the yt-dlp command
            cookie_success = False
            
            if is_spotify_url and playlist_mode:
                # For Spotify playlists/albums - this should rarely be used for single tracks
                search_term = track_name_or_url if not track_name_or_url.startswith('http') else "tamil songs 90s"
                
                yt_cmd = [
                    'yt-dlp',
                    '-x', '--audio-format', 'mp3',
                    '--audio-quality', '320K',  # Explicit 320kbps bitrate
                    '--format', 'bestaudio[ext=m4a]/bestaudio/best',  # Prefer best audio quality
                    '--no-playlist',  # Avoid downloading entire YouTube playlists
                    '--max-downloads', '1',  # Limit to single track
                    '-o', str(output_dir / '%(title)s.%(ext)s'),
                    f"ytsearch1:{search_term}"  # Search for only 1 result
                ]
                
                # Add cookies if available (try different browsers)
                try:
                    yt_cmd.extend(['--cookies-from-browser', 'edge'])
                    yt_cmd.extend(['--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'])
                    cookie_success = True
                except:
                    logger.warning("Edge cookies not available, trying without cookies")
            elif playlist_mode and not is_spotify_url:
                # Non-Spotify playlist URL
                yt_cmd = [
                    'yt-dlp',
                    '--extract-audio',
                    '--audio-format', 'mp3',
                    '--audio-quality', '320K',  # Explicit 320kbps bitrate
                    '--embed-metadata',
                    '--embed-thumbnail',
                    '--ignore-errors',
                    '--max-downloads', '50',  # Reasonable limit
                    '--format', 'bestaudio[ext=m4a]/bestaudio/best',  # Prefer best audio quality
                    '-o', str(output_dir / '%(title)s.%(ext)s'),
                    track_name_or_url
                ]
                
                # Try to add cookies for direct URLs
                if track_name_or_url.startswith('http'):
                    try:
                        yt_cmd.extend(['--cookies-from-browser', 'edge'])
                        yt_cmd.extend(['--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'])
                        cookie_success = True
                    except:
                        logger.warning("Could not add browser cookies")
            else:
                # Single track search
                search_term = track_name_or_url
                if is_spotify_url:
                    # If it's a Spotify URL but we don't have metadata, try to extract some info
                    if 'spotify.com/track' in track_name_or_url:
                        # Try to make a generic but relevant search
                        search_term = "popular song 2024"  # More specific than "trending music"
                    else:
                        search_term = track_name_or_url
                
                yt_cmd = [
                    'yt-dlp',
                    '--extract-audio',
                    '--audio-format', 'mp3',
                    '--audio-quality', '320K',  # Explicit 320kbps bitrate
                    '--embed-metadata',
                    '--embed-thumbnail',
                    '--no-playlist',
                    '--max-downloads', '1',  # Limit to 1 result for single tracks
                    '--format', 'bestaudio[ext=m4a]/bestaudio/best',  # Prefer best audio quality
                    '-o', str(output_dir / '%(title)s.%(ext)s'),
                    f"ytsearch1:{search_term}"  # Always search with ytsearch1 for single tracks
                ]
                
                yt_cmd = [
                    'yt-dlp',
                    '--extract-audio',
                    '--audio-format', 'mp3',
                    '--audio-quality', '320K',  # Explicit 320kbps bitrate
                    '--embed-metadata',
                    '--embed-thumbnail',
                    '--no-playlist',
                    '--max-downloads', '1',  # Limit to 1 result for single tracks
                    '--format', 'bestaudio[ext=m4a]/bestaudio/best',  # Prefer best audio quality
                    '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    '--sleep-requests', '1',  # Small delay between requests
                    '--no-warnings',
                    '-o', str(output_dir / '%(title)s.%(ext)s'),
                    f"ytsearch1:{search_term}"  # Always search with ytsearch1 for single tracks
                ]
                
                logger.info("Using basic yt-dlp without cookies")
            
            logger.info(f"Running yt-dlp fallback: {' '.join(yt_cmd)}")
            
            # Update progress
            if user_id in self.download_progress:
                self.download_progress[user_id]['current_track'] = 'Searching on YouTube...'
                self.download_progress[user_id]['status'] = 'downloading'
                await self.update_progress_message(user_id)
            
            process = await asyncio.create_subprocess_exec(
                *yt_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(output_dir)
            )
            
            # Process output with timeout
            try:
                await asyncio.wait_for(self._process_ytdlp_output(process, user_id), 300)  # 5 minute timeout
            except asyncio.TimeoutError:
                logger.warning("yt-dlp fallback timed out")
                process.kill()
                await self.send_message(chat_id, "⏰ YouTube download also timed out. Please try again later.")
                return False
            
            return_code = await process.wait()
            downloaded_files = list(output_dir.glob("*.mp3")) + list(output_dir.glob("*.flac"))  # Look for MP3 and FLAC files
            logger.info("yt-dlp fallback downloaded files: %s", [f.name for f in downloaded_files])
            
            if return_code == 0 and downloaded_files:
                # Don't send success message here - let the main process handle final messaging
                if user_id in self.download_progress:
                    self.download_progress[user_id]['status'] = 'completed'
                    self.download_progress[user_id]['percentage'] = 100
                    self.download_progress[user_id]['current_track'] = f'Downloaded {len(downloaded_files)} tracks'
                    await self.update_progress_message(user_id)
                return True
            else:
                # Check if we have any files despite the error
                all_files = list(output_dir.glob("*.mp3")) + list(output_dir.glob("*.flac")) + list(output_dir.glob("*.m4a"))
                if not all_files and cookie_success:
                    # If cookies were used and we got no files, try again without cookies
                    logger.info("First attempt with cookies failed, trying without cookies...")
                    
                    # Build advanced fallback command with anti-detection measures
                    clean_search = track_name_or_url.replace('ytsearch1:', '').strip()
                    simple_cmd = [
                        'yt-dlp',
                        '--extract-audio',
                        '--audio-format', 'mp3',
                        '--audio-quality', '320K',
                        '--embed-metadata',
                        '--no-playlist',
                        '--max-downloads', '1',
                        '--format', 'bestaudio[ext=m4a]/bestaudio/best',
                        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.76',
                        '--sleep-requests', '3',  # Longer delay for fallback
                        '--sleep-interval', '2',
                        '--extractor-args', 'youtube:player_client=web,mweb',  # Use mobile web client
                        '--no-warnings',
                        '--ignore-errors',
                        '-o', str(output_dir / '%(title)s.%(ext)s'),
                        f"ytsearch1:{clean_search}"
                    ]
                    
                    # Try the simple command
                    try:
                        logger.info(f"Running simple yt-dlp: {' '.join(simple_cmd)}")
                        simple_process = await asyncio.create_subprocess_exec(
                            *simple_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.STDOUT,
                            cwd=str(output_dir)
                        )
                        
                        # Process output for simple command
                        await asyncio.wait_for(self._process_ytdlp_output(simple_process, user_id), 180)  # 3 min timeout
                        return_code = await simple_process.wait()
                        
                        # Check for files again
                        all_files = list(output_dir.glob("*.mp3")) + list(output_dir.glob("*.flac")) + list(output_dir.glob("*.m4a"))
                        
                        if return_code == 0 and all_files:
                            logger.info("Advanced fallback succeeded!")
                            if user_id in self.download_progress:
                                self.download_progress[user_id]['status'] = 'completed'
                                self.download_progress[user_id]['percentage'] = 100
                                self.download_progress[user_id]['current_track'] = f'Downloaded {len(all_files)} tracks'
                                await self.update_progress_message(user_id)
                            return True
                        else:
                            # Third fallback: Try with different search approach
                            logger.info("Trying final fallback with different search method...")
                            
                            # Extract just the song title for simpler search
                            song_parts = clean_search.split(' - ')
                            if len(song_parts) >= 2:
                                simple_search = song_parts[1].split('(')[0].strip()  # Get just the song name
                            else:
                                simple_search = clean_search.split('(')[0].strip()
                            
                            final_cmd = [
                                'yt-dlp',
                                '--extract-audio',
                                '--audio-format', 'mp3',
                                '--audio-quality', '320K',
                                '--no-playlist',
                                '--max-downloads', '1',
                                '--format', 'bestaudio/best',
                                '--user-agent', 'Mozilla/5.0 (Android 11; Mobile; rv:105.0) Gecko/105.0 Firefox/105.0',  # Mobile user agent
                                '--sleep-requests', '5',
                                '--extractor-args', 'youtube:player_client=android',  # Android client
                                '--ignore-errors',
                                '--no-warnings',
                                '-o', str(output_dir / '%(title)s.%(ext)s'),
                                f"ytsearch1:{simple_search} song"
                            ]
                            
                            try:
                                logger.info(f"Running final fallback: {' '.join(final_cmd[:10])}... (simplified search)")
                                final_process = await asyncio.create_subprocess_exec(
                                    *final_cmd,
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.STDOUT,
                                    cwd=str(output_dir)
                                )
                                
                                await asyncio.wait_for(self._process_ytdlp_output(final_process, user_id), 120)
                                return_code = await final_process.wait()
                                
                                # Final check for files
                                all_files = list(output_dir.glob("*.mp3")) + list(output_dir.glob("*.flac")) + list(output_dir.glob("*.m4a"))
                                if return_code == 0 and all_files:
                                    logger.info("Final fallback succeeded!")
                                    if user_id in self.download_progress:
                                        self.download_progress[user_id]['status'] = 'completed'
                                        self.download_progress[user_id]['percentage'] = 100
                                        self.download_progress[user_id]['current_track'] = f'Downloaded {len(all_files)} tracks'
                                        await self.update_progress_message(user_id)
                                    return True
                            except Exception as e:
                                logger.warning(f"Final fallback also failed: {e}")
                    except Exception as e:
                        logger.warning(f"Advanced fallback failed: {e}")
                
                # Final check - if still no files, show error
                if not all_files:
                    logger.warning("yt-dlp fallback failed or no files downloaded")
                    await self.send_message(chat_id, 
                        "❌ **YouTube is currently blocking downloads.**\n\n"
                        "**This happens because:**\n"
                        "• YouTube has strict anti-automation measures\n"
                        "• Your region may have additional restrictions\n"
                        "• High traffic periods trigger more blocking\n\n"
                        "**Try again later or use a different playlist.**")
                return len(all_files) > 0  # Return True if we have files, even if yt-dlp reported errors
                
        except Exception as e:
            logger.error(f"yt-dlp fallback error: {e}")
            await self.send_message(chat_id, f"❌ YouTube fallback error: {str(e)[:100]}")
            return False

    async def _process_ytdlp_output(self, process, user_id: int):
        """Process yt-dlp output and update progress."""
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line_str = line.decode(errors='ignore').strip()
            logger.info(f"yt-dlp: {line_str}")
            
            # Check for cookie database access errors (informational, not fatal)
            if "Could not copy Chrome cookie database" in line_str or "cookie database" in line_str.lower():
                logger.warning("Browser cookie access failed - continuing without cookies")
                continue  # Continue processing, this is just a warning
            
            # Check for other browser cookie warnings
            if "See  https://github.com/yt-dlp/yt-dlp/issues/7271" in line_str:
                logger.info("Cookie database access issue - this is expected on some systems")
                continue
            
            # Check for cookie extraction messages (informational)
            if "Extracting cookies from" in line_str:
                logger.info("Attempting to extract browser cookies")
                continue
            
            # Check for YouTube bot detection
            if "Sign in to confirm you're not a bot" in line_str or "bot" in line_str.lower():
                logger.warning("YouTube bot detection encountered")
                if user_id in self.download_progress:
                    chat_id = self.download_progress[user_id].get('chat_id')
                    if chat_id:
                        await self.send_message(
                            chat_id,
                            "🤖 **YouTube is blocking automated downloads right now.**\\n\\n"
                            "**This is temporary and happens when:**\\n"
                            "• YouTube detects too many automated requests\\n"
                            "• Your IP address has been flagged temporarily\\n"
                            "• YouTube's anti-bot systems are extra strict\\n\\n"
                            "**Solutions:**\\n"
                            "• ✅ Wait 15-30 minutes and try again\\n"
                            "• ✅ Try different songs from your playlist\\n"
                            "• ✅ Use shorter, simpler search terms\\n"
                            "• ✅ Try again during off-peak hours\\n\\n"
                            "⏰ **The bot will keep trying other songs in your playlist!**",
                            parse_mode="Markdown"
                        )
                return  # Stop processing
            
            if user_id in self.download_progress:
                # Update progress based on yt-dlp output
                if "Downloading" in line_str:
                    self.download_progress[user_id]['current_track'] = 'Downloading from YouTube...'
                elif "Processing" in line_str:
                    self.download_progress[user_id]['current_track'] = 'Processing audio...'
                elif "Destination:" in line_str:
                    # Extract filename from destination
                    parts = line_str.split('Destination: ')
                    if len(parts) > 1:
                        filename = Path(parts[1]).stem
                        self.download_progress[user_id]['current_track'] = f'Downloaded: {filename}'

    async def parse_ytdlp_output(self, user_id: int, output: str) -> None:
        """Parse yt-dlp output for progress updates (YouTube)."""
        if user_id not in self.download_progress:
            return
        progress_info = self.download_progress[user_id]
        import re
        # --- NEW: Accurate playlist progress tracking ---
        match = re.search(r'Downloading item (\d+) of (\d+)', output)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            progress_info['completed_tracks'] = current - 1
            progress_info['total_tracks'] = total
        # Look for percentage in yt-dlp output
        match2 = re.search(r'\[download\]\s+(\d+\.\d+)%', output)
        if match2:
            percentage = float(match2.group(1))
            progress_info['percentage'] = percentage
            progress_info['status'] = 'downloading'
        # Look for current file name
        match3 = re.search(r'Destination: (.+)', output)
        if match3:
            import os
            current_track = os.path.basename(match3.group(1))
            progress_info['current_track'] = current_track
        # Mark as completed if 100%
        if '[download] 100%' in output or '[ExtractAudio]' in output:
            progress_info['percentage'] = 100
            progress_info['status'] = 'completed'

    async def download_youtube_with_ytdlp(self, url: str, output_dir: Path, fmt: str, user_id: int = None, chat_id: int = None) -> bool:
        """Download YouTube video or playlist using yt-dlp with dynamic format selection."""
        try:
            # Get playlist metadata first (number of entries)
            playlist_total = 1
            if "playlist" in url:
                try:
                    logger.info("Fetching playlist metadata...")
                    meta_cmd = ["yt-dlp", "--flat-playlist", "--print", "%(id)s", url]
                    result = subprocess.run(meta_cmd, capture_output=True, text=True)
                    video_ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                    playlist_total = len(video_ids)
                    logger.info(f"Playlist contains {playlist_total} videos.")
                    if user_id in self.download_progress:
                        self.download_progress[user_id]['total_tracks'] = playlist_total
                        self.download_progress[user_id]['completed_tracks'] = 0
                except Exception as e:
                    logger.error(f"Failed to get playlist count: {e}")

            out_tpl = str(output_dir / '%(title)s.%(ext)s')
            
            # --- MODIFIED PART ---
            if fmt == 'mp3':
                # MP3 Audio Command
                cmd = [
                    'yt-dlp',
                    '--ignore-errors', '--no-abort-on-error', '--no-check-certificate',
                    '--extractor-args', 'youtube:player_client=android,web',
                    '--user-agent', 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                    '-f', 'bestaudio[ext=m4a]/bestaudio/best',
                    '--audio-quality', '320K',
                    '--audio-format', 'mp3',
                    '--extract-audio',
                    '--embed-metadata', '--embed-thumbnail',
                    '-o', out_tpl,
                    url
                ]
            elif fmt == 'flac':
                # FLAC Audio Command
                cmd = [
                    'yt-dlp',
                    '--ignore-errors', '--no-abort-on-error', '--no-check-certificate',
                    '--extractor-args', 'youtube:player_client=android,web',
                    '--user-agent', 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                    '-f', 'bestaudio[acodec^=opus]/bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
                    '--audio-quality', '0',  # Lossless
                    '--audio-format', 'flac',
                    '--extract-audio',
                    '--embed-metadata', '--embed-thumbnail',
                    '-o', out_tpl,
                    url
                ]
            else:
                # This is a video download, fmt is the resolution (e.g., "720", "1080")
                try:
                    height = int(fmt)  # Validate that fmt is a number
                    
                    # This tells yt-dlp to get the best MP4 video AT OR BELOW the chosen height,
                    # plus the best MP4 audio, and merge them.
                    format_selector = f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                    
                    cmd = [
                        'yt-dlp',
                        '--ignore-errors', '--no-abort-on-error', '--no-check-certificate',
                        '--extractor-args', 'youtube:player_client=android,web',
                        '--user-agent', 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                        '-f', format_selector,  # Use the dynamic format selector
                        '--merge-output-format', 'mp4',
                        '--embed-metadata', '--embed-thumbnail', '--write-thumbnail',
                        '-o', out_tpl,
                        url
                    ]
                except ValueError:
                    logger.error(f"Invalid format passed to downloader: {fmt}")
                    if chat_id:
                        await self.send_message(chat_id, "❌ An internal error occurred. Invalid format.")
                    return False
            # --- END MODIFIED PART ---
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(output_dir)
            )
            
            progress_task = asyncio.create_task(self.update_progress_periodically(user_id))
            
            try:
                import re
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode(errors='ignore').strip()
                    logger.info(f"yt-dlp: {line_str}")
                    if user_id is not None and user_id in self.download_progress:
                        match = re.search(r'Downloading item (\d+) of (\d+)', line_str)
                        if match:
                            current = int(match.group(1))
                            total = int(match.group(2))
                            self.download_progress[user_id]['completed_tracks'] = current - 1
                            self.download_progress[user_id]['total_tracks'] = total
                        if '[ExtractAudio] Destination:' in line_str:
                            import os
                            filepath = line_str.split('Destination:')[-1].strip()
                            filename = os.path.basename(filepath)
                            self.download_progress[user_id]['current_track'] = filename
                        if '[ExtractAudio] Destination:' in line_str and 'completed_tracks' in self.download_progress[user_id]:
                            self.download_progress[user_id]['completed_tracks'] += 1
                            total = self.download_progress[user_id].get('total_tracks', 1)
                            percent = int((self.download_progress[user_id]['completed_tracks'] / total) * 100)
                            self.download_progress[user_id]['percentage'] = percent
                        await self.parse_ytdlp_output(user_id, line_str)
            finally:
                progress_task.cancel()

            return_code = await process.wait()
            
            downloaded_files = list(output_dir.glob("*"))
            logger.info("Downloaded files: %s", [f.name for f in downloaded_files])
            
            if return_code != 0 and not downloaded_files:
                logger.error("yt-dlp failed with return code %s and no files were downloaded.", return_code)
                await self.send_message(chat_id, "❌ Download failed. Please check the YouTube URL.")
                return False
            elif return_code != 0 and downloaded_files:
                logger.warning("yt-dlp had partial errors (code %s), but some files were downloaded.", return_code)
                await self.send_message(chat_id, "⚠️ Some videos were skipped, but the rest were downloaded.")
            else:
                logger.info("yt-dlp finished cleanly.")
            
            logger.info(f"Downloaded: {len(downloaded_files)} tracks.")
            if user_id is not None and user_id in self.download_progress:
                if self.download_progress[user_id]['completed_tracks'] < self.download_progress[user_id]['total_tracks']:
                    self.download_progress[user_id]['completed_tracks'] = self.download_progress[user_id]['total_tracks']
                self.download_progress[user_id]['percentage'] = 100
                self.download_progress[user_id]['status'] = 'completed'
                await self.update_progress_message(user_id)
            if user_id is not None and user_id in self.download_progress:
                if self.download_progress[user_id]['completed_tracks'] == 0:
                    await self.edit_message(
                        self.download_progress[user_id]['chat_id'],
                        self.download_progress[user_id]['message_id'],
                        "❌ Download failed for all tracks. Please check your link or try again later."
                    )
            return return_code == 0
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            if chat_id is not None:
                await self.send_message(chat_id, f"❌ yt-dlp error: {e}")
            return False

    def create_zip_file(self, directory: Path, zip_path: Path, password: str, loop=None, user_id: int = None) -> bool:
        """Create password-protected ZIP file from directory with progress callback."""
        try:
            media_files = (
                list(directory.rglob('*.mp3')) +
                list(directory.rglob('*.m4a')) +
                list(directory.rglob('*.flac')) +
                list(directory.rglob('*.mp4'))
            )
            total_files = len(media_files)
            if not media_files:
                logger.error("No media files (.mp3, .m4a, .flac, .mp4) found for ZIP creation.")
                return False

            with pyzipper.AESZipFile(zip_path, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zipf:
                zipf.setpassword(password.encode('utf-8'))  # Set random ZIP password
                for idx, file_path in enumerate(media_files, 1):
                    arcname = CloudUploader.safe_filename(file_path.name, 240)
                    with open(file_path, 'rb') as f:
                        zipf.writestr(arcname, f.read())
                    percent = int((idx / total_files) * 100)
                    if loop and not loop.is_closed():
                        if user_id in self.download_progress:
                            self.download_progress[user_id]['upload_progress'] = percent
                            self.download_progress[user_id]['upload_status'] = f"Compressing files... ({idx}/{total_files})"
                            future = asyncio.run_coroutine_threadsafe(
                                self.update_progress_message(user_id),
                                loop
                            )
                            # Don't wait for result to avoid blocking, but handle the future
                            future.add_done_callback(lambda f: None)
            logger.info(f"Password-protected ZIP created: {zip_path}")
            return True
        except Exception as e:
            logger.error(f"Error creating password-protected ZIP file: {e}")
            return False
    
    async def process_download(self, chat_id: int, user_id: int, url_info: Dict, yt_format: str = None) -> None:
        """Process music download with progress tracking (extended for YouTube)"""
        if user_id in self.active_downloads:
            await self.send_message(chat_id, "❌ You already have an active download. Please wait for it to complete.")
            return
        
        self.active_downloads.add(user_id)
        platform = url_info['platform']
        content_type = url_info['type']

        progress_message = await self.send_message(
            chat_id,
            f"🚀 Starting download...\n\n📺 **Platform:** {platform.title()}\n📁 **Type:** {content_type.title()}\n🔗 **URL:** {url_info['url']}"
        )

        if not progress_message:
            self.active_downloads.discard(user_id)
            return

        # Initialize progress dict with playlist_name
        self.download_progress[user_id] = {
            'chat_id': chat_id,
            'message_id': progress_message['message_id'],
            'current_track': 'Initializing...',
            'percentage': 0,
            'status': 'starting',
            'total_tracks': 1,
            'completed_tracks': 0,
            'upload_progress': 0,
            'upload_status': '',
            'platform': platform,
            'playlist_name': None,  # <-- IMPORTANT: Add this key
            'zip_password': str(random.randint(1000, 9999))  # <--- ADD THIS LINE
        }

        # --- NEW: Fetch Playlist Name ---
        try:
            if platform == 'youtube':
                # For YouTube, fetch title/playlist title before download
                await self.edit_message(chat_id, progress_message['message_id'], "Fetching video/playlist info...")
                title = await self.get_youtube_playlist_title(url_info['url'])
                if title:
                    self.download_progress[user_id]['playlist_name'] = title
                    msg_prefix = "Playlist" if content_type == 'playlist' else "Video"
                    await self.edit_message(chat_id, progress_message['message_id'], f"🎵 {msg_prefix}: {title}\n\nStarting download...")
            # (Spotify playlist name is fetched *during* download, which is fine)
        except Exception as e:
            logger.error(f"Could not fetch playlist name: {e}")
        # --- END NEW ---

        user_dir = None
        try:
            user_dir = self.temp_dir / f"user_{user_id}_{int(time.time())}"
            user_dir.mkdir(parents=True, exist_ok=True)

            if platform == 'spotify':
                # Extract metadata first for better track info
                await self.send_message(chat_id, "🎵 Extracting track information from Spotify...")
                self.download_progress[user_id]['current_track'] = 'Extracting track info...'
                await self.update_progress_message(user_id)
                
                metadata = await self.extract_spotify_metadata(url_info['url'])
                if metadata:
                    self.download_progress[user_id]['current_track'] = f"Found: {metadata['search_term']}"
                    await self.update_progress_message(user_id)
                    await self.send_message(chat_id, f"✅ Track found: **{metadata['search_term']}**\n🎶 Starting download...")
                
                success = await self.run_spotdl_command(
                    url_info['url'],
                    str(user_dir),
                    user_id,
                    chat_id,
                    metadata=metadata
                )
            elif platform == 'youtube':
                if yt_format is None:
                    await self.edit_message(
                        chat_id,
                        progress_message['message_id'],
                        "❌ Please specify MP3 or MP4 format."
                    )
                    return
                # Use yt-dlp with live progress
                success = await self.download_youtube_with_ytdlp(url_info['url'], user_dir, yt_format, user_id, chat_id)
            else:
                success = False

            if not success:
                # Check if we still have downloaded files
                downloaded_files = list(user_dir.glob("*.mp3")) + list(user_dir.glob("*.m4a")) + list(user_dir.glob("*.flac")) + list(user_dir.glob("*.mp4"))
                if downloaded_files:
                    # Some songs exist → make ZIP and upload
                    await self.send_message(chat_id, "⚠️ Some tracks failed, but the rest were downloaded. Uploading to cloud...")
                    await self.handle_zip_and_upload(chat_id, user_id, user_dir, url_info)
                    return
                else:
                    # No files at all
                    error_msg = f"❌ No tracks could be downloaded.\n\n"
                    if platform == 'spotify':
                        error_msg += "**Possible reasons:**\n• The Spotify track/playlist may not be available\n• SpotDL couldn't find matching songs on YouTube\n• The link might be broken or private\n\n**Try:**\n• Check if the Spotify link works in the Spotify app\n• Try a different track or playlist\n• Make sure the playlist is public"
                    else:
                        error_msg += f"Please check the {platform.title()} link or try again later."
                    
                    await self.edit_message(
                        chat_id,
                        progress_message['message_id'],
                        error_msg
                    )
                    return
            
            # Get downloaded files (mp3, m4a, or mp4)
            logger.info(f"Files in {user_dir}: {list(user_dir.glob('*'))}")
            if platform == 'youtube':
                # Check if yt_format is numeric (video resolution like "1080") or audio format
                try:
                    int(yt_format)  # If this succeeds, it's a video resolution
                    downloaded_files = list(user_dir.glob('*.mp4')) + list(user_dir.glob('*.webm'))
                except (ValueError, TypeError):
                    # It's an audio format like 'mp3' or 'flac'
                    downloaded_files = list(user_dir.glob('*.mp3')) + list(user_dir.glob('*.m4a')) + list(user_dir.glob('*.flac'))
            else:
                downloaded_files = list(user_dir.glob('*.mp3'))
            
            if not downloaded_files:
                await self.edit_message(
                    chat_id, 
                    progress_message['message_id'],
                    f"❌ No files were downloaded. Please check the {platform.title()} URL."
                )
                return
            
            # --- NEW: Unified ZIP+upload for playlists and large files ---
            is_playlist = False
            if self.download_progress[user_id].get('total_tracks', 1) > 1:
                is_playlist = True
            if len(downloaded_files) > 1:
                is_playlist = True
            any_large = any(f.stat().st_size > self.file_size_threshold for f in downloaded_files)
            if is_playlist or any_large:
                # ZIP the folder and upload
                await self.handle_zip_and_upload(chat_id, user_id, user_dir, url_info)
            else:
                # Handle single file
                file_path = downloaded_files[0]
                file_size = file_path.stat().st_size
                if file_size <= self.file_size_threshold:
                    await self.edit_message(
                        chat_id, 
                        progress_message['message_id'],
                        "📤 Sending audio file..."
                    )
                    success = await self.send_audio(chat_id, file_path)
                    if success:
                        await self.edit_message(
                            chat_id, 
                            progress_message['message_id'],
                            "✅ Download complete! Audio file sent."
                        )
                    else:
                        await self.edit_message(
                            chat_id, 
                            progress_message['message_id'],
                            "❌ Failed to send audio file."
                        )
                else:
                    # File is too large, upload to cloud
                    await self.handle_large_file_upload(chat_id, user_id, file_path)
            
        except Exception as e:
            logger.error(f"Error in download process: {e}")
            if progress_message:
                await self.edit_message(
                    chat_id, 
                    progress_message['message_id'],
                    "❌ An error occurred during download. Please try again."
                )
        
        finally:
            # Cleanup
            self.active_downloads.discard(user_id)
            if user_id in self.download_progress:
                del self.download_progress[user_id]
            # Clean up temporary files
            try:
                if user_dir and user_dir.exists():
                    time.sleep(2)  # Wait for file handles to close
                    shutil.rmtree(user_dir, ignore_errors=True)
            except Exception as e:
                logger.error(f"Error cleaning up temp directory: {e}")
    
    async def handle_large_file_upload(self, chat_id: int, user_id: int, file_path: Path):
        """Handle upload of large single file"""
        try:
            if user_id in self.download_progress:
                self.download_progress[user_id]['upload_status'] = "Preparing for upload..."
                await self.update_progress_message(user_id)
            
            # Upload to cloud storage
            upload_url = await self.uploader.upload_file(
                file_path, 
                lambda progress, status: self.handle_upload_progress(user_id, progress, status)
            )
            
            if upload_url:
                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                msg_text = (
                    f"✅ **Download Complete!**\n\n"
                    f"📁 **File:** {file_path.name}\n"
                    f"📊 **Size:** {file_size_mb:.1f} MB\n"
                    f"🔗 **Download Link:** {upload_url}\n\n"
                    f"💡 *File was too large for direct sending*"
                )
                if user_id in self.download_progress:
                    await self.edit_message(
                        chat_id,
                        self.download_progress[user_id]['message_id'],
                        msg_text,
                        parse_mode="Markdown"  # <--- ADD THIS
                    )
                    return  # 👈 stop progress updates after final link
            else:
                if user_id in self.download_progress:
                    await self.edit_message(
                        chat_id,
                        self.download_progress[user_id]['message_id'],
                        "❌ Upload failed, please try again. The file was downloaded but couldn't be uploaded to cloud storage."
                    )
        
        except Exception as e:
            logger.error(f"Error uploading large file: {e}")
            if user_id in self.download_progress:
                await self.edit_message(
                    chat_id,
                    self.download_progress[user_id]['message_id'],
                    "❌ Upload failed, please try again. An error occurred during cloud upload."
                )

    async def handle_zip_and_upload(self, chat_id: int, user_id: int, directory: Path, url_info: Dict):
        """Handle ZIP creation and upload with proper naming (always safe for PixelDrain)."""
        try:
            # Update progress
            if user_id in self.download_progress:
                self.download_progress[user_id]['upload_status'] = "Creating ZIP file..."
                self.download_progress[user_id]['upload_progress'] = 0
                await self.update_progress_message(user_id)

            # Get proper content name
            content_name = self.get_content_name(directory, url_info, user_id)
            
            # Create ZIP file with content name
            zip_path = directory.parent / f"{content_name}.zip"

            # Always ensure zip_path name is safe and ASCII
            safe_zip_name = CloudUploader.safe_filename(zip_path.name, 255)
            zip_path = zip_path.with_name(safe_zip_name)

            # Update progress during ZIP creation
            if user_id in self.download_progress:
                self.download_progress[user_id]['upload_status'] = "Compressing files..."
                self.download_progress[user_id]['upload_progress'] = 25
                await self.update_progress_message(user_id)

            # --- MODIFICATION 1: Get the password ---
            zip_password = self.download_progress[user_id].get('zip_password', '1234')  # Get password, fallback just in case

            # Use user_id for live progress
            loop = asyncio.get_running_loop()
            
            # --- MODIFICATION 2: Pass the password to the zipping function ---
            success = await loop.run_in_executor(
                None, lambda: self.create_zip_file(directory, zip_path, zip_password, loop, user_id)
            )

            if not success:
                if user_id in self.download_progress:
                    await self.edit_message(
                        chat_id,
                        self.download_progress[user_id]['message_id'],
                        "❌ Failed to create ZIP file. Please try again."
                    )
                return
            
            # Update progress after ZIP creation
            if user_id in self.download_progress:
                self.download_progress[user_id]['upload_status'] = "ZIP file created, uploading..."
                self.download_progress[user_id]['upload_progress'] = 50
                await self.update_progress_message(user_id)
            
            zip_size = zip_path.stat().st_size
            
            # Upload ZIP to cloud storage
            if user_id in self.download_progress:
                self.download_progress[user_id]['upload_status'] = "Uploading to cloud storage..."
                self.download_progress[user_id]['upload_progress'] = 60
                await self.update_progress_message(user_id)

            upload_url = await self.uploader.upload_file(
                zip_path, 
                lambda progress, status: self.handle_upload_progress(user_id, progress, status)
            )
            
            if upload_url:
                zip_size_mb = zip_size / (1024 * 1024)
                track_count = len(list(directory.glob('*.mp3')) + list(directory.glob('*.m4a')) + list(directory.glob('*.flac')) + list(directory.glob('*.mp4')))
                
                # --- MODIFICATION 3: Add password to the final message ---
                msg_text = (
                    f"✅ **{url_info['platform'].title()} {url_info['type'].title()} Download Complete!**\n\n"
                    f"📁 **Name:** {content_name}\n"
                    f"🎵 **Tracks:** {track_count}\n"
                    f"📊 **Size:** {zip_size_mb:.1f} MB\n"
                    f"🔗 **Download Link:** {upload_url}\n\n"
                    f"🔑 **ZIP Password: {zip_password}**"
                )
                if user_id in self.download_progress:
                    await self.edit_message(
                        chat_id,
                        self.download_progress[user_id]['message_id'],
                        msg_text,
                        parse_mode="Markdown"  # <--- ADD THIS
                    )
                    return  # 👈 stop progress updates after final link
            else:
                if user_id in self.download_progress:
                    await self.edit_message(
                        chat_id,
                        self.download_progress[user_id]['message_id'],
                        "❌ Upload failed, please try again. The files were downloaded but couldn't be uploaded to cloud storage."
                    )
            
            # Clean up ZIP file
            try:
                if zip_path.exists():
                    zip_path.unlink()
            except Exception as e:
                logger.error(f"Error cleaning up ZIP file: {e}")
            
        except Exception as e:
            logger.error(f"Error in ZIP and upload process: {e}")
            if user_id in self.download_progress:
                await self.edit_message(
                    chat_id,
                    self.download_progress[user_id]['message_id'],
                    "❌ An error occurred during processing. Please try again."
                )

    async def handle_message(self, message: Dict) -> None:
        """Handle incoming message (now starts the conversation)"""
        try:
            chat_id = message['chat']['id']
            user_id = message['from']['id']

            if 'text' not in message:
                return

            text = message['text'].strip()

            # Handle /start command
            if text == '/start':
                welcome_message = """🎧 **Music Downloader Bot**

Send me a Spotify or YouTube link and I'll download it for you! 🎵"""
                await self.send_message(chat_id, welcome_message, 'Markdown')
                return

            # Handle /stop command
            elif text == '/stop':
                if user_id in self.active_downloads:
                    self.active_downloads.discard(user_id)
                if user_id in self.download_progress:
                    del self.download_progress[user_id]
                if user_id in self.user_state:  # <-- Renamed
                    del self.user_state[user_id]
                if hasattr(self, 'user_tasks') and user_id in self.user_tasks:
                    task = self.user_tasks.pop(user_id)
                    task.cancel()
                await self.send_message(chat_id, "🛑 All tasks stopped for you.", 'Markdown')
                return

            # Check for Spotify URL
            spotify_info = self.extract_spotify_url_info(text)
            if spotify_info:
                # Spotify is simple: just download it
                await self.send_message(
                    chat_id, 
                    "🎵 **Spotify link detected!**\n\n_Starting download..._",
                    'Markdown'
                )
                task = asyncio.create_task(self.process_download(chat_id, user_id, spotify_info))
                self.user_tasks[user_id] = task
                return
            
            # Check for YouTube URL
            youtube_info = self.extract_youtube_url_info(text)
            if youtube_info:
                # Fetch metadata using YouTube API v3
                metadata = None
                if youtube_info['type'] == 'video':
                    metadata = await self.youtube_api.get_video_info(youtube_info['id'])
                elif youtube_info['type'] == 'playlist':
                    metadata = await self.youtube_api.get_playlist_info(youtube_info['id'])
                
                # Show metadata if available
                if metadata:
                    meta_msg = f"🎬 **{metadata.get('title', 'YouTube Content')}**\n"
                    if youtube_info['type'] == 'video':
                        meta_msg += f"📺 Channel: {metadata.get('channel', 'Unknown')}\n"
                        meta_msg += f"👁️ Views: {metadata.get('views', 'N/A')}\n"
                    elif youtube_info['type'] == 'playlist':
                        meta_msg += f"📺 Channel: {metadata.get('channel', 'Unknown')}\n"
                        meta_msg += f"📊 Videos: {metadata.get('item_count', 'N/A')}\n"
                    await self.send_message(chat_id, meta_msg, 'Markdown')
                
                # Store the user's state and ask the FIRST question
                self.user_state[user_id] = {'url_info': youtube_info, 'state': 'awaiting_type'}
                await self.send_media_type_choice(chat_id, user_id)
                return

            # No valid URL found
            await self.send_message(
                chat_id,
                "❌ Please send a valid Spotify or YouTube URL."
            )

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def send_media_type_choice(self, chat_id: int, user_id: int):
        """Asks the FIRST question: Audio or Video?"""
        keyboard = {
            "inline_keyboard": [[
                {"text": "🎵 Audio (MP3/FLAC)", "callback_data": f"yt_type|mp3|{user_id}"},
                {"text": "🎬 Video (MP4)", "callback_data": f"yt_type|mp4|{user_id}"}
            ]]
        }
        await self.send_message(chat_id, "🎬 YouTube link detected! What do you want to download?", reply_markup=keyboard)

    async def send_audio_quality_choice(self, chat_id: int, user_id: int, message_id_to_edit: int):
        """Asks the SECOND question for audio: Lossless or Compressed?"""
        keyboard = {
            "inline_keyboard": [[
                {"text": "🎵 MP3 (320kbps)", "callback_data": f"yt_audio|mp3|{user_id}"},
                {"text": "💎 FLAC (Lossless)", "callback_data": f"yt_audio|flac|{user_id}"}
            ]]
        }
        # Edit the text of the previous message
        await self.edit_message(chat_id, message_id_to_edit, "🎵 Audio selected. Choose your quality:")
        # Then update just the buttons
        await self.edit_message_reply_markup(chat_id, message_id_to_edit, keyboard)

    async def send_video_quality_choice(self, chat_id: int, user_id: int, resolutions: List[int], message_id_to_edit: int):
        """Asks the SECOND question for video: Which resolution?"""
        keyboard_rows = []
        
        # Create buttons for video resolutions, 2 per row
        video_buttons = []
        for res in reversed(resolutions):  # Start from highest quality
            video_buttons.append(
                # CRITICAL: Note the new callback_data prefix 'yt_video|'
                {"text": f"🎬 {res}p (MP4)", "callback_data": f"yt_video|{res}|{user_id}"}
            )
        
        for i in range(0, len(video_buttons), 2):
            keyboard_rows.append(video_buttons[i:i+2])

        keyboard = {"inline_keyboard": keyboard_rows}
        
        # Edit the text of the previous message
        await self.edit_message(
            chat_id,
            message_id_to_edit,
            "🎬 Video selected. Choose your resolution:"
        )
        # Then update just the buttons
        await self.edit_message_reply_markup(chat_id, message_id_to_edit, keyboard)

    async def handle_callback_query(self, callback_query: Dict):
        """Handle all button clicks in the conversation flow"""
        try:
            chat_id = callback_query['message']['chat']['id']
            user_id = callback_query['from']['id']
            message_id = callback_query['message']['message_id']  # The message with the buttons
            data = callback_query.get('data', '')

            # --- Check if the button is for this user ---
            if f"|{user_id}" not in data:
                # This is a button from a previous session or for another user
                await self.send_message(chat_id, "❌ This button is not for you.")
                return

            # --- Get user state ---
            if user_id not in self.user_state:
                await self.send_message(chat_id, "❌ This session has expired. Please send the link again.")
                await self.edit_message(chat_id, message_id, "This session has expired.")
                return
            
            state_data = self.user_state[user_id]
            url_info = state_data['url_info']

            # --- STATE 1: User chose "Audio" or "Video" ---
            if data.startswith("yt_type|"):
                _, media_type, _ = data.split('|')
                
                if media_type == 'mp3':
                    # User chose Audio. Now ask for audio quality.
                    state_data['state'] = 'awaiting_audio_quality'
                    await self.send_audio_quality_choice(chat_id, user_id, message_id)
                
                elif media_type == 'mp4':
                    # User chose Video. Now fetch resolutions.
                    state_data['state'] = 'awaiting_video_quality'
                    await self.edit_message(chat_id, message_id, "🎬 Video selected. Checking available formats...")
                    
                    resolutions = await self.get_youtube_resolutions(url_info['url'])
                    if not resolutions:
                        await self.edit_message(chat_id, message_id, "❌ Could not find any downloadable formats for that video.")
                        del self.user_state[user_id]
                        return
                    
                    # Now ask for video quality.
                    await self.send_video_quality_choice(chat_id, user_id, resolutions, message_id)

            # --- STATE 2: User chose "MP3" or "FLAC" ---
            elif data.startswith("yt_audio|"):
                _, fmt, _ = data.split('|')  # fmt will be 'mp3' or 'flac'
                
                await self.edit_message(chat_id, message_id, f"✅ Got it! Starting download for {fmt.upper()}...")
                
                # Start the download
                task = asyncio.create_task(self.process_download(chat_id, user_id, url_info, yt_format=fmt))
                self.user_tasks[user_id] = task
                del self.user_state[user_id]  # Clean up state

            # --- STATE 3: User chose "1080p", "720p", etc. ---
            elif data.startswith("yt_video|"):
                _, fmt, _ = data.split('|')  # fmt will be the resolution, e.g., "1080"
                
                await self.edit_message(chat_id, message_id, f"✅ Got it! Starting download for {fmt}p MP4...")
                
                # Start the download
                task = asyncio.create_task(self.process_download(chat_id, user_id, url_info, yt_format=fmt))
                self.user_tasks[user_id] = task
                del self.user_state[user_id]  # Clean up state

        except Exception as e:
            logger.error(f"Error handling callback query: {e}", exc_info=True)
            if 'chat_id' in locals():
                await self.send_message(locals()['chat_id'], "❌ An error occurred. Please try again.")

    async def run(self):
        """Main bot loop"""
        logger.info("Starting Music Telegram Bot...")
        logger.info(f"Using temp directory: {self.temp_dir}")

        while True:
            try:
                updates = await self.get_updates()

                for update in updates:
                    if 'message' in update:
                        await self.handle_message(update['message'])
                    elif 'callback_query' in update:
                        await self.handle_callback_query(update['callback_query'])

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)

    async def update_progress_message(self, user_id: int):
        """Update progress message for user using Markdown and a clear progress bar (Spotify/YouTube)."""
        if user_id not in self.download_progress:
            return
        
        # Add throttling to prevent spam - only update every 10 seconds
        current_time = time.time()
        last_update_key = f'last_progress_update_{user_id}'
        if hasattr(self, last_update_key):
            if current_time - getattr(self, last_update_key) < 10:  # 10 second throttle
                return
        setattr(self, last_update_key, current_time)
        
        progress_info = self.download_progress[user_id]
        chat_id = progress_info.get('chat_id')
        message_id = progress_info.get('message_id')
        current_track = progress_info.get('current_track', 'Unknown')
        percentage = progress_info.get('percentage', 0)
        status = progress_info.get('status', 'starting')
        total_tracks = progress_info.get('total_tracks', 1)
        completed_tracks = progress_info.get('completed_tracks', 0)
        upload_progress = progress_info.get('upload_progress', 0)
        upload_status = progress_info.get('upload_status', '')

        progress_bar_length = 20  # Ensure this is defined for upload progress bar
        def get_smooth_bar(progress: float, length: int = 20) -> str:
            # Unicode blocks for smoother appearance
            blocks = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
            full_blocks = int(progress * length)
            remainder = int((progress * length - full_blocks) * 8)
            bar = "█" * full_blocks
            if full_blocks < length:
                bar += blocks[remainder] + " " * (length - full_blocks - 1)
            return f"[{bar}]"

        # Create animated Unicode progress bar
        bar_text = get_smooth_bar(percentage / 100, progress_bar_length)

        # Debug logging for progress bar updates
        logger.info(f"Updating progress for user {user_id}: {percentage}% {current_track}")
        logger.info(f"chat_id: {chat_id}, message_id: {message_id}")

        msg = ""
        if upload_status:
            # Show upload progress
            upload_bar_length = int(progress_bar_length * upload_progress / 100)
            upload_bar = '[' + '=' * upload_bar_length + '-' * (progress_bar_length - upload_bar_length) + ']'
            # NEW: Show "Upload completed!" when done
            wait_note = "⏱️ **Please wait...**"
            if upload_progress >= 100 and "completed" in upload_status.lower():
                wait_note = "✅ **Upload completed!**"
            msg = f"""
🎵 **Download Complete**

📦 **Upload Progress:**
{upload_bar} {upload_progress:.1f}%

📤 **Status:** {upload_status}

{wait_note}
"""
        else:
            # Show download progress
            completed_tracks = progress_info.get('completed_tracks', 0)
            total_tracks = progress_info.get('total_tracks', 1)
            # Prevent divide-by-zero or overflow
            if total_tracks <= 0:
                total_tracks = 1
            if completed_tracks > total_tracks:
                completed_tracks = total_tracks
            percentage = (completed_tracks / total_tracks) * 100
            if percentage > 100:
                percentage = 100
            bar_length = 20
            filled_length = int(bar_length * completed_tracks // total_tracks) if total_tracks else 0
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            msg = f"""
🎵 **Download Progress**

📊 **Progress:** Downloaded {completed_tracks} of {total_tracks} tracks
{bar} {percentage:.1f}%

🎼 **Current:** {current_track}

📱 **Status:** {status.title()}
"""
        await self.edit_message(chat_id, message_id, msg, parse_mode="Markdown")

    def get_content_name(self, directory: Path, url_info: Dict, user_id: int) -> str:
        """
        Generate a proper content name based on user's request:
        - Playlist: Use playlist name.
        - Single Track: Use song name.
        """
        try:
            progress_info = self.download_progress.get(user_id)
            is_playlist = False

            if progress_info:
                # Check 1: Did we download multiple tracks?
                if progress_info.get('total_tracks', 1) > 1:
                    is_playlist = True
                
                # Check 2: Was the original link a playlist?
                if url_info.get('type') in ['playlist', 'album', 'artist']:
                    is_playlist = True

                # --- Playlist Naming Logic ---
                if is_playlist:
                    playlist_name = progress_info.get('playlist_name')
                    if playlist_name:
                        logger.info(f"Using playlist name: {playlist_name}")
                        return playlist_name

            # --- Single File Naming Logic ---
            # (If it's not a playlist, or we failed to get the playlist name)
            media_files = (
                list(directory.rglob('*.mp3')) +
                list(directory.rglob('*.m4a')) +
                list(directory.rglob('*.flac')) +
                list(directory.rglob('*.mp4'))
            )
            
            if len(media_files) == 1:
                song_name = media_files[0].stem  # .stem gets name without extension
                logger.info(f"Using single song name: {song_name}")
                return song_name
            elif len(media_files) > 1 and progress_info.get('playlist_name'):
                # This is a fallback for Spotify playlists where total_tracks might be 1
                # but we got a playlist name
                logger.info(f"Using playlist name (fallback): {progress_info.get('playlist_name')}")
                return progress_info.get('playlist_name')

            # --- Fallback (if all else fails) ---
            logger.warning("Falling back to generic content name.")
            platform = url_info.get('platform', 'music')
            content_type = url_info.get('type', 'content')
            content_id = url_info.get('id', str(int(time.time())))
            return f"{platform}_{content_type}_{content_id}"

        except Exception as e:
            logger.error(f"Error in get_content_name: {e}")
            # Final fallback
            return f"download_{user_id}_{int(time.time())}"

    async def update_progress_periodically(self, user_id: int) -> None:
        """Update progress message periodically for live progress bar (Spotify/YouTube)."""
        last_update = 0
        while user_id in self.download_progress:
            try:
                current_time = time.time()
                progress_info = self.download_progress[user_id]
                # --- Fallback for Spotify: count .mp3 files if progress is stuck ---
                if progress_info.get('platform') == 'spotify':
                    try:
                        # Find the user's temp directory (search for the latest one)
                        user_dirs = sorted(
                            Path(self.temp_dir).glob(f"user_{user_id}_*"),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True
                        )
                        if user_dirs:
                            user_dir = user_dirs[0]
                            downloaded_files = list(user_dir.glob('*.mp3'))
                            completed = len(downloaded_files)
                            if completed > 0:
                                progress_info['completed_tracks'] = completed
                                if progress_info.get('total_tracks', 1) > 0:
                                    progress_info['percentage'] = int((completed / progress_info['total_tracks']) * 100)
                    except Exception as e:
                        logger.warning(f"Could not update Spotify fallback progress: {e}")
                # --- End fallback ---

                if current_time - last_update >= 15:
                    await self.update_progress_message(user_id)
                    last_update = current_time
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in progress update: {e}")
                await asyncio.sleep(2)

    def handle_upload_progress(self, user_id: int, progress: int, status: str):
        """Callback to update upload progress in download_progress."""
        if user_id in self.download_progress:
            self.download_progress[user_id]['upload_progress'] = progress
            self.download_progress[user_id]['upload_status'] = status
            # Don't call update_progress_message here to reduce spam
            # The periodic updater will handle it

async def main():
    """Main function to run the bot"""
    try:
        bot = MusicTelegramBot()
        await bot.run()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.info("Please set your environment variables:")
        logger.info("export TELEGRAM_BOT_TOKEN='your_bot_token_here'")
        logger.info("export PIXELDRAIN_API_KEY='your_pixeldrain_api_key_here'")
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == "__main__":
    asyncio.run(main())