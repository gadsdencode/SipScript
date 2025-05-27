import streamlit as st
import pandas as pd
import re
import csv
import io
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

def process_youtube_episode(youtube_url, extraction_method, quality_level, 
                           db, youtube_handler, transcript_processor, progress_placeholder=None):
    """Process a single YouTube URL and return the result"""
    result = {
        "success": False,
        "message": "",
        "video_id": None,
        "title": None,
        "error": None
    }
    
    video_id = validate_youtube_url(youtube_url)
    if not video_id:
        result["message"] = "Invalid YouTube URL"
        result["error"] = "Please enter a valid YouTube URL."
        return result
    
    # Set video_id in result
    result["video_id"] = video_id
    
    # Check if episode already exists
    existing_episode = db.get_episode_by_video_id(video_id)
    if existing_episode:
        result["message"] = "Episode already exists"
        result["title"] = existing_episode['title']
        result["error"] = f"This episode has already been processed: {existing_episode['title']}"
        return result
    
    # Choose extraction method based on user selection
    transcript_data = None
    extraction_error = None
    
    try:
        if "Caption-Based" in extraction_method:
            if progress_placeholder:
                progress_placeholder.info(f"📝 Extracting transcript from YouTube captions for video {video_id}...")
            
            transcript_data = youtube_handler.extract_transcript(video_id)
            if not transcript_data:
                extraction_error = "Could not extract transcript from captions."
        
        elif "Web Scraping" in extraction_method:
            if progress_placeholder:
                progress_placeholder.info(f"🌐 Extracting transcript using web scraping for video {video_id}...")
            
            transcript_data = youtube_handler.extract_transcript_web_scraping(video_id)
            if not transcript_data:
                extraction_error = "Could not extract transcript using web scraping."
        
        else:  # Audio-based
            def audio_progress_callback(message):
                if progress_placeholder:
                    progress_placeholder.info(f"🎵 {message} (Video ID: {video_id})")
            
            if progress_placeholder:
                progress_placeholder.info(f"🎤 Extracting transcript from audio for video {video_id}... This may take several minutes.")
            
            transcript_data = youtube_handler.extract_transcript_from_audio(
                video_id, 
                progress_callback=audio_progress_callback,
                quality_level=quality_level.split(" (")[0]  # Extract just "Fast", "Balanced", or "Best Quality"
            )
            if not transcript_data:
                extraction_error = "Could not extract transcript from audio."
        
        if extraction_error:
            result["message"] = "Extraction failed"
            result["error"] = extraction_error
            return result
        
        # Process transcript with AI
        if progress_placeholder:
            progress_placeholder.info(f"🧠 Enhancing transcript with AI for video {video_id}...")
        
        enhanced_transcript = transcript_processor.enhance_transcript(
            transcript_data['transcript']
        )
        
        # Save to database
        if progress_placeholder:
            progress_placeholder.info(f"💾 Saving to database for video {video_id}...")
        
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
        
        result["success"] = True
        result["message"] = "Processing completed successfully"
        result["title"] = transcript_data['title']
        
    except Exception as e:
        result["message"] = "Processing failed"
        result["error"] = str(e)
    
    return result

