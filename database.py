import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional

class DatabaseManager:
    def __init__(self, db_path: str = "podcast_transcripts.db"):
        """Initialize database manager with SQLite database"""
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create episodes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    date TEXT NOT NULL,
                    url TEXT NOT NULL,
                    raw_transcript TEXT NOT NULL,
                    enhanced_transcript TEXT NOT NULL,
                    extraction_method TEXT DEFAULT 'caption',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create index for better search performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodes_video_id ON episodes(video_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodes_date ON episodes(date)
            """)
            
            # Create full-text search index for transcripts
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                    title, enhanced_transcript, 
                    content='episodes',
                    content_rowid='id'
                )
            """)
            
            # Create triggers to keep FTS table in sync
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS episodes_fts_insert AFTER INSERT ON episodes BEGIN
                    INSERT INTO episodes_fts(rowid, title, enhanced_transcript) 
                    VALUES (new.id, new.title, new.enhanced_transcript);
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS episodes_fts_delete AFTER DELETE ON episodes BEGIN
                    DELETE FROM episodes_fts WHERE rowid = old.id;
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS episodes_fts_update AFTER UPDATE ON episodes BEGIN
                    UPDATE episodes_fts SET title = new.title, enhanced_transcript = new.enhanced_transcript 
                    WHERE rowid = new.id;
                END
            """)
            
            conn.commit()
    
    def save_episode(self, episode_data: Dict) -> int:
        """Save episode data to database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO episodes 
                (video_id, title, date, url, raw_transcript, enhanced_transcript, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                episode_data['video_id'],
                episode_data['title'],
                episode_data['date'],
                episode_data['url'],
                episode_data['raw_transcript'],
                episode_data['enhanced_transcript'],
                datetime.now().isoformat()
            ))
            
            episode_id = cursor.lastrowid
            conn.commit()
            return episode_id
    
    def get_episode_by_video_id(self, video_id: str) -> Optional[Dict]:
        """Get episode by video ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM episodes WHERE video_id = ?
            """, (video_id,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_episodes(self) -> List[Dict]:
        """Get all episodes ordered by date"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM episodes ORDER BY date DESC
            """)
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def search_transcripts(self, query: str) -> List[Dict]:
        """Search transcripts using full-text search"""
        if not query.strip():
            return []
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # First try FTS search
            try:
                cursor.execute("""
                    SELECT episodes.* FROM episodes_fts
                    JOIN episodes ON episodes.id = episodes_fts.rowid
                    WHERE episodes_fts MATCH ?
                    ORDER BY rank, episodes.date DESC
                """, (query,))
                
                rows = cursor.fetchall()
                if rows:
                    return [dict(row) for row in rows]
            except sqlite3.OperationalError:
                # FTS might not be working, fall back to LIKE search
                pass
            
            # Fallback to LIKE search
            search_pattern = f"%{query}%"
            cursor.execute("""
                SELECT * FROM episodes 
                WHERE title LIKE ? OR enhanced_transcript LIKE ? OR raw_transcript LIKE ?
                ORDER BY date DESC
            """, (search_pattern, search_pattern, search_pattern))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_episode_count(self) -> int:
        """Get total number of episodes"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM episodes")
            return cursor.fetchone()[0]
    
    def delete_episode(self, episode_id: int) -> bool:
        """Delete episode by ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def update_episode_transcript(self, episode_id: int, enhanced_transcript: str) -> bool:
        """Update enhanced transcript for an episode"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE episodes 
                SET enhanced_transcript = ?, updated_at = ?
                WHERE id = ?
            """, (enhanced_transcript, datetime.now().isoformat(), episode_id))
            conn.commit()
            return cursor.rowcount > 0
