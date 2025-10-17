"""
Custom Exception Classes for YouTube Transcript Application

This module defines a hierarchy of custom exceptions for more specific and meaningful
error handling throughout the application. Each exception includes contextual information
and user-friendly messages.
"""

from typing import Optional, Dict, Any
import traceback


class ApplicationError(Exception):
    """
    Base exception class for all application-specific errors.
    All custom exceptions should inherit from this class.
    """
    
    def __init__(self, 
                 message: str, 
                 user_message: Optional[str] = None,
                 error_code: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None,
                 cause: Optional[Exception] = None):
        """
        Initialize the ApplicationError.
        
        Args:
            message: Technical error message for logging/debugging
            user_message: User-friendly error message for display
            error_code: Optional error code for categorization
            details: Additional context information
            cause: The underlying exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.user_message = user_message or "An error occurred. Please try again."
        self.error_code = error_code
        self.details = details or {}
        self.cause = cause
        
        # Preserve the original traceback if cause is provided
        if cause:
            self.__cause__ = cause
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to a dictionary for logging or API responses."""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "user_message": self.user_message,
            "error_code": self.error_code,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None
        }


class YouTubeAPIError(ApplicationError):
    """Exception raised for YouTube API related errors."""
    
    def __init__(self, 
                 message: str,
                 video_id: Optional[str] = None,
                 operation: Optional[str] = None,
                 is_blocking: bool = False,
                 is_rate_limit: bool = False,
                 cause: Optional[Exception] = None):
        """
        Initialize YouTubeAPIError.
        
        Args:
            message: Technical error message
            video_id: The video ID being processed
            operation: The operation that failed (e.g., 'extract_transcript')
            is_blocking: Whether YouTube is blocking requests (IP blocking)
            is_rate_limit: Whether this is a rate limit error
            cause: The underlying exception
        """
        user_message = self._generate_user_message(is_blocking, is_rate_limit, operation)
        
        details = {
            "video_id": video_id,
            "operation": operation,
            "is_blocking": is_blocking,
            "is_rate_limit": is_rate_limit
        }
        
        super().__init__(
            message=message,
            user_message=user_message,
            error_code="YOUTUBE_API_ERROR",
            details=details,
            cause=cause
        )
    
    def _generate_user_message(self, is_blocking: bool, is_rate_limit: bool, operation: Optional[str]) -> str:
        """Generate a user-friendly error message based on the error type."""
        if is_blocking:
            return ("YouTube is blocking requests from this server. "
                   "Please try using the Caption-Based extraction method or wait and try again later.")
        elif is_rate_limit:
            return "YouTube API rate limit exceeded. Please wait a few minutes and try again."
        elif operation == "extract_transcript":
            return "Failed to extract transcript from YouTube. Please verify the video URL and try a different extraction method."
        else:
            return "Failed to access YouTube video. Please check the URL and try again."


class CaptionScrapeError(ApplicationError):
    """Exception raised when web scraping for captions fails."""
    
    def __init__(self,
                 message: str,
                 video_id: Optional[str] = None,
                 url: Optional[str] = None,
                 status_code: Optional[int] = None,
                 cause: Optional[Exception] = None):
        """
        Initialize CaptionScrapeError.
        
        Args:
            message: Technical error message
            video_id: The video ID being scraped
            url: The URL that failed to scrape
            status_code: HTTP status code if applicable
            cause: The underlying exception
        """
        user_message = "Failed to extract captions from YouTube page. The video may not have captions available."
        
        if status_code == 404:
            user_message = "Video not found. Please check the YouTube URL."
        elif status_code == 403:
            user_message = "Access denied. The video may be private or restricted."
        
        details = {
            "video_id": video_id,
            "url": url,
            "status_code": status_code
        }
        
        super().__init__(
            message=message,
            user_message=user_message,
            error_code="CAPTION_SCRAPE_ERROR",
            details=details,
            cause=cause
        )


