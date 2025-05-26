import re
from datetime import datetime
from typing import Optional, Dict
from youtube_transcript_api import YouTubeTranscriptApi
import requests

class YouTubeHandler:
    def __init__(self):
        """Initialize YouTube handler"""
        pass
    
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
            print(f"Error extracting transcript for video {video_id}: {str(e)}")
            return None
    
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
