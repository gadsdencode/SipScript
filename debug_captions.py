import requests
import re
import json

def debug_youtube_captions(video_id):
    """Debug what caption data is available in YouTube page"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    print(f"Fetching: {url}")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to fetch page: {response.status_code}")
        return
    
    html = response.text
    print(f"Page size: {len(html)} characters")
    
    # Look for player config
    player_config_pattern = r'ytInitialPlayerResponse\s*=\s*({.+?});'
    match = re.search(player_config_pattern, html)
    
    if match:
        print("Found ytInitialPlayerResponse")
        try:
            config_json = match.group(1)
            player_data = json.loads(config_json)
            
            # Check for captions
            captions = player_data.get('captions', {})
            print(f"Captions object: {bool(captions)}")
            
            if captions:
                renderer = captions.get('playerCaptionsTracklistRenderer', {})
                print(f"Caption renderer: {bool(renderer)}")
                
                tracks = renderer.get('captionTracks', [])
                print(f"Found {len(tracks)} caption tracks")
                
                for i, track in enumerate(tracks):
                    lang = track.get('languageCode', 'unknown')
                    name = track.get('name', {}).get('simpleText', 'No name')
                    kind = track.get('kind', 'standard')
                    has_url = 'baseUrl' in track
                    print(f"  Track {i}: {lang} - {name} - {kind} - Has URL: {has_url}")
                    
                    if has_url and lang.startswith('en'):
                        print(f"    URL: {track['baseUrl'][:100]}...")
                        return track['baseUrl']
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
    else:
        print("No ytInitialPlayerResponse found")
    
    # Look for any caption-related URLs
    caption_patterns = [
        r'"baseUrl":"([^"]*timedtext[^"]*)"',
        r'"baseUrl":"([^"]*caption[^"]*)"',
        r'(https://www\.youtube\.com/api/timedtext[^"]*)'
    ]
    
    all_urls = []
    for pattern in caption_patterns:
        urls = re.findall(pattern, html)
        all_urls.extend(urls)
    
    print(f"Found {len(all_urls)} potential caption URLs")
    for url in all_urls[:3]:  # Show first 3
        print(f"  {url[:100]}...")
    
    return all_urls[0] if all_urls else None

if __name__ == "__main__":
    # Test with a known video
    video_id = "3CD0kEPePrE"  # Replace with actual video ID
    caption_url = debug_youtube_captions(video_id)
    
    if caption_url:
        print(f"\nTrying to download caption file...")
        try:
            clean_url = caption_url.replace('\\u0026', '&').replace('\\/', '/')
            response = requests.get(clean_url)
            print(f"Caption response status: {response.status_code}")
            print(f"Caption content length: {len(response.text)}")
            print(f"First 200 chars: {response.text[:200]}")
        except Exception as e:
            print(f"Error downloading captions: {e}")