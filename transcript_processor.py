import os
import re
from typing import Optional, Dict, Union, List
from openai import OpenAI

class TranscriptProcessor:
    def __init__(self, api_key=None):
        """Initialize transcript processor with OpenAI client"""
        # Use provided API key or fall back to environment variable
        if api_key:
            self.client = OpenAI(api_key=api_key)
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("Warning: No OpenAI API key provided or found in environment variables.")
                print("AI-powered features will not work correctly.")
            self.client = OpenAI(api_key=api_key)
    
    def enhance_transcript(self, raw_transcript: str) -> str:
        """
        Enhance raw transcript using OpenAI API
        Clean up grammar, punctuation, and improve readability
        """
        if not raw_transcript or not raw_transcript.strip():
            raise ValueError("Raw transcript is empty or invalid")
        
        # Split long transcripts into chunks to avoid token limits
        chunks = self._split_transcript(raw_transcript)
        enhanced_chunks = []
        
        for chunk in chunks:
            try:
                enhanced_chunk = self._process_chunk(chunk)
                enhanced_chunks.append(enhanced_chunk)
            except Exception as e:
                # If processing fails, use the original chunk
                print(f"Warning: Failed to enhance chunk: {str(e)}")
                enhanced_chunks.append(chunk)
        
        return "\n\n".join(enhanced_chunks)
    
    def _split_transcript(self, transcript: str, max_chunk_size: int = 3000) -> list:
        """Split transcript into manageable chunks for API processing"""
        # Clean up the transcript first
        transcript = self._basic_cleanup(transcript)
        
        # Split by sentences if possible, otherwise by words
        sentences = re.split(r'(?<=[.!?])\s+', transcript)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                current_chunk += sentence + " "
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [transcript]
    
    def _basic_cleanup(self, text: str) -> str:
        """Basic cleanup of transcript text"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove timestamp markers if present
        text = re.sub(r'\[\d+:\d+:\d+\]', '', text)
        text = re.sub(r'\d+:\d+', '', text)
        
        # Clean up common transcript artifacts
        text = re.sub(r'\[Music\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[Applause\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[Laughter\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[Inaudible\]', '', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    def _process_chunk(self, chunk: str) -> str:
        """Process a single chunk using OpenAI API"""
        prompt = """You are an expert transcript editor. Please clean up the following podcast transcript by:

1. Correcting spelling, grammar, and punctuation errors
2. Adding proper paragraph breaks for readability
3. Maintaining the speaker's natural speaking style and voice
4. Preserving all original content and meaning
5. Removing any obvious transcription artifacts or repeated words
6. Ensuring proper capitalization

Important: Do not add, remove, or change the actual content or meaning. Only improve the technical quality of the text.

Transcript to clean:"""

        try:
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional transcript editor specializing in podcast content. Your job is to clean up transcripts while preserving the original meaning and speaker's voice."
                    },
                    {
                        "role": "user",
                        "content": f"{prompt}\n\n{chunk}"
                    }
                ],
                temperature=0.1,  # Low temperature for consistent editing
                max_tokens=4000
            )
            
            enhanced_text = response.choices[0].message.content.strip()
            
            # Basic validation - ensure we got meaningful output
            if len(enhanced_text) < len(chunk) * 0.5:
                raise ValueError("Enhanced text is suspiciously short")
            
            return enhanced_text
            
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def extract_key_topics(self, transcript: str) -> Dict:
        """Extract key topics and themes from the transcript"""
        if not transcript or len(transcript.strip()) < 100:
            return {
                "topics": [],
                "key_points": [],
                "summary": "Transcript too short to summarize"
            }
        
        prompt = """Analyze the following podcast transcript and extract the main topics, themes, and key points discussed. 
        
Return your analysis as a JSON object with this structure:
{
    "topics": ["topic1", "topic2", "topic3"],
    "key_points": ["point1", "point2", "point3"],
    "summary": "Brief summary of the episode"
}

Focus on substantial topics and avoid minor tangents."""

        try:
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing podcast content and extracting key themes and topics."
                    },
                    {
                        "role": "user", 
                        "content": f"{prompt}\n\nTranscript:\n{transcript[:4000]}"  # Limit input length
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            import json
            try:
                result = json.loads(response.choices[0].message.content)
                # Validate the result has the expected structure
                if not isinstance(result, dict):
                    raise ValueError("Result is not a dictionary")
                
                # Ensure all expected keys exist
                result.setdefault("topics", [])
                result.setdefault("key_points", [])
                result.setdefault("summary", "No summary generated")
                
                return result
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse JSON response: {str(e)}")
                return {
                    "topics": [],
                    "key_points": [],
                    "summary": "Failed to parse topic extraction results"
                }
            
        except Exception as e:
            print(f"Warning: Failed to extract topics: {str(e)}")
            return {
                "topics": [],
                "key_points": [],
                "summary": "Topic extraction failed"
            }
    
    def generate_summary(self, transcript: str, max_length: int = 500) -> str:
        """Generate a concise summary of the transcript"""
        if not transcript or len(transcript.strip()) < 100:
            return "Transcript too short to summarize"
        
        prompt = f"""Please provide a concise summary of this podcast transcript in approximately {max_length} characters. 
        Focus on the main points, key discussions, and any notable insights shared.
        
        Transcript:"""
        
        try:
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at creating concise, informative summaries of podcast content."
                    },
                    {
                        "role": "user",
                        "content": f"{prompt}\n\n{transcript[:4000]}"
                    }
                ],
                temperature=0.2,
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            return f"Summary generation failed: {str(e)}"
