import re
import os
import tempfile
from datetime import datetime
from typing import Optional, Dict
from youtube_transcript_api import YouTubeTranscriptApi
import requests
import yt_dlp
import whisper
from pydub import AudioSegment
from googleapiclient.discovery import build

class YouTubeHandler:
    def __init__(self):
        """Initialize YouTube handler"""
        self.whisper_model = None  # Load model only when needed to save memory
        self.youtube_api = None
        self._init_youtube_api()
    
    def _init_youtube_api(self):
        """Initialize YouTube Data API with authentication"""
        try:
            api_key = os.getenv('YOUTUBE_API_KEY')
            if api_key:
                self.youtube_api = build('youtube', 'v3', developerKey=api_key)
                print("YouTube API initialized successfully with authentication")
            else:
                print("YouTube API key not found, using fallback methods")
        except Exception as e:
            print(f"Failed to initialize YouTube API: {e}")
    
    def _get_video_metadata_with_api(self, video_id: str) -> Dict:
        """Get video metadata using authenticated YouTube Data API"""
        try:
            if self.youtube_api:
                request = self.youtube_api.videos().list(
                    part="snippet,contentDetails",
                    id=video_id
                )
                response = request.execute()
                
                if response['items']:
                    video = response['items'][0]
                    snippet = video['snippet']
                    
                    # Parse duration if available
                    duration = None
                    if 'contentDetails' in video and 'duration' in video['contentDetails']:
                        duration_str = video['contentDetails']['duration']
                        # Convert ISO 8601 duration to seconds (PT1H2M3S format)
                        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
                        if match:
                            hours, minutes, seconds = match.groups()
                            duration = (int(hours or 0) * 3600 + 
                                      int(minutes or 0) * 60 + 
                                      int(seconds or 0))
                    
                    # Parse upload date
                    upload_date = snippet.get('publishedAt', '')
                    try:
                        date_obj = datetime.fromisoformat(upload_date.replace('Z', '+00:00'))
                        formatted_date = date_obj.strftime('%Y-%m-%d')
                    except:
                        formatted_date = datetime.now().strftime('%Y-%m-%d')
                    
                    return {
                        'title': self._clean_title(snippet.get('title', f'Video {video_id}')),
                        'date': formatted_date,
                        'channel': snippet.get('channelTitle', 'Unknown Channel'),
                        'duration': duration
                    }
        except Exception as e:
            print(f"API metadata extraction failed: {e}")
        
        # Fallback metadata
        return {
            'title': f"Coffee with Scott Adams - Episode {video_id}",
            'date': datetime.now().strftime('%Y-%m-%d'),
            'channel': "Scott Adams",
            'duration': None
        }
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats"""
        patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def extract_transcript(self, video_id: str) -> Optional[Dict]:
        """
        Extract transcript and metadata from YouTube video
        Returns dict with transcript, title, date, and other metadata
        """
        try:
            # Get transcript using youtube-transcript-api
            transcript_list = YouTubeTranscriptApi.get_transcript(
                video_id,
                languages=['en', 'en-US', 'en-GB']  # Prefer English transcripts
            )
            
            # Combine transcript segments into full text
            full_transcript = self._combine_transcript_segments(transcript_list)
            
            if not full_transcript or len(full_transcript.strip()) < 50:
                raise ValueError("Transcript is too short or empty")
            
            # Get video metadata
            metadata = self._get_video_metadata(video_id)
            
            return {
                'transcript': full_transcript,
                'title': metadata.get('title', f'Video {video_id}'),
                'date': metadata.get('date', datetime.now().strftime('%Y-%m-%d')),
                'duration': metadata.get('duration'),
                'channel': metadata.get('channel'),
                'video_id': video_id
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"Error extracting transcript for video {video_id}: {error_msg}")
            
            # Check for specific YouTube blocking errors
            if "IP belonging to a cloud provider" in error_msg:
                raise Exception("YouTube is temporarily blocking requests from this cloud environment. This is common but usually resolves quickly. You can try again in a few minutes, or try a different video.")
            elif "blocked" in error_msg.lower():
                raise Exception("YouTube has temporarily blocked access to captions. Try again in a few minutes or try the Audio-Based extraction method.")
            else:
                raise Exception(f"Caption extraction failed: {error_msg}")
            
            return None

    def extract_transcript_from_audio(self, video_id: str, progress_callback=None, quality_level="Fast") -> Optional[Dict]:
        """
        Extract transcript from YouTube video audio using Whisper AI
        This method downloads audio and uses speech recognition for transcription
        """
        temp_dir = None
        try:
            # Create temporary directory for audio files
            temp_dir = tempfile.mkdtemp()
            audio_path = os.path.join(temp_dir, f"{video_id}.wav")
            
            if progress_callback:
                progress_callback("Downloading audio from YouTube...")
            
            # Download audio using yt-dlp with optimized settings and bot bypass
            ydl_opts = {
                'format': 'worstaudio/worst',  # Use lower quality for faster processing
                'outtmpl': os.path.join(temp_dir, f"{video_id}.%(ext)s"),
                'extractaudio': True,
                'audioformat': 'mp3',  # MP3 is smaller and faster to process
                'audioquality': '9',   # Lower quality for speed
                'quiet': True,
                'no_warnings': True,
                # Add headers to appear more like a regular browser
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip,deflate',
                    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                    'Keep-Alive': '300',
                    'Connection': 'keep-alive',
                },
                # Try to bypass age restrictions
                'age_limit': None,
                'skip_download': False,
            }
            
            url = f"https://www.youtube.com/watch?v={video_id}"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract video info first
                info = ydl.extract_info(url, download=False)
                title = info.get('title', f'Video {video_id}')
                duration = info.get('duration')
                upload_date = info.get('upload_date')
                channel = info.get('uploader')
                
                # Format date
                if upload_date:
                    try:
                        date_obj = datetime.strptime(upload_date, '%Y%m%d')
                        formatted_date = date_obj.strftime('%Y-%m-%d')
                    except:
                        formatted_date = datetime.now().strftime('%Y-%m-%d')
                else:
                    formatted_date = datetime.now().strftime('%Y-%m-%d')
                
                # Download audio
                ydl.download([url])
            
            # Find the downloaded audio file
            downloaded_files = [f for f in os.listdir(temp_dir) if f.startswith(video_id)]
            if not downloaded_files:
                raise Exception("Failed to download audio file")
            
            audio_file = os.path.join(temp_dir, downloaded_files[0])
            
            if progress_callback:
                progress_callback("Converting audio format...")
            
            # Convert and compress audio for faster processing
            audio = AudioSegment.from_file(audio_file)
            
            # Compress audio: reduce sample rate and convert to mono for speed
            audio = audio.set_frame_rate(16000)  # Lower sample rate for faster processing
            audio = audio.set_channels(1)       # Convert to mono
            
            # Export as WAV for Whisper
            audio_path = os.path.join(temp_dir, f"{video_id}_compressed.wav")
            audio.export(audio_path, format="wav")
            
            if progress_callback:
                progress_callback("Loading speech recognition model...")
            
            # Load Whisper model based on quality level
            model_map = {
                "Fast": "tiny",
                "Balanced": "base", 
                "Best Quality": "small"
            }
            
            model_size = model_map.get(quality_level, "tiny")
            
            if self.whisper_model is None or getattr(self, '_current_model_size', None) != model_size:
                if progress_callback:
                    progress_callback(f"Loading {model_size} speech recognition model...")
                self.whisper_model = whisper.load_model(model_size)
                self._current_model_size = model_size
            
            if progress_callback:
                progress_callback("Transcribing audio... This may take a few minutes.")
            
            # Transcribe audio with optimized settings
            result = self.whisper_model.transcribe(
                audio_path,
                fp16=False,  # Use FP32 for CPU compatibility
                verbose=False,  # Reduce output
                language="en",  # Assume English for Scott Adams podcasts
                temperature=0.0,  # More consistent results
                compression_ratio_threshold=2.4,  # Prevent cutting off content
                logprob_threshold=-1.0,  # Include more uncertain words
                no_speech_threshold=0.6  # Better handling of quiet sections
            )
            transcript_text = result["text"]
            
            if not transcript_text or len(transcript_text.strip()) < 50:
                raise ValueError("Generated transcript is too short or empty")
            
            # Clean up the transcript
            cleaned_transcript = self._clean_whisper_transcript(transcript_text)
            
            return {
                'transcript': cleaned_transcript,
                'title': self._clean_title(title),
                'date': formatted_date,
                'duration': duration,
                'channel': channel,
                'video_id': video_id,
                'extraction_method': 'audio'  # Mark this as audio-extracted
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"Error extracting transcript from audio for video {video_id}: {error_msg}")
            
            # Check for specific YouTube blocking errors
            if "Sign in to confirm you're not a bot" in error_msg:
                raise Exception("YouTube is blocking audio downloads from this environment. This is common on cloud platforms. Try using the Caption-Based extraction method instead, which often works better.")
            elif "blocked" in error_msg.lower() or "forbidden" in error_msg.lower():
                raise Exception("YouTube has blocked access to this video's audio. Try using the Caption-Based extraction method instead.")
            else:
                raise Exception(f"Audio extraction failed: {error_msg}")
            
            return None
        finally:
            # Clean up temporary files
            if temp_dir and os.path.exists(temp_dir):
                import shutil
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass  # Best effort cleanup
    
    def _combine_transcript_segments(self, transcript_list: list) -> str:
        """Combine transcript segments into readable text"""
        if not transcript_list:
            return ""
        
        # Extract text from each segment
        text_segments = []
        for segment in transcript_list:
            text = segment.get('text', '').strip()
            if text:
                # Clean up common transcript artifacts
                text = self._clean_transcript_text(text)
                text_segments.append(text)
        
        # Join segments with spaces
        full_text = ' '.join(text_segments)
        
        # Basic formatting cleanup
        full_text = re.sub(r'\s+', ' ', full_text)  # Multiple spaces to single space
        full_text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', full_text)  # Ensure space after punctuation
        
        return full_text.strip()
    
    def _clean_transcript_text(self, text: str) -> str:
        """Clean individual transcript text segments"""
        # Remove common transcript artifacts
        text = re.sub(r'\[.*?\]', '', text)  # Remove bracketed content
        text = re.sub(r'\(.*?\)', '', text)  # Remove parenthetical content
        
        # Fix common transcription issues
        text = re.sub(r'\buh\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bum\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\ber\b', '', text, flags=re.IGNORECASE)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _get_video_metadata(self, video_id: str) -> Dict:
        """
        Get video metadata from YouTube
        This is a simplified approach - in production you might want to use YouTube Data API
        """
        try:
            # Try to extract basic info from YouTube page
            url = f"https://www.youtube.com/watch?v={video_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                html = response.text
                
                # Extract title
                title_match = re.search(r'"title":"([^"]+)"', html)
                title = title_match.group(1) if title_match else f"Video {video_id}"
                
                # Clean up title (decode unicode escapes)
                title = title.encode().decode('unicode_escape')
                
                # Extract upload date (simplified approach)
                date_match = re.search(r'"uploadDate":"([^"]+)"', html)
                if date_match:
                    upload_date = date_match.group(1)
                    try:
                        # Parse ISO date format
                        date_obj = datetime.fromisoformat(upload_date.replace('Z', '+00:00'))
                        date = date_obj.strftime('%Y-%m-%d')
                    except:
                        date = datetime.now().strftime('%Y-%m-%d')
                else:
                    date = datetime.now().strftime('%Y-%m-%d')
                
                # Extract channel name
                channel_match = re.search(r'"author":"([^"]+)"', html)
                channel = channel_match.group(1) if channel_match else "Unknown Channel"
                
                return {
                    'title': self._clean_title(title),
                    'date': date,
                    'channel': channel,
                    'duration': None  # Would need YouTube Data API for accurate duration
                }
                
        except Exception as e:
            print(f"Warning: Could not extract metadata for video {video_id}: {str(e)}")
        
        # Fallback metadata
        return {
            'title': f"Coffee with Scott Adams - Episode {video_id}",
            'date': datetime.now().strftime('%Y-%m-%d'),
            'channel': "Scott Adams",
            'duration': None
        }
    
    def _clean_title(self, title: str) -> str:
        """Clean up video title"""
        # Remove common unwanted characters
        title = re.sub(r'[^\w\s\-\:\.\,\!\?]', '', title)
        
        # Limit length
        if len(title) > 200:
            title = title[:200] + "..."
        
        return title.strip()
    
    def validate_coffee_with_scott_adams(self, video_id: str) -> bool:
        """
        Validate if the video is likely a Coffee with Scott Adams episode
        This is a basic check - you might want to enhance this
        """
        try:
            metadata = self._get_video_metadata(video_id)
            title = metadata.get('title', '').lower()
            channel = metadata.get('channel', '').lower()
            
            # Check for Scott Adams related keywords
            scott_keywords = ['scott adams', 'coffee with scott', 'real coffee']
            
            return any(keyword in title or keyword in channel for keyword in scott_keywords)
            
        except Exception as e:
            print(f"Warning: Could not validate video {video_id}: {str(e)}")
            return True  # Default to allowing the video
    
    def get_available_transcript_languages(self, video_id: str) -> list:
        """Get list of available transcript languages for a video"""
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            languages = []
            
            for transcript in transcript_list:
                languages.append({
                    'language': transcript.language,
                    'language_code': transcript.language_code,
                    'is_generated': transcript.is_generated,
                    'is_translatable': transcript.is_translatable
                })
            
            return languages
            
        except Exception as e:
            print(f"Error getting transcript languages for {video_id}: {str(e)}")
            return []

    def _clean_whisper_transcript(self, text: str) -> str:
        """Clean Whisper-generated transcript text"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Whisper sometimes adds timestamps or markers, remove them
        text = re.sub(r'\[\d+:\d+:\d+\.\d+\s*-->\s*\d+:\d+:\d+\.\d+\]', '', text)
        text = re.sub(r'\d+:\d+\.\d+', '', text)
        
        # Clean up common speech recognition artifacts
        text = re.sub(r'\[MUSIC\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[APPLAUSE\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[LAUGHTER\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[INAUDIBLE\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[UNCLEAR\]', '', text, flags=re.IGNORECASE)
        
        # Remove common filler words that speech recognition might capture
        text = re.sub(r'\b(uh|um|er|ah)\b', '', text, flags=re.IGNORECASE)
        
        # Ensure proper sentence spacing
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)
        
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()

    def extract_transcript_with_api(self, video_id: str) -> Optional[Dict]:
        """
        Extract transcript using authenticated YouTube Data API
        This bypasses IP blocking by using official API access
        """
        try:
            if not self.youtube_api:
                raise Exception("YouTube API not initialized. API key required.")
            
            # Get video metadata first
            metadata = self._get_video_metadata_with_api(video_id)
            
            # Get list of available captions
            captions_request = self.youtube_api.captions().list(
                part="snippet",
                videoId=video_id
            )
            captions_response = captions_request.execute()
            
            if not captions_response.get('items'):
                raise Exception("No captions available for this video")
            
            # Find English captions (prefer manually created over auto-generated)
            english_caption = None
            for caption in captions_response['items']:
                lang = caption['snippet']['language']
                track_kind = caption['snippet'].get('trackKind', 'standard')
                
                if lang in ['en', 'en-US', 'en-GB']:
                    if track_kind == 'standard':  # Manually created captions
                        english_caption = caption
                        break
                    elif english_caption is None:  # Auto-generated as fallback
                        english_caption = caption
            
            if not english_caption:
                raise Exception("No English captions found for this video")
            
            # Download the caption content
            caption_id = english_caption['id']
            download_request = self.youtube_api.captions().download(
                id=caption_id,
                tfmt='srt'  # SubRip format
            )
            
            # Execute the download
            caption_content = download_request.execute()
            
            if isinstance(caption_content, bytes):
                caption_content = caption_content.decode('utf-8')
            
            # Parse SRT content to extract text
            transcript_text = self._parse_srt_content(caption_content)
            
            if not transcript_text or len(transcript_text.strip()) < 50:
                raise Exception("Generated transcript is too short or empty")
            
            return {
                'transcript': transcript_text,
                'title': metadata.get('title', f'Video {video_id}'),
                'date': metadata.get('date', datetime.now().strftime('%Y-%m-%d')),
                'duration': metadata.get('duration'),
                'channel': metadata.get('channel'),
                'video_id': video_id,
                'extraction_method': 'api_captions'
            }
            
        except Exception as e:
            print(f"Error extracting transcript with API for video {video_id}: {str(e)}")
            raise Exception(f"API caption extraction failed: {str(e)}")
    
    def _parse_srt_content(self, srt_content: str) -> str:
        """Parse SRT subtitle content to extract plain text"""
        import re
        
        lines = srt_content.split('\n')
        text_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip sequence numbers and timestamp lines
            if line.isdigit() or '-->' in line or not line:
                i += 1
                continue
            
            # Clean subtitle text
            cleaned_line = re.sub(r'<[^>]+>', '', line)  # Remove HTML tags
            cleaned_line = re.sub(r'\[.*?\]', '', cleaned_line)  # Remove bracketed content
            cleaned_line = cleaned_line.strip()
            
            if cleaned_line:
                text_lines.append(cleaned_line)
            
            i += 1
        
        # Join and clean up text
        full_text = ' '.join(text_lines)
        full_text = re.sub(r'\s+', ' ', full_text)
        full_text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', full_text)
        
        return full_text.strip()
