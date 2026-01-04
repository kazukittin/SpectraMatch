# -*- coding: utf-8 -*-
"""
SpectraMatch - Image Scanner Module (v2 - Scalable)
SQLite + Faiss対応の大規模スキャナー

4万枚以上の画像を処理可能なアーキテクチャ:
- SQLiteによる永続化（増分スキャン対応）
- Faissによる高速類似検索
- 停止フラグによる中断対応
"""

import logging
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import Callable, List, Optional, Set, Dict, Tuple
import numpy as np

from PySide6.QtCore import QObject, Signal

from .comparator import ImageInfo, SimilarityGroup
from .hasher import ImageHasher
from .database import ImageDatabase

# サポートする画像拡張子
SUPPORTED_EXTENSIONS: Set[str] = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', 
    '.tiff', '.tif', '.webp', '.ico', '.heic', '.heif'
}

logger = logging.getLogger(__name__)


class ScanMode(Enum):
    """スキャンモード"""
    AI_CLIP = "ai_clip"      # CLIP セマンティック検索（高精度）


@dataclass
class ScanResult:
    """スキャン結果"""
    total_files: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    cached_files: int = 0  # キャッシュから読み込んだファイル数
    groups: List[SimilarityGroup] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    mode: ScanMode = ScanMode.AI_CLIP
    all_images: List['ImageInfo'] = field(default_factory=list)  # 全画像リスト（ブレ画像表示用）


