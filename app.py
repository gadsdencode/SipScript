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
    # Get OpenAI API key
    import os
    openai_api_key = os.getenv("OPENAI_API_KEY", "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")
    
    db = DatabaseManager()
    youtube_handler = YouTubeHandler()
    transcript_processor = TranscriptProcessor(api_key=openai_api_key)
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
        
        # Extract topics and generate summary
        if progress_placeholder:
            progress_placeholder.info(f"📊 Extracting topics and generating summary for video {video_id}...")
        
        # Extract key topics (which includes topics, key points, and a summary)
        topics_data = transcript_processor.extract_key_topics(enhanced_transcript)
        
        # Generate a more detailed summary if needed
        detailed_summary = transcript_processor.generate_summary(enhanced_transcript)
        
        # Convert topics and key_points lists to strings for storage
        topics_str = None
        key_points_str = None
        summary = None
        
        if isinstance(topics_data, dict):
            import json
            if 'topics' in topics_data and topics_data['topics']:
                topics_str = json.dumps(topics_data['topics'])
            if 'key_points' in topics_data and topics_data['key_points']:
                key_points_str = json.dumps(topics_data['key_points'])
            if 'summary' in topics_data and topics_data['summary']:
                summary = topics_data['summary']
        
        # If the topic extraction didn't provide a summary, use the detailed one
        if not summary:
            summary = detailed_summary
        
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
            'extraction_method': transcript_data.get('extraction_method', 'caption'),
            'topics': topics_str,
            'key_points': key_points_str,
            'summary': summary
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
    st.markdown("Created by Gadsdencode")
    st.markdown("---")
    
    # Check for OpenAI API key
    import os
    openai_api_key = os.getenv("OPENAI_API_KEY", "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")
    
    # Only show warning if API key is truly missing (not when using our hardcoded default)
    if not openai_api_key or openai_api_key == "your-openai-api-key-here":
        st.warning("""
        ⚠️ **OpenAI API Key Not Configured**
        
        Some features like transcript enhancement, topic extraction, and summary generation require an OpenAI API key.
        
        To fix this:
        1. Get an API key from [OpenAI Platform](https://platform.openai.com/api-keys)
        2. Set it as an environment variable named `OPENAI_API_KEY`
        
        Without this key, topic extraction and summary generation will fail.
        """)
    
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
                                if ('url' in col.lower()) or ('link' in col.lower()):
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
                tab1, tab2, tab3 = st.tabs(["Summary & Topics", "Enhanced Transcript", "Raw Transcript"])
                
                with tab1:
                    # Display summary if available
                    if episode.get('summary'):
                        st.subheader("Episode Summary")
                        st.markdown(f"<div style='background-color: #f0f2f6; padding: 15px; border-radius: 5px; border-left: 4px solid #4CAF50; color: black;'>{episode['summary']}</div>", unsafe_allow_html=True)
                    
                    # Display topics if available
                    if episode.get('topics'):
                        try:
                            import json
                            topics = json.loads(episode['topics'])
                            
                            st.subheader("Main Topics")
                            topic_cols = st.columns(min(3, len(topics)))
                            
                            for i, topic in enumerate(topics):
                                col_index = i % len(topic_cols)
                                with topic_cols[col_index]:
                                    st.markdown(f"<div style='background-color: #e1f5fe; margin: 5px 0; padding: 10px; border-radius: 5px; text-align: center; color: black;'><b>{topic}</b></div>", unsafe_allow_html=True)
                        except:
                            st.write("Topics data not available in proper format.")
                    
                    # Display key points if available
                    if episode.get('key_points'):
                        try:
                            import json
                            key_points = json.loads(episode['key_points'])
                            
                            st.subheader("Key Points")
                            for i, point in enumerate(key_points, 1):
                                st.markdown(f"<div style='background-color: #fff8e1; margin: 5px 0; padding: 10px; border-radius: 5px; color: black;'><b>{i}.</b> {point}</div>", unsafe_allow_html=True)
                        except:
                            st.write("Key points data not available in proper format.")
                    
                    # If no summary or topics available
                    if not episode.get('summary') and not episode.get('topics') and not episode.get('key_points'):
                        st.info("No summary or topic data available for this episode.")
                        
                        # Offer to generate them
                        if st.button("Generate Summary and Topics", key=f"gen_summary_{episode['id']}"):
                            with st.spinner("Analyzing transcript and generating summary..."):
                                try:
                                    # Process only a chunk of the transcript to avoid token limits
                                    transcript_chunk = episode['enhanced_transcript'][:4000]  # First 4000 characters
                                    
                                    # Generate topics and summary
                                    topics_data = transcript_processor.extract_key_topics(transcript_chunk)
                                    detailed_summary = transcript_processor.generate_summary(transcript_chunk)
                                    
                                    # Convert topics and key_points to strings for storage
                                    import json
                                    topics_str = None
                                    key_points_str = None
                                    summary = None
                                    
                                    if isinstance(topics_data, dict):
                                        if 'topics' in topics_data and topics_data['topics']:
                                            topics_str = json.dumps(topics_data['topics'])
                                        if 'key_points' in topics_data and topics_data['key_points']:
                                            key_points_str = json.dumps(topics_data['key_points'])
                                        if 'summary' in topics_data and topics_data['summary'] and "failed" not in topics_data['summary'].lower():
                                            summary = topics_data['summary']
                                    
                                    # If topic extraction didn't provide a summary, use the detailed one
                                    if not summary or "failed" in summary.lower():
                                        summary = detailed_summary
                                    
                                    # Check if we have valid data
                                    if (not topics_str and not key_points_str) or not summary or "failed" in summary.lower():
                                        st.error("Failed to generate meaningful topics or summary. Please try again or adjust the transcript.")
                                        return
                                    
                                    # Update the episode in the database
                                    updated_data = {
                                        'video_id': episode['video_id'],
                                        'title': episode['title'],
                                        'date': episode['date'],
                                        'url': episode['url'],
                                        'raw_transcript': episode['raw_transcript'],
                                        'enhanced_transcript': episode['enhanced_transcript'],
                                        'extraction_method': episode.get('extraction_method', 'caption'),
                                        'topics': topics_str,
                                        'key_points': key_points_str,
                                        'summary': summary
                                    }
                                    
                                    db.save_episode(updated_data)
                                    st.success("Summary and topics generated successfully!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error generating summary and topics: {str(e)}")
                                    st.info("Tip: Try again or check your OpenAI API key configuration.")
                
                with tab2:
                    st.text_area(
                        "Enhanced Transcript:", 
                        episode['enhanced_transcript'], 
                        height=300, 
                        key=f"enhanced_{episode['id']}"
                    )
                
                with tab3:
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
                        
                        # Show topics and summary if available
                        if result.get('summary') or result.get('topics'):
                            st.markdown("### Summary & Topics")
                            st.markdown("<hr style='margin: 0.5em 0; border-color: #f0f0f0;'>", unsafe_allow_html=True)
                            
                            # Show summary if available
                            if result.get('summary'):
                                st.subheader("Episode Summary")
                                st.markdown(f"<div style='background-color: #f0f2f6; padding: 15px; border-radius: 5px; border-left: 4px solid #4CAF50; color: black;'>{result['summary']}</div>", unsafe_allow_html=True)
                            
                            # Show topics if available
                            col1, col2 = st.columns([1, 1])
                            
                            with col1:
                                if result.get('topics'):
                                    try:
                                        import json
                                        topics = json.loads(result['topics'])
                                        
                                        st.subheader("Main Topics")
                                        for topic in topics:
                                            st.markdown(f"<div style='background-color: #e1f5fe; margin: 5px 0; padding: 10px; border-radius: 5px; color: black;'><b>•</b> {topic}</div>", unsafe_allow_html=True)
                                    except:
                                        pass
                            
                            with col2:
                                if result.get('key_points'):
                                    try:
                                        import json
                                        key_points = json.loads(result['key_points'])
                                        
                                        st.subheader("Key Points")
                                        for i, point in enumerate(key_points, 1):
                                            st.markdown(f"<div style='background-color: #fff8e1; margin: 5px 0; padding: 10px; border-radius: 5px; color: black;'><b>{i}.</b> {point}</div>", unsafe_allow_html=True)
                                    except:
                                        pass
                        
                        # Add a separator before the transcript sections
                        st.markdown("<hr style='margin: 1em 0; border-color: #f0f0f0;'>", unsafe_allow_html=True)
                        
                        # Create tabs for context and full transcript
                        st.markdown("### Transcript Details")
                        tab1, tab2 = st.tabs(["Context Snippets", "Full Transcript"])
                        
                        with tab1:
                            # Get the full transcript
                            full_transcript = result['enhanced_transcript']
                            
                            # Show context snippets for better readability
                            st.markdown("**Key passages containing search terms:**")
                            context_snippets = extract_context_snippets(
                                result['enhanced_transcript'], 
                                search_query, 
                                context_length=150
                            )
                            
                            for i, snippet in enumerate(context_snippets, 1):
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
                        
                        with tab2:
                            # Apply highlighting using HTML spans
                            highlighted_transcript = full_transcript
                            for term in search_terms:
                                if term:
                                    # Replace all instances with highlighted version
                                    pattern = re.compile(f'({re.escape(term)})', re.IGNORECASE)
                                    highlighted_transcript = pattern.sub(
                                        r'<span style="background-color: yellow; font-weight: bold; padding: 2px; color: black;">\1</span>',
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
        
        # Additional statistics about topics and summaries
        if all_episodes:
            col1, col2 = st.columns(2)
            with col1:
                episodes_with_summaries = sum(1 for ep in all_episodes if ep.get('summary'))
                summary_percentage = round((episodes_with_summaries / len(all_episodes)) * 100, 1) if all_episodes else 0
                st.metric("Episodes with Summaries", f"{episodes_with_summaries}/{len(all_episodes)} ({summary_percentage}%)")
            
            with col2:
                episodes_with_topics = sum(1 for ep in all_episodes if ep.get('topics'))
                topics_percentage = round((episodes_with_topics / len(all_episodes)) * 100, 1) if all_episodes else 0
                st.metric("Episodes with Topics", f"{episodes_with_topics}/{len(all_episodes)} ({topics_percentage}%)")
        
        st.markdown("---")
        
        # Database Operations
        tab1, tab2, tab3 = st.tabs(["Episode Management", "Data Enrichment", "Database Info"])
        
        with tab1:
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
        
        with tab2:
            st.subheader("Generate Summaries and Topics")
            
            # Check if we have episodes that need enrichment
            if all_episodes:
                # Count episodes without summaries or topics
                episodes_missing_data = [ep for ep in all_episodes if not ep.get('summary') or not ep.get('topics')]
                
                if episodes_missing_data:
                    st.info(f"Found {len(episodes_missing_data)} episode(s) that need summaries or topics.")
                    
                    # Options for batch processing
                    process_options = st.radio(
                        "Choose processing option:",
                        ["Process all episodes missing data", "Select specific episodes to process"],
                        key="process_option"
                    )
                    
                    episodes_to_process = []
                    
                    if process_options == "Process all episodes missing data":
                        episodes_to_process = episodes_missing_data
                    else:
                        # Allow selecting specific episodes
                        episode_options = [f"{ep['id']} - {ep['title'][:50]}..." for ep in episodes_missing_data]
                        selected_episodes = st.multiselect(
                            "Select episodes to process:",
                            options=episode_options,
                            key="selected_episodes"
                        )
                        
                        # Extract episode IDs from selection
                        selected_ids = [int(ep.split(" - ")[0]) for ep in selected_episodes]
                        episodes_to_process = [ep for ep in episodes_missing_data if ep['id'] in selected_ids]
                    
                    # Add advanced options
                    with st.expander("Advanced Options"):
                        chunk_size = st.slider(
                            "Transcript chunk size (characters):",
                            min_value=1000,
                            max_value=8000,
                            value=4000,
                            step=500,
                            help="Larger chunks include more context but may exceed token limits"
                        )
                        
                        max_retries = st.number_input(
                            "Max retries per episode:",
                            min_value=0,
                            max_value=5,
                            value=2,
                            help="Number of times to retry processing an episode if it fails"
                        )
                    
                    if st.button("Generate Summaries and Topics", disabled=len(episodes_to_process) == 0):
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        error_log = []
                        
                        # Process each episode
                        for i, episode in enumerate(episodes_to_process):
                            progress_percent = i / len(episodes_to_process)
                            progress_bar.progress(progress_percent)
                            status_text.info(f"Processing {i+1}/{len(episodes_to_process)}: {episode['title'][:50]}...")
                            
                            success = False
                            retries = 0
                            
                            # Try to process with retries
                            while not success and retries <= max_retries:
                                try:
                                    if retries > 0:
                                        status_text.warning(f"Retry {retries}/{max_retries} for episode: {episode['title'][:50]}...")
                                    
                                    # Process transcript in chunks if it's very long
                                    transcript = episode['enhanced_transcript']
                                    transcript_chunk = transcript[:chunk_size]  # Use only the first chunk for topic extraction
                                    
                                    # Generate topics and summary
                                    topics_data = transcript_processor.extract_key_topics(transcript_chunk)
                                    
                                    # If no error occurred with topics, try to get a detailed summary
                                    detailed_summary = transcript_processor.generate_summary(transcript_chunk)
                                    
                                    # Convert topics and key_points to strings for storage
                                    import json
                                    topics_str = None
                                    key_points_str = None
                                    summary = None
                                    
                                    if isinstance(topics_data, dict):
                                        if 'topics' in topics_data and topics_data['topics']:
                                            topics_str = json.dumps(topics_data['topics'])
                                        if 'key_points' in topics_data and topics_data['key_points']:
                                            key_points_str = json.dumps(topics_data['key_points'])
                                        if 'summary' in topics_data and topics_data['summary']:
                                            summary = topics_data['summary']
                                    
                                    # If topic extraction didn't provide a summary, use the detailed one
                                    if not summary or "failed" in summary.lower():
                                        summary = detailed_summary
                                    
                                    # Check if we have valid data
                                    if (topics_str or key_points_str) and summary and "failed" not in summary.lower():
                                        # Update the episode in the database
                                        updated_data = {
                                            'video_id': episode['video_id'],
                                            'title': episode['title'],
                                            'date': episode['date'],
                                            'url': episode['url'],
                                            'raw_transcript': episode['raw_transcript'],
                                            'enhanced_transcript': episode['enhanced_transcript'],
                                            'extraction_method': episode.get('extraction_method', 'caption'),
                                            'topics': topics_str,
                                            'key_points': key_points_str,
                                            'summary': summary
                                        }
                                        
                                        db.save_episode(updated_data)
                                        success = True
                                    else:
                                        raise ValueError("No valid topics or summary generated")
                                    
                                except Exception as e:
                                    retries += 1
                                    error_message = f"Error processing episode {episode['id']}: {str(e)}"
                                    if retries > max_retries:
                                        error_log.append({
                                            "episode_id": episode['id'],
                                            "title": episode['title'],
                                            "error": str(e)
                                        })
                            
                            # Show success or failure for this episode
                            if success:
                                status_text.success(f"Successfully processed episode {i+1}/{len(episodes_to_process)}")
                            else:
                                status_text.error(f"Failed to process episode {i+1}/{len(episodes_to_process)} after {max_retries} retries")
                        
                        progress_bar.progress(1.0)
                        
                        # Show final results
                        st.subheader("Processing Results")
                        successful_count = len(episodes_to_process) - len(error_log)
                        st.success(f"Successfully processed {successful_count} out of {len(episodes_to_process)} episodes.")
                        
                        if error_log:
                            st.error(f"Failed to process {len(error_log)} episodes.")
                            with st.expander("Show Error Details"):
                                for error in error_log:
                                    st.markdown(f"**Episode {error['episode_id']}:** {error['title']}")
                                    st.markdown(f"*Error:* {error['error']}")
                                    st.markdown("---")
                        
                        # Offer to reload the page
                        if successful_count > 0:
                            if st.button("Reload Page to See Results"):
                                st.rerun()
                else:
                    st.success("All episodes have summaries and topics already!")
            else:
                st.info("No episodes in database yet.")
        
        with tab3:
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
