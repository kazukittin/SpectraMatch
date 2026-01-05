# -*- coding: utf-8 -*-
"""
SpectraMatch - Configuration Manager
設定の保存・読み込みを管理
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any

class ConfigManager:
    """設定管理クラス"""
    
    DEFAULT_CONFIG = {
        "scan_folders": [],
        "similarity_threshold": 85,
        "theme": "dark",
        "cache_enabled": True
    }
    
    def __init__(self):
        self.config_dir = Path.home() / ".SpectraMatch"
        self.config_file = self.config_dir / "config.json"
        self.config = self.DEFAULT_CONFIG.copy()
        self.load()
    
    def load(self):
        """設定をファイルから読み込む"""
        if not self.config_file.exists():
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                # デフォルト設定をベースに、保存された設定で上書き（キー不足防止）
                self.config.update(saved_config)
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def save(self):
        """設定をファイルに保存する"""
        try:
            if not self.config_dir.exists():
                self.config_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get_scan_folders(self) -> List[str]:
        """スキャン対象フォルダのリストを取得"""
        return self.config.get("scan_folders", [])
    
    def set_scan_folders(self, folders: List[str]):
        """スキャン対象フォルダを設定"""
        self.config["scan_folders"] = folders
        self.save()
    
    def get_threshold(self) -> int:
        """類似度閾値を取得"""
        return self.config.get("similarity_threshold", 85)
    
    def set_threshold(self, threshold: int):
        """類似度閾値を設定"""
        self.config["similarity_threshold"] = threshold
        self.save()
