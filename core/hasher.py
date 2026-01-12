# -*- coding: utf-8 -*-
"""
SpectraMatch - Image Hasher Module
画像情報の抽出を担当するモジュール
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import cv2

logger = logging.getLogger(__name__)


def imread_unicode(file_path: Path) -> Optional[np.ndarray]:
    """
    日本語/マルチバイト文字パス対応の画像読み込み
    """
    try:
        # バイナリとして読み込み
        stream = np.fromfile(str(file_path), dtype=np.uint8)
        if stream is None or len(stream) == 0:
            return None
        
        # cv2.imdecodeでデコード
        img = cv2.imdecode(stream, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        logger.error(f"[Load] 例外: {file_path} - {e}")
        return None


class ImageHasher:
    """
    画像情報抽出クラス
    """
    
    # 先頭バイト読み込みサイズ
    QUICK_HASH_BYTES = 4096  # 4KB
    
    # pHash設定
    PHASH_SIZE = 8  # 8x8 = 64ビットハッシュ
    PHASH_HIGHFREQ_FACTOR = 4  # DCT用の高周波係数
    
    def __init__(self):
        """ImageHasherの初期化"""
        pass
    
    def compute_file_size(self, file_path: Path) -> int:
        """ファイルサイズを取得"""
        return file_path.stat().st_size
    
    def compute_quick_hash(self, file_path: Path) -> str:
        """先頭4KBのMD5ハッシュを計算"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            data = f.read(self.QUICK_HASH_BYTES)
            hasher.update(data)
        return hasher.hexdigest()
    
    def compute_phash(self, file_path: Path) -> Optional[int]:
        """
        pHash（知覚ハッシュ）を計算
        
        視覚的に似た画像は近いハッシュ値を持つ。
        DCT（離散コサイン変換）ベースのアルゴリズムを使用。
        
        Returns:
            64ビットのハッシュ値（int）、失敗時はNone
        """
        try:
            img = imread_unicode(file_path)
            if img is None:
                return None
            
            # グレースケールに変換
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img
            
            # DCT用にリサイズ（32x32が一般的）
            img_size = self.PHASH_SIZE * self.PHASH_HIGHFREQ_FACTOR
            resized = cv2.resize(gray, (img_size, img_size), interpolation=cv2.INTER_AREA)
            
            # float32に変換してDCT
            resized = np.float32(resized)
            dct = cv2.dct(resized)
            
            # 左上の低周波成分のみ使用（8x8）
            dct_low = dct[:self.PHASH_SIZE, :self.PHASH_SIZE]
            
            # DC成分（左上隅）を除外した中央値を計算
            dct_flat = dct_low.flatten()
            median = np.median(dct_flat[1:])  # DC成分を除外
            
            # 中央値より大きいか小さいかで0/1を決定
            diff = dct_low > median
            
            # 64ビットハッシュに変換
            hash_value = 0
            for i, bit in enumerate(diff.flatten()):
                if bit:
                    hash_value |= (1 << i)
            
            # SQLiteは符号付き64ビット整数のため、符号付きに変換
            # 最上位ビットが1の場合、負の値として扱う
            if hash_value >= (1 << 63):
                hash_value -= (1 << 64)
            
            return hash_value
            
        except Exception as e:
            logger.error(f"[pHash] 例外: {file_path} - {e}")
            return None
    
    def compute_phash_distance(self, hash1: int, hash2: int) -> int:
        """
        2つのpHashのハミング距離を計算
        
        Returns:
            ハミング距離（0-64）、値が小さいほど類似
        """
        # 負の値は64ビットのビットパターンとして扱う
        xor = (hash1 ^ hash2) & 0xFFFFFFFFFFFFFFFF
        return bin(xor).count('1')
    
    def compute_phash_similarity(self, hash1: int, hash2: int) -> float:
        """
        2つのpHashの類似度を計算
        
        Returns:
            類似度（0.0-1.0）、1.0が完全一致
        """
        distance = self.compute_phash_distance(hash1, hash2)
        return 1.0 - (distance / 64.0)
    
    def compute_sharpness(self, file_path: Path) -> Tuple[float, int, int]:
        """
        ブレ検知（鮮明度スコア）と解像度を計算
        """
        try:
            img = imread_unicode(file_path)
            if img is None:
                return 0.0, 0, 0
            
            height, width = img.shape[:2]
            
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img
            
            ANALYSIS_SIZE = 500  # 分析用サイズ（長辺）
            h, w = gray.shape[:2]
            if max(h, w) > ANALYSIS_SIZE:
                scale = ANALYSIS_SIZE / max(h, w)
                new_w = int(w * scale)
                new_h = int(h * scale)
                gray_resized = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
            else:
                gray_resized = gray
            
            laplacian = cv2.Laplacian(gray_resized, cv2.CV_64F)
            sharpness = laplacian.var()
            
            return float(sharpness), width, height
        except Exception as e:
            logger.error(f"[Sharpness] 例外: {file_path} - {e}")
            return 0.0, 0, 0
