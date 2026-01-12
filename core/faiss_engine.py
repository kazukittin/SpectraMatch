# -*- coding: utf-8 -*-
"""
SpectraMatch - Faiss Search Engine Module
Faissによる高速類似検索エンジン (CLIP専用)
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Faiss遅延インポート
_faiss = None
_FAISS_AVAILABLE = None


def _check_faiss_available() -> bool:
    """Faissが利用可能かチェック"""
    global _faiss, _FAISS_AVAILABLE
    
    if _FAISS_AVAILABLE is not None:
        return _FAISS_AVAILABLE
    
    try:
        import faiss
        _faiss = faiss
        _FAISS_AVAILABLE = True
        logger.info("Faiss loaded successfully")
        return True
    except ImportError as e:
        logger.warning(f"Faiss not available: {e}")
        _FAISS_AVAILABLE = False
        return False


class FaissSearchEngine:
    """
    Faissによる高速類似検索エンジン (CLIP専用)
    """
    
    def __init__(self):
        self.clip_index = None
        self.clip_ids: List[int] = []
        
    @property
    def is_available(self) -> bool:
        return _check_faiss_available()
    
    def build_clip_index(self, data: List[Tuple[int, np.ndarray]]):
        """
        CLIP埋め込み用のインデックスを構築
        """
        if not self.is_available or not data:
            return
        
        self.clip_ids = [item[0] for item in data]
        embeddings = np.stack([item[1] for item in data], axis=0).astype(np.float32)
        
        # 正規化
        _faiss.normalize_L2(embeddings)
        
        # IndexFlatIP: 内積による検索（正規化済みなのでコサイン類似度）
        dim = embeddings.shape[1]
        self.clip_index = _faiss.IndexFlatIP(dim)
        self.clip_index.add(embeddings)
        
        logger.info(f"Built CLIP index with {len(data)} vectors, dim={dim}")
    
    def search_clip_neighbors(
        self,
        query_embedding: np.ndarray,
        k: int = 50
    ) -> List[Tuple[int, float]]:
        """クエリ埋め込みの近傍を検索"""
        if self.clip_index is None:
            return []
        
        query = query_embedding.reshape(1, -1).astype(np.float32)
        _faiss.normalize_L2(query)
        
        k = min(k, self.clip_index.ntotal)
        similarities, indices = self.clip_index.search(query, k)
        
        result = []
        for sim, idx in zip(similarities[0], indices[0]):
            if idx >= 0 and idx < len(self.clip_ids):
                result.append((self.clip_ids[idx], float(sim)))
        
        return result
    
    def clear(self):
        """インデックスをクリア"""
        self.clip_index = None
        self.clip_ids = []


def find_similar_groups_faiss_clip(
    clip_data: List[Tuple[int, str, np.ndarray]],
    threshold: float = 0.85
) -> List[List[Tuple[int, str, float]]]:
    """
    Faissを使用したCLIP類似グループ検出（連鎖防止版）
    """
    if not _check_faiss_available() or len(clip_data) < 2:
        return []
    
    n = len(clip_data)
    ids = [item[0] for item in clip_data]
    paths = [item[1] for item in clip_data]
    embeddings = np.stack([item[2] for item in clip_data], axis=0).astype(np.float32)
    
    # 正規化
    _faiss.normalize_L2(embeddings)
    
    # インデックス構築
    dim = embeddings.shape[1]
    index = _faiss.IndexFlatIP(dim)
    index.add(embeddings)
    
    # k近傍検索
    k = min(21, n)
    similarities, indices = index.search(embeddings, k)
    
    # 各画像の直接類似画像を収集
    direct_neighbors: Dict[int, List[Tuple[int, float]]] = {}
    for i in range(n):
        neighbors = []
        for j_idx in range(1, k):
            j = indices[i, j_idx]
            sim = similarities[i, j_idx]
            if j >= 0 and j != i and sim >= threshold:
                neighbors.append((j, float(sim)))
        if neighbors:
            direct_neighbors[i] = neighbors
    
    if not direct_neighbors:
        return []
    
    # 相互類似チェック
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
    
    used = set()
    result = []
    
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
            group = [(ids[m], paths[m]) for m in group_members]
            result.append(group)
            for m in group_members:
                used.add(m)
    
    for i, j in mutual_pairs:
        if i not in used and j not in used:
            group = [(ids[i], paths[i]), (ids[j], paths[j])]
            result.append(group)
            used.add(i)
            used.add(j)
    
    return result


def compute_phash_distance(hash1: int, hash2: int) -> int:
    """2つのpHashのハミング距離を計算（符号付き整数対応）"""
    # 負の値は64ビットのビットパターンとして扱う
    xor = (hash1 ^ hash2) & 0xFFFFFFFFFFFFFFFF
    return bin(xor).count('1')


def find_similar_groups_hybrid(
    data: List[Tuple[int, str, np.ndarray, Optional[int]]],
    clip_threshold: float = 0.85,
    phash_threshold: float = 0.85,
    require_both: bool = True
) -> List[List[Tuple[int, str, float]]]:
    """
    CLIP + pHash ハイブリッド類似グループ検出
    
    Args:
        data: [(id, path, embedding, phash), ...] のリスト
        clip_threshold: CLIP類似度の閾値 (0.0-1.0)
        phash_threshold: pHash類似度の閾値 (0.0-1.0)、ハミング距離から変換
        require_both: Trueの場合、CLIPとpHash両方の閾値を満たす必要がある
                     Falseの場合、どちらか一方を満たせばOK
    
    Returns:
        類似画像グループのリスト
    """
    if not _check_faiss_available() or len(data) < 2:
        return []
    
    n = len(data)
    ids = [item[0] for item in data]
    paths = [item[1] for item in data]
    embeddings = np.stack([item[2] for item in data], axis=0).astype(np.float32)
    phashes = [item[3] for item in data]  # Noneの可能性あり
    
    # pHashの最大ハミング距離を計算（閾値から逆算）
    max_phash_distance = int((1.0 - phash_threshold) * 64)
    
    logger.info(f"Hybrid detection: CLIP threshold={clip_threshold}, pHash threshold={phash_threshold} (max distance={max_phash_distance})")
    
    # CLIP埋め込みを正規化
    _faiss.normalize_L2(embeddings)
    
    # FAISSインデックス構築
    dim = embeddings.shape[1]
    index = _faiss.IndexFlatIP(dim)
    index.add(embeddings)
    
    # k近傍検索
    k = min(21, n)
    similarities, indices = index.search(embeddings, k)
    
    # ハイブリッドフィルタリング: CLIPとpHash両方でチェック
    direct_neighbors: Dict[int, List[Tuple[int, float]]] = {}
    
    for i in range(n):
        neighbors = []
        for j_idx in range(1, k):
            j = indices[i, j_idx]
            clip_sim = similarities[i, j_idx]
            
            if j < 0 or j == i:
                continue
            
            # CLIP類似度チェック
            clip_ok = clip_sim >= clip_threshold
            
            # pHash類似度チェック
            phash_ok = False
            if phashes[i] is not None and phashes[j] is not None:
                distance = compute_phash_distance(phashes[i], phashes[j])
                phash_ok = distance <= max_phash_distance
            else:
                # pHashがない場合はCLIPのみで判断
                phash_ok = True if not require_both else False
            
            # ハイブリッド判定
            if require_both:
                is_similar = clip_ok and phash_ok
            else:
                is_similar = clip_ok or phash_ok
            
            if is_similar:
                neighbors.append((j, float(clip_sim)))
        
        if neighbors:
            direct_neighbors[i] = neighbors
    
    if not direct_neighbors:
        logger.info("No similar pairs found with hybrid detection")
        return []
    
    # 相互類似チェック（CLIPのみの時と同じロジック）
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
    
    logger.info(f"Found {len(mutual_pairs)} mutual pairs with hybrid detection")
    
    # グループ化
    used = set()
    result = []
    
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
            group = [(ids[m], paths[m]) for m in group_members]
            result.append(group)
            for m in group_members:
                used.add(m)
    
    # 残りのペア
    for i, j in mutual_pairs:
        if i not in used and j not in used:
            group = [(ids[i], paths[i]), (ids[j], paths[j])]
            result.append(group)
            used.add(i)
            used.add(j)
    
    logger.info(f"Hybrid detection found {len(result)} groups")
    return result
