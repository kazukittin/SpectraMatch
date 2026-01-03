# -*- coding: utf-8 -*-
"""
SpectraMatch - CLIP Engine Module
OpenAI CLIPモデルによるセマンティック類似検索エンジン

CLIPは画像とテキストの両方を同じ埋め込み空間にマッピングできるモデルで、
視覚的な類似性だけでなく、意味的な類似性も捉えることができる。
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# 遅延インポート用のフラグ
_CLIP_AVAILABLE = None
_torch = None
_CLIPProcessor = None
_CLIPModel = None
_Image = None


def _check_clip_available() -> bool:
    """CLIPが利用可能かチェック（遅延インポート）"""
    global _CLIP_AVAILABLE, _torch, _CLIPProcessor, _CLIPModel, _Image
    
    if _CLIP_AVAILABLE is not None:
        return _CLIP_AVAILABLE
    
    try:
        import torch
        from transformers import CLIPProcessor, CLIPModel
        from PIL import Image
        
        _torch = torch
        _CLIPProcessor = CLIPProcessor
        _CLIPModel = CLIPModel
        _Image = Image
        _CLIP_AVAILABLE = True
        logger.info("CLIP dependencies loaded successfully")
        return True
        
    except ImportError as e:
        logger.warning(f"CLIP dependencies not available: {e}")
        _CLIP_AVAILABLE = False
        return False


class CLIPEngine:
    """
    CLIPモデルによるセマンティック類似検索エンジン
    
    特徴:
    - OpenAI CLIP (ViT-B/32) を使用
    - 画像を512次元のベクトルに変換
    - コサイン類似度で類似性を判定
    - GPU/CPU自動選択
    """
    
    # 使用するCLIPモデル
    MODEL_NAME = "openai/clip-vit-base-patch32"
    EMBEDDING_DIM = 512
    
    def __init__(self):
        """CLIPEngineの初期化"""
        self.model = None
        self.processor = None
        self.device = None
        self._is_loaded = False
    
    @property
    def is_available(self) -> bool:
        """CLIPが利用可能かどうか"""
        return _check_clip_available()
    
    @property
    def is_loaded(self) -> bool:
        """モデルがロード済みかどうか"""
        return self._is_loaded
    
    def load_model(self, progress_callback=None) -> bool:
        """
        CLIPモデルをロード
        
        Args:
            progress_callback: 進捗通知用コールバック(message)
            
        Returns:
            ロード成功したかどうか
        """
        if not self.is_available:
            logger.error("CLIP dependencies are not installed")
            return False
        
        if self._is_loaded:
            return True
        
        try:
            if progress_callback:
                progress_callback("AIモデルをロード中... (初回は数分かかる場合があります)")
            
            # デバイス選択
            if _torch.cuda.is_available():
                self.device = _torch.device("cuda")
                logger.info("Using CUDA for CLIP inference")
            elif hasattr(_torch.backends, 'mps') and _torch.backends.mps.is_available():
                self.device = _torch.device("mps")
                logger.info("Using MPS (Apple Silicon) for CLIP inference")
            else:
                self.device = _torch.device("cpu")
                logger.info("Using CPU for CLIP inference")
            
            if progress_callback:
                progress_callback(f"AIモデルをロード中... ({self.device})")
            
            # モデルとプロセッサをロード
            self.processor = _CLIPProcessor.from_pretrained(self.MODEL_NAME)
            self.model = _CLIPModel.from_pretrained(self.MODEL_NAME)
            self.model = self.model.to(self.device)
            self.model.eval()  # 推論モードに設定
            
            self._is_loaded = True
            logger.info(f"CLIP model loaded successfully on {self.device}")
            
            if progress_callback:
                progress_callback("AIモデルのロード完了")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            return False
    
    def unload_model(self):
        """モデルをアンロードしてメモリを解放"""
        if self.model is not None:
            del self.model
            self.model = None
        if self.processor is not None:
            del self.processor
            self.processor = None
        
        if _torch is not None and _torch.cuda.is_available():
            _torch.cuda.empty_cache()
        
        self._is_loaded = False
        logger.info("CLIP model unloaded")
    
    def extract_embedding(self, image_path: Path) -> Optional[np.ndarray]:
        """
        画像から特徴量ベクトル（Embedding）を抽出
        
        Args:
            image_path: 画像ファイルのパス
            
        Returns:
            512次元の正規化されたベクトル、失敗時はNone
        """
        if not self._is_loaded:
            logger.error("Model not loaded. Call load_model() first.")
            return None
        
        try:
            # 画像を読み込み
            image = _Image.open(image_path).convert("RGB")
            
            # 前処理
            inputs = self.processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # 推論（勾配計算なし）
            with _torch.no_grad():
                outputs = self.model.get_image_features(**inputs)
            
            # 正規化してnumpy配列に変換
            embedding = outputs.cpu().numpy().flatten()
            embedding = embedding / np.linalg.norm(embedding)
            
            # メモリ解放
            del inputs, outputs
            if _torch.cuda.is_available():
                _torch.cuda.empty_cache()
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to extract embedding from {image_path}: {e}")
            return None
    
    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        2つのベクトル間のコサイン類似度を計算
        
        コサイン類似度:
        - 1.0: 完全に同じ方向（最も類似）
        - 0.0: 直交（無関係）
        - -1.0: 正反対の方向
        
        Args:
            vec1: 1つ目のベクトル
            vec2: 2つ目のベクトル
            
        Returns:
            コサイン類似度 (-1.0 ~ 1.0)
        """
        # ベクトルが正規化済みの場合、内積がコサイン類似度
        return float(np.dot(vec1, vec2))
    
    def compute_similarity(
        self, 
        embedding1: np.ndarray, 
        embedding2: np.ndarray
    ) -> float:
        """
        2つの画像埋め込み間の類似度を計算
        
        Args:
            embedding1: 1つ目の画像の埋め込みベクトル
            embedding2: 2つ目の画像の埋め込みベクトル
            
        Returns:
            類似度スコア (0.0 ~ 1.0)
        """
        # コサイン類似度を0-1の範囲に変換
        cos_sim = self.cosine_similarity(embedding1, embedding2)
        # -1~1 を 0~1 にマッピング
        return (cos_sim + 1.0) / 2.0


