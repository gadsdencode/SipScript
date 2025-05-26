import streamlit as st
import pandas as pd
import re
from datetime import datetime
from database import DatabaseManager
from youtube_handler import YouTubeHandler
from transcript_processor import TranscriptProcessor

# Initialize components
@st.cache_resource
def initialize_components():
    db = DatabaseManager()
    youtube_handler = YouTubeHandler()
    transcript_processor = TranscriptProcessor()
    return db, youtube_handler, transcript_processor

def validate_youtube_url(url):
    """Validate if the provided URL is a valid YouTube URL"""
    youtube_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
        r'(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]+)'
    ]
    
    for pattern in youtube_patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def main():
    st.title("Coffee with Scott Adams - Transcript Extractor & Enhancer")
    st.markdown("---")
    
    # Initialize components
    db, youtube_handler, transcript_processor = initialize_components()
    
    # Sidebar for navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("Choose a page", ["Add Episode", "Browse Episodes", "Search Transcripts"])
    
    if page == "Add Episode":
        st.header("Add New Episode")
        
        # URL Input
        youtube_url = st.text_input(
            "Enter YouTube URL for Coffee with Scott Adams episode:",
            placeholder="https://www.youtube.com/watch?v=..."
        )
        
        if st.button("Extract and Process Transcript", disabled=not youtube_url):
            video_id = validate_youtube_url(youtube_url)
            
            if not video_id:
                st.error("Please enter a valid YouTube URL.")
                return
            
            # Check if episode already exists
            existing_episode = db.get_episode_by_video_id(video_id)
            if existing_episode:
                st.warning("This episode has already been processed!")
                st.info(f"Episode Title: {existing_episode['title']}")
                return
            
            with st.spinner("Extracting transcript from YouTube..."):
                try:
                    # Extract transcript and metadata
                    transcript_data = youtube_handler.extract_transcript(video_id)
                    
                    if not transcript_data:
                        st.error("Could not extract transcript from this video. The video might not have captions available.")
                        return
                    
                    st.success("Transcript extracted successfully!")
                    
                    # Display raw transcript preview
                    st.subheader("Raw Transcript Preview:")
                    st.text_area("Raw transcript (first 500 characters):", 
                               transcript_data['transcript'][:500] + "...", 
                               height=150, disabled=True)
                    
                except Exception as e:
                    st.error(f"Error extracting transcript: {str(e)}")
                    return
            
            with st.spinner("Enhancing transcript with AI..."):
                try:
                    # Process transcript with AI
                    enhanced_transcript = transcript_processor.enhance_transcript(
                        transcript_data['transcript']
                    )
                    
                    st.success("Transcript enhanced successfully!")
                    
                    # Display enhanced transcript preview
                    st.subheader("Enhanced Transcript Preview:")
                    st.text_area("Enhanced transcript (first 500 characters):", 
                               enhanced_transcript[:500] + "...", 
                               height=150, disabled=True)
                    
                except Exception as e:
                    st.error(f"Error enhancing transcript: {str(e)}")
                    enhanced_transcript = transcript_data['transcript']  # Fallback to raw transcript
            
            with st.spinner("Saving to database..."):
                try:
                    # Save to database
                    episode_data = {
                        'video_id': video_id,
                        'title': transcript_data['title'],
                        'date': transcript_data['date'],
                        'url': youtube_url,
                        'raw_transcript': transcript_data['transcript'],
                        'enhanced_transcript': enhanced_transcript
                    }
                    
                    db.save_episode(episode_data)
                    st.success("Episode saved to database!")
                    
                    # Display episode info
                    st.subheader("Episode Information:")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Title:** {transcript_data['title']}")
                        st.write(f"**Date:** {transcript_data['date']}")
                    with col2:
                        st.write(f"**Video ID:** {video_id}")
                        st.write(f"**URL:** {youtube_url}")
                    
                except Exception as e:
                    st.error(f"Error saving to database: {str(e)}")
    
    elif page == "Browse Episodes":
        st.header("Browse Episodes")
        
        episodes = db.get_all_episodes()
        
        if not episodes:
            st.info("No episodes found. Add some episodes first!")
            return
        
        # Display episodes in a table
        df = pd.DataFrame(episodes)
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        
        # Sort by date (newest first)
        df = df.sort_values('date', ascending=False)
        
        st.subheader(f"Total Episodes: {len(df)}")
        
        # Display episodes
        for idx, episode in df.iterrows():
            with st.expander(f"{episode['title']} - {episode['date']}"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**Date:** {episode['date']}")
                    st.write(f"**Video ID:** {episode['video_id']}")
                    
                with col2:
                    st.link_button("Watch on YouTube", episode['url'])
                
                # Show transcript tabs
                tab1, tab2 = st.tabs(["Enhanced Transcript", "Raw Transcript"])
                
                with tab1:
                    st.text_area(
                        "Enhanced Transcript:", 
                        episode['enhanced_transcript'], 
                        height=300, 
                        key=f"enhanced_{episode['id']}"
                    )
                
                with tab2:
                    st.text_area(
                        "Raw Transcript:", 
                        episode['raw_transcript'], 
                        height=300, 
                        key=f"raw_{episode['id']}"
                    )
    
    elif page == "Search Transcripts":
        st.header("Search Transcripts")
        
        search_query = st.text_input("Enter search term:", placeholder="Enter words or phrases to search...")
        
        if search_query:
            search_results = db.search_transcripts(search_query)
            
            if search_results:
                st.subheader(f"Found {len(search_results)} result(s)")
                
                for result in search_results:
                    with st.expander(f"{result['title']} - {result['date']}"):
                        st.write(f"**Date:** {result['date']}")
                        st.link_button("Watch on YouTube", result['url'])
                        
                        # Highlight search terms in transcript
                        highlighted_transcript = result['enhanced_transcript']
                        
                        # Simple highlighting by replacing search terms with markdown bold
                        search_terms = search_query.lower().split()
                        for term in search_terms:
                            pattern = re.compile(re.escape(term), re.IGNORECASE)
                            highlighted_transcript = pattern.sub(f"**{term.upper()}**", highlighted_transcript)
                        
                        st.markdown("**Transcript (with search terms highlighted):**")
                        st.markdown(highlighted_transcript)
            else:
                st.info("No results found for your search query.")
    
    # Footer
    st.markdown("---")
    st.markdown("*Built with Streamlit for Coffee with Scott Adams podcast transcript management*")

if __name__ == "__main__":
    main()
