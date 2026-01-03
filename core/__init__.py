# -*- coding: utf-8 -*-
"""
SpectraMatch Core Module
画像類似検出のコアロジックを提供するモジュール
"""

from .hasher import ImageHasher, HashType
from .comparator import ImageComparator, ImageInfo, SimilarityGroup
from .scanner import ImageScanner, ScanResult, ScanMode
from .database import ImageDatabase
from .clip_engine import CLIPEngine, find_similar_groups_clip

# Faissはオプション
try:
    from .faiss_engine import FaissSearchEngine, find_similar_groups_faiss_phash, find_similar_groups_faiss_clip
except ImportError:
    FaissSearchEngine = None
    find_similar_groups_faiss_phash = None
    find_similar_groups_faiss_clip = None

__all__ = [
    "ImageHasher",
    "HashType",
    "ImageComparator",
    "ImageInfo",
    "SimilarityGroup",
    "ImageScanner",
    "ScanResult",
    "ScanMode",
    "ImageDatabase",
    "CLIPEngine",
    "find_similar_groups_clip",
    "FaissSearchEngine",
    "find_similar_groups_faiss_phash",
    "find_similar_groups_faiss_clip",
]
