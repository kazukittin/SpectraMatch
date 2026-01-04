# -*- coding: utf-8 -*-
"""
SpectraMatch - EXE ビルドスクリプト (Specファイル使用版)
"""

import subprocess
import sys
from pathlib import Path

def main():
    """メインビルド関数"""
    print("=" * 60)
    print("SpectraMatch EXE Builder (via Spec file)")
    print("=" * 60)
    
    project_root = Path(__file__).parent
    spec_file = project_root / "SpectraMatch.spec"
    
    # コマンドの構築
    # すべての設定は SpectraMatch.spec に記述されているため、specファイルを指定するだけ
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_file)
    ]
    
    print(f"\nビルドを開始します（これには数分かかります）...\n")
    
    try:
        subprocess.run(cmd, cwd=str(project_root), check=True)
        print("\n" + "=" * 60)
        print("✅ ビルド完了!")
        print(f"   出力先: {project_root / 'dist' / 'SpectraMatch'}")
        print("=" * 60)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ ビルド失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
