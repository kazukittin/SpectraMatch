# -*- coding: utf-8 -*-
"""
SpectraMatch Core Module
画像類似検出のコアロジックを提供するモジュール
"""

from .hasher import ImageHasher
from .comparator import ImageInfo, SimilarityGroup
from .scanner import ImageScanner, ScanResult, ScanMode
from .database import ImageDatabase
from .clip_engine import CLIPEngine

# Faissはオプション
try:
    from .faiss_engine import FaissSearchEngine, find_similar_groups_faiss_clip, find_similar_groups_hybrid
except ImportError:
    FaissSearchEngine = None
    find_similar_groups_faiss_clip = None
    find_similar_groups_hybrid = None

__all__ = [
    "ImageHasher",
    "ImageInfo",
    "SimilarityGroup",
    "ImageScanner",
    "ScanResult",
    "ScanMode",
    "ImageDatabase",
    "CLIPEngine",
    "FaissSearchEngine",
    "find_similar_groups_faiss_clip",
    "find_similar_groups_hybrid",
]
