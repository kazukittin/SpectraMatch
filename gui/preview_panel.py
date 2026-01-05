# -*- coding: utf-8 -*-
"""
SpectraMatch - Preview Panel
選択した画像のプレビューと詳細情報を表示するパネル
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy
)
from PySide6.QtGui import QPixmap, QImage

logger = logging.getLogger(__name__)


class PreviewPanel(QWidget):
    """
    画像プレビューパネル
    
    選択された画像の大きなプレビューと詳細情報を表示
    """
    
    # 画像が削除対象としてマークされたときに発行
    mark_for_deletion = Signal(Path)
    unmark_for_deletion = Signal(Path)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_image_path: Optional[Path] = None
        self.is_marked_for_deletion = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        """UIを構築"""
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)
        self.setStyleSheet("""
            QWidget {
                background-color: #252525;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # ヘッダー
        header = QLabel("📷 プレビュー")
        header.setStyleSheet("""
            color: #00ffff;
            font-size: 14px;
            font-weight: bold;
            padding: 8px 0;
        """)
        layout.addWidget(header)
        
        # 区切り線
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #4a4a4a;")
        layout.addWidget(sep)
        
        # プレビュー画像エリア
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("""
            background-color: #1a1a1a;
            border: 1px solid #3a3a3a;
            border-radius: 8px;
        """)
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(250)
        self.preview_label.setStyleSheet("background-color: transparent;")
        self.preview_label.setText("画像を選択してください")
        self.preview_label.setStyleSheet("""
            color: #666;
            font-size: 12px;
            background-color: transparent;
        """)
        preview_layout.addWidget(self.preview_label)
        
        layout.addWidget(self.preview_container)
        
        # ファイル情報エリア
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 8px;
            }
            QLabel {
                background-color: transparent;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(6)
        
        # ファイル名
        self.filename_label = QLabel("ファイル名: -")
        self.filename_label.setWordWrap(True)
        self.filename_label.setStyleSheet("color: #e0e0e0; font-weight: bold;")
        info_layout.addWidget(self.filename_label)
        
        # 解像度
        self.resolution_label = QLabel("解像度: -")
        self.resolution_label.setStyleSheet("color: #95a5a6;")
        info_layout.addWidget(self.resolution_label)
        
        # ファイルサイズ
        self.filesize_label = QLabel("サイズ: -")
        self.filesize_label.setStyleSheet("color: #95a5a6;")
        info_layout.addWidget(self.filesize_label)
        
        # 鮮明度スコア
        self.sharpness_label = QLabel("鮮明度: -")
        self.sharpness_label.setStyleSheet("color: #95a5a6;")
        info_layout.addWidget(self.sharpness_label)
        
        # パス
        self.path_label = QLabel("パス: -")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #666; font-size: 10px;")
        info_layout.addWidget(self.path_label)
        
        layout.addWidget(info_frame)
        
        # 削除ステータス表示
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            color: #2ecc71;
            font-weight: bold;
            font-size: 12px;
            padding: 8px;
        """)
        layout.addWidget(self.status_label)
        
        # アクションボタン
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.toggle_delete_btn = QPushButton("🗑️ 削除対象にする")
        self.toggle_delete_btn.setMinimumHeight(40)
        self.toggle_delete_btn.setEnabled(False)
        self.toggle_delete_btn.clicked.connect(self._on_toggle_delete)
        self.toggle_delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                border: 2px solid transparent;
            }
            QPushButton:hover {
                background-color: #e74c3c;
                border: 2px solid #c0392b;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #555;
            }
        """)
        btn_layout.addWidget(self.toggle_delete_btn)
        
        layout.addLayout(btn_layout)
        
        layout.addStretch()
        
        # 「画像なし」状態を表示
        self.clear_preview()
    
    def show_image(self, image_path: Path, info: dict = None):
        """
        画像をプレビュー表示
        
        Args:
            image_path: 画像のパス
            info: 画像情報の辞書 (width, height, file_size, sharpness_score, is_marked)
        """
        self.current_image_path = image_path
        
        if not image_path.exists():
            self.preview_label.setText("画像が見つかりません")
            return
        
        # 画像を読み込んでプレビュー表示
        try:
            pixmap = QPixmap(str(image_path))
            if pixmap.isNull():
                self.preview_label.setText("読み込みエラー")
                return
            
            # プレビューサイズに合わせてスケール
            preview_size = self.preview_label.size()
            scaled_pixmap = pixmap.scaled(
                preview_size.width() - 16,
                250,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled_pixmap)
            self.preview_label.setStyleSheet("background-color: transparent;")
            
        except Exception as e:
            logger.error(f"Preview error: {e}")
            self.preview_label.setText("読み込みエラー")
            return
        
        # ファイル情報を更新
        self.filename_label.setText(f"📄 {image_path.name}")
        
        if info:
            width = info.get('width', 0)
            height = info.get('height', 0)
            file_size = info.get('file_size', 0)
            sharpness = info.get('sharpness_score', 0)
            self.is_marked_for_deletion = info.get('is_marked', False)
            
            self.resolution_label.setText(f"📐 解像度: {width} × {height}")
            self.filesize_label.setText(f"💾 サイズ: {self._format_size(file_size)}")
            self.sharpness_label.setText(f"✨ 鮮明度: {sharpness:.1f}")
        else:
            # ファイルから直接情報を取得
            try:
                stat = image_path.stat()
                self.filesize_label.setText(f"💾 サイズ: {self._format_size(stat.st_size)}")
                
                # 画像サイズ
                pixmap = QPixmap(str(image_path))
                self.resolution_label.setText(f"📐 解像度: {pixmap.width()} × {pixmap.height()}")
            except Exception:
                pass
            
            self.sharpness_label.setText("✨ 鮮明度: -")
            self.is_marked_for_deletion = False
        
        self.path_label.setText(f"📁 {str(image_path.parent)}")
        
        # ボタンを有効化
        self.toggle_delete_btn.setEnabled(True)
        self._update_delete_button_style()
    
    def clear_preview(self):
        """プレビューをクリア"""
        self.current_image_path = None
        self.is_marked_for_deletion = False
        
        self.preview_label.clear()
        self.preview_label.setText("画像を選択してください")
        self.preview_label.setStyleSheet("""
            color: #666;
            font-size: 12px;
            background-color: transparent;
        """)
        
        self.filename_label.setText("📄 ファイル名: -")
        self.resolution_label.setText("📐 解像度: -")
        self.filesize_label.setText("💾 サイズ: -")
        self.sharpness_label.setText("✨ 鮮明度: -")
        self.path_label.setText("📁 パス: -")
        self.status_label.setText("")
        
        self.toggle_delete_btn.setEnabled(False)
        self._update_delete_button_style()
    
    def set_marked_for_deletion(self, is_marked: bool):
        """削除マーク状態を設定"""
        self.is_marked_for_deletion = is_marked
        self._update_delete_button_style()
    
    def _update_delete_button_style(self):
        """削除ボタンのスタイルを更新"""
        if self.is_marked_for_deletion:
            self.toggle_delete_btn.setText("✓ 削除対象から外す")
            self.toggle_delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    font-weight: bold;
                    padding: 8px 16px;
                    border-radius: 4px;
                    border: 2px solid #c0392b;
                }
                QPushButton:hover {
                    background-color: #27ae60;
                    border: 2px solid #2ecc71;
                }
                QPushButton:disabled {
                    background-color: #2a2a2a;
                    color: #555;
                }
            """)
            self.status_label.setText("🗑️ 削除対象")
            self.status_label.setStyleSheet("""
                color: #e74c3c;
                font-weight: bold;
                font-size: 12px;
                padding: 8px;
                background-color: rgba(231, 76, 60, 0.1);
                border-radius: 4px;
            """)
        else:
            self.toggle_delete_btn.setText("🗑️ 削除対象にする")
            self.toggle_delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4a4a4a;
                    color: white;
                    font-weight: bold;
                    padding: 8px 16px;
                    border-radius: 4px;
                    border: 2px solid transparent;
                }
                QPushButton:hover {
                    background-color: #e74c3c;
                    border: 2px solid #c0392b;
                }
                QPushButton:disabled {
                    background-color: #2a2a2a;
                    color: #555;
                }
            """)
            if self.current_image_path:
                self.status_label.setText("✅ 保持")
                self.status_label.setStyleSheet("""
                    color: #2ecc71;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 8px;
                    background-color: rgba(46, 204, 113, 0.1);
                    border-radius: 4px;
                """)
            else:
                self.status_label.setText("")
    
    def _on_toggle_delete(self):
        """削除マークをトグル"""
        if not self.current_image_path:
            return
        
        self.is_marked_for_deletion = not self.is_marked_for_deletion
        self._update_delete_button_style()
        
        if self.is_marked_for_deletion:
            self.mark_for_deletion.emit(self.current_image_path)
        else:
            self.unmark_for_deletion.emit(self.current_image_path)
    
    def _format_size(self, size_bytes: int) -> str:
        """ファイルサイズを読みやすい形式に変換"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
