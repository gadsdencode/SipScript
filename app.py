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

def highlight_search_terms(text, search_query):
    """Highlight search terms in text with HTML styling while preserving all text"""
    if not search_query or not text:
        return text
    
    # Split search query into individual terms
    search_terms = [term.strip() for term in search_query.split() if term.strip()]
    
    highlighted_text = text
    
    # Create different colors for different search terms
    colors = ['#ffeb3b', '#ff9800', '#4caf50', '#2196f3', '#9c27b0', '#f44336']
    
    for i, term in enumerate(search_terms):
        if term:
            color = colors[i % len(colors)]
            # Use HTML highlighting with background color - preserve the original case
            pattern = re.compile(f'({re.escape(term)})', re.IGNORECASE)
            highlighted_text = pattern.sub(
                lambda m: f'<span style="background-color: {color}; padding: 2px 4px; border-radius: 3px; font-weight: bold; color: #000;">{m.group(1)}</span>',
                highlighted_text
            )
    
    return highlighted_text

def extract_context_snippets(text, search_query, context_length=150):
    """Extract context snippets around search terms"""
    if not search_query or not text:
        return []
    
    search_terms = [term.strip().lower() for term in search_query.split() if term.strip()]
    snippets = []
    
    for term in search_terms:
        # Find all occurrences of the term
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        matches = list(pattern.finditer(text))
        
        for match in matches:
            start_pos = max(0, match.start() - context_length)
            end_pos = min(len(text), match.end() + context_length)
            
            # Extract context around the match
            context = text[start_pos:end_pos]
            
            # Clean up the snippet
            if start_pos > 0:
                context = "..." + context
            if end_pos < len(text):
                context = context + "..."
            
            # Highlight the search term in the snippet
            highlighted_context = highlight_search_terms(context, term)
            
            if highlighted_context not in snippets:
                snippets.append(highlighted_context)
    
    return snippets[:5]  # Return top 5 unique snippets