class CLIPImageInfo:
    """
    CLIP用の画像情報を保持するクラス
    
    Attributes:
        path: ファイルパス
        embedding: CLIP埋め込みベクトル (512次元)
    """
    
    def __init__(self, path: Path, embedding: Optional[np.ndarray] = None):
        self.path = path
        self.embedding = embedding
    
    def __hash__(self):
        return hash(str(self.path))
    
    def __eq__(self, other):
        if not isinstance(other, CLIPImageInfo):
            return False
        return self.path == other.path


def find_similar_groups_clip(
    image_infos: List,  # List[ImageInfo] with clip_embedding attribute
    threshold: float = 0.85,
    clip_engine: Optional[CLIPEngine] = None
) -> List[Tuple[List, float, float]]:
    """
    CLIP埋め込みに基づいて類似画像グループを検出（NumPyベクトル化版）
    
    行列演算で高速にコサイン類似度行列を計算:
    similarity_matrix = embeddings @ embeddings.T
    (正規化済みベクトルの場合、内積がコサイン類似度)
    
    Args:
        image_infos: 画像情報のリスト（clip_embedding属性を持つ）
        threshold: 類似度閾値 (0.0-1.0)
        clip_engine: CLIPEngineインスタンス
        
    Returns:
        [(画像リスト, 最小類似度, 最大類似度), ...] のリスト
    """
    n = len(image_infos)
    if n < 2:
        return []
    
    # 有効な埋め込みを持つ画像のみフィルタリング
    valid_infos = [
        info for info in image_infos 
        if hasattr(info, 'clip_embedding') and info.clip_embedding is not None
    ]
    n = len(valid_infos)
    if n < 2:
        return []
    
    # 埋め込みベクトルを行列にスタック (N x 512)
    embeddings = np.stack([info.clip_embedding for info in valid_infos], axis=0)
    
    # ベクトル化されたコサイン類似度計算
    # 正規化済みベクトルの場合: similarity = A @ A.T
    similarity_matrix = embeddings @ embeddings.T
    
    # -1~1 を 0~1 にマッピング
    similarity_matrix = (similarity_matrix + 1.0) / 2.0
    
    # 閾値以上のペアを抽出（上三角のみ、対角線を除く）
    similar_pairs = np.argwhere(
        (similarity_matrix >= threshold) & 
        (np.triu(np.ones((n, n), dtype=bool), k=1))
    )
    
    if len(similar_pairs) == 0:
        return []
    
    # Union-Find
    parent = list(range(n))
    rank = [0] * n
    
    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    
    def union(x: int, y: int):
        px, py = find(x), find(y)
        if px == py:
            return
        if rank[px] < rank[py]:
            px, py = py, px
        parent[py] = px
        if rank[px] == rank[py]:
            rank[px] += 1
    
    # 類似度情報を保存
    similarities: Dict[Tuple[int, int], float] = {}
    for i, j in similar_pairs:
        union(i, j)
        similarities[(i, j)] = float(similarity_matrix[i, j])
    
    # グループを構築
    group_members: Dict[int, List[int]] = {}
    for i in range(n):
        root = find(i)
        if root not in group_members:
            group_members[root] = []
        group_members[root].append(i)
    
    # 結果を構築
    result = []
    for root, members in group_members.items():
        if len(members) < 2:
            continue
        
        group_images = [valid_infos[i] for i in members]
        
        # グループ内の類似度統計
        min_sim = 1.0
        max_sim = 0.0
        for i, m1 in enumerate(members):
            for m2 in members[i+1:]:
                key = (min(m1, m2), max(m1, m2))
                if key in similarities:
                    s = similarities[key]
                    min_sim = min(min_sim, s)
                    max_sim = max(max_sim, s)
        
        result.append((group_images, min_sim, max_sim))
    
    return result

