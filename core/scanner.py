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
from typing import Callable, List, Optional, Set, Dict
import numpy as np

from PySide6.QtCore import QObject, Signal

from .comparator import ImageComparator, ImageInfo, SimilarityGroup
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
    PHASH = "phash"          # DCT pHash（高速）
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
    mode: ScanMode = ScanMode.PHASH


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
        comparator: Optional[ImageComparator] = None,
        max_workers: int = 4,
        db: Optional[ImageDatabase] = None
    ):
        super().__init__()
        self.hasher = hasher or ImageHasher()
        self.comparator = comparator or ImageComparator(self.hasher)
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
        return self.clip_engine.is_available
    
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
        threshold: float = 10,
        recursive: bool = True,
        mode: ScanMode = ScanMode.PHASH,
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
    
    def _process_image_phash(self, file_path: Path) -> Optional[Dict]:
        """pHashモード: 画像を処理してDB用データを返す"""
        if self._stop_event.is_set():
            return None
        
        try:
            stat = file_path.stat()
            file_size = stat.st_size
            last_modified = stat.st_mtime
            
            phash = self.hasher.compute_phash(file_path)
            phash_int = 0
            if phash is not None:
                phash_int = self.hasher.phash_to_int(phash)
                # デバッグ: ハッシュ値がオール0でないか確認
                if phash_int == 0:
                    logger.warning(f"[Hash] オール0ハッシュ: {file_path.name}")
            else:
                logger.warning(f"[Hash] pHash計算失敗: {file_path.name}")
            
            sharpness, width, height = self.hasher.compute_sharpness(file_path)
            
            # デバッグログ
            logger.debug(f"[Process] {file_path.name}: size={file_size}, {width}x{height}, phash={phash_int:016x}, blur={sharpness:.1f}")
            
            return {
                'path': file_path,
                'file_size': file_size,
                'last_modified': last_modified,
                'width': width,
                'height': height,
                'phash_int': phash_int,
                'blur_score': sharpness,
                'embedding': None
            }
        except Exception as e:
            logger.error(f"画像処理エラー: {file_path} - {e}")
            return None
    
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
            
            # Phase 3: 画像処理
            mode_name = "AIセマンティック分析" if mode == ScanMode.AI_CLIP else "ハッシュ計算"
            process_func = (
                self._process_image_clip if mode == ScanMode.AI_CLIP 
                else self._process_image_phash
            )
            
            processed = cached_count
            batch_records: List[Dict] = []
            BATCH_SIZE = 100
            
            # AIモードはシングルスレッド、pHashは並列
            if mode == ScanMode.AI_CLIP:
                for path in files_to_process:
                    if self._stop_event.is_set():
                        break
                    
                    rec = process_func(path)
                    if rec:
                        batch_records.append(rec)
                        result.processed_files += 1
                    else:
                        result.skipped_files += 1
                        result.errors.append(f"スキップ: {path}")
                    
                    processed += 1
                    
                    # バッチでDBに保存
                    if len(batch_records) >= BATCH_SIZE:
                        self.db.batch_upsert(batch_records)
                        batch_records = []
                    
                    if processed % 5 == 0 or processed == result.total_files:
                        self.progress_updated.emit(
                            processed, result.total_files,
                            f"{mode_name}中... ({processed}/{result.total_files})"
                        )
            else:
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_path = {
                        executor.submit(process_func, path): path 
                        for path in files_to_process
                    }
                    
                    for future in as_completed(future_to_path):
                        if self._stop_event.is_set():
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        
                        path = future_to_path[future]
                        try:
                            rec = future.result()
                            if rec:
                                batch_records.append(rec)
                                result.processed_files += 1
                            else:
                                result.skipped_files += 1
                                result.errors.append(f"スキップ: {path}")
                        except Exception as e:
                            result.skipped_files += 1
                            result.errors.append(f"エラー: {path} - {e}")
                        
                        processed += 1
                        
                        if len(batch_records) >= BATCH_SIZE:
                            self.db.batch_upsert(batch_records)
                            batch_records = []
                        
                        if processed % 20 == 0 or processed == result.total_files:
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
            
            # Phase 4: 類似度分析（Faiss使用）
            self.progress_updated.emit(
                result.total_files, result.total_files,
                "類似画像を分析中..."
            )
            
            if mode == ScanMode.AI_CLIP:
                result.groups = self._find_groups_clip(threshold)
            else:
                result.groups = self._find_groups_phash(int(threshold))
            
            self.progress_updated.emit(
                result.total_files,
                result.total_files,
                f"完了! {len(result.groups)}個の類似グループを検出"
            )
            
        except Exception as e:
            error_msg = f"スキャンエラー: {e}"
            logger.error(error_msg, exc_info=True)
            result.errors.append(error_msg)
            self.scan_error.emit(error_msg)
        
        finally:
            self.scan_completed.emit(result)
    
    def _find_groups_phash(self, threshold: int) -> List[SimilarityGroup]:
        """DBからpHashデータを取得してグループ化"""
        # Faissが利用可能ならFaissを使用
        try:
            from .faiss_engine import find_similar_groups_faiss_phash, _check_faiss_available
            if _check_faiss_available():
                phash_data = self.db.get_all_phashes()
                if len(phash_data) < 2:
                    return []
                
                groups = find_similar_groups_faiss_phash(phash_data, threshold)
                return self._convert_to_similarity_groups(groups, is_phash=True)
        except ImportError:
            pass
        
        # フォールバック: NumPy実装
        return self._find_groups_phash_numpy(threshold)
    
    def _find_groups_phash_numpy(self, threshold: int) -> List[SimilarityGroup]:
        """NumPyによるpHashグループ化（フォールバック）"""
        phash_data = self.db.get_all_phashes()
        logger.info(f"[Compare] pHashデータ数: {len(phash_data)}, 閾値: {threshold}")
        
        if len(phash_data) < 2:
            logger.warning("[Compare] pHashデータが2件未満のため比較をスキップ")
            return []
        
        n = len(phash_data)
        ids = [item[0] for item in phash_data]
        paths = [item[1] for item in phash_data]
        phashes = np.array([item[2] for item in phash_data], dtype=np.uint64)
        
        # デバッグ: ユニークなハッシュ数を確認
        unique_hashes = len(set(phashes.tolist()))
        logger.info(f"[Compare] ユニークハッシュ数: {unique_hashes}/{n}")
        
        # ベクトル化ハミング距離
        xor_matrix = phashes[:, np.newaxis] ^ phashes[np.newaxis, :]
        
        def popcount_vec(x):
            x = x.astype(np.uint64)
            result = np.zeros_like(x, dtype=np.int32)
            for shift in range(8):
                byte_vals = ((x >> (shift * 8)) & 0xFF).astype(np.uint8)
                result += np.array([bin(b).count('1') for b in byte_vals.flat]).reshape(byte_vals.shape)
            return result
        
        distance_matrix = popcount_vec(xor_matrix)
        
        # デバッグ: 距離行列の統計（対角線以外）
        upper_tri = np.triu_indices(n, k=1)
        distances_upper = distance_matrix[upper_tri]
        if len(distances_upper) > 0:
            logger.info(f"[Compare] 距離統計: min={distances_upper.min()}, max={distances_upper.max()}, mean={distances_upper.mean():.2f}")
            # 距離0のペア数（完全一致）
            exact_matches = np.sum(distances_upper == 0)
            logger.info(f"[Compare] 完全一致ペア数 (距離=0): {exact_matches}")
        
        similar_pairs = np.argwhere(
            (distance_matrix <= threshold) & 
            (np.triu(np.ones((n, n), dtype=bool), k=1))
        )
        
        logger.info(f"[Compare] 閾値{threshold}以下のペア数: {len(similar_pairs)}")
        
        # Union-Find
        parent = list(range(n))
        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[py] = px
        
        for i, j in similar_pairs:
            union(i, j)
        
        groups_dict: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            if root not in groups_dict:
                groups_dict[root] = []
            groups_dict[root].append(i)
        
        result = []
        group_id = 0
        for members in groups_dict.values():
            if len(members) >= 2:
                group_id += 1
                group_images = []
                for m in members:
                    img_data = self.db.get_image_by_path(paths[m])
                    if img_data:
                        info = ImageInfo(
                            path=Path(img_data['path']),
                            file_size=img_data.get('file_size', 0),
                            width=img_data.get('width', 0),
                            height=img_data.get('height', 0),
                            phash_int=img_data.get('phash_int', 0),
                            sharpness_score=img_data.get('blur_score', 0)
                        )
                        group_images.append(info)
                
                if len(group_images) >= 2:
                    result.append(SimilarityGroup(
                        group_id=group_id,
                        images=group_images,
                        is_exact_match=False,
                        min_distance=0,
                        max_distance=threshold
                    ))
        
        return result
    
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
        """NumPyによるCLIPグループ化（フォールバック）"""
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
        
        similar_pairs = np.argwhere(
            (similarity_matrix >= threshold) & 
            (np.triu(np.ones((n, n), dtype=bool), k=1))
        )
        
        if len(similar_pairs) == 0:
            return []
        
        # Union-Find
        parent = list(range(n))
        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[py] = px
        
        for i, j in similar_pairs:
            union(i, j)
        
        groups_dict: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            if root not in groups_dict:
                groups_dict[root] = []
            groups_dict[root].append(i)
        
        result = []
        group_id = 0
        for members in groups_dict.values():
            if len(members) >= 2:
                group_id += 1
                group_images = []
                for m in members:
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