def main():
    st.title("Coffee with Scott Adams - Transcript Extractor & Enhancer")
    st.markdown("---")
    
    # Initialize components
    db, youtube_handler, transcript_processor = initialize_components()
    
    # Sidebar for navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("Choose a page", ["Add Episode", "Browse Episodes", "Search Transcripts", "Database Management"])
    
    if page == "Add Episode":
        st.header("Add New Episode")
        
        # URL Input
        youtube_url = st.text_input(
            "Enter YouTube URL for Coffee with Scott Adams episode:",
            placeholder="https://www.youtube.com/watch?v=..."
        )
        
        # Extraction method selection
        st.subheader("Choose Transcript Extraction Method")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📝 Caption-Based Extraction**")
            st.markdown("• Fast and efficient")
            st.markdown("• Uses existing YouTube captions")
            st.markdown("• Best for videos with good captions")
            
        with col2:
            st.markdown("**🎤 Audio-Based Extraction**")
            st.markdown("• High accuracy speech recognition")
            st.markdown("• Works when captions aren't available")
            st.markdown("• Takes longer but more reliable")
        
        extraction_method = st.radio(
            "Select extraction method:",
            ["Caption-Based (Fast)", "Audio-Based (High Quality)"],
            horizontal=True
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
            
            # Choose extraction method based on user selection
            if "Caption-Based" in extraction_method:
                with st.spinner("Extracting transcript from YouTube captions..."):
                    try:
                        transcript_data = youtube_handler.extract_transcript(video_id)
                        
                        if not transcript_data:
                            st.error("Could not extract transcript from captions. Try the Audio-Based method instead.")
                            return
                        
                        st.success("Transcript extracted successfully from captions!")
                        
                    except Exception as e:
                        st.error(f"Error extracting transcript from captions: {str(e)}")
                        st.info("💡 Tip: Try the Audio-Based extraction method if captions aren't available.")
                        return
            else:
                # Audio-based extraction with progress updates
                progress_placeholder = st.empty()
                
                def progress_callback(message):
                    progress_placeholder.info(f"🎵 {message}")
                
                with st.spinner("Extracting transcript from audio... This may take several minutes."):
                    try:
                        transcript_data = youtube_handler.extract_transcript_from_audio(
                            video_id, 
                            progress_callback=progress_callback
                        )
                        
                        if not transcript_data:
                            st.error("Could not extract transcript from audio. Please try a different video.")
                            return
                        
                        progress_placeholder.empty()
                        st.success("Transcript extracted successfully from audio!")
                        
                    except Exception as e:
                        progress_placeholder.empty()
                        st.error(f"Error extracting transcript from audio: {str(e)}")
                        st.info("💡 Tip: Try the Caption-Based extraction method if available.")
                        return
            
            # Display raw transcript preview
            st.subheader("Raw Transcript Preview:")
            extraction_type = transcript_data.get('extraction_method', 'caption')
            st.caption(f"Extracted using: {extraction_type}-based method")
            st.text_area("Raw transcript (first 500 characters):", 
                       transcript_data['transcript'][:500] + "...", 
                       height=150, disabled=True)
            
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
                        'enhanced_transcript': enhanced_transcript,
                        'extraction_method': transcript_data.get('extraction_method', 'caption')
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
        for idx, row in df.iterrows():
            episode = row.to_dict()
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
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**Date:** {result['date']}")
                            st.write(f"**Video ID:** {result['video_id']}")
                            
                        with col2:
                            st.link_button("Watch on YouTube", result['url'])
                        
                        # Count occurrences
                        search_terms = [term.strip() for term in search_query.lower().split() if term.strip()]
                        total_matches = 0
                        for term in search_terms:
                            matches = len(re.findall(re.escape(term), result['enhanced_transcript'], re.IGNORECASE))
                            total_matches += matches
                        
                        st.markdown(f"**Found {total_matches} match(es) in transcript:**")
                        
                        # Get the full transcript
                        full_transcript = result['enhanced_transcript']
                        
                        # Apply highlighting using HTML spans
                        highlighted_transcript = full_transcript
                        for term in search_terms:
                            if term:
                                # Replace all instances with highlighted version
                                pattern = re.compile(f'({re.escape(term)})', re.IGNORECASE)
                                highlighted_transcript = pattern.sub(
                                    r'<span style="background-color: yellow; font-weight: bold; padding: 2px;">\1</span>',
                                    highlighted_transcript
                                )
                        
                        # Display the FULL transcript with highlighting in a scrollable container
                        st.markdown(
                            f"""
                            <div style="
                                background-color: #f8f9fa;
                                padding: 15px;
                                border-radius: 5px;
                                border-left: 4px solid #007acc;
                                max-height: 500px;
                                overflow-y: auto;
                                font-family: Arial, sans-serif;
                                line-height: 1.5;
                                white-space: pre-wrap;
                                word-wrap: break-word;
                                color: black;
                            ">
                                {highlighted_transcript}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        
                        # Show context snippets for better readability
                        st.markdown("**Key passages containing search terms:**")
                        context_snippets = extract_context_snippets(
                            result['enhanced_transcript'], 
                            search_query, 
                            context_length=150
                        )
                        
                        for i, snippet in enumerate(context_snippets[:3], 1):  # Show top 3 snippets
                            st.markdown(
                                f"""
                                <div style="
                                    background-color: #fff3cd;
                                    padding: 10px;
                                    margin: 5px 0;
                                    border-radius: 3px;
                                    border-left: 3px solid #ffc107;
                                    color: black;
                                ">
                                    <small><strong>Snippet {i}:</strong></small><br>
                                    {snippet}
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
            else:
                st.info("No results found for your search query.")
    
    elif page == "Database Management":
        st.header("Database Management")
        
        # Database Statistics
        total_episodes = db.get_episode_count()
        all_episodes = db.get_all_episodes()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Episodes", total_episodes)
        
        with col2:
            if all_episodes:
                total_words = sum(len(episode['enhanced_transcript'].split()) for episode in all_episodes)
                st.metric("Total Words", f"{total_words:,}")
            else:
                st.metric("Total Words", "0")
        
        with col3:
            if all_episodes:
                latest_date = max(episode['date'] for episode in all_episodes)
                st.metric("Latest Episode", latest_date)
            else:
                st.metric("Latest Episode", "None")
        
        st.markdown("---")
        
        # Database Operations
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Episode Management")
            
            if all_episodes:
                # Show episodes in a table format
                df = pd.DataFrame(all_episodes)
                df_display = df[['id', 'title', 'date', 'video_id']].copy()
                df_display.columns = ['ID', 'Title', 'Date', 'Video ID']
                
                st.dataframe(df_display, use_container_width=True)
                
                # Delete episode functionality
                st.markdown("**Delete Episode:**")
                episode_to_delete = st.selectbox(
                    "Select episode to delete:",
                    options=[f"{ep['id']} - {ep['title'][:50]}..." for ep in all_episodes],
                    key="delete_episode"
                )
                
                if st.button("Delete Selected Episode", type="secondary"):
                    if episode_to_delete:
                        episode_id = int(episode_to_delete.split(" - ")[0])
                        if db.delete_episode(episode_id):
                            st.success("Episode deleted successfully!")
                            st.rerun()
                        else:
                            st.error("Failed to delete episode.")
            else:
                st.info("No episodes in database yet.")
        
        with col2:
            st.subheader("Database Info")
            
            # Show database file info
            import os
            db_path = db.db_path
            if os.path.exists(db_path):
                file_size = os.path.getsize(db_path)
                st.write(f"**Database file:** {db_path}")
                st.write(f"**File size:** {file_size / 1024:.2f} KB")
                st.write(f"**Total episodes:** {total_episodes}")
            
            # Export functionality
            st.markdown("**Export Data:**")
            
            if st.button("Export to CSV"):
                if all_episodes:
                    df = pd.DataFrame(all_episodes)
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=f"podcast_transcripts_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No data to export.")
            
            # Database maintenance
            st.markdown("**Database Maintenance:**")
            
            if st.button("Optimize Database"):
                try:
                    # Run VACUUM to optimize the database
                    import sqlite3
                    with sqlite3.connect(db.db_path) as conn:
                        conn.execute("VACUUM")
                        conn.commit()
                    st.success("Database optimized successfully!")
                except Exception as e:
                    st.error(f"Failed to optimize database: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("*Built with Streamlit for Coffee with Scott Adams podcast transcript management*")

if __name__ == "__main__":
    main()
