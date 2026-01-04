# -*- coding: utf-8 -*-
"""
SpectraMatch - Image Comparator Module
画像情報を保持するデータ構造
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import numpy as np


@dataclass
class ImageInfo:
    """
    画像情報を保持するデータクラス
    
    Attributes:
        path: ファイルパス
        file_size: ファイルサイズ（バイト）
        width: 画像幅（ピクセル）
        height: 画像高さ（ピクセル）
        sharpness_score: 鮮明度スコア（Laplacian分散値、高いほど鮮明）
        clip_embedding: CLIP埋め込みベクトル（512次元、AIモード用）
        phash_int: 互換性維持のためのダミー（常に0）
    """
    path: Path
    file_size: int = 0
    width: int = 0
    height: int = 0
    sharpness_score: float = 0.0
    clip_embedding: Optional[np.ndarray] = None
    phash_int: int = 0
    
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
        min_distance: グループ内の最小距離（CLIPでは類似度%の逆数等）
        max_distance: グループ内の最大距離
    """
    group_id: int
    images: List[ImageInfo] = field(default_factory=list)
    is_exact_match: bool = False
    min_distance: float = 0.0
    max_distance: float = 0.0
    
    def add_image(self, image: ImageInfo):
        """画像をグループに追加"""
        if image not in self.images:
            self.images.append(image)
    
    @property
    def count(self) -> int:
        """グループ内の画像数"""
        return len(self.images)
