# -*- coding: utf-8 -*-
"""
SpectraMatch - 画像類似検出・削除ソフトウェア

DCT（離散コサイン変換）ベースのPerceptual Hashを用いた
ロバストな類似画像検知システム。

使用方法:
    python main.py
"""

import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from gui.main_window import MainWindow


def setup_logging(debug: bool = False):
    """ロギングの設定"""
    log_dir = Path.home() / ".spectramatch"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_file), encoding="utf-8")
        ]
    )
    return log_file


def main():
    """アプリケーションのエントリーポイント"""
    # デバッグモードの確認
    debug_mode = "--debug" in sys.argv or "-d" in sys.argv
    setup_logging(debug=debug_mode)
    logger = logging.getLogger(__name__)
    logger.info("SpectraMatch を起動しています...")
    if debug_mode:
        logger.info("デバッグモード有効")
    
    # High DPI対応
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # アプリケーション作成
    app = QApplication(sys.argv)
    app.setApplicationName("SpectraMatch")
    app.setApplicationVersion("1.0.0")
    
    # Fusionスタイル適用 (ダークテーマと相性が良い)
    app.setStyle("Fusion")
    
    # メインウィンドウ表示
    window = MainWindow()
    window.show()
    
    logger.info("SpectraMatch の起動が完了しました")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
