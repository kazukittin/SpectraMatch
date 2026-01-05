# -*- coding: utf-8 -*-
"""
SpectraMatch - Settings Dialog
設定ダイアログ（モーダル）
"""

import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QListWidget, QListWidgetItem, QFileDialog,
    QFrame, QMessageBox, QGroupBox, QWidget, QTabWidget
)

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """
    設定ダイアログ
    
    - スキャン対象フォルダの管理
    - 類似度閾値の設定
    - キャッシュ管理
    """
    
    # 設定が適用されたときに発行するシグナル
    settings_applied = Signal(list, int)  # (folders, threshold)
    cache_cleared = Signal()
    
    def __init__(
        self, 
        parent=None, 
        current_folders: List[Path] = None,
        current_threshold: int = 85,
        db=None
    ):
        super().__init__(parent)
        self.current_folders = list(current_folders) if current_folders else []
        self.current_threshold = current_threshold
        self.db = db
        
        self._setup_ui()
        self._load_current_settings()
    
    def _setup_ui(self):
        """UIを構築"""
        self.setWindowTitle("設定")
        self.setMinimumSize(500, 500)
        self.setModal(True)
        
        # ダークテーマスタイル
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #4a4a4a;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
                background-color: #323232;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #00ffff;
            }
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3a3a3a;
            }
            QListWidget::item:selected {
                background-color: #00ffff;
                color: #1e1e1e;
            }
            QListWidget::item:hover {
                background-color: #3a3a3a;
            }
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
            QSlider::groove:horizontal {
                background: #4a4a4a;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00ffff;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::sub-page:horizontal {
                background: #00ffff;
                border-radius: 4px;
            }
            QLabel {
                color: #e0e0e0;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # タイトル
        title = QLabel("⚙️ 設定")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #00ffff;")
        layout.addWidget(title)
        
        # === スキャン対象フォルダ ===
        folder_group = QGroupBox("📁 スキャン対象フォルダ")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(12)
        
        # フォルダリスト
        self.folder_list = QListWidget()
        self.folder_list.setMinimumHeight(150)
        folder_layout.addWidget(self.folder_list)
        
        # フォルダ操作ボタン
        folder_btn_layout = QHBoxLayout()
        folder_btn_layout.setSpacing(8)
        
        self.add_folder_btn = QPushButton("➕ フォルダを追加")
        self.add_folder_btn.setStyleSheet(
            "background-color: #27ae60; color: white;"
        )
        self.add_folder_btn.clicked.connect(self._on_add_folder)
        folder_btn_layout.addWidget(self.add_folder_btn)
        
        self.remove_folder_btn = QPushButton("➖ 選択を削除")
        self.remove_folder_btn.setStyleSheet(
            "background-color: #e74c3c; color: white;"
        )
        self.remove_folder_btn.clicked.connect(self._on_remove_folder)
        folder_btn_layout.addWidget(self.remove_folder_btn)
        
        folder_btn_layout.addStretch()
        folder_layout.addLayout(folder_btn_layout)
        
        layout.addWidget(folder_group)
        
        # === 類似度閾値 ===
        threshold_group = QGroupBox("🎚️ 類似度閾値")
        threshold_layout = QVBoxLayout(threshold_group)
        threshold_layout.setSpacing(12)
        
        # 説明
        threshold_desc = QLabel(
            "類似度がこの値以上の画像ペアを「類似」として検出します。\n"
            "値を下げると検出数が増え、上げると厳密になります。"
        )
        threshold_desc.setStyleSheet("color: #95a5a6; font-size: 11px;")
        threshold_desc.setWordWrap(True)
        threshold_layout.addWidget(threshold_desc)
        
        # スライダーと値表示
        slider_layout = QHBoxLayout()
        slider_layout.setSpacing(16)
        
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(50, 99)
        self.threshold_slider.setValue(85)
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.setTickInterval(10)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        slider_layout.addWidget(self.threshold_slider)
        
        self.threshold_value_label = QLabel("85%")
        self.threshold_value_label.setFixedWidth(60)
        self.threshold_value_label.setAlignment(Qt.AlignCenter)
        self.threshold_value_label.setStyleSheet(
            "background-color: #00ffff; color: #1e1e1e; "
            "font-weight: bold; border-radius: 4px; padding: 8px; font-size: 14px;"
        )
        slider_layout.addWidget(self.threshold_value_label)
        
        threshold_layout.addLayout(slider_layout)
        
        # 閾値の目安
        self.threshold_hint = QLabel("標準 (85%以上を類似とみなす)")
        self.threshold_hint.setStyleSheet("color: #f39c12; font-size: 12px;")
        threshold_layout.addWidget(self.threshold_hint)
        
        layout.addWidget(threshold_group)
        
        # === キャッシュ管理 ===
        cache_group = QGroupBox("🗄️ キャッシュ管理")
        cache_layout = QVBoxLayout(cache_group)
        cache_layout.setSpacing(12)
        
        # キャッシュ説明
        cache_desc = QLabel(
            "スキャン済みの画像情報はキャッシュに保存され、\n"
            "再スキャン時に高速化されます。"
        )
        cache_desc.setStyleSheet("color: #95a5a6; font-size: 11px;")
        cache_layout.addWidget(cache_desc)
        
        # キャッシュ情報
        self.cache_info_label = QLabel("キャッシュ: 計算中...")
        self.cache_info_label.setStyleSheet("color: #3498db;")
        cache_layout.addWidget(self.cache_info_label)
        
        # キャッシュ削除ボタン
        self.clear_cache_btn = QPushButton("🗑️ キャッシュを削除")
        self.clear_cache_btn.setStyleSheet(
            "background-color: #c0392b; color: white; "
            "font-weight: bold; padding: 12px;"
        )
        self.clear_cache_btn.setToolTip(
            "データベースに保存された画像情報を削除します\n"
            "次回スキャン時に全ファイルを再解析します"
        )
        self.clear_cache_btn.clicked.connect(self._on_clear_cache)
        cache_layout.addWidget(self.clear_cache_btn)
        
        layout.addWidget(cache_group)
        
        # スペーサー
        layout.addStretch()
        
        # === ボタン ===
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        self.apply_btn = QPushButton("適用")
        self.apply_btn.setMinimumWidth(100)
        self.apply_btn.setStyleSheet(
            "background-color: #00ffff; color: #1e1e1e; font-weight: bold;"
        )
        self.apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.apply_btn)
        
        layout.addLayout(btn_layout)
        
        # キャッシュ情報を更新
        self._update_cache_info()
    
    def _load_current_settings(self):
        """現在の設定を読み込む"""
        # フォルダリスト
        self.folder_list.clear()
        for folder in self.current_folders:
            item = QListWidgetItem(str(folder))
            item.setToolTip(str(folder))
            item.setData(Qt.UserRole, folder)
            self.folder_list.addItem(item)
        
        # 閾値
        self.threshold_slider.setValue(self.current_threshold)
        self._on_threshold_changed(self.current_threshold)
    
    def _update_cache_info(self):
        """キャッシュ情報を更新"""
        if self.db:
            try:
                count = self.db.count_images()
                self.cache_info_label.setText(f"キャッシュ: {count}枚の画像情報を保存中")
            except Exception as e:
                self.cache_info_label.setText("キャッシュ: 情報取得失敗")
        else:
            self.cache_info_label.setText("キャッシュ: 利用不可")
    
    def _on_add_folder(self):
        """フォルダ追加"""
        folder = QFileDialog.getExistingDirectory(self, "スキャン対象フォルダを選択")
        if folder:
            path = Path(folder)
            # 重複チェック
            existing_paths = [
                self.folder_list.item(i).data(Qt.UserRole) 
                for i in range(self.folder_list.count())
            ]
            if path not in existing_paths:
                item = QListWidgetItem(str(path))
                item.setToolTip(str(path))
                item.setData(Qt.UserRole, path)
                self.folder_list.addItem(item)
    
    def _on_remove_folder(self):
        """選択フォルダ削除"""
        current = self.folder_list.currentItem()
        if current:
            self.folder_list.takeItem(self.folder_list.row(current))
    
    def _on_threshold_changed(self, value: int):
        """閾値変更"""
        self.threshold_value_label.setText(f"{value}%")
        
        if value >= 95:
            hint = "厳密 (ほぼ同一画像のみ)"
            color = "#e74c3c"
        elif value >= 90:
            hint = "やや厳密 (高い類似度)"
            color = "#e67e22"
        elif value >= 80:
            hint = "標準 (同一画像の異なるバージョン)"
            color = "#f39c12"
        elif value >= 70:
            hint = "緩い (類似した構図)"
            color = "#27ae60"
        else:
            hint = "非常に緩い (要注意: 誤検出が増える可能性)"
            color = "#9b59b6"
        
        self.threshold_hint.setText(hint)
        self.threshold_hint.setStyleSheet(f"color: {color}; font-size: 12px;")
    
    def _on_clear_cache(self):
        """キャッシュ削除"""
        if not self.db:
            return
        
        reply = QMessageBox.question(
            self, "キャッシュ削除の確認",
            "保存されている全ての画像情報を削除します。\n"
            "次回スキャン時に全ファイルを再解析する必要があります。\n\n"
            "続行しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.db.clear_all()
                self.db.vacuum()
                self._update_cache_info()
                self.cache_cleared.emit()
                QMessageBox.information(
                    self, "完了", 
                    "キャッシュを削除しました。"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "エラー", 
                    f"キャッシュの削除に失敗しました:\n{e}"
                )
    
    def _on_apply(self):
        """設定を適用"""
        # フォルダリストを取得
        folders = []
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            folders.append(item.data(Qt.UserRole))
        
        # 閾値を取得
        threshold = self.threshold_slider.value()
        
        # シグナル発行
        self.settings_applied.emit(folders, threshold)
        
        # ダイアログを閉じる
        self.accept()
    
    def get_folders(self) -> List[Path]:
        """現在のフォルダリストを取得"""
        folders = []
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            folders.append(item.data(Qt.UserRole))
        return folders
    
    def get_threshold(self) -> int:
        """現在の閾値を取得"""
        return self.threshold_slider.value()
