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
        
    # 1. PATHから検索
    for cmd in ["python", "python3", "py"]:
        path = shutil.which(cmd)
        if path: return path
    
    # 2. Windows レジストリから検索
    if os.name == 'nt':
        try:
            import winreg
            # PythonCore (Official)
            access_registry = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
            try:
                key = winreg.OpenKey(access_registry, r"SOFTWARE\Python\PythonCore")
                # 最新バージョンを探す
                vers = []
                i = 0
                while True:
                    try:
                        vers.append(winreg.EnumKey(key, i))
                        i += 1
                    except OSError:
                        break
                if vers:
                    vers.sort(key=lambda s: [int(x) for x in s.split('.') if x.isdigit()], reverse=True)
                    latest = vers[0]
                    with winreg.OpenKey(key, f"{latest}\\InstallPath") as path_key:
                        install_path = winreg.QueryValue(path_key, None)
                        exe_path = os.path.join(install_path, "python.exe")
                        if os.path.exists(exe_path):
                            return exe_path
            except OSError:
                pass
                
            # CurrentUserも確認
            access_registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            try:
                key = winreg.OpenKey(access_registry, r"SOFTWARE\Python\PythonCore")
                vers = []
                i = 0
                while True:
                    try:
                        vers.append(winreg.EnumKey(key, i))
                        i += 1
                    except OSError:
                        break
                if vers:
                    vers.sort(key=lambda s: [int(x) for x in s.split('.') if x.isdigit()], reverse=True)
                    latest = vers[0]
                    with winreg.OpenKey(key, f"{latest}\\InstallPath") as path_key:
                        install_path = winreg.QueryValue(path_key, None)
                        exe_path = os.path.join(install_path, "python.exe")
                        if os.path.exists(exe_path):
                            return exe_path
            except OSError:
                pass
        except Exception as e:
            logger.debug(f"Registry lookup failed: {e}")

    # 3. 一般的なインストールパスを確認 (ユーザープロファイルなど)
    common_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python310\python.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python39\python.exe"),
        r"C:\Python310\python.exe",
        r"C:\Python311\python.exe",
        r"C:\Python312\python.exe",
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p

    # 見つからない場合、Noneを返す（sys.executableを返すと無限ループになるため）
    return None

def get_install_command() -> List[str]:
    """インストール用のコマンド引数リストを返す"""
    AI_ENV_PATH.mkdir(parents=True, exist_ok=True)
    python_exe = find_python_executable() or "python"
    return [
        python_exe, "-m", "pip", "install",
        "torch", "transformers", "pillow", "numpy",
        "--target", str(AI_ENV_PATH),
        "--no-cache-dir",
        "--only-binary=:all:",
        "--no-warn-script-location",
        "--progress-bar", "off"
    ]

def is_ai_installed_on_disk() -> bool:
    """
    ファイルシステムベースでAIライブラリがインストール済みかチェック。
    インストール直後でプロセス再起動前でもTrueを返せる軽量チェック。
    """
    required_packages = ["torch", "transformers", "PIL", "numpy"]
    for pkg in required_packages:
        pkg_path = AI_ENV_PATH / pkg
        if not pkg_path.exists():
            logger.debug(f"Package not found on disk: {pkg_path}")
            return False
    logger.info(f"All AI packages found on disk at {AI_ENV_PATH}")
    return True


def is_ai_installed() -> bool:
    """AIエンジンがインストールされているか確認"""
    
    # PyInstaller環境の場合はサブプロセスでシステムPythonを使ってチェック
    if getattr(sys, 'frozen', False):
        return _check_ai_via_subprocess()
    
    # 通常のPython環境の場合は直接インポートテスト
    return _check_ai_direct_import()


