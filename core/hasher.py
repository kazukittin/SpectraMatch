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