class TranscriptionError(ApplicationError):
    """Exception raised during audio transcription processes."""
    
    def __init__(self,
                 message: str,
                 video_id: Optional[str] = None,
                 stage: Optional[str] = None,
                 is_download_error: bool = False,
                 is_whisper_error: bool = False,
                 cause: Optional[Exception] = None):
        """
        Initialize TranscriptionError.
        
        Args:
            message: Technical error message
            video_id: The video ID being transcribed
            stage: The stage of transcription that failed (download, convert, transcribe)
            is_download_error: Whether this is an audio download error
            is_whisper_error: Whether this is a Whisper model error
            cause: The underlying exception
        """
        user_message = self._generate_user_message(stage, is_download_error, is_whisper_error)
        
        details = {
            "video_id": video_id,
            "stage": stage,
            "is_download_error": is_download_error,
            "is_whisper_error": is_whisper_error
        }
        
        super().__init__(
            message=message,
            user_message=user_message,
            error_code="TRANSCRIPTION_ERROR",
            details=details,
            cause=cause
        )
    
    def _generate_user_message(self, stage: Optional[str], is_download_error: bool, is_whisper_error: bool) -> str:
        """Generate a user-friendly error message based on the error type."""
        if is_download_error:
            return ("Failed to download audio from YouTube. "
                   "The video may be restricted or unavailable. "
                   "Try using the Caption-Based extraction method instead.")
        elif is_whisper_error:
            return ("Failed to transcribe audio. "
                   "The audio quality may be poor or the file may be corrupted. "
                   "Try using a different quality level or extraction method.")
        elif stage == "convert":
            return "Failed to convert audio format. Please try again with different quality settings."
        else:
            return "Failed to transcribe audio. Please try a different extraction method."


class ProcessingError(ApplicationError):
    """Exception raised during transcript processing and enhancement."""
    
    def __init__(self,
                 message: str,
                 operation: Optional[str] = None,
                 chunk_index: Optional[int] = None,
                 is_api_error: bool = False,
                 is_rate_limit: bool = False,
                 is_token_limit: bool = False,
                 cause: Optional[Exception] = None):
        """
        Initialize ProcessingError.
        
        Args:
            message: Technical error message
            operation: The processing operation (enhance, summarize, extract_topics)
            chunk_index: The chunk index that failed (if applicable)
            is_api_error: Whether this is an OpenAI API error
            is_rate_limit: Whether this is a rate limit error
            is_token_limit: Whether this is a token limit error
            cause: The underlying exception
        """
        user_message = self._generate_user_message(operation, is_api_error, is_rate_limit, is_token_limit)
        
        details = {
            "operation": operation,
            "chunk_index": chunk_index,
            "is_api_error": is_api_error,
            "is_rate_limit": is_rate_limit,
            "is_token_limit": is_token_limit
        }
        
        super().__init__(
            message=message,
            user_message=user_message,
            error_code="PROCESSING_ERROR",
            details=details,
            cause=cause
        )
    
    def _generate_user_message(self, operation: Optional[str], is_api_error: bool, 
                              is_rate_limit: bool, is_token_limit: bool) -> str:
        """Generate a user-friendly error message based on the error type."""
        if is_rate_limit:
            return "AI processing rate limit exceeded. Please wait a few seconds and try again."
        elif is_token_limit:
            return "Transcript is too long for AI processing. Consider using a shorter video or lower quality setting."
        elif is_api_error:
            return "Failed to connect to AI service. Please check your API key and try again."
        elif operation == "enhance":
            return "Failed to enhance transcript. The original transcript will be saved instead."
        elif operation == "summarize":
            return "Failed to generate summary. The transcript has been saved without a summary."
        elif operation == "extract_topics":
            return "Failed to extract topics. The transcript has been saved without topic analysis."
        else:
            return "Failed to process transcript. Please try again with different settings."


class DatabaseError(ApplicationError):
    """Exception raised for database-related errors."""
    
    def __init__(self,
                 message: str,
                 operation: Optional[str] = None,
                 table: Optional[str] = None,
                 is_connection_error: bool = False,
                 is_constraint_error: bool = False,
                 cause: Optional[Exception] = None):
        """
        Initialize DatabaseError.
        
        Args:
            message: Technical error message
            operation: The database operation (insert, update, delete, select)
            table: The table involved in the operation
            is_connection_error: Whether this is a connection error
            is_constraint_error: Whether this is a constraint violation
            cause: The underlying exception
        """
        user_message = self._generate_user_message(operation, is_connection_error, is_constraint_error)
        
        details = {
            "operation": operation,
            "table": table,
            "is_connection_error": is_connection_error,
            "is_constraint_error": is_constraint_error
        }
        
        super().__init__(
            message=message,
            user_message=user_message,
            error_code="DATABASE_ERROR",
            details=details,
            cause=cause
        )
    
    def _generate_user_message(self, operation: Optional[str], is_connection_error: bool, 
                              is_constraint_error: bool) -> str:
        """Generate a user-friendly error message based on the error type."""
        if is_connection_error:
            return "Failed to connect to database. Please try again later."
        elif is_constraint_error:
            return "This item already exists in the database. No need to process it again."
        elif operation == "insert":
            return "Failed to save transcript to database. Please try again."
        elif operation == "select":
            return "Failed to retrieve data from database. Please try again."
        elif operation == "update":
            return "Failed to update database record. Please try again."
        elif operation == "delete":
            return "Failed to delete record from database. Please try again."
        else:
            return "Database operation failed. Please try again later."


