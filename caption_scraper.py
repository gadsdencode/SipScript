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
        Extract captions directly from YouTube's web page
        This method scrapes the page HTML to find caption data
        """
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                return None
            
            html_content = response.text
            
            # Extract video title and metadata
            title = self._extract_title(html_content)
            upload_date = self._extract_upload_date(html_content)
            channel = self._extract_channel(html_content)
            
            # Look for caption data in the page
            caption_text = self._extract_caption_data(html_content)
            
            if not caption_text or len(caption_text.strip()) < 50:
                return None
            
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
            # Look for caption tracks in the page data
            caption_patterns = [
                r'"captionTracks"\s*:\s*\[([^\]]+)\]',
                r'"captions"\s*:\s*{[^}]*"playerCaptionsTracklistRenderer"[^}]*}',
                r'"automaticCaptions"\s*:\s*{([^}]+)}'
            ]
            
            for pattern in caption_patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    caption_data = match.group(0)
                    # Look for English caption URLs
                    url_matches = re.findall(r'"baseUrl"\s*:\s*"([^"]+)"', caption_data)
                    
                    for url in url_matches:
                        if 'lang=en' in url or '&lang=en' in url:
                            # Clean up the URL
                            clean_url = url.replace('\\u0026', '&').replace('\\/', '/')
                            caption_text = self._download_caption_file(clean_url)
                            if caption_text:
                                return caption_text
            
            # Fallback: look for embedded subtitle data
            subtitle_pattern = r'"text"\s*:\s*"([^"]+)"'
            subtitle_matches = re.findall(subtitle_pattern, html)
            
            if subtitle_matches:
                # Combine all subtitle text
                combined_text = ' '.join([self._clean_text(text) for text in subtitle_matches])
                if len(combined_text) > 100:  # Only return if substantial content
                    return combined_text
            
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
        """Parse XML caption format"""
        text_matches = re.findall(r'<text[^>]*>([^<]+)</text>', xml_content)
        combined_text = ' '.join([self._clean_text(text) for text in text_matches])
        return combined_text

    def _parse_json_captions(self, json_content: str) -> str:
        """Parse JSON caption format"""
        try:
            data = json.loads(json_content)
            if 'events' in data:
                text_parts = []
                for event in data['events']:
                    if 'segs' in event:
                        for seg in event['segs']:
                            if 'utf8' in seg:
                                text_parts.append(seg['utf8'])
                return ' '.join(text_parts)
        except:
            pass
        
        # Fallback: regex extraction
        text_matches = re.findall(r'"text"\s*:\s*"([^"]+)"', json_content)
        return ' '.join([self._clean_text(text) for text in text_matches])

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