def _check_ai_via_subprocess() -> bool:
    """サブプロセスでシステムPythonを使ってAIライブラリをチェック"""
    import subprocess
    
    python_exe = find_python_executable()
    if python_exe is None:
        # システムPythonが見つからない場合はディスクチェックにフォールバック
        logger.warning("System Python not found, falling back to disk check")
        return is_ai_installed_on_disk()
    
    if python_exe == sys.executable and getattr(sys, 'frozen', False):
         # Should not happen with new logic, but safe guard
         return is_ai_installed_on_disk()
    
    # Pythonスクリプトでインポートテスト
    test_script = f'''
import sys
sys.path.insert(0, r"{AI_ENV_PATH}")
try:
    import numpy
    import torch
    import transformers
    import PIL.Image
    print("OK")
except Exception as e:
    print(f"ERROR: {{e}}")
'''
    
    try:
        result = subprocess.run(
            [python_exe, "-c", test_script],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        output = result.stdout.strip()
        if output == "OK":
            logger.info("AI components verified via subprocess")
            return True
        else:
            logger.warning(f"AI check via subprocess failed: {output} {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("AI check subprocess timed out")
        return False
    except Exception as e:
        logger.error(f"AI check subprocess error: {e}")
        return False


def _check_ai_direct_import() -> bool:
    """直接インポートでAIライブラリをチェック（通常Python環境用）"""
    # sys.path を再チェック
    if str(AI_ENV_PATH) not in sys.path:
        sys.path.insert(0, str(AI_ENV_PATH))
    
    # Windowsの場合、DLL検索パスにも追加
    if os.name == 'nt' and AI_ENV_PATH.exists():
        try:
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

    importlib.invalidate_caches()
    
    try:
        import numpy
        import torch
        import transformers
        import PIL.Image
        
        logger.info(f"AI components detected: torch={torch.__version__}, transformers={transformers.__version__}")
        return True
    except (ImportError, ModuleNotFoundError) as e:
        logger.warning(f"AI component missing or failed to load: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during AI check: {e}")
        return False

_CLIP_AVAILABLE = None

def _check_clip_available() -> bool:
    """CLIPが利用可能かチェック（内部キャッシュあり）"""
    global _CLIP_AVAILABLE
    # 実行時に動的にチェックする（インストール直後に対応するため）
    _CLIP_AVAILABLE = is_ai_installed()
    return _CLIP_AVAILABLE

class CLIPEngine:
    """CLIPによる特徴抽出エンジン（PyInstaller対応版）
    
    PyInstallerでビルドされた環境では、外部のシステムPythonを使って
    ワーカープロセスでCLIP処理を行う。
    """
    
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        self.model_name = model_name
        self.model = None
        self.processor = None
        self.device = "cpu"
        self._use_subprocess = getattr(sys, 'frozen', False)
        self._worker_process = None
        self._worker_ready = False
        
    @property
    def is_available(self) -> bool:
        return is_ai_installed()
    
    def _get_worker_script_path(self) -> Path:
        """ワーカースクリプトのパスを取得"""
        if getattr(sys, 'frozen', False):
            # PyInstaller環境: exeと同じディレクトリかリソースから
            base_path = Path(sys.executable).parent
            worker_path = base_path / "core" / "clip_worker.py"
            if worker_path.exists():
                return worker_path
            # フォールバック: _MEIPASSからも探す
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                worker_path = Path(meipass) / "core" / "clip_worker.py"
                if worker_path.exists():
                    return worker_path
        # 開発環境
        return Path(__file__).parent / "clip_worker.py"
    
    def _start_worker(self, progress_callback=None) -> bool:
        """ワーカープロセスを起動（タイムアウト付き）"""
        import subprocess
        import json
        import threading
        import queue
        
        if self._worker_process is not None and self._worker_process.poll() is None:
            # すでに起動中
            return self._worker_ready
        
        python_exe = find_python_executable()
        if not python_exe:
            msg = "System Python not found. Please install Python 3.9+."
            logger.error(msg)
            if progress_callback: progress_callback(f"エラー: {msg}")
            return False

        worker_script = self._get_worker_script_path()
        
        logger.info(f"Starting worker: python={python_exe}, script={worker_script}")
        
        if not worker_script.exists():
            logger.error(f"Worker script not found: {worker_script}")
            return False
        
        try:
            if progress_callback:
                progress_callback("AIワーカーを起動中...")
            
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            
            # 環境変数を設定（AIライブラリのパスを含める）
            env = os.environ.copy()
            env['PYTHONPATH'] = str(AI_ENV_PATH) + os.pathsep + env.get('PYTHONPATH', '')
            
            self._worker_process = subprocess.Popen(
                [python_exe, str(worker_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=creationflags,
                env=env
            )
            
            logger.info(f"Worker process started with PID: {self._worker_process.pid}")
            
            # モデル読み込み完了を待つ（タイムアウト付き）
            if progress_callback:
                progress_callback("AIモデルを読み込み中...")
            
            # 非同期読み取り用のキュー
            output_queue = queue.Queue()
            
            def read_output():
                """ワーカーの出力を読み取るスレッド"""
                try:
                    while True:
                        line = self._worker_process.stdout.readline()
                        if line:
                            output_queue.put(('stdout', line))
                        else:
                            break
                except Exception as e:
                    output_queue.put(('error', str(e)))
            
            def read_stderr():
                """ワーカーのエラー出力を読み取るスレッド"""
                try:
                    while True:
                        line = self._worker_process.stderr.readline()
                        if line:
                            output_queue.put(('stderr', line))
                            logger.debug(f"Worker stderr: {line.strip()}")
                        else:
                            break
                except Exception:
                    pass
            
            # 読み取りスレッドを開始
            stdout_thread = threading.Thread(target=read_output, daemon=True)
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            
            # タイムアウト付きで待機（最大5分）
            timeout_seconds = 300
            start_time = __import__('time').time()
            
            while True:
                elapsed = __import__('time').time() - start_time
                if elapsed > timeout_seconds:
                    logger.error(f"Worker startup timed out after {timeout_seconds}s")
                    self._worker_process.kill()
                    return False
                
                # プロセスが終了していないかチェック
                if self._worker_process.poll() is not None:
                    # プロセスが終了した
                    stderr_output = []
                    while not output_queue.empty():
                        try:
                            msg_type, msg = output_queue.get_nowait()
                            if msg_type == 'stderr':
                                stderr_output.append(msg)
                        except queue.Empty:
                            break
                    logger.error(f"Worker terminated unexpectedly: {''.join(stderr_output)}")
                    return False
                
                try:
                    msg_type, line = output_queue.get(timeout=1.0)
                except queue.Empty:
                    # 進捗表示を更新
                    remaining = int(timeout_seconds - elapsed)
                    if progress_callback and remaining % 10 == 0:
                        progress_callback(f"AIモデルを読み込み中... (残り{remaining}秒)")
                    continue
                
                if msg_type == 'error':
                    logger.error(f"Read error: {line}")
                    return False
                
                if msg_type == 'stderr':
                    continue
                
                try:
                    data = json.loads(line.strip())
                    status = data.get("status")
                    
                    if status == "loading":
                        msg = data.get("message", "Loading...")
                        logger.info(msg)
                        if progress_callback:
                            progress_callback(msg)
                    elif status == "ready":
                        self.device = data.get("device", "cpu")
                        logger.info(f"CLIP worker ready on {self.device}")
                        self._worker_ready = True
                        return True
                    elif status == "fatal":
                        error_msg = data.get('error', 'Unknown error')
                        traceback_info = data.get('traceback', '')
                        logger.error(f"Worker fatal error: {error_msg}\n{traceback_info}")
                        return False
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from worker: {line}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to start worker: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def _stop_worker(self):
        """ワーカープロセスを停止"""
        if self._worker_process is not None:
            try:
                self._worker_process.stdin.write("QUIT\n")
                self._worker_process.stdin.flush()
                self._worker_process.wait(timeout=5)
            except Exception:
                self._worker_process.kill()
            finally:
                self._worker_process = None
                self._worker_ready = False
        
    def load_model(self, progress_callback=None):
        """モデルを読み込む"""
        if self._use_subprocess:
            return self._start_worker(progress_callback)
        
        # 通常版（直接インポート）
        if self.model is not None: 
            return True
        
        if not is_ai_installed():
            logger.error("CLIP dependencies are not installed.")
            return False
            
        try:
            if progress_callback: 
                progress_callback("AIモデルを読み込み中...")
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
        """画像から特徴ベクトルを抽出"""
        if self._use_subprocess:
            return self._get_embedding_via_worker(image_path)
        else:
            return self._get_embedding_direct(image_path)
    
    def _get_embedding_via_worker(self, image_path: Path) -> Optional[np.ndarray]:
        """ワーカープロセス経由で特徴抽出"""
        import json
        import base64
        
        if not self._worker_ready:
            if not self._start_worker():
                return None
        
        try:
            # 画像パスをワーカーに送信
            self._worker_process.stdin.write(f"{image_path}\n")
            self._worker_process.stdin.flush()
            
            # 結果を受信
            line = self._worker_process.stdout.readline()
            if not line:
                logger.error("Worker returned empty response")
                self._worker_ready = False
                return None
            
            data = json.loads(line.strip())
            
            if data.get("status") == "ok":
                embedding_b64 = data["embedding"]
                embedding_bytes = base64.b64decode(embedding_b64)
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                return embedding
            else:
                logger.error(f"Worker error: {data.get('error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error communicating with worker: {e}")
            self._worker_ready = False
            return None
    
    def _get_embedding_direct(self, image_path: Path) -> Optional[np.ndarray]:
        """直接インポートで特徴抽出（通常Python環境用）"""
        if not self.load_model(): 
            return None
        import torch
        from PIL import Image
        try:
            image = Image.open(image_path).convert("RGB")
            inputs = self.processor(images=image, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.model.get_image_features(**inputs)
            embedding = outputs.cpu().numpy()[0]
            norm = np.linalg.norm(embedding)
            if norm > 1e-6: 
                embedding = embedding / norm
            return embedding
        except Exception as e:
            logger.error(f"Error extracting features: {e}")
            return None
    
    def __del__(self):
        """デストラクタ: ワーカーを停止"""
        self._stop_worker()
    
    def extract_embedding(self, image_path: Path) -> Optional[np.ndarray]:
        """画像から特徴ベクトルを抽出（get_embeddingのエイリアス）"""
        return self.get_embedding(image_path)
    
    def extract_embeddings_batch(
        self, 
        image_paths: List[Path], 
        batch_size: int = 32
    ) -> List[Optional[np.ndarray]]:
        """複数画像から特徴ベクトルをバッチ抽出
        
        Args:
            image_paths: 画像パスのリスト
            batch_size: バッチサイズ（ワーカー版では無視）
        
        Returns:
            各画像の埋め込みベクトルのリスト（失敗した場合はNone）
        """
        results = []
        for path in image_paths:
            embedding = self.get_embedding(path)
            results.append(embedding)
        return results
