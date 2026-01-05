# -*- coding: utf-8 -*-
"""
SpectraMatch - Preview Panel
選択した画像のプレビューを表示するパネル (画像のみ)
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QSizePolicy
)
from PySide6.QtGui import QPixmap

logger = logging.getLogger(__name__)


class PreviewPanel(QWidget):
    """
    画像プレビューパネル
    
    選択された画像の大きなプレビューを表示（情報は表示しない）
    """
    
    # 互換性のために残すが、UIからは発火しない
    mark_for_deletion = Signal(Path)
    unmark_for_deletion = Signal(Path)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_image_path: Optional[Path] = None
        self.is_marked_for_deletion = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        """UIを構築"""
        # 幅制限は解除または調整
        self.setMinimumWidth(320)
        self.setStyleSheet("""
            QWidget {
                background-color: #252525;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # プレビュー画像エリア
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                color: #666;
                font-size: 14px;
            }
        """)
        self.preview_label.setText("画像を選択してください")
        
        layout.addWidget(self.preview_label)
        
        # アスペクト比を保って拡大縮小するために、resizeEventでの制御が必要かもしれないが、
        # QLabelのsetScaledContents(False)とpixmap.scaledで対応する
    
    def show_image(self, image_path: Path, info: dict = None):
        """画像をプレビュー表示"""
        self.current_image_path = image_path
        
        if not image_path.exists():
            self.preview_label.setText("画像が見つかりません")
            return
        
        try:
            pixmap = QPixmap(str(image_path))
            if pixmap.isNull():
                self.preview_label.setText("読み込みエラー")
                return
            
            self._update_preview(pixmap)
            
        except Exception as e:
            logger.error(f"Preview error: {e}")
            self.preview_label.setText("読み込みエラー")
    
    def _update_preview(self, pixmap: QPixmap):
        """プレビュー画像の更新（サイズ調整含む）"""
        if pixmap.isNull():
            return
            
        # プレビューエリアに合わせてスケール
        size = self.size()
        # マージンを考慮
        w = size.width() - 4
        h = size.height() - 4
        
        if w <= 0 or h <= 0:
            return
            
        scaled_pixmap = pixmap.scaled(
            w, h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.preview_label.setPixmap(scaled_pixmap)
    
    def resizeEvent(self, event):
        """リサイズ時に画像を再描画"""
        if self.current_image_path and self.current_image_path.exists():
            pixmap = QPixmap(str(self.current_image_path))
            if not pixmap.isNull():
                self._update_preview(pixmap)
        super().resizeEvent(event)
    
    def clear_preview(self):
        """プレビューをクリア"""
        self.current_image_path = None
        self.preview_label.clear()
        self.preview_label.setText("画像を選択してください")
    
    # 以下、インターフェース互換性のためのダミーメソッド
    def set_marked_for_deletion(self, is_marked: bool):
        pass
