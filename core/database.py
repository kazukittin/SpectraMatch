# -*- coding: utf-8 -*-
"""
SpectraMatch - Database Module
SQLiteを使用した永続化層

4万枚以上の画像でもメモリを圧迫しないよう、
画像情報をSQLiteデータベースに保存・管理する。
"""

import sqlite3
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterator
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


class ImageDatabase:
    """
    画像情報を管理するSQLiteデータベースクラス
    
    機能:
    - 画像メタデータの永続化
    - 増分スキャン（未変更ファイルはスキップ）
    - バッチ処理によるメモリ効率の良い操作
    """
    
    DB_VERSION = 1
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        ImageDatabaseの初期化
        
        Args:
            db_path: データベースファイルのパス（省略時は~/.spectramatch/cache.db）
        """
        if db_path is None:
            db_dir = Path.home() / ".spectramatch"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "cache.db"
        
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._init_schema()
    
    def _connect(self):
        """データベースに接続"""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # パフォーマンス最適化
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=10000")
    
    def _init_schema(self):
        """テーブルスキーマを初期化"""
        cursor = self.conn.cursor()
        
        # imagesテーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                file_size INTEGER,
                last_modified REAL,
                width INTEGER,
                height INTEGER,
                phash_int INTEGER,
                blur_score REAL,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # インデックス
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_images_path ON images(path)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash_int)
        """)
        
        # メタデータテーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # バージョン確認・設定
        cursor.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("db_version", str(self.DB_VERSION))
        )
        
        self.conn.commit()
    
    def close(self):
        """データベース接続を閉じる"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def get_file_info(self, path: Path) -> Optional[Dict]:
        """
        ファイル情報を取得
        
        Args:
            path: ファイルパス
            
        Returns:
            ファイル情報の辞書、存在しない場合はNone
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM images WHERE path = ?",
            (str(path),)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def is_file_changed(self, path: Path) -> bool:
        """
        ファイルが更新されたかチェック（増分スキャン用）
        
        Args:
            path: ファイルパス
            
        Returns:
            True=更新あり/新規、False=変更なし
        """
        try:
            stat = path.stat()
            current_mtime = stat.st_mtime
            current_size = stat.st_size
        except OSError:
            return True
        
        info = self.get_file_info(path)
        if info is None:
            return True
        
        # サイズまたは更新日時が変わっていたら再計算が必要
        if info['file_size'] != current_size:
            return True
        if abs(info['last_modified'] - current_mtime) > 1:  # 1秒の誤差許容
            return True
        
        return False
    
    def upsert_image(
        self,
        path: Path,
        file_size: int,
        last_modified: float,
        width: int = 0,
        height: int = 0,
        phash_int: int = 0,
        blur_score: float = 0.0,
        embedding: Optional[np.ndarray] = None
    ):
        """
        画像情報を挿入または更新
        
        Args:
            path: ファイルパス
            file_size: ファイルサイズ
            last_modified: 最終更新日時
            width: 画像幅
            height: 画像高さ
            phash_int: pHash整数値
            blur_score: 鮮明度スコア
            embedding: CLIP埋め込みベクトル
        """
        embedding_blob = None
        if embedding is not None:
            embedding_blob = pickle.dumps(embedding)
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO images 
                (path, file_size, last_modified, width, height, phash_int, blur_score, embedding, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(path) DO UPDATE SET
                file_size = excluded.file_size,
                last_modified = excluded.last_modified,
                width = excluded.width,
                height = excluded.height,
                phash_int = excluded.phash_int,
                blur_score = excluded.blur_score,
                embedding = excluded.embedding,
                updated_at = CURRENT_TIMESTAMP
        """, (str(path), file_size, last_modified, width, height, phash_int, blur_score, embedding_blob))
        self.conn.commit()
    
    def batch_upsert(self, records: List[Dict]):
        """
        複数レコードを一括挿入/更新
        
        Args:
            records: レコードのリスト
        """
        cursor = self.conn.cursor()
        for rec in records:
            embedding_blob = None
            if rec.get('embedding') is not None:
                embedding_blob = pickle.dumps(rec['embedding'])
            
            cursor.execute("""
                INSERT INTO images 
                    (path, file_size, last_modified, width, height, phash_int, blur_score, embedding, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(path) DO UPDATE SET
                    file_size = excluded.file_size,
                    last_modified = excluded.last_modified,
                    width = excluded.width,
                    height = excluded.height,
                    phash_int = excluded.phash_int,
                    blur_score = excluded.blur_score,
                    embedding = excluded.embedding,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                str(rec['path']),
                rec.get('file_size', 0),
                rec.get('last_modified', 0),
                rec.get('width', 0),
                rec.get('height', 0),
                rec.get('phash_int', 0),
                rec.get('blur_score', 0),
                embedding_blob
            ))
        self.conn.commit()
    
    def get_all_phashes(self) -> List[Tuple[int, str, int]]:
        """
        全てのpHash値を取得
        
        Returns:
            [(id, path, phash_int), ...] のリスト
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, path, phash_int FROM images WHERE phash_int IS NOT NULL AND phash_int != 0"
        )
        return [(row['id'], row['path'], row['phash_int']) for row in cursor.fetchall()]
    
    def get_all_embeddings(self) -> List[Tuple[int, str, np.ndarray]]:
        """
        全ての埋め込みベクトルを取得
        
        Returns:
            [(id, path, embedding), ...] のリスト
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, path, embedding FROM images WHERE embedding IS NOT NULL"
        )
        result = []
        for row in cursor.fetchall():
            if row['embedding']:
                embedding = pickle.loads(row['embedding'])
                result.append((row['id'], row['path'], embedding))
        return result
    
    def get_images_by_ids(self, ids: List[int]) -> List[Dict]:
        """
        IDリストから画像情報を取得
        
        Args:
            ids: 画像IDのリスト
            
        Returns:
            画像情報の辞書リスト
        """
        if not ids:
            return []
        
        placeholders = ','.join('?' * len(ids))
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT * FROM images WHERE id IN ({placeholders})",
            ids
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_image_by_path(self, path: str) -> Optional[Dict]:
        """パスから画像情報を取得"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM images WHERE path = ?", (path,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def iter_all_images(self, batch_size: int = 1000) -> Iterator[List[Dict]]:
        """
        全画像をバッチで反復処理（メモリ効率的）
        
        Args:
            batch_size: バッチサイズ
            
        Yields:
            画像情報の辞書リスト
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM images")
        total = cursor.fetchone()[0]
        
        offset = 0
        while offset < total:
            cursor.execute(
                "SELECT * FROM images LIMIT ? OFFSET ?",
                (batch_size, offset)
            )
            batch = [dict(row) for row in cursor.fetchall()]
            if not batch:
                break
            yield batch
            offset += batch_size
    
    def get_all_images(self) -> List[Dict]:
        """
        全画像情報を取得
        
        Returns:
            画像情報の辞書リスト
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM images ORDER BY blur_score ASC")
        return [dict(row) for row in cursor.fetchall()]

    
    def count_images(self) -> int:
        """画像総数を取得"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM images")
        return cursor.fetchone()[0]
    
    def clear_all(self):
        """全レコードを削除"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM images")
        self.conn.commit()
    
    def vacuum(self):
        """データベースを最適化"""
        self.conn.execute("VACUUM")
