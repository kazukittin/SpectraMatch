# -*- coding: utf-8 -*-
"""
SpectraMatch - CLIP Engine Module
AIコンポーネントのオンデマンドインストールをサポート。
"""

import os
import sys
import logging
import shutil
import importlib
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
    if not getattr(sys, 'frozen', False):
        return sys.executable
    for cmd in ["python", "python3", "py"]:
        path = shutil.which(cmd)
        if path: return path
    return sys.executable

def get_install_command() -> List[str]:
    """インストール用のコマンド引数リストを返す"""
    AI_ENV_PATH.mkdir(parents=True, exist_ok=True)
    python_exe = find_python_executable()
    return [
        python_exe, "-m", "pip", "install",
        "torch", "transformers", "pillow", "numpy",
        "--target", str(AI_ENV_PATH),
        "--no-cache-dir",
        "--only-binary=:all:",
        "--no-warn-script-location",
        "--progress-bar", "off"
    ]

def is_ai_installed() -> bool:
    """AIエンジンがインストールされているか確認"""
    # 1. 念のため sys.path を再チェック
    if str(AI_ENV_PATH) not in sys.path:
        sys.path.append(str(AI_ENV_PATH))
    
    # デバッグ用に sys.path をログ出力
    logger.debug(f"Current sys.path: {sys.path}")
    
    # 2. Windowsの場合、DLL検索パスにも追加（torch等のバイナリ用）
    if os.name == 'nt' and AI_ENV_PATH.exists():
        try:
            # 主要なライブラリのDLLディレクトリを登録
            dll_dirs = [
                str(AI_ENV_PATH),
                str(AI_ENV_PATH / "torch" / "lib"),
                str(AI_ENV_PATH / "PIL"),
                str(AI_ENV_PATH / "numpy" / "core"),
                str(AI_ENV_PATH / "numpy" / ".libs"),
            ]
            for d in dll_dirs:
                if os.path.isdir(d):
                    os.add_dll_directory(d)
        except (AttributeError, OSError):
            pass

    # 3. ファイルシステムキャッシュの無効化
    importlib.invalidate_caches()
    
    try:
        # 4. 依存関係の個別インポート試行（原因特定用）
        import numpy
        import torch
        import transformers
        import PIL.Image
        
        # 5. バージョン情報をログに出して確認
        logger.info(f"AI components detected: torch={torch.__version__}, transformers={transformers.__version__}")
        return True
    except (ImportError, ModuleNotFoundError) as e:
        logger.warning(f"AI component missing or failed to load: {e}")
        # 詳細なデバッグ情報をログに出力
        try:
            import traceback
            logger.debug(traceback.format_exc())
        except:
            pass
        return False
    except Exception as e:
        logger.error(f"Unexpected error during AI check: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

_CLIP_AVAILABLE = None

def _check_clip_available() -> bool:
    """CLIPが利用可能かチェック（内部キャッシュあり）"""
    global _CLIP_AVAILABLE
    # 実行時に動的にチェックする（インストール直後に対応するため）
    _CLIP_AVAILABLE = is_ai_installed()
    return _CLIP_AVAILABLE

class CLIPEngine:
    """CLIPによる特徴抽出エンジン"""
    
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        self.model_name = model_name
        self.model = None
        self.processor = None
        self.device = "cpu"
        
    @property
    def is_available(self) -> bool:
        return is_ai_installed()
        
    def load_model(self, progress_callback=None):
        if self.model is not None: return True
        
        # インストール済みか再確認
        if not is_ai_installed():
            logger.error("CLIP dependencies are not installed.")
            return False
            
        try:
            if progress_callback: progress_callback("AIモデルを読み込み中...")
            import torch
            from transformers import CLIPProcessor, CLIPModel
            
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading CLIP model: {self.model_name} on {self.device}...")
            
            self.model = CLIPModel.from_pretrained(self.model_name).to(self.device)
            self.processor = CLIPProcessor.from_pretrained(self.model_name)
            
            logger.info("CLIP model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load CLIP: {e}")
            import traceback
            logger.debug(traceback.format_exc())
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
            logger.error(f"Error extracting features: {e}")
            return None
