# -*- coding: utf-8 -*-
"""
PyInstaller Runtime Hook for PyTorch
"""

import sys
import os

# torch._dynamo を完全に無効化
os.environ["TORCH_DYNAMO_DISABLE"] = "1"
os.environ["TORCHDYNAMO_DISABLE"] = "1"

# numpy 関連の競合を避ける設定
os.environ["NUMPY_MADVISE_HUGEPAGE"] = "0"

def _patch_torch_numpy():
    """
    torch._numpy._ufuncs.py の NameError を回避するためのパッチ
    このエラーは PyInstaller でパッケージ化した際に発生する PyTorch 2.x のバグです
    """
    try:
        import types
        
        # すでにインポートされている場合はスキップ
        if 'torch._numpy' in sys.modules:
            return

        # ダミーのモジュール構成を作成
        # transformers が必要とする最小限の構造を維持しつつ、エラーの出る箇所をバイパス
        mod_name = 'torch._numpy'
        m = types.ModuleType(mod_name)
        sys.modules[mod_name] = m
        
        # サブモジュールもダミー化
        for sub in ['_dtypes', '_dtypes_impl', '_funcs', '_ufuncs', '_util', '_ndarray']:
            full_sub = f"{mod_name}.{sub}"
            sm = types.ModuleType(full_sub)
            sys.modules[full_sub] = sm
            setattr(m, sub, sm)
            
        print("PyTorch compatibility patch applied")
    except Exception as e:
        print(f"Failed to apply patch: {e}")

# フックを実行
_patch_torch_numpy()
