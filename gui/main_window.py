# -*- coding: utf-8 -*-
"""
SpectraMatch - Main Window
シンプルなレイアウト：ヘッダー + メインエリア + フッター + プレビューパネル
"""

import os
import logging
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Slot, QProcess
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar,
    QFileDialog, QMessageBox, QApplication,
    QComboBox, QStackedWidget, QPlainTextEdit, QSplitter
)
from PySide6.QtGui import QFont

from core.scanner import ImageScanner, ScanResult, ScanMode
from core.comparator import SimilarityGroup
from core.clip_engine import is_ai_installed, is_ai_installed_on_disk, get_install_command
from .image_grid import ImageGridWidget, BlurredImagesGridWidget
from .settings_dialog import SettingsDialog
from .preview_panel import PreviewPanel
from .styles import DarkTheme

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    SpectraMatch メインウィンドウ
    
    レイアウト:
    - QSplitter で左サイドバー(300px) と右メインエリアを分割
    - 左: スキャン対象フォルダリスト、閾値スライダー、スキャンボタン
    - 右: 類似グループ結果表示
    """
    
    def __init__(self):
        super().__init__()
        self.scanner = ImageScanner()
        self.current_folders: List[Path] = []
        self.current_threshold: int = 85  # デフォルト閾値
        self.scan_result: ScanResult = None
        self.current_view_mode = "similar"  # "similar" or "blurred"
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        self.setWindowTitle("SpectraMatch - 画像類似検出・削除ツール")
        self.setMinimumSize(1280, 800)
        self.resize(1500, 900)
        self.setStyleSheet(DarkTheme.get_stylesheet())
        
        # 中央ウィジェット
        central_widget = QWidget()
        central_layout = QHBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        
        # スプリッター（メインエリア + プレビューパネル）
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #4a4a4a;
            }
            QSplitter::handle:hover {
                background-color: #00ffff;
            }
        """)
        
        # メインエリア
        main_area = self._create_main_area()
        splitter.addWidget(main_area)
        
        # プレビューパネル（右側）
        self.preview_panel = PreviewPanel()
        splitter.addWidget(self.preview_panel)
        
        # 初期サイズ比率（メイン:プレビュー = 残り:350）
        splitter.setSizes([1100, 350])
        splitter.setStretchFactor(0, 1)  # メインエリアは伸縮
        splitter.setStretchFactor(1, 0)  # プレビューパネルは固定
        
        central_layout.addWidget(splitter)
        self.setCentralWidget(central_widget)
    
    
    def _create_main_area(self) -> QWidget:
        """メインエリアを作成（サイドバーなし版）"""
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ヘッダー（ツールバー）
        header = QWidget()
        header.setStyleSheet("background-color: #2b2b2b; border-bottom: 1px solid #4a4a4a;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(8)
        
        # 表示モード切替ボタン - 類似画像
        self.view_similar_btn = QPushButton("📊 類似画像")
        self.view_similar_btn.setCheckable(True)
        self.view_similar_btn.setChecked(True)
        self.view_similar_btn.setToolTip(
            "🔍 類似画像表示モード\n\n"
            "AI (CLIP) が検出した類似画像をグループ別に表示します。\n"
            "同じような構図・被写体の画像をまとめて確認できます。"
        )
        self.view_similar_btn.clicked.connect(lambda: self._switch_view("similar"))
        self.view_similar_btn.setStyleSheet("""
            QPushButton {
                background-color: #00ffff;
                color: #1e1e1e;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                border: 2px solid transparent;
            }
            QPushButton:hover {
                background-color: #33ffff;
                border: 2px solid #00ffff;
            }
            QPushButton:checked {
                background-color: #00ffff;
            }
        """)
        header_layout.addWidget(self.view_similar_btn)
        
        # 表示モード切替ボタン - ブレ画像
        self.view_blurred_btn = QPushButton("📷 ブレ画像")
        self.view_blurred_btn.setCheckable(True)
        self.view_blurred_btn.setChecked(False)
        self.view_blurred_btn.setToolTip(
            "📷 ブレ画像表示モード\n\n"
            "鮮明度スコアが低い（ブレている）画像を表示します。\n"
            "ブレが酷い順にソートされるので、不要な画像を素早く特定できます。"
        )
        self.view_blurred_btn.clicked.connect(lambda: self._switch_view("blurred"))
        self.view_blurred_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                border: 2px solid transparent;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
                border: 2px solid #e74c3c;
            }
            QPushButton:checked {
                background-color: #e74c3c;
            }
        """)
        header_layout.addWidget(self.view_blurred_btn)
        
        header_layout.addStretch()
        
        self.status_label = QLabel("⚙️ 設定からフォルダを追加 → 🔍 スキャン開始")
        self.status_label.setStyleSheet("color: #808080; font-size: 12px;")
        header_layout.addWidget(self.status_label)
        
        header_layout.addSpacing(12)
        
        # 設定ボタン（アイコンのみ）
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setMinimumSize(44, 44)
        self.settings_btn.setMaximumSize(44, 44)
        self.settings_btn.setToolTip(
            "⚙️ 設定\n\n"
            "• スキャン対象フォルダの追加・削除\n"
            "• 類似度閾値の調整\n"
            "• キャッシュの管理"
        )
        self.settings_btn.clicked.connect(self._on_open_settings)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #b0b0b0;
                font-size: 24px;
                border: none;
                border-radius: 22px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                color: #00ffff;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        header_layout.addWidget(self.settings_btn)
        
        layout.addWidget(header)
        
        # スタックウィジェット（類似画像/ブレ画像切替）
        self.view_stack = QStackedWidget()
        
        # 類似画像グリッド
        self.image_grid = ImageGridWidget()
        self.view_stack.addWidget(self.image_grid)
        
        # ブレ画像グリッド
        self.blurred_grid = BlurredImagesGridWidget()
        self.view_stack.addWidget(self.blurred_grid)
        
        layout.addWidget(self.view_stack, 1)
        
        # フッター（操作ボタン）
        footer = QWidget()
        footer.setStyleSheet("background-color: #2b2b2b; border-top: 1px solid #4a4a4a;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 10, 16, 10)
        footer_layout.setSpacing(10)
        
        # 左側：スキャン・選択ボタン
        # スキャンボタン
        self.scan_btn = QPushButton("🔍 スキャン")
        self.scan_btn.setObjectName("scanButton")
        self.scan_btn.setMinimumHeight(40)
        self.scan_btn.setMinimumWidth(120)
        self.scan_btn.setEnabled(False)
        self.scan_btn.setToolTip(
            "🔍 スキャン開始\n\n"
            "設定で指定したフォルダ内の画像をスキャンし、\n"
            "AI (CLIP) で類似画像を検出します。\n\n"
            "※ 初回スキャン時はAIモデルのダウンロードが必要です"
        )
        self.scan_btn.clicked.connect(self._on_start_scan)
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                border: 2px solid transparent;
            }
            QPushButton:hover {
                background-color: #2ecc71;
                border: 2px solid #27ae60;
            }
            QPushButton:disabled {
                background-color: #4a4a4a;
                color: #808080;
            }
        """)
        footer_layout.addWidget(self.scan_btn)
        
        # 中止ボタン（スキャン中のみ表示）
        self.stop_btn = QPushButton("⏹ 中止")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setVisible(False)
        self.stop_btn.setToolTip("⏹ スキャンを中止\n\n現在のスキャン処理を中断します。")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                border: 2px solid transparent;
            }
            QPushButton:hover {
                background-color: #c0392b;
                border: 2px solid #e74c3c;
            }
        """)
        self.stop_btn.clicked.connect(self._on_stop_scan)
        footer_layout.addWidget(self.stop_btn)
        
        # スマート全選択ボタン
        self.smart_select_btn = QPushButton("⚡ 全選択")
        self.smart_select_btn.setMinimumHeight(40)
        self.smart_select_btn.setMinimumWidth(100)
        self.smart_select_btn.setToolTip(
            "⚡ スマート全選択\n\n"
            "全グループで品質スコアに基づいて自動選択します：\n"
            "• 解像度（高い方を優先）\n"
            "• 鮮明度（ブレが少ない方を優先）\n"
            "• ファイルサイズ（大きい方を優先）\n\n"
            "各グループで最良の1枚を残し、他を削除対象にします。"
        )
        self.smart_select_btn.setEnabled(False)
        self.smart_select_btn.clicked.connect(self._on_smart_select_all)
        self.smart_select_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                border: 2px solid transparent;
            }
            QPushButton:hover {
                background-color: #a569bd;
                border: 2px solid #9b59b6;
            }
            QPushButton:disabled {
                background-color: #4a4a4a;
                color: #808080;
            }
        """)
        footer_layout.addWidget(self.smart_select_btn)
        
        footer_layout.addSpacing(20)
        
        # 進捗表示
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumWidth(200)
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setMaximumHeight(20)
        footer_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
        footer_layout.addWidget(self.progress_label)
        
        footer_layout.addStretch()
        
        # 右側：削除関連
        # 削除対象カウントラベル
        self.delete_count_label = QLabel("")
        self.delete_count_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 13px;")
        footer_layout.addWidget(self.delete_count_label)
        
        # 削除ボタン
        self.delete_btn = QPushButton("🗑️ 選択した画像を削除")
        self.delete_btn.setObjectName("deleteButton")
        self.delete_btn.setMinimumHeight(40)
        self.delete_btn.setMinimumWidth(180)
        self.delete_btn.setEnabled(False)
        self.delete_btn.setToolTip(
            "🗑️ 選択した画像を削除\n\n"
            "選択された画像をゴミ箱に移動します。\n"
            "（完全削除ではないので復元可能です）"
        )
        self.delete_btn.clicked.connect(self._on_delete_files)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
                border: 2px solid transparent;
            }
            QPushButton:hover {
                background-color: #c0392b;
                border: 2px solid #e74c3c;
            }
            QPushButton:disabled {
                background-color: #4a4a4a;
                color: #808080;
            }
        """)
        footer_layout.addWidget(self.delete_btn)
        
        layout.addWidget(footer)
        
        # 内部で使用するダミーのコンボボックス（互換性維持）
        self.algo_combo = QComboBox()
        self.algo_combo.addItem("🤖 AI Semantic (CLIP)", ScanMode.AI_CLIP)
        self.algo_combo.setVisible(False)
        
        # ログ表示エリア（互換性維持、非表示）
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setVisible(False)
        
        # 設定サマリー（互換性維持）
        self.settings_summary = QLabel("")
        self.settings_summary.setVisible(False)
        
        return main_widget
    
    def _switch_view(self, mode: str):
        """表示モードを切り替え"""
        self.current_view_mode = mode
        
        if mode == "similar":
            self.view_stack.setCurrentWidget(self.image_grid)
            self.view_similar_btn.setChecked(True)
            self.view_similar_btn.setStyleSheet(
                "background-color: #00ffff; color: #1e1e1e; "
                "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
            )
            self.view_blurred_btn.setChecked(False)
            self.view_blurred_btn.setStyleSheet(
                "background-color: #4a4a4a; color: white; "
                "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
            )
        else:  # blurred
            self.view_stack.setCurrentWidget(self.blurred_grid)
            self.view_blurred_btn.setChecked(True)
            self.view_blurred_btn.setStyleSheet(
                "background-color: #e74c3c; color: white; "
                "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
            )
            self.view_similar_btn.setChecked(False)
            self.view_similar_btn.setStyleSheet(
                "background-color: #4a4a4a; color: white; "
                "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
            )
            
            # ブレ画像を表示（スキャン結果がある場合）
            if self.scan_result and hasattr(self.scan_result, 'all_images'):
                self._display_blurred_images()
    
    def _display_blurred_images(self):
        """ブレ画像を鮮明度昇順（ブレが酷い順）で表示"""
        if not self.scan_result or not hasattr(self.scan_result, 'all_images'):
            return
        
        # 鮮明度スコアで昇順ソート（低い=ブレている順）
        sorted_images = sorted(
            self.scan_result.all_images, 
            key=lambda x: x.sharpness_score
        )
        
        self.blurred_grid.set_images(sorted_images)
        self.status_label.setText(f"📷 ブレ画像: {len(sorted_images)}枚（鮮明度昇順）")
        self.status_label.setStyleSheet("color: #e74c3c;")
    
    @Slot()
    def _on_select_all_blurred(self):
        """ブレ画像の全選択"""
        self.blurred_grid.select_all()
    
    @Slot()
    def _on_clear_blurred_selection(self):
        """ブレ画像の選択解除"""
        self.blurred_grid.clear_selection()
    
    def _connect_signals(self):
        """シグナル接続"""
        self.scanner.progress_updated.connect(self._on_progress_updated)
        self.scanner.scan_completed.connect(self._on_scan_completed)
        self.scanner.scan_error.connect(self._on_scan_error)
        self.image_grid.files_to_delete_changed.connect(self._on_delete_count_changed)
        self.blurred_grid.files_to_delete_changed.connect(self._on_delete_count_changed)
        
        # プレビュー関連
        self.image_grid.image_selected.connect(self._on_image_selected)
        self.blurred_grid.image_selected.connect(self._on_image_selected)
        
        # プレビューパネルからの操作
        self.preview_panel.mark_for_deletion.connect(self._on_preview_mark_delete)
        self.preview_panel.unmark_for_deletion.connect(self._on_preview_unmark_delete)
    
    @Slot(object)
    def _on_image_selected(self, image_info):
        """画像が選択されたときにプレビューを表示"""
        # 現在の削除状態を確認する必要があるが、
        # ImageInfoオブジェクト自体には削除フラグは持たせていない（UI側で管理）
        # なので、とりあえず画像情報を表示し、削除状態はFalse（初期値）としておく
        # ※本来はGrid側から削除状態も送るのがベストだが、今回は簡易実装
        
        # 削除状態を確認するために、現在のビューから検索するのはコストが高い
        # ここではシンプルに画像情報を表示する
        
        info = {
            'width': image_info.width,
            'height': image_info.height,
            'file_size': image_info.file_size,
            'sharpness_score': image_info.sharpness_score,
            'is_marked': False  # 初期値。後でUIの状態と同期させるのは少し複雑
        }
        
        # Grid側で管理している削除状態を取得できればよいが...
        # ここでは「画像選択」だけなので、とりあえず表示する
        self.preview_panel.show_image(image_info.path, info)

    @Slot(Path)
    def _on_preview_mark_delete(self, path: Path):
        """プレビューパネルで削除マークされた"""
        # TODO: Grid側の該当画像のチェックボックスをONにする連携が必要
        # 現状のアーキテクチャでは逆方向（Main -> Grid内の特定カード）へのアクセスが難しい
        # 今回はメッセージだけ表示しておく
        pass

    @Slot(Path)
    def _on_preview_unmark_delete(self, path: Path):
        """プレビューパネルで削除マークが外された"""
        pass
    
    @Slot()
    def _on_open_settings(self):
        """設定ダイアログを開く"""
        dialog = SettingsDialog(
            parent=self,
            current_folders=self.current_folders,
            current_threshold=self.current_threshold,
            db=self.scanner.db
        )
        dialog.settings_applied.connect(self._on_settings_applied)
        dialog.cache_cleared.connect(self._on_cache_cleared)
        dialog.exec()
    
    @Slot(list, int)
    def _on_settings_applied(self, folders: list, threshold: int):
        """設定が適用されたときの処理"""
        self.current_folders = folders
        self.current_threshold = threshold
        
        # スキャンボタンの有効/無効を更新
        self.scan_btn.setEnabled(len(self.current_folders) > 0)
        
        # 設定サマリーを更新
        self._update_settings_summary()
        
        logger.info(f"Settings applied: {len(folders)} folders, threshold={threshold}%")
    
    @Slot()
    def _on_cache_cleared(self):
        """キャッシュがクリアされたときの処理"""
        self.progress_label.setText("キャッシュを削除しました")
    
    def _update_settings_summary(self):
        """設定サマリーを更新"""
        if not self.current_folders:
            self.settings_summary.setText("📁 フォルダ未設定\n⚙️ 設定ボタンから追加してください")
            self.settings_summary.setStyleSheet(
                "color: #e74c3c; font-size: 11px; padding: 8px; "
                "background-color: #1e1e1e; border-radius: 4px;"
            )
        else:
            folder_names = [f.name for f in self.current_folders[:3]]
            folder_text = ", ".join(folder_names)
            if len(self.current_folders) > 3:
                folder_text += f" 他{len(self.current_folders) - 3}件"
            
            self.settings_summary.setText(
                f"📁 {folder_text}\n"
                f"🎚️ 類似度閾値: {self.current_threshold}%"
            )
            self.settings_summary.setStyleSheet(
                "color: #2ecc71; font-size: 11px; padding: 8px; "
                "background-color: #1e1e1e; border-radius: 4px;"
            )
    
    @Slot(int)
    def _on_algorithm_changed(self, index: int):
        """アルゴリズム変更時（現在はCLIPのみ）"""
        pass
    
    @Slot()
    def _on_start_scan(self):
        """スキャン開始"""
        if not self.current_folders:
            return
            
        if not is_ai_installed():
            reply = QMessageBox.question(
                self, "AIエンジン未検出",
                "AIスキャンに必要なコンポーネント(約2GB)がインストールされていません。\n"
                "セットアップを開始しますか？（完了まで数分かかります）",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._install_ai_engine()
            return
            
        self._on_start_scan_actual()
        
    def _install_ai_engine(self):
        """AIエンジンのセットアップ (QProcess版)"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("AI環境を準備中...")
        self.scan_btn.setEnabled(False)
        self.log_view.clear()
        self.log_view.setVisible(True)
        self.log_view.appendPlainText("--- AI環境セットアップ開始 ---")
        
        self.installer_process = QProcess(self)
        self.installer_process.setProcessChannelMode(QProcess.MergedChannels)
        
        # エラー発生時のハンドラ
        self.installer_process.errorOccurred.connect(self._on_installer_error)
        self.installer_process.readyReadStandardOutput.connect(self._on_installer_output)
        self.installer_process.finished.connect(self._on_installer_finished)
        
        cmd = get_install_command()
        self.log_view.appendPlainText(f"実行コマンド: {' '.join(cmd)}")
        
        # Windowsでウィンドウを表示しない設定
        # CREATE_NO_WINDOW (0x08000000)
        # Note: PyInstaller環境では subprocess 等のフラグ管理が重要なため、QProcessのデフォルトを信頼しつつ、
        # 必要ならここで調整
        
        self.installer_process.start(cmd[0], cmd[1:])
        
        if not self.installer_process.waitForStarted(5000):
            self.log_view.appendPlainText("エラー: プロセスの起動に失敗しました。")
            self.scan_btn.setEnabled(True)

    def _on_installer_error(self, error):
        """プロセスのエラーイベント"""
        errors = {
            QProcess.FailedToStart: "プログラムが見つからないか、実行権限がありません。",
            QProcess.Crashed: "プロセスがクラッシュしました。",
            QProcess.Timedout: "タイムアウトしました。",
            QProcess.WriteError: "書き込みエラーが発生しました。",
            QProcess.ReadError: "読み込みエラーが発生しました。",
            QProcess.UnknownError: "未知のエラーが発生しました。"
        }
        msg = errors.get(error, f"エラーコード: {error}")
        self.log_view.appendPlainText(f"\n[ERROR] {msg}")
        logger.error(f"Installer QProcess Error: {msg}")
        
    def _on_installer_output(self):
        """インストーラーの出力を解析して進捗表示"""
        data = self.installer_process.readAllStandardOutput().data().decode(errors='replace')
        
        # ログ全体をテキストエリアに追加
        self.log_view.appendPlainText(data.strip())
        # スクロールを末尾へ
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )
        
        for line in data.splitlines():
            line = line.strip()
            if not line: continue
            
            # パッケージ名を表示
            if "Collecting" in line:
                pkg = line.split("Collecting")[-1].strip()
                self.progress_label.setText(f"ダウンロード中: {pkg}")
                # 大まかな進捗（パッケージごとに増やす）
                val = self.progress_bar.value() + 5
                self.progress_bar.setValue(min(val, 90))
            elif "Installing collected packages" in line:
                self.progress_label.setText("📦 最終インストール中... (2〜5分ほどかかります。閉じずにお待ちください)")
                self.progress_label.setStyleSheet("color: #f1c40f; font-weight: bold;")
                self.progress_bar.setValue(95)
                self.log_view.appendPlainText("\n[INFO] パッケージの展開と配置を開始しました。これには数分かかります...")
            
            logger.info(f"[Installer] {line}")

    def _on_installer_finished(self, exit_code, exit_status):
        """インストール完了"""
        # self.progress_bar.setVisible(False) # プログレスバーは消さないでおく（完了100%を見せたい場合）
        self.scan_btn.setEnabled(True)
        
        if exit_code == 0:
            self.log_view.appendPlainText("\n--- セットアップ完了 ---")
            # インストール直後はファイルシステムベースでチェック（インポートは再起動後に有効化）
            if is_ai_installed_on_disk():
                self.progress_label.setText("セットアップ完了 - 再起動が必要です")
                self.progress_bar.setValue(100)
                QMessageBox.information(
                    self, "セットアップ完了",
                    "AIエンジンのインストールが完了しました！\n\n"
                    "新しいライブラリを読み込むため、アプリを再起動してください。\n"
                    "再起動後、スキャンを開始できます。"
                )
            else:
                QMessageBox.warning(
                    self, "確認失敗",
                    "インストールは完了しましたが、一部ファイルが見つかりません。\n"
                    "アプリを再起動してから再度お試しください。"
                )
        else:
            self.log_view.appendPlainText("\n--- セットアップ失敗 ---")
            err = self.installer_process.readAllStandardError().data().decode(errors='replace')
            self.log_view.appendPlainText(f"Error: {err}")
            logger.error(f"Installer Error: {err}")
            QMessageBox.critical(self, "エラー", f"インストールに失敗しました。\n詳細ログを確認してください。")
            self.progress_label.setText("セットアップ失敗")

    @Slot()
    def _on_start_scan_actual(self):
        """実際の開始処理（チェック通過後）"""
        self.scan_btn.setEnabled(False)
        self.scan_btn.setVisible(False)
        self.stop_btn.setVisible(True)
        self.settings_btn.setEnabled(False)  # スキャン中は設定変更不可
        self.algo_combo.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.smart_select_btn.setEnabled(False)
        self.image_grid.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        threshold = self.current_threshold
        mode = self.algo_combo.currentData()
        
        # 最初のフォルダをスキャン
        self.scanner.start_scan(self.current_folders[0], threshold, mode=mode)
    
    @Slot()
    def _on_stop_scan(self):
        """スキャン中止"""
        self.progress_label.setText("中止中...")
        self.stop_btn.setEnabled(False)
        self.scanner.stop_scan()
    
    @Slot(int, int, str)
    def _on_progress_updated(self, current: int, total: int, message: str):
        """進捗更新"""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.progress_label.setText(message)
    
    @Slot(object)
    def _on_scan_completed(self, result: ScanResult):
        """スキャン完了"""
        self.scan_result = result
        
        # ボタン状態を復元
        self.scan_btn.setEnabled(True)
        self.scan_btn.setVisible(True)
        self.stop_btn.setVisible(False)
        self.stop_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.algo_combo.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if result.groups:
            self.image_grid.set_groups(result.groups)
            total_images = sum(g.count for g in result.groups)
            cache_info = f", キャッシュ: {result.cached_files}" if result.cached_files > 0 else ""
            self.status_label.setText(
                f"✅ {len(result.groups)}グループ / {total_images}枚 "
                f"(処理: {result.processed_files}{cache_info}, スキップ: {result.skipped_files})"
            )
            self.status_label.setStyleSheet("color: #2ecc71;")
            self.progress_label.setText("スキャン完了")
            self.smart_select_btn.setEnabled(True)
        else:
            cache_info = f", キャッシュ: {result.cached_files}" if result.cached_files > 0 else ""
            self.status_label.setText(
                f"類似画像なし (処理: {result.processed_files}{cache_info})"
            )
            self.status_label.setStyleSheet("color: #3498db;")
            self.progress_label.setText("類似画像は見つかりませんでした")
            self.smart_select_btn.setEnabled(False)
    
    @Slot(str)
    def _on_scan_error(self, error: str):
        """スキャンエラー"""
        self.scan_btn.setEnabled(True)
        self.scan_btn.setVisible(True)
        self.stop_btn.setVisible(False)
        self.stop_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.algo_combo.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText(f"エラー: {error}")
        QMessageBox.critical(self, "エラー", f"スキャン中にエラーが発生しました:\n{error}")
    
    @Slot(int)
    def _on_delete_count_changed(self, count: int):
        """削除対象数変更"""
        self.delete_btn.setEnabled(count > 0)
        if count > 0:
            self.delete_count_label.setText(f"🗑️ {count}枚を削除対象に選択中")
        else:
            self.delete_count_label.setText("")
    
    @Slot()
    def _on_delete_files(self):
        """ファイル削除（ゴミ箱へ移動）+ 即時UI更新"""
        # 現在の表示モードに応じてファイルを取得
        if self.current_view_mode == "blurred":
            files = self.blurred_grid.get_all_files_to_delete()
        else:
            files = self.image_grid.get_all_files_to_delete()
        
        if not files:
            return
        
        reply = QMessageBox.question(
            self, "削除確認",
            f"{len(files)}枚の画像をゴミ箱に移動します。\n"
            "続行しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # send2trashをインポート
        try:
            from send2trash import send2trash
        except ImportError:
            # send2trashがない場合は従来のos.removeを使用
            reply = QMessageBox.warning(
                self, "警告",
                "send2trashがインストールされていません。\n"
                "ファイルを完全に削除しますか？\n"
                "（pip install Send2Trash でインストール推奨）",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            send2trash = None
        
        deleted_files = []
        errors = []
        for path in files:
            try:
                if send2trash:
                    send2trash(str(path))
                else:
                    os.remove(path)
                deleted_files.append(path)
            except Exception as e:
                errors.append(f"{path.name}: {e}")
        
        # ===== 即時UI更新 =====
        removed_groups = 0
        if deleted_files:
            # 両方のグリッドから削除されたファイルを除去
            removed_groups = self.image_grid.remove_deleted_files(deleted_files)
            self.blurred_grid.remove_deleted_files(deleted_files)
            
            # scan_resultも更新（内部データの整合性維持）
            if self.scan_result:
                deleted_paths_set = {str(p) for p in deleted_files}
                
                # all_imagesから削除
                if hasattr(self.scan_result, 'all_images'):
                    self.scan_result.all_images = [
                        img for img in self.scan_result.all_images
                        if str(img.path) not in deleted_paths_set
                    ]
                
                # groupsも更新
                groups_to_keep = []
                for group in self.scan_result.groups:
                    group.images = [
                        img for img in group.images
                        if str(img.path) not in deleted_paths_set
                    ]
                    if len(group.images) >= 2:
                        groups_to_keep.append(group)
                self.scan_result.groups = groups_to_keep
            
            # ステータス更新
            if self.scan_result and self.scan_result.groups:
                total_images = sum(g.count for g in self.scan_result.groups)
                self.status_label.setText(
                    f"✅ {len(self.scan_result.groups)}グループ / {total_images}枚"
                )
            elif self.scan_result:
                self.status_label.setText("類似画像なし")
            
            # 削除対象カウントをリセット
            self.delete_count_label.setText("")
            self.delete_btn.setEnabled(False)
        
        # 結果メッセージ
        if send2trash:
            msg = f"{len(deleted_files)}枚の画像をゴミ箱に移動しました。"
        else:
            msg = f"{len(deleted_files)}枚の画像を削除しました。"
        
        if removed_groups > 0:
            msg += f"\n（{removed_groups}グループが1枚以下になり削除されました）"
        
        if errors:
            msg += f"\n\n{len(errors)}件のエラー:\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                msg += f"\n... 他{len(errors)-5}件"
        
        self.progress_label.setText(f"🗑️ {len(deleted_files)}枚を削除しました")
        QMessageBox.information(self, "完了", msg)
    
    @Slot()
    def _on_smart_select_all(self):
        """全グループでスマート自動選択を実行"""
        self.image_grid.smart_select_all()
        self.progress_label.setText("⚡ スマート選択を適用しました")
    
    @Slot()
    def _on_clear_cache(self):
        """キャッシュを削除"""
        reply = QMessageBox.question(
            self, "キャッシュ削除",
            "データベースに保存された全ての画像情報を削除します。\n"
            "次回スキャン時に全ファイルを再解析します。\n\n"
            "続行しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            # データベースをクリア
            self.scanner.db.clear_all()
            self.scanner.db.vacuum()
            
            # サムネイルキャッシュもクリア
            from .image_grid import clear_thumbnail_cache
            clear_thumbnail_cache()
            
            # 表示をクリア
            self.image_grid.clear()
            self.blurred_grid.clear()
            self.scan_result = None
            
            self.status_label.setText("キャッシュを削除しました")
            self.status_label.setStyleSheet("color: #f39c12;")
            self.progress_label.setText("🗑️ キャッシュを削除しました。次回スキャンで全ファイルを再解析します。")
            
            QMessageBox.information(self, "完了", "キャッシュを削除しました。")
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"キャッシュ削除中にエラーが発生しました:\n{e}")
