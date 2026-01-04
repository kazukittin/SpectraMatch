
import sys
import os
from pathlib import Path
import importlib
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug_import")

AI_ENV_PATH = Path.home() / ".spectramatch" / "ai_libs"
print(f"Checking AI_ENV_PATH: {AI_ENV_PATH}")
print(f"Exists: {AI_ENV_PATH.exists()}")

if AI_ENV_PATH.exists():
    print(f"Contents of AI_ENV_PATH: {os.listdir(AI_ENV_PATH)}")

if str(AI_ENV_PATH) not in sys.path:
    sys.path.insert(0, str(AI_ENV_PATH))

if os.name == 'nt' and AI_ENV_PATH.exists():
    dll_dirs = [
        str(AI_ENV_PATH),
        str(AI_ENV_PATH / "torch" / "lib"),
        str(AI_ENV_PATH / "PIL"),
        str(AI_ENV_PATH / "numpy" / "core"),
        str(AI_ENV_PATH / "numpy" / ".libs"),
    ]
    for d in dll_dirs:
        if os.path.isdir(d):
            print(f"Adding DLL directory: {d}")
            try:
                os.add_dll_directory(d)
            except Exception as e:
                print(f"Failed to add DLL dir {d}: {e}")

importlib.invalidate_caches()

def try_import(name):
    print(f"\n--- Trying to import {name} ---")
    try:
        mod = importlib.import_module(name)
        print(f"Successfully imported {name}")
        print(f"File: {getattr(mod, '__file__', 'No __file__')}")
        print(f"Version: {getattr(mod, '__version__', 'No __version__')}")
        return mod
    except Exception as e:
        print(f"Failed to import {name}: {e}")
        import traceback
        traceback.print_exc()
        return None

try_import("numpy")
try_import("torch")
try_import("transformers")
try_import("PIL.Image")
