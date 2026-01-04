# -*- coding: utf-8 -*-
"""
SpectraMatch - CLIP Engine Module
AIコンポーネントのオンデマンドインストールをサポート。
"""

import os
import sys
import logging
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# AIライブラリの保存先
AI_ENV_PATH = Path.home() / ".spectramatch" / "ai_libs"

# Pythonパスに追加
if str(AI_ENV_PATH) not in sys.path:
    sys.path.append(str(AI_ENV_PATH))

def find_python_executable() -> str:
    """システムのPython実行ファイルのパスを見つける"""
    # 1. sys.executable を確認（開発環境用）
    # ただし、EXE化されている場合は自分自身(EXE)を指すので注意
    if not getattr(sys, 'frozen', False):
        return sys.executable
        
    # 2. EXE化されている場合、環境変数や一般的なパスから探す
    # python 又は python3 が PATH にあればそれを使うのが最も確実
    for cmd in ["python", "python3", "py"]:
        path = shutil.which(cmd)
        if path:
            return path
            
    # 3. 見つからない場合は最終手段として sys.executable (恐らく失敗するが)
    return sys.executable

def get_install_command() -> List[str]:
    """インストール用のコマンド引数リストを返す"""
    AI_ENV_PATH.mkdir(parents=True, exist_ok=True)
    python_exe = find_python_executable()
    
    logger.info(f"Using Python executable for install: {python_exe}")
    
    return [
        python_exe, "-m", "pip", "install",
        "torch", "transformers", "pillow", "numpy",
        "--target", str(AI_ENV_PATH),
        "--no-warn-script-location",
        "--progress-bar", "off"  # 解析しやすいように進捗バーはOFF
    ]

def is_ai_installed() -> bool:
    """AIエンジンがインストールされているか確認"""
    try:
        if str(AI_ENV_PATH) not in sys.path:
            sys.path.append(str(AI_ENV_PATH))
        
        # 依存関係をチェック
        import torch
        import transformers
        return True
    except ImportError:
        return False
    except Exception as e:
        logger.error(f"Error checking AI installation: {e}")
        return False

# CLIPEngine クラス等は前回と同じため省略（あるいは継承）
class CLIPEngine:
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        self.model_name = model_name
        self.model = None
        self.processor = None
        self.device = "cpu"
        
    def load_model(self):
        if self.model is not None: return True
        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = CLIPModel.from_pretrained(self.model_name).to(self.device)
            self.processor = CLIPProcessor.from_pretrained(self.model_name)
            return True
        except Exception as e:
            logger.error(f"Failed to load CLIP: {e}")
            return False

    def get_embedding(self, image_path: Path) -> Optional[np.ndarray]:
        if not self.load_model(): return None
        import torch
        from PIL import Image
        try:
            image = Image.open(image_path).convert("RGB")
            inputs = self.processor(images=image, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.model.get_image_features(**inputs)
            embedding = outputs.cpu().numpy()[0]
            norm = np.linalg.norm(embedding)
            if norm > 1e-6: embedding = embedding / norm
            return embedding
        except Exception as e:
            logger.error(f"Error: {e}")
            return None
