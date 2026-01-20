# -*- coding: utf-8 -*-
"""
SpectraMatch - Converter Dialog
画像変換・削除ツール（バッチファイル機能の移植）
"""

import gc
import logging
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Signal, QThread, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFileDialog, QMessageBox, QListWidget, 
    QGroupBox, QPlainTextEdit, QLineEdit, QSpinBox, QTabWidget,
    QWidget
)

from core.image_converter import ImageConverter

logger = logging.getLogger(__name__)




class CombinedThread(QThread):
    """変換とリネームを一括で行うスレッド"""
    progress_updated = Signal(int, int, str)
    finished = Signal(int, int, list)  # success, fail, errors
    
    def __init__(self, folder_path: Path, digits: int = 3):
        super().__init__()
        self.folder_path = folder_path
        self.digits = digits
        self.is_running = True
        
    def run(self):
        total_success = 0
        total_fail = 0
        all_errors = []
        
        # 1. JPG変換処理
        # 連番リネーム済みのファイル (NNN.jpg) はスキップ
        # 連番だがJPGでないファイル (NNN.png) は変換対象
        
        target_files = ImageConverter.get_target_files(self.folder_path)
        total = len(target_files)
        
        # 連番チェック用関数
        def is_already_processed(path: Path) -> bool:
            # NNN.jpg 形式かどうか
            if path.suffix.lower() not in ['.jpg', '.jpeg']:
                return False
            stem = path.stem
            import re
            return bool(re.match(rf'^\d{{{self.digits}}}$', stem))
            
        filtered_targets = []
        for p in target_files:
            if is_already_processed(p):
                continue
            filtered_targets.append(p)
            
        # 変換実行
        for i, file_path in enumerate(filtered_targets):
            if not self.is_running:
                break
                
            msg = f"Converting ({i+1}/{len(filtered_targets)}): {file_path.name}"
            self.progress_updated.emit(i, len(filtered_targets), msg)
            
            success, error = ImageConverter.convert_to_jpg(file_path)
            
            if success:
                total_success += 1
            else:
                total_fail += 1
                all_errors.append(f"Convert Error {file_path.name}: {error}")
                logger.error(f"Failed to convert {file_path}: {error}")
            
            if (i + 1) % 100 == 0:
                gc.collect()
        
        # メモリ解放
        gc.collect()
        
        # 2. 連番リネーム処理
        if self.is_running:
            self.progress_updated.emit(0, 0, "リネームの準備中...")
            
            # 少し待つ
            import time
            time.sleep(0.5)
            
            # image_converter.py 側でも既に連番の場合はスキップされるようになっているが、
            # ここで明示的にスキップ条件を確認
            
            success, fail, errors = ImageConverter.rename_folder_sequential(
                self.folder_path, "", self.digits
            )
            
            total_success += success
            total_fail += fail
            all_errors.extend(errors)
            
        self.progress_updated.emit(100, 100, "完了")
        self.finished.emit(total_success, total_fail, all_errors)

    def stop(self):
        self.is_running = False


