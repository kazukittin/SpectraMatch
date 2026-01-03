# -*- coding: utf-8 -*-
"""
SpectraMatch - Image Comparator Module
画像の類似度判定と類似グループの管理を担当するモジュール

将来的なAIモデル組み込みを見越し、抽象基底クラスを使用した
拡張性の高い設計を採用。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

from .hasher import ImageHasher, HashType


@dataclass
class ImageInfo:
    """
    画像情報を保持するデータクラス
    
    Attributes:
        path: ファイルパス
        file_size: ファイルサイズ（バイト）
        quick_hash: 先頭4KBのハッシュ
        full_hash: ファイル全体のハッシュ
        phash: Perceptual Hash（64要素bool配列）
        phash_int: Perceptual Hash（整数表現）
        width: 画像幅（ピクセル）
        height: 画像高さ（ピクセル）
        sharpness_score: 鮮明度スコア（Laplacian分散値、高いほど鮮明）
        clip_embedding: CLIP埋め込みベクトル（512次元、AIモード用）
    """
    path: Path
    file_size: int = 0
    quick_hash: str = ""
    full_hash: str = ""
    phash: Optional[np.ndarray] = None
    phash_int: int = 0
    width: int = 0
    height: int = 0
    sharpness_score: float = 0.0
    clip_embedding: Optional[np.ndarray] = None
    
    @property
    def resolution(self) -> int:
        """総ピクセル数（解像度比較用）"""
        return self.width * self.height
    
    @property
    def resolution_str(self) -> str:
        """解像度の文字列表現"""
        return f"{self.width} x {self.height}"
    
    def quality_score(self) -> float:
        """
        総合品質スコアを計算
        解像度と鮮明度を加味した正規化スコア
        """
        # 解像度スコア (1000万ピクセルを基準に正規化)
        res_score = min(self.resolution / 10_000_000, 1.0)
        # 鮮明度スコア (1000を基準に正規化)
        sharp_score = min(self.sharpness_score / 1000, 1.0)
        # 重み付け平均 (解像度40%, 鮮明度60%)
        return res_score * 0.4 + sharp_score * 0.6
    
    def __hash__(self):
        """辞書のキーとして使用するためのハッシュ"""
        return hash(str(self.path))
    
    def __eq__(self, other):
        """等価比較"""
        if not isinstance(other, ImageInfo):
            return False
        return self.path == other.path


@dataclass
class SimilarityGroup:
    """
    類似画像グループを表すデータクラス
    
    Attributes:
        group_id: グループの一意識別子
        images: グループに属する画像情報のリスト
        is_exact_match: 完全一致かどうか（True=バイナリ一致, False=類似）
        min_distance: グループ内の最小ハミング距離
        max_distance: グループ内の最大ハミング距離
    """
    group_id: int
    images: List[ImageInfo] = field(default_factory=list)
    is_exact_match: bool = False
    min_distance: int = 0
    max_distance: int = 0
    
    def add_image(self, image: ImageInfo):
        """画像をグループに追加"""
        if image not in self.images:
            self.images.append(image)
    
    @property
    def count(self) -> int:
        """グループ内の画像数"""
        return len(self.images)


class BaseComparator(ABC):
    """
    画像比較の抽象基底クラス
    
    将来的なAIモデル（CLIP等）の組み込みを見越し、
    インターフェースを統一するための基底クラス。
    """
    
    @abstractmethod
    def compute_similarity(
        self, 
        image1: ImageInfo, 
        image2: ImageInfo
    ) -> Tuple[bool, float]:
        """
        2つの画像の類似度を計算
        
        Args:
            image1: 1つ目の画像情報
            image2: 2つ目の画像情報
            
        Returns:
            (類似かどうか, 類似度スコア) のタプル
        """
        pass
    
    @abstractmethod
    def find_similar_groups(
        self, 
        images: List[ImageInfo],
        threshold: int
    ) -> List[SimilarityGroup]:
        """
        類似画像のグループを検出
        
        Args:
            images: 画像情報のリスト
            threshold: 類似度閾値
            
        Returns:
            類似グループのリスト
        """
        pass


class ImageComparator(BaseComparator):
    """
    DCT pHashベースの画像比較クラス
    
    2段階のフィルタリングパイプライン:
    1. 完全一致検出（高速）: ファイルサイズ → 先頭ハッシュ → 全体ハッシュ
    2. 類似画像検出（高精度）: pHashのハミング距離
    """
    
    def __init__(self, hasher: Optional[ImageHasher] = None):
        """
        ImageComparatorの初期化
        
        Args:
            hasher: ImageHasherインスタンス（省略時は内部で生成）
        """
        self.hasher = hasher or ImageHasher()
        self._group_counter = 0
    
    def _get_next_group_id(self) -> int:
        """次のグループIDを取得"""
        self._group_counter += 1
        return self._group_counter
    
    def compute_similarity(
        self, 
        image1: ImageInfo, 
        image2: ImageInfo
    ) -> Tuple[bool, float]:
        """
        2つの画像の類似度を計算
        
        Args:
            image1: 1つ目の画像情報
            image2: 2つ目の画像情報
            
        Returns:
            (類似かどうか, ハミング距離) のタプル
        """
        if image1.phash is None or image2.phash is None:
            return False, 64  # 最大距離
        
        distance = ImageHasher.hamming_distance(image1.phash, image2.phash)
        return True, distance
    
    def find_exact_duplicates(
        self, 
        images: List[ImageInfo]
    ) -> Tuple[List[SimilarityGroup], List[ImageInfo]]:
        """
        Step 1: 完全一致（バイナリ重複）を検出
        
        処理フロー:
        1. ファイルサイズでグループ化
        2. 同サイズ内で先頭4KBハッシュを比較
        3. 先頭ハッシュ一致時、全体ハッシュで最終確認
        
        Args:
            images: 画像情報のリスト
            
        Returns:
            (完全一致グループのリスト, 重複しなかった画像のリスト)
        """
        # ファイルサイズでグループ化
        size_groups: Dict[int, List[ImageInfo]] = {}
        for img in images:
            if img.file_size not in size_groups:
                size_groups[img.file_size] = []
            size_groups[img.file_size].append(img)
        
        exact_groups: List[SimilarityGroup] = []
        non_duplicates: List[ImageInfo] = []
        processed: Set[Path] = set()
        
        for size, size_group in size_groups.items():
            if len(size_group) == 1:
                # サイズが一意 → 重複なし
                non_duplicates.append(size_group[0])
                continue
            
            # 同サイズ内でクイックハッシュでグループ化
            quick_hash_groups: Dict[str, List[ImageInfo]] = {}
            for img in size_group:
                qh = img.quick_hash
                if qh not in quick_hash_groups:
                    quick_hash_groups[qh] = []
                quick_hash_groups[qh].append(img)
            
            for qh, qh_group in quick_hash_groups.items():
                if len(qh_group) == 1:
                    non_duplicates.append(qh_group[0])
                    continue
                
                # 全体ハッシュでグループ化
                full_hash_groups: Dict[str, List[ImageInfo]] = {}
                for img in qh_group:
                    fh = img.full_hash
                    if fh not in full_hash_groups:
                        full_hash_groups[fh] = []
                    full_hash_groups[fh].append(img)
                
                for fh, fh_group in full_hash_groups.items():
                    if len(fh_group) == 1:
                        non_duplicates.append(fh_group[0])
                    else:
                        # 完全一致グループを作成
                        group = SimilarityGroup(
                            group_id=self._get_next_group_id(),
                            images=fh_group,
                            is_exact_match=True,
                            min_distance=0,
                            max_distance=0
                        )
                        exact_groups.append(group)
                        for img in fh_group:
                            processed.add(img.path)
        
        return exact_groups, non_duplicates
    
    def find_similar_groups(
        self, 
        images: List[ImageInfo],
        threshold: int = 10
    ) -> List[SimilarityGroup]:
        """
        Step 2: 類似画像のグループを検出（NumPyベクトル化版）
        
        pHash間のハミング距離が閾値以下の画像をグループ化。
        NumPyの行列演算で高速に距離行列を計算。
        
        Args:
            images: 画像情報のリスト
            threshold: ハミング距離の閾値（0-64）
            
        Returns:
            類似グループのリスト
        """
        # 有効なpHashを持つ画像のみフィルタリング
        valid_indices = [i for i, img in enumerate(images) if img.phash is not None]
        n = len(valid_indices)
        
        if n < 2:
            return []
        
        # pHash整数値を配列に変換
        hash_array = np.array(
            [images[i].phash_int for i in valid_indices], 
            dtype=np.uint64
        )
        
        # ベクトル化されたハミング距離計算
        # XORで異なるビットを検出
        # (N, 1) XOR (1, N) = (N, N) の距離行列
        xor_matrix = hash_array[:, np.newaxis] ^ hash_array[np.newaxis, :]
        
        # ビットカウント（popcount）- 各要素の1のビット数をカウント
        # NumPyにはpopcountがないので、効率的なビットカウント関数を使用
        def popcount_vectorized(x):
            """64bit整数配列のビットカウント（並列処理）"""
            # 8bit単位でカウント
            x = x.astype(np.uint64)
            result = np.zeros_like(x, dtype=np.int32)
            for shift in range(8):
                byte_vals = ((x >> (shift * 8)) & 0xFF).astype(np.uint8)
                # ルックアップテーブルを使用したビットカウント
                result += np.array([bin(b).count('1') for b in byte_vals.flat]).reshape(byte_vals.shape)
            return result
        
        # 距離行列を計算
        distance_matrix = popcount_vectorized(xor_matrix)
        
        # 閾値以下のペアを抽出（上三角のみ）
        similar_pairs = np.argwhere(
            (distance_matrix <= threshold) & 
            (np.triu(np.ones((n, n), dtype=bool), k=1))
        )
        
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
        
        # 距離情報を保存
        distances: Dict[Tuple[int, int], int] = {}
        for i, j in similar_pairs:
            union(i, j)
            distances[(i, j)] = distance_matrix[i, j]
        
        # グループを構築
        group_members: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            if root not in group_members:
                group_members[root] = []
            group_members[root].append(i)
        
        # 2個以上のメンバーを持つグループのみ返す
        result: List[SimilarityGroup] = []
        for root, members in group_members.items():
            if len(members) < 2:
                continue
            
            # インデックスを元の画像リストのインデックスに変換
            original_indices = [valid_indices[m] for m in members]
            group_images = [images[i] for i in original_indices]
            
            # グループ内の距離統計
            min_dist = 64
            max_dist = 0
            for i, m1 in enumerate(members):
                for m2 in members[i+1:]:
                    key = (min(m1, m2), max(m1, m2))
                    if key in distances:
                        d = distances[key]
                        min_dist = min(min_dist, d)
                        max_dist = max(max_dist, d)
            
            group = SimilarityGroup(
                group_id=self._get_next_group_id(),
                images=group_images,
                is_exact_match=False,
                min_distance=min_dist,
                max_distance=max_dist
            )
            result.append(group)
        
        return result
    
    def analyze_images(
        self, 
        images: List[ImageInfo],
        threshold: int = 10
    ) -> List[SimilarityGroup]:
        """
        2段階のフィルタリングパイプラインを実行
        
        Args:
            images: 画像情報のリスト
            threshold: 類似度閾値
            
        Returns:
            すべての類似グループ（完全一致 + 類似）
        """
        # Step 1: 完全一致を検出
        exact_groups, non_duplicates = self.find_exact_duplicates(images)
        
        # Step 2: 残りの画像で類似検出
        similar_groups = self.find_similar_groups(non_duplicates, threshold)
        
        # 両方の結果を結合
        return exact_groups + similar_groups


class CLIPComparator(BaseComparator):
    """
    CLIPモデルベースの画像比較クラス（将来実装用プレースホルダー）
    
    このクラスは将来のディープラーニングモデル統合のための
    スケルトン実装です。
    """
    
    def __init__(self, model_name: str = "ViT-B/32"):
        """
        CLIPComparatorの初期化
        
        Args:
            model_name: 使用するCLIPモデル
        """
        self.model_name = model_name
        self.model = None  # 将来: CLIPモデルをロード
        self._group_counter = 0
    
    def compute_similarity(
        self, 
        image1: ImageInfo, 
        image2: ImageInfo
    ) -> Tuple[bool, float]:
        """
        CLIPによる類似度計算（未実装）
        
        将来的には:
        1. 両画像からCLIP埋め込みベクトルを生成
        2. コサイン類似度を計算
        3. 閾値と比較
        """
        raise NotImplementedError("CLIPComparator is not yet implemented")
    
    def find_similar_groups(
        self, 
        images: List[ImageInfo],
        threshold: int
    ) -> List[SimilarityGroup]:
        """
        CLIP埋め込みによる類似グループ検出（未実装）
        """
        raise NotImplementedError("CLIPComparator is not yet implemented")
