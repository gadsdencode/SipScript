# Overview

This is a **YouTube Transcript Archive and Search System** built with Streamlit. The application allows users to extract, enhance, and search through YouTube video transcripts. It supports multiple extraction methods including YouTube's native captions, web scraping, and Whisper-based audio transcription as fallbacks. The system uses OpenAI's GPT models to enhance raw transcripts with proper formatting, punctuation, and readability improvements.

The application stores all processed transcripts in a SQLite database with support for full-text search, topic extraction, and summary generation. It includes an admin authentication system for content management.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Frontend Architecture

**Technology**: Streamlit web framework  
**Rationale**: Streamlit provides rapid development of data-focused web applications with minimal frontend code. It's ideal for internal tools and dashboards that need quick iteration.

**Key Components**:
- Session state management for component caching
- Real-time search with highlight functionality
- CSV export capabilities for transcript data
- Admin authentication flow

## Backend Architecture

**Core Processing Pipeline**:

1. **Video Input Validation** (`validate_youtube_url`)
   - Supports multiple YouTube URL formats (watch, youtu.be, embed)
   - Extracts video ID using regex pattern matching
   - Problem solved: Handle various user input formats consistently

2. **Multi-Strategy Transcript Extraction** (`YouTubeHandler`)
   - **Primary**: YouTube Transcript API for native captions
   - **Fallback 1**: Web scraping via CaptionScraper (timedtext API and page scraping)
   - **Fallback 2**: Audio extraction + Whisper transcription
   - Rationale: YouTube's bot protection and API limitations require multiple extraction strategies. Each method has different success rates and quota limits.

3. **AI Enhancement Pipeline** (`TranscriptProcessor`)
   - Chunk-based processing (3000 char chunks) to handle token limits
   - OpenAI GPT integration for grammar and formatting improvements
   - Fallback to original text if enhancement fails
   - Problem solved: Raw transcripts often lack punctuation and proper formatting, making them hard to read

4. **Metadata Enrichment**
   - YouTube Data API integration for official metadata
   - Fallback scraping for title, date, channel information
   - Ensures metadata availability even when API quotas are exhausted

## Data Storage

**Technology**: SQLite database  
**Rationale**: Lightweight, serverless, file-based storage suitable for single-instance deployments without operational overhead.

**Schema Design**:

- **episodes table**: Stores video metadata and transcripts
  - Tracks both raw and enhanced transcripts
  - Includes extraction method for debugging/analytics
  - Supports optional AI-generated topics, key points, and summaries
  - Timestamp tracking (created_at, updated_at)

- **admin_users table**: Authentication and authorization
  - Password hashing for security
  - Active/inactive status flags
  - Email-based identification

**Key Design Decisions**:
- Stores both raw and enhanced transcripts to preserve original data
- extraction_method field tracks which strategy succeeded (caption/web_scraping/audio)
- TEXT fields for flexible content length without size limitations

## Authentication & Authorization

**Mechanism**: Custom password hashing with secrets module  
**Rationale**: Lightweight authentication without external dependencies. Suitable for small team/admin-only access.

**Implementation**:
- SHA-256 password hashing
- Session-based authentication via Streamlit session state
- Simple admin user management

**Limitation**: Not suitable for public-facing multi-tenant scenarios. For production scale, consider OAuth or JWT-based systems.

## Error Handling Strategy

**Multi-Layer Fallbacks**:
- Transcript extraction: 3 methods with graceful degradation
- API processing: Chunk-level error isolation
- Database operations: Try/except with rollback support

**Problem Addressed**: YouTube's increasing bot protection and API rate limits require robust fallback mechanisms. The system prioritizes availability over perfection.

# External Dependencies

## APIs and Services

1. **OpenAI API** (Required for enhancement)
   - Purpose: Transcript enhancement, summarization, topic extraction
   - Configuration: API key via `OPENAI_API_KEY` environment variable
   - Model: GPT-based text processing
   - Rate Limits: Chunked processing to stay within token limits

2. **YouTube Data API v3** (Optional but recommended)
   - Purpose: Official video metadata retrieval
   - Configuration: API key via `YOUTUBE_API_KEY` environment variable
   - Quota: Daily quota limitations require fallback scraping
   - Authentication: Developer API key

3. **YouTube Transcript API** (Primary transcript source)
   - Library: `youtube-transcript-api`
   - Purpose: Native caption extraction
   - Limitation: Subject to YouTube's bot detection

## Third-Party Libraries

**Core Processing**:
- `yt-dlp`: Audio download for Whisper transcription fallback
- `whisper`: OpenAI's audio transcription model (loaded on-demand for memory efficiency)
- `pydub`: Audio processing and format conversion

**Web Scraping**:
- `requests`: HTTP client for web scraping
- `beautifulsoup4`: HTML parsing (implied by scraping logic)

**Data Processing**:
- `pandas`: Data manipulation and CSV export
- `sqlite3`: Database interface (Python standard library)

**Authentication & Security**:
- `hashlib`: Password hashing (Python standard library)
- `secrets`: Secure random generation (Python standard library)

**UI Framework**:
- `streamlit`: Web application framework
- `python-dotenv`: Environment variable management

## Storage Dependencies

**SQLite Database**: 
- File: `podcast_transcripts.db`
- No external database server required
- Automatic creation and migration support

**Temporary Files**:
- Audio downloads stored in system temp directory
- Automatic cleanup after processing

## Environment Variables Required

```
OPENAI_API_KEY=<required-for-enhancement>
YOUTUBE_API_KEY=<optional-improves-metadata>
```

## Known Integration Challenges

1. **YouTube Bot Protection**: Increasingly aggressive bot detection requires cookie-based authentication for yt-dlp
2. **API Quotas**: YouTube Data API has daily quota limits necessitating web scraping fallbacks
3. **Whisper Model Size**: Large model files require on-demand loading to manage memory
4. **Audio Extraction**: yt-dlp may require browser cookies for successful downloads