# -*- coding: utf-8 -*-
"""
SpectraMatch - Image Hasher Module
画像ハッシュ計算を担当するモジュール

このモジュールは2種類のハッシュを提供:
1. バイナリハッシュ (MD5) - 完全一致検出用
2. Perceptual Hash (pHash) - 類似画像検出用（DCTベース）
"""

import hashlib
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import cv2
from scipy.fftpack import dct


class HashType(Enum):
    """ハッシュタイプの列挙型"""
    MD5 = "md5"           # バイナリ完全一致用
    SHA256 = "sha256"     # バイナリ完全一致用（より厳密）
    PHASH = "phash"       # Perceptual Hash（類似検出用）


class ImageHasher:
    """
    画像ハッシュ計算クラス
    
    DCTベースのPerceptual Hash実装:
    1. 画像を32x32にリサイズ
    2. グレースケール化
    3. DCT（離散コサイン変換）を適用
    4. 左上8x8の低周波成分を抽出
    5. 平均値との比較で64bitハッシュを生成
    
    この方法により、以下の変換に対してロバストな検出が可能:
    - リサイズ
    - 再圧縮（JPEG等）
    - 色調補正
    - 軽微なブレ・ノイズ
    """
    
    # pHash計算用の定数
    PHASH_SIZE = 32        # リサイズ後のサイズ
    PHASH_HIGHFREQ_FACTOR = 4  # 抽出する低周波領域のサイズ係数
    
    # 先頭バイト読み込みサイズ（高速フィルタリング用）
    QUICK_HASH_BYTES = 4096  # 4KB
    
    def __init__(self):
        """ImageHasherの初期化"""
        pass
    
    def compute_file_size(self, file_path: Path) -> int:
        """
        ファイルサイズを取得
        
        Args:
            file_path: 対象ファイルのパス
            
        Returns:
            ファイルサイズ（バイト）
        """
        return file_path.stat().st_size
    
    def compute_quick_hash(self, file_path: Path) -> str:
        """
        先頭4KBのMD5ハッシュを計算（高速フィルタリング用）
        
        大量のファイルを効率的にフィルタリングするため、
        まず先頭部分のみを比較する。
        
        Args:
            file_path: 対象ファイルのパス
            
        Returns:
            先頭4KBのMD5ハッシュ（16進数文字列）
        """
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            data = f.read(self.QUICK_HASH_BYTES)
            hasher.update(data)
        return hasher.hexdigest()
    
    def compute_binary_hash(
        self, 
        file_path: Path, 
        hash_type: HashType = HashType.MD5
    ) -> str:
        """
        ファイル全体のバイナリハッシュを計算
        
        ファイルサイズと先頭ハッシュが一致した場合に、
        完全な重複確認のために使用する。
        
        Args:
            file_path: 対象ファイルのパス
            hash_type: ハッシュアルゴリズム（MD5またはSHA256）
            
        Returns:
            ファイル全体のハッシュ（16進数文字列）
        """
        if hash_type == HashType.SHA256:
            hasher = hashlib.sha256()
        else:
            hasher = hashlib.md5()
        
        # 大きなファイルでもメモリ効率よく処理
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    
    def compute_phash(self, file_path: Path) -> Optional[np.ndarray]:
        """
        DCTベースのPerceptual Hashを計算
        
        アルゴリズムの詳細:
        1. 画像を32x32にリサイズ（高周波成分を除去）
        2. グレースケールに変換（色情報を除去）
        3. 2D DCT（離散コサイン変換）を適用
        4. 左上8x8の低周波成分のみを抽出
        5. DC成分（[0,0]）を除いた平均値を計算
        6. 各成分を平均値と比較し、64bitのバイナリハッシュを生成
        
        Args:
            file_path: 対象画像ファイルのパス
            
        Returns:
            64要素のbool配列（pHash）、失敗時はNone
        """
        try:
            # 画像を読み込み
            img = cv2.imread(str(file_path))
            if img is None:
                return None
            
            # グレースケールに変換
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img
            
            # 32x32にリサイズ（高周波成分を減衰させる）
            resized = cv2.resize(gray, (self.PHASH_SIZE, self.PHASH_SIZE), 
                                interpolation=cv2.INTER_AREA)
            
            # float型に変換（DCT計算用）
            img_float = np.float64(resized)
            
            # 2D DCT（離散コサイン変換）を適用
            # DCTは画像を周波数成分に分解する
            # 左上ほど低周波（画像の大まかな構造）、右下ほど高周波（細部）
            dct_result = dct(dct(img_float, axis=0, norm='ortho'), axis=1, norm='ortho')
            
            # 左上8x8の低周波成分を抽出
            # この領域が画像の「本質的な特徴」を表す
            low_freq_size = self.PHASH_SIZE // self.PHASH_HIGHFREQ_FACTOR
            dct_low = dct_result[:low_freq_size, :low_freq_size]
            
            # DC成分（左上角、画像全体の平均輝度）を除外して平均を計算
            # DC成分は照明条件に強く依存するため除外
            dct_flat = dct_low.flatten()
            dct_without_dc = dct_flat[1:]  # DC成分を除く
            median_val = np.median(dct_without_dc)
            
            # 各成分を中央値と比較し、バイナリハッシュを生成
            # 中央値より大きければ1、小さければ0
            phash = dct_flat > median_val
            
            return phash
            
        except Exception as e:
            # 読み込み失敗時はNoneを返す
            return None
    
    def phash_to_int(self, phash: np.ndarray) -> int:
        """
        pHash配列を整数に変換
        
        Args:
            phash: 64要素のbool配列
            
        Returns:
            64bit整数
        """
        # bool配列を整数に変換
        hash_int = 0
        for bit in phash:
            hash_int = (hash_int << 1) | int(bit)
        return hash_int
    
    def phash_to_hex(self, phash: np.ndarray) -> str:
        """
        pHash配列を16進数文字列に変換
        
        Args:
            phash: 64要素のbool配列
            
        Returns:
            16文字の16進数文字列
        """
        hash_int = self.phash_to_int(phash)
        return format(hash_int, '016x')
    
    @staticmethod
    def hamming_distance(hash1: np.ndarray, hash2: np.ndarray) -> int:
        """
        2つのpHash間のハミング距離を計算
        
        ハミング距離 = 異なるビットの数
        - 距離0: 完全一致
        - 距離1-5: 非常に類似（ほぼ同一画像）
        - 距離6-10: 類似（同じ画像の異なるバージョン）
        - 距離11以上: 異なる画像の可能性が高い
        
        Args:
            hash1: 1つ目のpHash
            hash2: 2つ目のpHash
            
        Returns:
            ハミング距離（0-64）
        """
        # XORで異なるビットを検出し、Trueの数をカウント
        return np.sum(hash1 != hash2)
    
    @staticmethod
    def hamming_distance_int(hash1: int, hash2: int) -> int:
        """
        2つの整数pHash間のハミング距離を計算
        
        Args:
            hash1: 1つ目のpHash（整数）
            hash2: 2つ目のpHash（整数）
            
        Returns:
            ハミング距離（0-64）
        """
        # XORして異なるビットを検出、1の数をカウント
        xor = hash1 ^ hash2
        return bin(xor).count('1')
    
    def compute_sharpness(self, file_path: Path) -> Tuple[float, int, int]:
        """
        ブレ検知（鮮明度スコア）と解像度を計算
        
        Laplacian（ラプラシアン）フィルタの分散を使用。
        - 高い値 = より鮮明な画像（エッジが多い）
        - 低い値 = ブレている/ぼやけている画像
        
        一般的な目安:
        - < 100: かなりブレている
        - 100-300: 軽微なブレ
        - 300-500: 普通
        - > 500: 鮮明
        
        Args:
            file_path: 対象画像ファイルのパス
            
        Returns:
            (鮮明度スコア, 幅, 高さ) のタプル
            失敗時は (0.0, 0, 0)
        """
        try:
            img = cv2.imread(str(file_path))
            if img is None:
                return 0.0, 0, 0
            
            height, width = img.shape[:2]
            
            # グレースケールに変換
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img
            
            # Laplacianフィルタを適用し、分散を計算
            # Laplacianは2次微分であり、エッジを強調する
            # 分散が高い = エッジが多い = 鮮明な画像
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = laplacian.var()
            
            return float(sharpness), width, height
            
        except Exception as e:
            return 0.0, 0, 0
    
    def get_image_metadata(self, file_path: Path) -> Tuple[int, int, float]:
        """
        画像のメタデータを取得
        
        Args:
            file_path: 対象画像ファイルのパス
            
        Returns:
            (幅, 高さ, 鮮明度スコア) のタプル
        """
        sharpness, width, height = self.compute_sharpness(file_path)
        return width, height, sharpness

