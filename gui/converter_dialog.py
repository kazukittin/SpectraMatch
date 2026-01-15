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


class ConverterThread(QThread):
    """変換処理をバックグラウンドで行うスレッド"""
    progress_updated = Signal(int, int, str)  # current, total, message
    finished = Signal()
    
    def __init__(self, files: List[Path]):
        super().__init__()
        self.files = files
        self.is_running = True
        self.failed_deletes = []
        
    def run(self):
        total = len(self.files)
        success_count = 0
        
        for i, file_path in enumerate(self.files):
            if not self.is_running:
                break
            
            # ファイルが存在しない場合はスキップ（既に削除された場合など）
            if not file_path.exists():
                msg = f"Skipping (not found): {file_path.name}"
                self.progress_updated.emit(i, total, msg)
                continue
                
            msg = f"Converting: {file_path.name}"
            self.progress_updated.emit(i, total, msg)
            
            success, error = ImageConverter.convert_to_jpg(file_path)
            
            if success:
                success_count += 1
                if error: # 変換成功だが削除失敗
                    self.failed_deletes.append(file_path)
            else:
                logger.error(f"Failed to convert {file_path}: {error}")
            
            # 5000件ごとにメモリ解放
            if (i + 1) % 5000 == 0:
                gc.collect()
        
        # 最終メモリ解放
        gc.collect()
        
        # 削除失敗したファイルを再トライ
        if self.failed_deletes:
            self.progress_updated.emit(total, total, "残ったファイルの削除を試みています...")
            import time
            import os
            import stat
            time.sleep(1.0) # 少し待つ
            
            still_failed = []
            for p in self.failed_deletes:
                try:
                    if p.exists():
                        # 読み取り専用属性を外してみる
                        try:
                            os.chmod(p, stat.S_IWRITE)
                        except:
                            pass
                            
                        os.remove(p)
                        logger.info(f"Deleted on retry: {p}")
                except Exception as e:
                    still_failed.append(str(p))
                    logger.warning(f"Still failed to delete: {p} - {e}")
            
            if still_failed:
                logger.warning(f"Total {len(still_failed)} files could not be deleted.")
                # エラーメッセージを含めて完了シグナルを送る
                self.progress_updated.emit(total, total, f"完了 (失敗: {len(still_failed)} files)")
                self.finished.emit()
                return
        
        self.progress_updated.emit(total, total, "完了")
        self.finished.emit()
        
    def stop(self):
        self.is_running = False

class RenameThread(QThread):
    """リネーム処理をバックグラウンドで行うスレッド"""
    finished = Signal(int, int, list)  # success_count, fail_count, errors
    
    def __init__(self, folder_path: Path, prefix: str, digits: int):
        super().__init__()
        self.folder_path = folder_path
        self.prefix = prefix
        self.digits = digits
        
    def run(self):
        success, fail, errors = ImageConverter.rename_folder_sequential(
            self.folder_path, self.prefix, self.digits
        )
        self.finished.emit(success, fail, errors)