def main():
    st.title("CWSA Transcript Extractor & Search")
    st.markdown("---")
    
    # Initialize components
    db, youtube_handler, transcript_processor = initialize_components()
    
    # Sidebar for navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("Choose a page", ["Add Episode", "Browse Episodes", "Search Transcripts", "Database Management"])
    
    if page == "Add Episode":
        st.header("Add New Episode(s)")
        
        # Create tabs for single vs batch processing
        single_tab, batch_tab = st.tabs(["Single Episode", "Batch Episodes"])
        
        with single_tab:
            # URL Input
            youtube_url = st.text_input(
                "Enter YouTube URL for Coffee with Scott Adams episode:",
                placeholder="https://www.youtube.com/watch?v=...",
                key="single_url_input"
            )
            
            # Extraction method selection
            st.subheader("Choose Transcript Extraction Method")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**📝 Caption-Based**")
                st.markdown("• Fast API extraction")
                st.markdown("• May be blocked")
                
            with col2:
                st.markdown("**🌐 Web Scraping**")
                st.markdown("• Bypasses all blocks")
                st.markdown("• Always works")
                st.markdown("• Most reliable")
                
            with col3:
                st.markdown("**🎤 Audio-Based**")
                st.markdown("• Speech recognition")
                st.markdown("• No captions needed")
                st.markdown("• Takes 2-5 minutes")
            
            extraction_method = st.radio(
                "Select extraction method:",
                ["Caption-Based (Fast)", "Web Scraping (Bypasses Blocks)", "Audio-Based (No Captions Needed)"],
                horizontal=True,
                key="single_extraction_method"
            )
            
            # Show quality options for audio-based extraction
            quality_level = "Fast"  # Default value
            if "Audio-Based" in extraction_method:
                st.info("💡 **Tip:** Audio extraction takes longer but works when captions aren't available. Processing time: 2-5 minutes for typical episodes.")
                
                quality_level = st.selectbox(
                    "Choose processing speed:",
                    ["Fast (tiny model)", "Balanced (base model)", "Best Quality (small model)"],
                    index=0,
                    help="Fast: ~2 min, Balanced: ~4 min, Best: ~6 min for typical episodes",
                    key="single_quality_level"
                )
            
            if st.button("Extract and Process Transcript", disabled=not youtube_url, key="single_process_button"):
                progress_placeholder = st.empty()
                result = process_youtube_episode(
                    youtube_url, 
                    extraction_method, 
                    quality_level,
                    db, 
                    youtube_handler, 
                    transcript_processor,
                    progress_placeholder
                )
                
                progress_placeholder.empty()
                
                if result["success"]:
                    st.success("Episode processed and saved successfully!")
                    st.info(f"Episode Title: {result['title']}")
                else:
                    st.error(f"Error: {result['error']}")
        
        with batch_tab:
            st.subheader("Batch Episode Processing")
            st.markdown("""
            Add multiple episodes at once by providing a list of YouTube URLs. 
            Each URL will be processed sequentially.
            """)
            
            # Offer two input methods: manual input and file upload
            input_method = st.radio(
                "Choose input method:",
                ["Enter URLs manually", "Upload a file (CSV or TXT)"],
                key="batch_input_method"
            )
            
            urls_to_process = []
            
            if input_method == "Enter URLs manually":
                urls_text = st.text_area(
                    "Enter YouTube URLs (one per line):",
                    placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
                    height=150,
                    key="batch_urls_text"
                )
                
                if urls_text:
                    # Split by newline and filter out empty lines
                    urls_to_process = [url.strip() for url in urls_text.split('\n') if url.strip()]
                    st.info(f"Found {len(urls_to_process)} URL(s) to process")
            else:
                uploaded_file = st.file_uploader("Upload a file with YouTube URLs", type=["txt", "csv"])
                
                if uploaded_file is not None:
                    try:
                        # Determine file type and parse accordingly
                        if uploaded_file.name.endswith('.csv'):
                            df = pd.read_csv(uploaded_file)
                            # Look for a column that might contain URLs
                            url_column = None
                            for col in df.columns:
                                if any(('url' in col.lower()) or ('link' in col.lower())):
                                    url_column = col
                                    break
                            
                            if url_column:
                                urls_to_process = df[url_column].dropna().tolist()
                            else:
                                # Assume the first column contains URLs
                                urls_to_process = df.iloc[:, 0].dropna().tolist()
                        else:
                            # Assume TXT file with one URL per line
                            content = uploaded_file.getvalue().decode("utf-8")
                            urls_to_process = [url.strip() for url in content.split('\n') if url.strip()]
                        
                        st.info(f"Found {len(urls_to_process)} URL(s) to process from the uploaded file")
                    except Exception as e:
                        st.error(f"Error parsing file: {str(e)}")
            
            # Extraction method selection (same as single mode but with different keys)
            st.subheader("Choose Transcript Extraction Method")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**📝 Caption-Based**")
                st.markdown("• Fast API extraction")
                st.markdown("• May be blocked")
                
            with col2:
                st.markdown("**🌐 Web Scraping**")
                st.markdown("• Bypasses all blocks")
                st.markdown("• Always works")
                st.markdown("• Most reliable")
                
            with col3:
                st.markdown("**🎤 Audio-Based**")
                st.markdown("• Speech recognition")
                st.markdown("• No captions needed")
                st.markdown("• Takes 2-5 minutes")
            
            batch_extraction_method = st.radio(
                "Select extraction method for all URLs:",
                ["Caption-Based (Fast)", "Web Scraping (Bypasses Blocks)", "Audio-Based (No Captions Needed)"],
                horizontal=True,
                key="batch_extraction_method"
            )
            
            # Show quality options for audio-based extraction
            batch_quality_level = "Fast"  # Default value
            if "Audio-Based" in batch_extraction_method:
                st.info("💡 **Tip:** Audio extraction takes longer but works when captions aren't available. For batch processing, the Fast option is recommended.")
                
                batch_quality_level = st.selectbox(
                    "Choose processing speed:",
                    ["Fast (tiny model)", "Balanced (base model)", "Best Quality (small model)"],
                    index=0,
                    help="Fast: ~2 min, Balanced: ~4 min, Best: ~6 min per episode",
                    key="batch_quality_level"
                )
            
            # Skip duplicate option
            skip_existing = st.checkbox(
                "Skip episodes that already exist in the database", 
                value=True,
                key="skip_existing"
            )
            
            # Process button
            if st.button("Process All URLs", disabled=len(urls_to_process) == 0, key="batch_process_button"):
                if len(urls_to_process) > 0:
                    st.subheader("Processing Results")
                    
                    # Create placeholders for results
                    progress_bar = st.progress(0)
                    status_placeholder = st.empty()
                    results_placeholder = st.empty()
                    
                    # Initialize results tracking
                    total_urls = len(urls_to_process)
                    results = {
                        "success": 0,
                        "skipped": 0,
                        "failed": 0,
                        "details": []
                    }
                    
                    # Process each URL
                    for i, url in enumerate(urls_to_process):
                        # Update progress
                        progress_percent = (i / total_urls)
                        progress_bar.progress(progress_percent)
                        status_placeholder.info(f"Processing URL {i+1} of {total_urls}: {url}")
                        
                        # Process the URL
                        result = process_youtube_episode(
                            url,
                            batch_extraction_method,
                            batch_quality_level,
                            db,
                            youtube_handler,
                            transcript_processor,
                            status_placeholder
                        )
                        
                        # Track result
                        if result["success"]:
                            results["success"] += 1
                            results["details"].append({
                                "url": url,
                                "status": "✅ Success",
                                "title": result["title"],
                                "message": "Processed successfully"
                            })
                        elif "already exists" in result.get("message", "").lower() and skip_existing:
                            results["skipped"] += 1
                            results["details"].append({
                                "url": url,
                                "status": "⏭️ Skipped",
                                "title": result.get("title", "Unknown"),
                                "message": "Already exists in database"
                            })
                        else:
                            results["failed"] += 1
                            results["details"].append({
                                "url": url,
                                "status": "❌ Failed",
                                "title": "N/A",
                                "message": result.get("error", "Unknown error")
                            })
                        
                        # Update results display
                        results_df = pd.DataFrame(results["details"])
                        results_placeholder.dataframe(results_df)
                    
                    # Complete progress bar
                    progress_bar.progress(1.0)
                    status_placeholder.success("Batch processing completed!")
                    
                    # Display final summary
                    st.subheader("Summary")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Successfully Processed", results["success"])
                    col2.metric("Skipped (Already Exist)", results["skipped"])
                    col3.metric("Failed", results["failed"])
    
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
            
            if all_episodes:
                export_format = st.selectbox(
                    "Select export format:",
                    ["CSV", "JSON"],
                    key="export_format"
                )
                
                if st.button("Export All Episodes", key="export_button"):
                    df = pd.DataFrame(all_episodes)
                    
                    if export_format == "CSV":
                        # Prepare CSV file for download
                        csv_data = df[['id', 'title', 'date', 'url', 'video_id']].to_csv(index=False)
                        
                        st.download_button(
                            label="Download CSV",
                            data=csv_data,
                            file_name="cwsa_episodes.csv",
                            mime="text/csv"
                        )
                    else:
                        # Prepare JSON file for download
                        json_data = df[['id', 'title', 'date', 'url', 'video_id']].to_json(orient="records")
                        
                        st.download_button(
                            label="Download JSON",
                            data=json_data,
                            file_name="cwsa_episodes.json",
                            mime="application/json"
                        )
            else:
                st.info("No episodes to export.")

if __name__ == "__main__":
    main()
