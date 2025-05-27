import sqlite3
import os
import hashlib
import secrets
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
                    topics TEXT,
                    key_points TEXT,
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create admin table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add extraction_method column if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE episodes ADD COLUMN extraction_method TEXT DEFAULT 'caption'")
            except sqlite3.OperationalError:
                # Column already exists
                pass
                
            # Add topics column if it doesn't exist
            try:
                cursor.execute("ALTER TABLE episodes ADD COLUMN topics TEXT")
            except sqlite3.OperationalError:
                # Column already exists
                pass
                
            # Add key_points column if it doesn't exist
            try:
                cursor.execute("ALTER TABLE episodes ADD COLUMN key_points TEXT")
            except sqlite3.OperationalError:
                # Column already exists
                pass
                
            # Add summary column if it doesn't exist
            try:
                cursor.execute("ALTER TABLE episodes ADD COLUMN summary TEXT")
            except sqlite3.OperationalError:
                # Column already exists
                pass
            
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
                    title, enhanced_transcript, topics, summary,
                    content='episodes',
                    content_rowid='id'
                )
            """)
            
            # Create triggers to keep FTS table in sync
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS episodes_fts_insert AFTER INSERT ON episodes BEGIN
                    INSERT INTO episodes_fts(rowid, title, enhanced_transcript, topics, summary) 
                    VALUES (new.id, new.title, new.enhanced_transcript, new.topics, new.summary);
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS episodes_fts_delete AFTER DELETE ON episodes BEGIN
                    DELETE FROM episodes_fts WHERE rowid = old.id;
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS episodes_fts_update AFTER UPDATE ON episodes BEGIN
                    UPDATE episodes_fts SET title = new.title, enhanced_transcript = new.enhanced_transcript, 
                    topics = new.topics, summary = new.summary
                    WHERE rowid = new.id;
                END
            """)
            
            # Create default admin user if none exists
            cursor.execute("SELECT COUNT(*) FROM admin_users")
            if cursor.fetchone()[0] == 0:
                # Create default admin user: admin@example.com / password123
                self._create_admin_user("admin@example.com", "password123")
            
            conn.commit()
    
    def _hash_password(self, password: str) -> str:
        """Hash a password for storing"""
        salt = hashlib.sha256(os.urandom(60)).hexdigest().encode('ascii')
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        password_hash = salt + password_hash
        return password_hash.hex()
    
    def _verify_password(self, stored_password_hash: str, provided_password: str) -> bool:
        """Verify a stored password against a provided password"""
        stored_password_hash = bytes.fromhex(stored_password_hash)
        salt = stored_password_hash[:64]
        stored_hash = stored_password_hash[64:]
        password_hash = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
        return password_hash == stored_hash
    
    def _create_admin_user(self, email: str, password: str) -> int:
        """Create admin user with hashed password"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            password_hash = self._hash_password(password)
            cursor.execute("""
                INSERT INTO admin_users (email, password_hash)
                VALUES (?, ?)
            """, (email, password_hash))
            conn.commit()
            return cursor.lastrowid
    
    def authenticate_admin(self, email: str, password: str) -> bool:
        """Authenticate admin credentials"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT password_hash FROM admin_users
                WHERE email = ? AND is_active = 1
            """, (email,))
            result = cursor.fetchone()
            if result:
                return self._verify_password(result[0], password)
            return False
    
    def get_admin_users(self) -> List[Dict]:
        """Get all admin users"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, email, is_active, created_at FROM admin_users
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def save_episode(self, episode_data: Dict) -> int:
        """Save episode data to database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            extraction_method = episode_data.get('extraction_method', 'caption')
            topics = episode_data.get('topics', None)
            key_points = episode_data.get('key_points', None)
            summary = episode_data.get('summary', None)
            
            cursor.execute("""
                INSERT OR REPLACE INTO episodes 
                (video_id, title, date, url, raw_transcript, enhanced_transcript, extraction_method, 
                topics, key_points, summary, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                episode_data['video_id'],
                episode_data['title'],
                episode_data['date'],
                episode_data['url'],
                episode_data['raw_transcript'],
                episode_data['enhanced_transcript'],
                extraction_method,
                topics,
                key_points,
                summary,
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