class ImageScanner(QObject):
    """
    大規模対応画像スキャナー
    
    特徴:
    - SQLiteによる永続化
    - 増分スキャン（未変更ファイルはスキップ）
    - Faissによる高速類似検索
    - 中断対応
    """
    
    progress_updated = Signal(int, int, str)
    scan_completed = Signal(object)
    scan_error = Signal(str)
    
    def __init__(
        self, 
        hasher: Optional[ImageHasher] = None,
        max_workers: int = 4,
        db: Optional[ImageDatabase] = None
    ):
        super().__init__()
        self.hasher = hasher or ImageHasher()
        self.max_workers = max_workers
        
        # データベース
        self.db = db or ImageDatabase()
        
        # CLIPエンジン（遅延初期化）
        self._clip_engine = None
        
        # スキャン制御
        self._stop_event = Event()
        self._scan_thread: Optional[Thread] = None
    
    @property
    def clip_engine(self):
        """CLIPエンジンを取得（遅延初期化）"""
        if self._clip_engine is None:
            from .clip_engine import CLIPEngine
            self._clip_engine = CLIPEngine()
        return self._clip_engine
    
    def is_clip_available(self) -> bool:
        try:
            return self.clip_engine.is_available
        except Exception as e:
            logger.warning(f"CLIP availability check failed: {e}")
            return False
    
    def is_faiss_available(self) -> bool:
        """Faissが利用可能かどうか"""
        try:
            from .faiss_engine import _check_faiss_available
            return _check_faiss_available()
        except:
            return False
    
    def is_scanning(self) -> bool:
        return self._scan_thread is not None and self._scan_thread.is_alive()
    
    def stop_scan(self):
        """スキャンを中断"""
        logger.info("Scan stop requested")
        self._stop_event.set()
        if self._scan_thread:
            self._scan_thread.join(timeout=10)
    
    def start_scan(
        self, 
        folder_path: Path, 
        threshold: float = 85.0,
        recursive: bool = True,
        mode: ScanMode = ScanMode.AI_CLIP,
        use_cache: bool = True
    ):
        """スキャンを開始（非同期）"""
        if self.is_scanning():
            self.scan_error.emit("スキャンは既に実行中です")
            return
        
        self._stop_event.clear()
        self._scan_thread = Thread(
            target=self._scan_worker,
            args=(folder_path, threshold, recursive, mode, use_cache),
            daemon=True
        )
        self._scan_thread.start()
    
    def _find_image_files(self, folder_path: Path, recursive: bool = True) -> List[Path]:
        """画像ファイルを探索"""
        image_files: List[Path] = []
        
        try:
            pattern = "**/*" if recursive else "*"
            for file_path in folder_path.glob(pattern):
                if self._stop_event.is_set():
                    break
                if file_path.is_file():
                    ext = file_path.suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        image_files.append(file_path)
        except PermissionError as e:
            logger.warning(f"アクセス拒否: {folder_path} - {e}")
        except Exception as e:
            logger.error(f"ファイル探索エラー: {folder_path} - {e}")
        
        return image_files
    
    # _process_image_phash は削除されました
    
    def _process_image_clip(self, file_path: Path) -> Optional[Dict]:
        """CLIPモード: 画像を処理してDB用データを返す"""
        if self._stop_event.is_set():
            return None
        
        try:
            stat = file_path.stat()
            file_size = stat.st_size
            last_modified = stat.st_mtime
            
            sharpness, width, height = self.hasher.compute_sharpness(file_path)
            embedding = self.clip_engine.extract_embedding(file_path)
            
            return {
                'path': file_path,
                'file_size': file_size,
                'last_modified': last_modified,
                'width': width,
                'height': height,
                'phash_int': 0,
                'blur_score': sharpness,
                'embedding': embedding
            }
        except Exception as e:
            logger.error(f"CLIP処理エラー: {file_path} - {e}")
            return None
    
    def _scan_worker(
        self, 
        folder_path: Path, 
        threshold: float,
        recursive: bool,
        mode: ScanMode,
        use_cache: bool
    ):
        """スキャンのメインワーカー"""
        result = ScanResult(mode=mode)
        
        try:
            # AIモードの場合、まずモデルをロード
            if mode == ScanMode.AI_CLIP:
                if not self.is_clip_available():
                    self.scan_error.emit(
                        "CLIPが利用できません。\n"
                        "pip install torch transformers を実行してください。"
                    )
                    self.scan_completed.emit(result)
                    return
                
                def progress_cb(msg):
                    self.progress_updated.emit(0, 0, msg)
                
                if not self.clip_engine.load_model(progress_cb):
                    self.scan_error.emit("CLIPモデルのロードに失敗しました")
                    self.scan_completed.emit(result)
                    return
            
            # Phase 1: ファイル探索
            self.progress_updated.emit(0, 0, "画像ファイルを検索中...")
            image_files = self._find_image_files(folder_path, recursive)
            result.total_files = len(image_files)
            
            if result.total_files == 0:
                self.progress_updated.emit(0, 0, "画像ファイルが見つかりませんでした")
                self.scan_completed.emit(result)
                return
            
            if self._stop_event.is_set():
                self.scan_completed.emit(result)
                return
            
            # Phase 2: 増分スキャン（キャッシュ確認）
            self.progress_updated.emit(0, result.total_files, "キャッシュを確認中...")
            
            files_to_process: List[Path] = []
            cached_count = 0
            
            if use_cache:
                for path in image_files:
                    if self._stop_event.is_set():
                        break
                    if self.db.is_file_changed(path):
                        files_to_process.append(path)
                    else:
                        cached_count += 1
                result.cached_files = cached_count
            else:
                files_to_process = image_files
            
            self.progress_updated.emit(
                cached_count, result.total_files,
                f"キャッシュ: {cached_count}件, 処理対象: {len(files_to_process)}件"
            )
            
            if self._stop_event.is_set():
                self.scan_completed.emit(result)
                return
            
            # CLIPモードはバッチ処理（高速化）
            mode_name = "AIセマンティック分析"
            processed = cached_count
            batch_records: List[Dict] = []
            BATCH_SIZE = 100
            
            CLIP_BATCH_SIZE = 32  # RTX4060に最適化
            
            for batch_start in range(0, len(files_to_process), CLIP_BATCH_SIZE):
                if self._stop_event.is_set():
                    break
                
                batch_end = min(batch_start + CLIP_BATCH_SIZE, len(files_to_process))
                batch_paths = files_to_process[batch_start:batch_end]
                
                # ファイル情報を先に取得
                file_infos = []
                for path in batch_paths:
                    try:
                        stat = path.stat()
                        sharpness, width, height = self.hasher.compute_sharpness(path)
                        file_infos.append({
                            'path': path,
                            'file_size': stat.st_size,
                            'last_modified': stat.st_mtime,
                            'width': width,
                            'height': height,
                            'blur_score': sharpness
                        })
                    except Exception as e:
                        logger.error(f"ファイル情報取得エラー: {path} - {e}")
                        file_infos.append(None)
                
                # バッチでCLIP埋め込みを抽出
                valid_paths = [info['path'] for info in file_infos if info is not None]
                embeddings = self.clip_engine.extract_embeddings_batch(valid_paths, batch_size=CLIP_BATCH_SIZE)
                
                # 結果をマージ
                embed_idx = 0
                for i, info in enumerate(file_infos):
                    if info is None:
                        result.skipped_files += 1
                        result.errors.append(f"スキップ: {batch_paths[i]}")
                    else:
                        embedding = embeddings[embed_idx] if embed_idx < len(embeddings) else None
                        embed_idx += 1
                        
                        if embedding is not None:
                            info['embedding'] = embedding
                            info['phash_int'] = 0
                            batch_records.append(info)
                            result.processed_files += 1
                        else:
                            result.skipped_files += 1
                            result.errors.append(f"CLIP処理失敗: {info['path']}")
                    
                    processed += 1
                
                # バッチでDBに保存
                if len(batch_records) >= BATCH_SIZE:
                    self.db.batch_upsert(batch_records)
                    batch_records = []
                
                # 進捗更新（バッチ単位で更新）
                self.progress_updated.emit(
                    processed, result.total_files,
                    f"{mode_name}中... ({processed}/{result.total_files})"
                )
            
            # 残りをDBに保存
            if batch_records:
                self.db.batch_upsert(batch_records)
            
            if self._stop_event.is_set():
                self.progress_updated.emit(processed, result.total_files, "中断されました")
                self.scan_completed.emit(result)
                return
            
            # Phase 4: 類似度分析
            self.progress_updated.emit(
                result.total_files, result.total_files,
                "類似画像を分析中..."
            )
            
            result.groups = self._find_groups_clip(threshold)
            
            self.progress_updated.emit(
                result.total_files,
                result.total_files,
                f"完了! {len(result.groups)}個の類似グループを検出"
            )
            
            # 全画像情報を取得（ブレ画像表示用）
            all_image_data = self.db.get_all_images()
            result.all_images = []
            for img_data in all_image_data:
                info = ImageInfo(
                    path=Path(img_data['path']),
                    file_size=img_data.get('file_size', 0),
                    width=img_data.get('width', 0),
                    height=img_data.get('height', 0),
                    phash_int=img_data.get('phash_int', 0),
                    sharpness_score=img_data.get('blur_score', 0)
                )
                result.all_images.append(info)
            
        except Exception as e:
            error_msg = f"スキャンエラー: {e}"
            logger.error(error_msg, exc_info=True)
            result.errors.append(error_msg)
            self.scan_error.emit(error_msg)
        
        finally:
            self.scan_completed.emit(result)
    
    # _find_groups_phash は削除されました
    
    def _find_groups_clip(self, threshold: float) -> List[SimilarityGroup]:
        """DBからCLIPデータを取得してグループ化"""
        clip_threshold = threshold / 100.0
        
        # Faissが利用可能ならFaissを使用
        try:
            from .faiss_engine import find_similar_groups_faiss_clip, _check_faiss_available
            if _check_faiss_available():
                clip_data = self.db.get_all_embeddings()
                if len(clip_data) < 2:
                    return []
                
                groups = find_similar_groups_faiss_clip(clip_data, clip_threshold)
                return self._convert_to_similarity_groups(groups, is_phash=False)
        except ImportError:
            pass
        
        # フォールバック: NumPy実装
        return self._find_groups_clip_numpy(clip_threshold)
    
    def _find_groups_clip_numpy(self, threshold: float) -> List[SimilarityGroup]:
        """NumPyによるCLIPグループ化（連鎖防止版）"""
        clip_data = self.db.get_all_embeddings()
        if len(clip_data) < 2:
            return []
        
        n = len(clip_data)
        ids = [item[0] for item in clip_data]
        paths = [item[1] for item in clip_data]
        embeddings = np.stack([item[2] for item in clip_data], axis=0)
        
        # コサイン類似度行列
        similarity_matrix = embeddings @ embeddings.T
        similarity_matrix = (similarity_matrix + 1.0) / 2.0
        
        # 各画像の直接類似画像を収集
        direct_neighbors: Dict[int, List[Tuple[int, float]]] = {}
        for i in range(n):
            neighbors = []
            for j in range(n):
                if i != j and similarity_matrix[i, j] >= threshold:
                    neighbors.append((j, float(similarity_matrix[i, j])))
            if neighbors:
                # 類似度順でソート
                neighbors.sort(key=lambda x: -x[1])
                direct_neighbors[i] = neighbors[:20]  # 上位20件に制限
        
        if not direct_neighbors:
            return []
        
        # 相互類似チェック: AがBに類似 かつ BがAに類似 の場合のみ
        mutual_pairs: set = set()
        for i, neighbors in direct_neighbors.items():
            for j, sim in neighbors:
                if j in direct_neighbors:
                    j_neighbors = {n[0] for n in direct_neighbors[j]}
                    if i in j_neighbors:
                        pair = (min(i, j), max(i, j))
                        mutual_pairs.add(pair)
        
        if not mutual_pairs:
            return []
        
        # 貪欲法でグループを構築（完全連結）
        used = set()
        result = []
        group_id = 0
        
        candidates = sorted(direct_neighbors.keys(), 
                           key=lambda x: len(direct_neighbors[x]), 
                           reverse=True)
        
        for center in candidates:
            if center in used:
                continue
            
            group_members = [center]
            
            for neighbor, sim in direct_neighbors.get(center, []):
                if neighbor in used:
                    continue
                
                pair = (min(center, neighbor), max(center, neighbor))
                if pair not in mutual_pairs:
                    continue
                
                # グループ内の全員と類似しているかチェック
                is_similar_to_all = True
                for member in group_members:
                    if member == center:
                        continue
                    member_pair = (min(member, neighbor), max(member, neighbor))
                    if member_pair not in mutual_pairs:
                        is_similar_to_all = False
                        break
                
                if is_similar_to_all:
                    group_members.append(neighbor)
            
            if len(group_members) >= 2:
                group_id += 1
                group_images = []
                for m in group_members:
                    img_data = self.db.get_image_by_path(paths[m])
                    if img_data:
                        embedding = None
                        if img_data.get('embedding'):
                            embedding = pickle.loads(img_data['embedding'])
                        info = ImageInfo(
                            path=Path(img_data['path']),
                            file_size=img_data.get('file_size', 0),
                            width=img_data.get('width', 0),
                            height=img_data.get('height', 0),
                            sharpness_score=img_data.get('blur_score', 0),
                            clip_embedding=embedding
                        )
                        group_images.append(info)
                
                if len(group_images) >= 2:
                    result.append(SimilarityGroup(
                        group_id=group_id,
                        images=group_images,
                        is_exact_match=False,
                        min_distance=0,
                        max_distance=int((1 - threshold) * 100)
                    ))
                    for m in group_members:
                        used.add(m)
        
        # 残りの相互類似ペアを2画像グループとして追加
        for i, j in mutual_pairs:
            if i not in used and j not in used:
                group_id += 1
                group_images = []
                for m in [i, j]:
                    img_data = self.db.get_image_by_path(paths[m])
                    if img_data:
                        embedding = None
                        if img_data.get('embedding'):
                            embedding = pickle.loads(img_data['embedding'])
                        info = ImageInfo(
                            path=Path(img_data['path']),
                            file_size=img_data.get('file_size', 0),
                            width=img_data.get('width', 0),
                            height=img_data.get('height', 0),
                            sharpness_score=img_data.get('blur_score', 0),
                            clip_embedding=embedding
                        )
                        group_images.append(info)
                
                if len(group_images) >= 2:
                    result.append(SimilarityGroup(
                        group_id=group_id,
                        images=group_images,
                        is_exact_match=False,
                        min_distance=0,
                        max_distance=int((1 - threshold) * 100)
                    ))
                    used.add(i)
                    used.add(j)
        
        return result
    
    def _convert_to_similarity_groups(
        self, 
        groups: List[List[tuple]], 
        is_phash: bool
    ) -> List[SimilarityGroup]:
        """Faiss結果をSimilarityGroupに変換"""
        result = []
        group_id = 0
        
        for group in groups:
            group_id += 1
            group_images = []
            
            for item in group:
                db_id, path = item[0], item[1]
                img_data = self.db.get_image_by_path(path)
                if img_data:
                    embedding = None
                    if img_data.get('embedding'):
                        embedding = pickle.loads(img_data['embedding'])
                    
                    info = ImageInfo(
                        path=Path(img_data['path']),
                        file_size=img_data.get('file_size', 0),
                        width=img_data.get('width', 0),
                        height=img_data.get('height', 0),
                        phash_int=img_data.get('phash_int', 0),
                        sharpness_score=img_data.get('blur_score', 0),
                        clip_embedding=embedding
                    )
                    group_images.append(info)
            
            if len(group_images) >= 2:
                result.append(SimilarityGroup(
                    group_id=group_id,
                    images=group_images,
                    is_exact_match=False,
                    min_distance=0,
                    max_distance=10
                ))
        
        return result
