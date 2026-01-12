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
        ブレ検知（鮮明度スコア）とノイズ検出を組み合わせた品質スコアを計算
        
        スコアが高いほど高品質（鮮明でノイズが少ない）
        スコアが低いほど低品質（ブレやノイズが多い）
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
            
            # 1. ブレ検出（Laplacian分散）
            laplacian = cv2.Laplacian(gray_resized, cv2.CV_64F)
            blur_score = laplacian.var()
            
            # 2. ノイズ検出（高周波成分の分析）
            noise_score = self._estimate_noise(gray_resized)
            
            # 3. 複合品質スコアの計算
            # ブレスコア（高いほど良い）とノイズスコア（低いほど良い）を組み合わせる
            # ノイズペナルティを適用: ノイズが多いほどスコアを下げる
            noise_penalty = max(0, 1 - (noise_score / 30))  # ノイズスコア30以上で大幅減点
            quality_score = blur_score * noise_penalty
            
            return float(quality_score), width, height
        except Exception as e:
            logger.error(f"[Sharpness] 例外: {file_path} - {e}")
            return 0.0, 0, 0
    
    def _estimate_noise(self, gray_img: np.ndarray) -> float:
        """
        画像のノイズレベルを推定
        
        手法: 
        1. ラプラシアン法によるノイズ推定（Immerkaer法の変形）
        2. ガウシアンフィルタとの差分による高周波ノイズ検出
        
        Returns:
            ノイズレベル（低いほど良い、0-100程度の範囲）
        """
        try:
            # 方法1: ガウシアンフィルタとの差分でノイズを推定
            # ノイズは高周波成分に現れるため、ぼかした画像との差分を見る
            blurred = cv2.GaussianBlur(gray_img, (5, 5), 0)
            diff = cv2.absdiff(gray_img, blurred)
            noise_level_1 = np.std(diff)
            
            # 方法2: ラプラシアンベースのノイズ推定（Immerkaer法）
            # ノイズはランダムな高周波成分として現れる
            # 3x3のラプラシアンカーネルを使用
            kernel = np.array([
                [1, -2, 1],
                [-2, 4, -2],
                [1, -2, 1]
            ], dtype=np.float64)
            
            sigma = cv2.filter2D(gray_img.astype(np.float64), -1, kernel)
            # ノイズの標準偏差を推定
            noise_level_2 = np.sqrt(np.pi / 2) * (1 / 6) * np.sum(np.abs(sigma)) / sigma.size
            
            # 方法3: 局所分散によるノイズ検出
            # 画像を小さなブロックに分割し、テクスチャの少ない領域の分散を見る
            block_size = 16
            h, w = gray_img.shape
            min_vars = []
            for y in range(0, h - block_size, block_size):
                for x in range(0, w - block_size, block_size):
                    block = gray_img[y:y+block_size, x:x+block_size]
                    var = np.var(block)
                    min_vars.append(var)
            
            # 最も分散の低いブロック（平坦な領域）のノイズを見る
            if min_vars:
                min_vars.sort()
                # 下位10%の分散を平均（平坦領域のノイズ推定）
                num_blocks = max(1, len(min_vars) // 10)
                noise_level_3 = np.sqrt(np.mean(min_vars[:num_blocks]))
            else:
                noise_level_3 = 0
            
            # 3つの方法を組み合わせて総合ノイズスコアを計算
            # 重み付け: ガウシアン差分を重視
            combined_noise = (noise_level_1 * 0.5 + 
                            noise_level_2 * 0.3 + 
                            noise_level_3 * 0.2)
            
            return float(combined_noise)
            
        except Exception as e:
            logger.error(f"[Noise] ノイズ推定エラー: {e}")
            return 0.0