class ValidationError(ApplicationError):
    """Exception raised for input validation errors."""
    
    def __init__(self,
                 message: str,
                 field: Optional[str] = None,
                 value: Any = None,
                 requirement: Optional[str] = None,
                 cause: Optional[Exception] = None):
        """
        Initialize ValidationError.
        
        Args:
            message: Technical error message
            field: The field that failed validation
            value: The invalid value
            requirement: Description of the requirement that wasn't met
            cause: The underlying exception
        """
        user_message = self._generate_user_message(field, requirement)
        
        details = {
            "field": field,
            "value": value,
            "requirement": requirement
        }
        
        super().__init__(
            message=message,
            user_message=user_message,
            error_code="VALIDATION_ERROR",
            details=details,
            cause=cause
        )
    
    def _generate_user_message(self, field: Optional[str], requirement: Optional[str]) -> str:
        """Generate a user-friendly error message based on the validation error."""
        if field == "url":
            return "Invalid YouTube URL. Please provide a valid YouTube video link."
        elif field == "transcript":
            return "Invalid transcript. The transcript is empty or too short to process."
        elif requirement:
            return f"Invalid input: {requirement}"
        elif field:
            return f"Invalid {field}. Please check your input and try again."
        else:
            return "Invalid input. Please check your data and try again."


class AuthenticationError(ApplicationError):
    """Exception raised for authentication-related errors."""
    
    def __init__(self,
                 message: str,
                 service: Optional[str] = None,
                 is_missing_key: bool = False,
                 is_invalid_key: bool = False,
                 cause: Optional[Exception] = None):
        """
        Initialize AuthenticationError.
        
        Args:
            message: Technical error message
            service: The service that requires authentication (YouTube, OpenAI, etc.)
            is_missing_key: Whether the API key is missing
            is_invalid_key: Whether the API key is invalid
            cause: The underlying exception
        """
        user_message = self._generate_user_message(service, is_missing_key, is_invalid_key)
        
        details = {
            "service": service,
            "is_missing_key": is_missing_key,
            "is_invalid_key": is_invalid_key
        }
        
        super().__init__(
            message=message,
            user_message=user_message,
            error_code="AUTHENTICATION_ERROR",
            details=details,
            cause=cause
        )
    
    def _generate_user_message(self, service: Optional[str], is_missing_key: bool, is_invalid_key: bool) -> str:
        """Generate a user-friendly error message based on the authentication error."""
        if is_missing_key:
            if service:
                return f"{service} API key is not configured. Please add your API key in the environment settings."
            else:
                return "API key is missing. Please configure your API keys in the environment settings."
        elif is_invalid_key:
            if service:
                return f"Invalid {service} API key. Please check your API key configuration."
            else:
                return "Invalid API key. Please verify your API key is correct."
        elif service == "admin":
            return "Invalid admin credentials. Please check your email and password."
        else:
            return "Authentication failed. Please check your credentials and try again."


class NetworkError(ApplicationError):
    """Exception raised for network-related errors."""
    
    def __init__(self,
                 message: str,
                 url: Optional[str] = None,
                 timeout: bool = False,
                 connection_error: bool = False,
                 cause: Optional[Exception] = None):
        """
        Initialize NetworkError.
        
        Args:
            message: Technical error message
            url: The URL that failed to connect
            timeout: Whether this is a timeout error
            connection_error: Whether this is a connection error
            cause: The underlying exception
        """
        user_message = self._generate_user_message(timeout, connection_error)
        
        details = {
            "url": url,
            "timeout": timeout,
            "connection_error": connection_error
        }
        
        super().__init__(
            message=message,
            user_message=user_message,
            error_code="NETWORK_ERROR",
            details=details,
            cause=cause
        )
    
    def _generate_user_message(self, timeout: bool, connection_error: bool) -> str:
        """Generate a user-friendly error message based on the network error."""
        if timeout:
            return "Request timed out. The server is taking too long to respond. Please try again."
        elif connection_error:
            return "Failed to connect to the service. Please check your internet connection and try again."
        else:
            return "Network error occurred. Please check your connection and try again."