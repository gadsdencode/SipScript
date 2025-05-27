import re
import requests
import json
from urllib.parse import unquote
from typing import Optional, Dict

class CaptionScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })

    def extract_captions_from_page(self, video_id: str) -> Optional[Dict]:
        """
        Extract captions directly from YouTube using multiple strategies
        """
        try:
            # Strategy 1: Try direct timedtext API
            caption_text = self._try_direct_timedtext_api(video_id)
            
            if not caption_text:
                # Strategy 2: Try transcript page scraping
                caption_text = self._try_transcript_page_scraping(video_id)
            
            if not caption_text or len(caption_text.strip()) < 50:
                return None
            
            # Get basic metadata
            title, upload_date, channel = self._get_basic_metadata(video_id)
            
            return {
                'transcript': caption_text,
                'title': title or f'Video {video_id}',
                'date': upload_date or '2024-01-01',
                'channel': channel or 'Unknown Channel',
                'video_id': video_id,
                'extraction_method': 'web_scraping'
            }
            
        except Exception as e:
            print(f"Error scraping captions for {video_id}: {e}")
            return None

    def _try_direct_timedtext_api(self, video_id: str) -> Optional[str]:
        """Try using youtube-transcript-api with authentication"""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            import os
            
            # Check if we have YouTube cookies for authentication
            cookies_file = os.environ.get('YOUTUBE_COOKIES')
            
            if cookies_file:
                # Use cookies for authentication to bypass IP blocking
                transcript_list = YouTubeTranscriptApi.get_transcript(
                    video_id, 
                    languages=['en', 'en-US'],
                    cookies=cookies_file
                )
            else:
                # Try without authentication first
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US'])
            
            if transcript_list:
                # Combine all text segments
                full_text = ' '.join([item['text'] for item in transcript_list])
                return self._clean_text(full_text)
                
        except ImportError:
            print("youtube-transcript-api not available")
        except Exception as e:
            if "IP" in str(e) or "blocked" in str(e).lower():
                print(f"YouTube is blocking requests from this server. Authentication needed: {e}")
                return "AUTH_REQUIRED"
            else:
                print(f"YouTube Transcript API failed: {e}")
            
        return None

    def _try_transcript_page_scraping(self, video_id: str) -> Optional[str]:
        """Try scraping the main video page for embedded captions"""
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                return None
            
            html_content = response.text
            return self._extract_caption_data(html_content)
            
        except Exception as e:
            print(f"Page scraping failed: {e}")
            return None

    def _get_basic_metadata(self, video_id: str) -> tuple:
        """Get basic video metadata"""
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                html = response.text
                title = self._extract_title(html)
                date = self._extract_upload_date(html)
                channel = self._extract_channel(html)
                return title, date, channel
        except:
            pass
        
        return None, None, None

    def _extract_title(self, html: str) -> Optional[str]:
        """Extract video title from HTML"""
        patterns = [
            r'"title"\s*:\s*"([^"]+)"',
            r'<title>([^<]+)</title>',
            r'property="og:title"\s+content="([^"]+)"'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                title = match.group(1)
                if ' - YouTube' in title:
                    title = title.replace(' - YouTube', '')
                return self._clean_text(title)
        return None

    def _extract_upload_date(self, html: str) -> Optional[str]:
        """Extract upload date from HTML"""
        patterns = [
            r'"uploadDate"\s*:\s*"([^"]+)"',
            r'"datePublished"\s*:\s*"([^"]+)"'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                date_str = match.group(1)
                try:
                    from datetime import datetime
                    # Parse ISO format date
                    date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    return date_obj.strftime('%Y-%m-%d')
                except:
                    continue
        return None

    def _extract_channel(self, html: str) -> Optional[str]:
        """Extract channel name from HTML"""
        patterns = [
            r'"author"\s*:\s*"([^"]+)"',
            r'"ownerChannelName"\s*:\s*"([^"]+)"',
            r'property="og:video:tag"\s+content="([^"]+)"'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return self._clean_text(match.group(1))
        return None

    def _extract_caption_data(self, html: str) -> Optional[str]:
        """Extract caption/subtitle data from HTML"""
        try:
            # Look for the player config that contains caption track URLs
            player_config_pattern = r'ytInitialPlayerResponse\s*=\s*({.+?});'
            match = re.search(player_config_pattern, html)
            
            if match:
                try:
                    config_json = match.group(1)
                    import json
                    player_data = json.loads(config_json)
                    
                    # Navigate to captions data
                    captions = player_data.get('captions', {})
                    caption_tracks = captions.get('playerCaptionsTracklistRenderer', {}).get('captionTracks', [])
                    
                    # Find English captions (prefer manual over auto-generated)
                    english_track = None
                    for track in caption_tracks:
                        if track.get('languageCode', '').startswith('en'):
                            if track.get('kind') != 'asr':  # Manual captions
                                english_track = track
                                break
                            elif english_track is None:  # Auto-generated as fallback
                                english_track = track
                    
                    if english_track and 'baseUrl' in english_track:
                        caption_url = english_track['baseUrl']
                        caption_text = self._download_caption_file(caption_url)
                        if caption_text and len(caption_text.strip()) > 100:
                            return caption_text
                
                except json.JSONDecodeError:
                    print("Failed to parse player config JSON")
            
            # Fallback: Look for caption tracks in a simpler pattern
            caption_url_pattern = r'"baseUrl":"([^"]*transcript[^"]*)"'
            url_matches = re.findall(caption_url_pattern, html)
            
            for url in url_matches:
                if 'lang=en' in url or '&tlang=en' in url:
                    clean_url = url.replace('\\u0026', '&').replace('\\/', '/').replace('\\/','/')
                    caption_text = self._download_caption_file(clean_url)
                    if caption_text and len(caption_text.strip()) > 100:
                        return caption_text
            
            # Another fallback: look for any transcript-like URLs
            transcript_patterns = [
                r'"baseUrl":"([^"]*timedtext[^"]*lang=en[^"]*)"',
                r'"baseUrl":"([^"]*caption[^"]*)"'
            ]
            
            for pattern in transcript_patterns:
                url_matches = re.findall(pattern, html)
                for url in url_matches:
                    clean_url = url.replace('\\u0026', '&').replace('\\/', '/').replace('\\/','/')
                    caption_text = self._download_caption_file(clean_url)
                    if caption_text and len(caption_text.strip()) > 100:
                        return caption_text
            
            return None
            
        except Exception as e:
            print(f"Error extracting caption data: {e}")
            return None

    def _download_caption_file(self, url: str) -> Optional[str]:
        """Download and parse caption file from URL"""
        try:
            # Decode URL if needed
            if '\\u' in url:
                url = url.encode().decode('unicode_escape')
            
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                content = response.text
                
                # Parse different caption formats
                if '<text' in content:  # XML format
                    return self._parse_xml_captions(content)
                elif '"text"' in content:  # JSON format
                    return self._parse_json_captions(content)
                else:  # Plain text
                    return self._clean_text(content)
            
        except Exception as e:
            print(f"Error downloading caption file: {e}")
        
        return None

    def _parse_xml_captions(self, xml_content: str) -> str:
        """Parse XML caption format (YouTube's timedtext format)"""
        # Extract text from <text> tags, handling both simple and complex formats
        text_patterns = [
            r'<text[^>]*>([^<]+)</text>',
            r'<text[^>]*><!\[CDATA\[([^\]]+)\]\]></text>',
            r'<text[^>]*>([^<]*(?:<[^/][^>]*>[^<]*</[^>]*>[^<]*)*)</text>'
        ]
        
        all_text = []
        for pattern in text_patterns:
            matches = re.findall(pattern, xml_content, re.DOTALL)
            for match in matches:
                cleaned = self._clean_text(match)
                if cleaned and len(cleaned) > 2:
                    all_text.append(cleaned)
        
        if all_text:
            return ' '.join(all_text)
        
        # Fallback: extract any text content
        simple_text = re.sub(r'<[^>]+>', ' ', xml_content)
        return self._clean_text(simple_text)

    def _parse_json_captions(self, json_content: str) -> str:
        """Parse JSON caption format"""
        try:
            import json
            data = json.loads(json_content)
            
            # Handle YouTube's JSON3 format
            if 'events' in data:
                text_parts = []
                for event in data['events']:
                    if 'segs' in event:
                        for seg in event['segs']:
                            if 'utf8' in seg:
                                text_parts.append(seg['utf8'])
                    elif 'dDurationMs' in event and 'segs' not in event:
                        # Sometimes text is directly in the event
                        if 'utf8' in event:
                            text_parts.append(event['utf8'])
                
                if text_parts:
                    return ' '.join([self._clean_text(text) for text in text_parts])
            
            # Handle other JSON formats
            if 'body' in data:
                text_parts = []
                for item in data.get('body', []):
                    if isinstance(item, dict) and 'content' in item:
                        text_parts.append(item['content'])
                if text_parts:
                    return ' '.join([self._clean_text(text) for text in text_parts])
                    
        except json.JSONDecodeError:
            pass
        
        # Fallback: regex extraction for any JSON-like text
        text_patterns = [
            r'"text"\s*:\s*"([^"]+)"',
            r'"utf8"\s*:\s*"([^"]+)"',
            r'"content"\s*:\s*"([^"]+)"'
        ]
        
        all_matches = []
        for pattern in text_patterns:
            matches = re.findall(pattern, json_content)
            all_matches.extend([self._clean_text(text) for text in matches])
        
        return ' '.join(all_matches)

    def _parse_vtt_captions(self, vtt_content: str) -> str:
        """Parse WebVTT caption format"""
        lines = vtt_content.split('\n')
        text_lines = []
        
        for line in lines:
            line = line.strip()
            # Skip VTT headers, timestamps, and empty lines
            if (not line or 
                line.startswith('WEBVTT') or 
                '-->' in line or 
                line.isdigit() or
                line.startswith('NOTE')):
                continue
            
            # Clean the text line
            cleaned = self._clean_text(line)
            if cleaned and len(cleaned) > 1:
                text_lines.append(cleaned)
        
        return ' '.join(text_lines)

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Decode HTML entities and Unicode escapes
        text = text.replace('\\n', ' ').replace('\\r', ' ')
        text = text.replace('\\"', '"').replace("\\'", "'")
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()