class ConverterDialog(QDialog):
    """
    画像変換ツールダイアログ
    指定フォルダ内の画像をJPGに変換し、元ファイルを削除する
    """
    
    def __init__(self, parent=None, default_path: Path = None):
        super().__init__(parent)
        self.current_folder = default_path if default_path and default_path.exists() else Path.home()
        self.target_files: List[Path] = []
        self.all_images: List[Path] = []
        self.converter_thread = None
        
        self._setup_ui()
        self._refresh_file_list()
        
    def _setup_ui(self):
        self.setWindowTitle("画像ツール")
        self.setMinimumSize(650, 600)
        self.setModal(True)
        
        # Style (similar to SettingsDialog)
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
            QGroupBox {
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
                font-weight: bold;
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
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QTabWidget::pane {
                border: 1px solid #4a4a4a;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #3a3a3a;
                color: #aaa;
                padding: 10px 20px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #00ffff;
                color: #1e1e1e;
                font-weight: bold;
            }
            QTabBar::tab:hover:!selected {
                background-color: #4a4a4a;
            }
            QLineEdit, QSpinBox {
                background-color: #1e1e1e;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 6px;
                color: #e0e0e0;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Folder Selection (共通)
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("📂 対象フォルダ:"))
        self.folder_label = QLabel(str(self.current_folder))
        self.folder_label.setStyleSheet("background-color: #1e1e1e; padding: 8px; border-radius: 4px; border: 1px solid #4a4a4a;")
        folder_layout.addWidget(self.folder_label, 1)
        
        self.select_folder_btn = QPushButton("選択...")
        self.select_folder_btn.clicked.connect(self._on_select_folder)
        folder_layout.addWidget(self.select_folder_btn)
        
        layout.addLayout(folder_layout)
        
        # Tab Widget
        self.tab_widget = QTabWidget()
        
        # === Tab 1: JPG変換 ===
        convert_tab = QWidget()
        convert_layout = QVBoxLayout(convert_tab)
        
        convert_desc = QLabel(
            "PNG, BMP, WEBP, JPEG, TIFF などの画像を JPG に変換し、変換に成功した元ファイルを削除します。"
        )
        convert_desc.setStyleSheet("color: #aaa;")
        convert_layout.addWidget(convert_desc)
        
        # File List
        list_group = QGroupBox("変換対象ファイル")
        list_layout = QVBoxLayout(list_group)
        
        self.file_list = QListWidget()
        list_layout.addWidget(self.file_list)
        
        self.convert_status_label = QLabel("0 files found")
        self.convert_status_label.setAlignment(Qt.AlignRight)
        self.convert_status_label.setStyleSheet("color: #00ffff;")
        list_layout.addWidget(self.convert_status_label)
        
        convert_layout.addWidget(list_group)
        
        # Convert Button
        self.convert_btn = QPushButton("▶ JPGに変換")
        self.convert_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        self.convert_btn.clicked.connect(self._on_run_convert)
        convert_layout.addWidget(self.convert_btn)
        
        self.tab_widget.addTab(convert_tab, "🔄 JPG変換")
        
        # === Tab 2: 連番リネーム ===
        rename_tab = QWidget()
        rename_layout = QVBoxLayout(rename_tab)
        
        rename_desc = QLabel(
            "フォルダ内の全画像ファイルを連番でリネームします。\n"
            "例: 001.jpg, 002.jpg, 003.png ..."
        )
        rename_desc.setStyleSheet("color: #aaa;")
        rename_layout.addWidget(rename_desc)
        
        # Options
        options_group = QGroupBox("リネーム設定")
        options_layout = QVBoxLayout(options_group)
        
        # Prefix
        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("プレフィックス:"))
        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText("例: img_ → img_001.jpg")
        self.prefix_input.textChanged.connect(self._update_rename_preview)
        prefix_layout.addWidget(self.prefix_input)
        options_layout.addLayout(prefix_layout)
        
        # Digits
        digits_layout = QHBoxLayout()
        digits_layout.addWidget(QLabel("桁数:"))
        self.digits_spinbox = QSpinBox()
        self.digits_spinbox.setRange(1, 6)
        self.digits_spinbox.setValue(3)
        self.digits_spinbox.valueChanged.connect(self._update_rename_preview)
        digits_layout.addWidget(self.digits_spinbox)
        digits_layout.addStretch()
        options_layout.addLayout(digits_layout)
        
        # Preview
        self.rename_preview = QLabel("プレビュー: 001.jpg, 002.jpg, 003.jpg ...")
        self.rename_preview.setStyleSheet("color: #f39c12; font-style: italic;")
        options_layout.addWidget(self.rename_preview)
        
        rename_layout.addWidget(options_group)
        
        # Rename File List
        rename_list_group = QGroupBox("対象画像ファイル")
        rename_list_layout = QVBoxLayout(rename_list_group)
        
        self.rename_file_list = QListWidget()
        rename_list_layout.addWidget(self.rename_file_list)
        
        self.rename_status_label = QLabel("0 files found")
        self.rename_status_label.setAlignment(Qt.AlignRight)
        self.rename_status_label.setStyleSheet("color: #00ffff;")
        rename_list_layout.addWidget(self.rename_status_label)
        
        rename_layout.addWidget(rename_list_group)
        
        # Rename Button
        self.rename_btn = QPushButton("▶ 連番リネーム実行")
        self.rename_btn.setStyleSheet("background-color: #9b59b6; color: white;")
        self.rename_btn.clicked.connect(self._on_run_rename)
        rename_layout.addWidget(self.rename_btn)
        
        self.tab_widget.addTab(rename_tab, "🔢 連番リネーム")
        
        layout.addWidget(self.tab_widget)
        
        # Progress (共通)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.progress_msg = QLabel("")
        self.progress_msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_msg)
        
        # Close Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.close_btn = QPushButton("閉じる")
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
        # 変換対象
        self.file_list.clear()
        self.target_files = ImageConverter.get_target_files(self.current_folder)
        
        for p in self.target_files:
            self.file_list.addItem(p.name)
            
        count = len(self.target_files)
        self.convert_status_label.setText(f"{count} files found")
        self.convert_btn.setEnabled(count > 0)
        
        # リネーム対象
        self.rename_file_list.clear()
        self.all_images = ImageConverter.get_all_images(self.current_folder)
        
        for p in self.all_images:
            self.rename_file_list.addItem(p.name)
            
        rename_count = len(self.all_images)
        self.rename_status_label.setText(f"{rename_count} files found")
        self.rename_btn.setEnabled(rename_count > 0)
        
        self._update_rename_preview()
        
    def _update_rename_preview(self):
        prefix = self.prefix_input.text()
        digits = self.digits_spinbox.value()
        
        examples = []
        for i in range(1, min(4, len(self.all_images) + 1)):
            if self.all_images:
                ext = self.all_images[i-1].suffix
            else:
                ext = ".jpg"
            examples.append(f"{prefix}{str(i).zfill(digits)}{ext}")
        
        if examples:
            self.rename_preview.setText(f"プレビュー: {', '.join(examples)} ...")
        else:
            self.rename_preview.setText("プレビュー: (ファイルがありません)")
            
    def _on_run_convert(self):
        if not self.target_files:
            return
            
        # Confirmation
        msg = f"{len(self.target_files)}個のファイルをJPGに変換します。\n変換後、元のファイルは削除されます。\n\n実行してもよろしいですか？"
        reply = QMessageBox.question(self, "実行確認", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
            
        # UI update
        self._set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self.target_files))
        self.progress_bar.setValue(0)
        
        # Start Thread
        self.converter_thread = ConverterThread(self.target_files)
        self.converter_thread.progress_updated.connect(self._on_progress)
        self.converter_thread.finished.connect(self._on_convert_finished)
        self.converter_thread.start()
        
    def _on_run_rename(self):
        if not self.all_images:
            return
            
        prefix = self.prefix_input.text()
        digits = self.digits_spinbox.value()
        
        # Confirmation
        msg = f"{len(self.all_images)}個のファイルを連番でリネームします。\n\n例: {prefix}{str(1).zfill(digits)}.jpg\n\n実行してもよろしいですか？"
        reply = QMessageBox.question(self, "実行確認", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
            
        # UI update
        self._set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_msg.setText("リネーム中...")
        
        # Start Rename Thread
        self.rename_thread = RenameThread(self.current_folder, prefix, digits)
        self.rename_thread.finished.connect(self._on_rename_finished)
        self.rename_thread.start()
        
    @Slot(int, int, list)
    def _on_rename_finished(self, success, fail, errors):
        self.progress_bar.setVisible(False)
        self.progress_msg.setText("")
        self._set_buttons_enabled(True)
        
        if fail > 0:
            QMessageBox.warning(
                self, "完了（一部エラー）", 
                f"リネーム完了:\n成功: {success}\n失敗: {fail}\n\nエラー:\n" + "\n".join(errors[:5])
            )
        else:
            QMessageBox.information(self, "完了", f"{success}個のファイルをリネームしました。")
        
        # リストを更新して新しいファイル名を表示
        self._refresh_file_list()
    
    def _set_buttons_enabled(self, enabled: bool):
        self.convert_btn.setEnabled(enabled)
        self.rename_btn.setEnabled(enabled)
        self.select_folder_btn.setEnabled(enabled)
        self.close_btn.setEnabled(enabled)
        
    @Slot(int, int, str)
    def _on_progress(self, current, total, message):
        self.progress_bar.setValue(current)
        self.progress_msg.setText(f"{message} ({current}/{total})")
        
    @Slot()
    @Slot()
    def _on_convert_finished(self):
        # スレッドから失敗リストを取得するのは少し複雑なので、
        # ここでは簡易的にログを確認するように促すか、
        # もしくはスレッド側でエラー情報を保持して完了シグナルで渡すのが理想的。
        # 今回はスレッドインスタンスに残っているfailed_deletesを確認する
        
        failed_count = 0
        if self.converter_thread and hasattr(self.converter_thread, 'failed_deletes'):
            # 再確認：まだ残っているものだけカウント
            failed_count = len([p for p in self.converter_thread.failed_deletes if p.exists()])
            
        self.progress_bar.setVisible(False)
        self.progress_msg.setText("")
        self._set_buttons_enabled(True)
        self._refresh_file_list()
        
        if failed_count > 0:
            QMessageBox.warning(
                self, 
                "完了（一部削除失敗）", 
                f"変換は完了しましたが、{failed_count}個の元ファイルを削除できませんでした。\n"
                "ファイルが他のアプリで開かれているか、権限がない可能性があります。\n\n"
                "ログを確認してください。"
            )
        else:
            QMessageBox.information(self, "完了", "すべての変換処理が完了しました。")
