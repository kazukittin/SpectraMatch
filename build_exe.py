# -*- coding: utf-8 -*-
"""
SpectraMatch - EXE Build Script

使用方法:
    python build_exe.py

このスクリプトはPyInstallerを使用してSpectraMatchをexeにビルドします。
"""

import subprocess
import sys
from pathlib import Path


def main():
    """メインビルド関数"""
    print("=" * 60)
    print("SpectraMatch EXE Builder")
    print("=" * 60)
    
    # プロジェクトルート
    project_root = Path(__file__).parent
    main_script = project_root / "main.py"
    icon_path = project_root / "icon" / "icon.png"
    
    # PyInstallerコマンドを構築
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=SpectraMatch",
        "--windowed",  # GUIアプリなのでコンソールを非表示
        "--noconfirm",  # 既存のビルドを上書き
        
        # アイコン設定（存在する場合）
        f"--icon={icon_path}" if icon_path.exists() else "",
        
        # データファイルを追加
        f"--add-data={project_root / 'icon'};icon",
        
        # 隠しインポート（自動検出されないモジュール）
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui", 
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=scipy",
        "--hidden-import=scipy.spatial",
        "--hidden-import=scipy.spatial.distance",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=torch",
        "--hidden-import=torch._dynamo",
        "--hidden-import=torch._numpy",
        "--hidden-import=torch._numpy._ufuncs",
        "--hidden-import=torch._numpy._ndarray",
        "--hidden-import=torch._numpy._dtypes",
        "--hidden-import=torch._numpy._dtypes_impl",
        "--hidden-import=torch._numpy._funcs",
        "--hidden-import=torch._numpy._util",
        "--hidden-import=torch.compiler",
        "--hidden-import=transformers",
        "--hidden-import=transformers.models.clip",
        "--hidden-import=transformers.models.clip.processing_clip",
        "--hidden-import=transformers.processing_utils",
        "--hidden-import=transformers.modeling_utils",
        "--hidden-import=transformers.integrations",
        "--hidden-import=faiss",
        "--hidden-import=send2trash",
        
        # ローカルモジュール
        "--hidden-import=core",
        "--hidden-import=core.comparator",
        "--hidden-import=core.hash_generator",
        "--hidden-import=core.scanner",
        "--hidden-import=gui",
        "--hidden-import=gui.main_window",
        "--hidden-import=gui.image_grid",
        "--hidden-import=gui.styles",
        
        # 不要なモジュールを除外
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        "--exclude-module=IPython",
        "--exclude-module=jupyter",
        "--exclude-module=pytest",
        
        # データ収集
        "--collect-data=transformers",
        "--collect-submodules=transformers",
        "--collect-submodules=torch._numpy",
        "--collect-submodules=torch._dynamo",
        "--collect-submodules=torch.compiler",
        
        # メインスクリプト
        str(main_script),
    ]
    
    # 空の引数を除去
    cmd = [arg for arg in cmd if arg]
    
    print("\n実行コマンド:")
    print(" ".join(cmd[:5]) + " ...")
    print("\nビルドを開始します...\n")
    
    # ビルド実行
    try:
        result = subprocess.run(cmd, cwd=str(project_root), check=True)
        print("\n" + "=" * 60)
        print("✅ ビルド完了!")
        print(f"   出力先: {project_root / 'dist' / 'SpectraMatch'}")
        print("=" * 60)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ ビルド失敗: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
