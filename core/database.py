# -*- coding: utf-8 -*-
"""
SpectraMatch - Database Module
SQLiteを使用した永続化層
"""

import sqlite3
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterator
import numpy as np

logger = logging.getLogger(__name__)


class ImageDatabase:
    """
    画像情報を管理するSQLiteデータベースクラス
    """
    
    DB_VERSION = 2  # pHash削除に伴いバージョンアップ
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_dir = Path.home() / ".spectramatch"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "cache_v2.db"
        
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._init_schema()
    
    def _connect(self):
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
    
    def _init_schema(self):
        cursor = self.conn.cursor()
        
        # imagesテーブル (phash_intを削除)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                file_size INTEGER,
                last_modified REAL,
                width INTEGER,
                height INTEGER,
                blur_score REAL,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_path ON images(path)")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        cursor.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("db_version", str(self.DB_VERSION))
        )
        
        self.conn.commit()
    
    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def get_file_info(self, path: Path) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM images WHERE path = ?", (str(path),))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def is_file_changed(self, path: Path) -> bool:
        try:
            stat = path.stat()
            current_mtime = stat.st_mtime
            current_size = stat.st_size
        except OSError:
            return True
        
        info = self.get_file_info(path)
        if info is None:
            return True
        
        if info['file_size'] != current_size:
            return True
        if abs(info['last_modified'] - current_mtime) > 1:
            return True
        
        return False
    
    def batch_upsert(self, records: List[Dict]):
        cursor = self.conn.cursor()
        for rec in records:
            embedding_blob = None
            if rec.get('embedding') is not None:
                embedding_blob = pickle.dumps(rec['embedding'])
            
            cursor.execute("""
                INSERT INTO images 
                    (path, file_size, last_modified, width, height, blur_score, embedding, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(path) DO UPDATE SET
                    file_size = excluded.file_size,
                    last_modified = excluded.last_modified,
                    width = excluded.width,
                    height = excluded.height,
                    blur_score = excluded.blur_score,
                    embedding = excluded.embedding,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                str(rec['path']),
                rec.get('file_size', 0),
                rec.get('last_modified', 0),
                rec.get('width', 0),
                rec.get('height', 0),
                rec.get('blur_score', 0),
                embedding_blob
            ))
        self.conn.commit()
    
    def get_all_embeddings(self) -> List[Tuple[int, str, np.ndarray]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, path, embedding FROM images WHERE embedding IS NOT NULL")
        result = []
        for row in cursor.fetchall():
            if row['embedding']:
                embedding = pickle.loads(row['embedding'])
                result.append((row['id'], row['path'], embedding))
        return result
    
    def get_image_by_path(self, path: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM images WHERE path = ?", (path,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_all_images(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM images ORDER BY blur_score ASC")
        return [dict(row) for row in cursor.fetchall()]

    def count_images(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM images")
        return cursor.fetchone()[0]
    
    def clear_all(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM images")
        self.conn.commit()
    
    def vacuum(self):
        self.conn.execute("VACUUM")