class ConverterDialog(QDialog):
    """
    画像変換ツールダイアログ (統合版)
    JPG変換と連番リネームを一括処理
    """
    
    def __init__(self, parent=None, default_path: Path = None):
        super().__init__(parent)
        self.current_folder = default_path if default_path and default_path.exists() else Path.home()
        self.target_files: List[Path] = []
        self.all_images: List[Path] = []
        self.worker_thread = None
        
        self._setup_ui()
        self._refresh_file_list()
        
    def _setup_ui(self):
        self.setWindowTitle("画像一括変換ツール")
        self.setMinimumSize(600, 450)
        self.setModal(True)
        
        # Style
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; }
            QGroupBox {
                border: 1px solid #4a4a4a; border-radius: 8px;
                margin-top: 12px; padding-top: 12px; background-color: #323232;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 12px; padding: 0 8px;
                color: #00ffff; font-weight: bold;
            }
            QPushButton {
                background-color: #4a4a4a; color: white; border: none;
                border-radius: 4px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #5a5a5a; }
            QPushButton:pressed { background-color: #3a3a3a; }
            QPushButton:disabled { background-color: #2a2a2a; color: #666; }
            QListWidget {
                background-color: #1e1e1e; border: 1px solid #4a4a4a;
                border-radius: 4px; color: #e0e0e0;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Folder Selection
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("📂 対象フォルダ:"))
        self.folder_label = QLabel(str(self.current_folder))
        self.folder_label.setStyleSheet("background-color: #1e1e1e; padding: 8px; border-radius: 4px; border: 1px solid #4a4a4a;")
        folder_layout.addWidget(self.folder_label, 1)
        
        self.select_folder_btn = QPushButton("選択...")
        self.select_folder_btn.clicked.connect(self._on_select_folder)
        folder_layout.addWidget(self.select_folder_btn)
        
        layout.addLayout(folder_layout)
        
        # Description Group
        desc_group = QGroupBox("処理内容")
        desc_layout = QVBoxLayout(desc_group)
        desc_layout.setSpacing(8)
        
        desc_label = QLabel(
            "以下の手順で画像を整理します：\n"
            "1. 全ての画像をJPG形式に変換（元ファイルは削除）\n"
            "2. ファイル名を3桁の連番にリネーム（例: 001.jpg, 002.jpg ...）\n\n"
            "※ 既に「NNN.jpg」形式になっているファイルはスキップされます。"
        )
        desc_label.setStyleSheet("color: #aaa; font-size: 13px; line-height: 1.4;")
        desc_layout.addWidget(desc_label)
        
        layout.addWidget(desc_group)
        
        # Status & Preview
        info_group = QGroupBox("ステータス")
        info_layout = QVBoxLayout(info_group)
        
        self.status_label = QLabel("Scanning...")
        info_layout.addWidget(self.status_label)
        
        self.preview_label = QLabel("処理後のイメージ: 001.jpg, 002.jpg ...")
        self.preview_label.setStyleSheet("color: #f39c12; font-style: italic;")
        info_layout.addWidget(self.preview_label)
        
        layout.addWidget(info_group)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.progress_msg = QLabel("")
        self.progress_msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_msg)
        
        layout.addStretch()
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        
        self.run_btn = QPushButton("▶ 整理を実行")
        self.run_btn.setMinimumHeight(44)
        self.run_btn.setStyleSheet("background-color: #27ae60; color: white; font-size: 16px;")
        self.run_btn.clicked.connect(self._on_run)
        btn_layout.addWidget(self.run_btn, 1)
        
        self.close_btn = QPushButton("閉じる")
        self.close_btn.setMinimumHeight(44)
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        
    def _on_select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "フォルダを選択", str(self.current_folder))
        if folder:
            self.current_folder = Path(folder)
            self.folder_label.setText(str(self.current_folder))
            self._refresh_file_list()
            
    def _refresh_file_list(self):
        self.status_label.setText("Scanning...")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        
        self.target_files = ImageConverter.get_target_files(self.current_folder)
        self.all_images = ImageConverter.get_all_images(self.current_folder)
        
        self._update_status()
        
    def _update_status(self):
        convert_count = len(self.target_files)
        total_count = len(self.all_images)
        
        status_text = f"現在の画像ファイル: {total_count}枚"
        if convert_count > 0:
            status_text += f"\nうちJPG変換対象: {convert_count}枚 (PNG/BMP/WEBP等)"
            
        self.status_label.setText(status_text)
        self.run_btn.setEnabled(total_count > 0 or convert_count > 0)
            
    def _on_run(self):
        # Confirmation
        msg = (
            f"フォルダ内の画像を整理します。\n"
            f"・JPG変換: {len(self.target_files)}枚\n"
            f"・連番リネーム: 全画像\n\n"
            "実行してもよろしいですか？"
        )
        
        reply = QMessageBox.question(self, "実行確認", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply != QMessageBox.Yes:
            return
            
        # UI update
        self._set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.progress_msg.setText("処理中...")
        
        # Start Thread
        self.worker_thread = CombinedThread(self.current_folder)
        self.worker_thread.progress_updated.connect(self._on_progress)
        self.worker_thread.finished.connect(self._on_finished)
        self.worker_thread.start()
        
    def _set_buttons_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
        self.select_folder_btn.setEnabled(enabled)
        self.close_btn.setEnabled(enabled)
        
    @Slot(int, int, str)
    def _on_progress(self, current, total, message):
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.progress_msg.setText(message)
        
    @Slot(int, int, list)
    def _on_finished(self, success, fail, errors):
        self.progress_bar.setVisible(False)
        self.progress_msg.setText("")
        self._set_buttons_enabled(True)
        self._refresh_file_list()
        
        if fail > 0 or errors:
            QMessageBox.warning(
                self, "完了（エラーあり）", 
                f"処理完了:\n成功: {success}\n失敗/エラー: {len(errors)}\n\n" + "\n".join(errors[:5])
            )
        else:
            QMessageBox.information(self, "完了", "画像の整理が完了しました！")

