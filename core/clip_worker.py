# -*- coding: utf-8 -*-
"""
SpectraMatch - CLIP Worker Script
PyInstallerビルド版から呼び出される外部ワーカースクリプト。
システムPythonで実行され、CLIPモデルを使った特徴抽出を行う。
"""

import sys
import json
import base64
from pathlib import Path

# AIライブラリのパスを追加
AI_ENV_PATH = Path.home() / ".spectramatch" / "ai_libs"
sys.path.insert(0, str(AI_ENV_PATH))

def main():
    """メイン処理: stdinから画像パスを受け取り、特徴ベクトルを返す"""
    import os
    
    # 環境情報をログ出力（デバッグ用）
    print(json.dumps({
        "status": "loading", 
        "message": "Initializing worker...",
        "python_version": sys.version,
        "cwd": os.getcwd()
    }), flush=True)
    
    try:
        import numpy as np
        print(json.dumps({"status": "loading", "message": "numpy loaded"}), flush=True)
    except ImportError as e:
        print(json.dumps({"status": "fatal", "error": f"Failed to import numpy: {e}"}), flush=True)
        return
    
    try:
        import torch
        print(json.dumps({
            "status": "loading", 
            "message": f"torch loaded (version: {torch.__version__})"
        }), flush=True)
    except ImportError as e:
        print(json.dumps({"status": "fatal", "error": f"Failed to import torch: {e}"}), flush=True)
        return
    
    try:
        from PIL import Image
        print(json.dumps({"status": "loading", "message": "PIL loaded"}), flush=True)
    except ImportError as e:
        print(json.dumps({"status": "fatal", "error": f"Failed to import PIL: {e}"}), flush=True)
        return
    
    try:
        from transformers import CLIPProcessor, CLIPModel
        print(json.dumps({"status": "loading", "message": "transformers loaded"}), flush=True)
    except ImportError as e:
        print(json.dumps({"status": "fatal", "error": f"Failed to import transformers: {e}"}), flush=True)
        return
    
    model_name = "openai/clip-vit-base-patch32"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    print(json.dumps({
        "status": "loading", 
        "message": f"Loading CLIP model on {device}..."
    }), flush=True)
    
    try:
        model = CLIPModel.from_pretrained(model_name).to(device)
        print(json.dumps({"status": "loading", "message": "CLIP model loaded, loading processor..."}), flush=True)
        
        processor = CLIPProcessor.from_pretrained(model_name)
        print(json.dumps({"status": "ready", "device": device}), flush=True)
    except Exception as e:
        import traceback
        print(json.dumps({
            "status": "fatal", 
            "error": f"Failed to load CLIP model: {e}",
            "traceback": traceback.format_exc()
        }), flush=True)
        return
    
    # stdinから画像パスを1行ずつ受け取って処理
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        if line == "QUIT":
            break
        
        try:
            image_path = Path(line)
            if not image_path.exists():
                result = {"status": "error", "path": line, "error": "File not found"}
                print(json.dumps(result), flush=True)
                continue
            
            image = Image.open(image_path).convert("RGB")
            inputs = processor(images=image, return_tensors="pt").to(device)
            
            with torch.no_grad():
                outputs = model.get_image_features(**inputs)
            
            embedding = outputs.cpu().numpy()[0]
            norm = np.linalg.norm(embedding)
            if norm > 1e-6:
                embedding = embedding / norm
            
            # numpy配列をbase64でエンコード
            embedding_bytes = embedding.astype(np.float32).tobytes()
            embedding_b64 = base64.b64encode(embedding_bytes).decode('ascii')
            
            result = {
                "status": "ok", 
                "path": line,
                "embedding": embedding_b64, 
                "shape": list(embedding.shape)
            }
            print(json.dumps(result), flush=True)
            
        except Exception as e:
            import traceback
            result = {
                "status": "error", 
                "path": line,
                "error": str(e), 
                "traceback": traceback.format_exc()
            }
            print(json.dumps(result), flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        result = {"status": "fatal", "error": str(e), "traceback": traceback.format_exc()}
        print(json.dumps(result), flush=True)
        sys.exit(1)
