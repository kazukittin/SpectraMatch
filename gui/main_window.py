# -*- coding: utf-8 -*-
"""
SpectraMatch - Main Window
QSplitterを使用した左サイドバー + 右メインエリアのレイアウト
アルゴリズム選択: pHash (高速) / AI CLIP (高精度)
"""

import os
import logging
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Slot, QProcess
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QProgressBar,
    QFileDialog, QMessageBox, QFrame, QApplication,
    QSplitter, QListWidget, QListWidgetItem, QSizePolicy,
    QComboBox, QStackedWidget, QPlainTextEdit, QMenu
)
from PySide6.QtGui import QFont

from core.scanner import ImageScanner, ScanResult, ScanMode
from core.comparator import SimilarityGroup
from core.clip_engine import is_ai_installed, is_ai_installed_on_disk, get_install_command
from .image_grid import ImageGridWidget, BlurredImagesGridWidget
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
        self.scan_result: ScanResult = None
        self.current_view_mode = "similar"  # "similar" or "blurred"
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        self.setWindowTitle("SpectraMatch - 画像類似検出・削除ツール")
        self.setMinimumSize(1280, 800)
        self.resize(1400, 900)
        self.setStyleSheet(DarkTheme.get_stylesheet())
        
        # メインスプリッター
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(3)
        self.setCentralWidget(splitter)
        
        # 左サイドバー
        sidebar = self._create_sidebar()
        splitter.addWidget(sidebar)
        
        # 右メインエリア
        main_area = self._create_main_area()
        splitter.addWidget(main_area)
        
        # 初期サイズ比率 (サイドバー:メインエリア = 300:残り)
        splitter.setSizes([300, 1100])
        splitter.setStretchFactor(0, 0)  # サイドバーは固定
        splitter.setStretchFactor(1, 1)  # メインエリアは伸縮
    
    def _create_sidebar(self) -> QWidget:
        """左サイドバーを作成"""
        sidebar = QWidget()
        sidebar.setObjectName("sidebarWidget")
        sidebar.setMinimumWidth(280)
        sidebar.setMaximumWidth(400)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # タイトル
        title = QLabel("SpectraMatch")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        subtitle = QLabel("画像類似検出・削除ツール")
        subtitle.setStyleSheet("color: #808080; font-size: 11px; margin-bottom: 10px;")
        layout.addWidget(subtitle)
        
        # 区切り線
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("background-color: #4a4a4a;")
        layout.addWidget(sep1)
        
        # スキャン対象フォルダセクション
        folder_section = QLabel("📁 スキャン対象フォルダ")
        folder_section.setObjectName("sectionLabel")
        layout.addWidget(folder_section)
        
        # フォルダリスト
        self.folder_list = QListWidget()
        self.folder_list.setMinimumHeight(120)
        self.folder_list.setMaximumHeight(200)
        layout.addWidget(self.folder_list)
        
        # フォルダ操作ボタン
        folder_btn_layout = QHBoxLayout()
        folder_btn_layout.setSpacing(8)
        
        self.add_folder_btn = QPushButton("+ 追加")
        self.add_folder_btn.clicked.connect(self._on_add_folder)
        folder_btn_layout.addWidget(self.add_folder_btn)
        
        self.remove_folder_btn = QPushButton("- 削除")
        self.remove_folder_btn.clicked.connect(self._on_remove_folder)
        folder_btn_layout.addWidget(self.remove_folder_btn)
        
        layout.addLayout(folder_btn_layout)
        
        # 区切り線
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("background-color: #4a4a4a;")
        
        # 内部で使用するダミーのコンボボックス（互換性維持）
        self.algo_combo = QComboBox()
        self.algo_combo.addItem("🤖 AI Semantic (CLIP)", ScanMode.AI_CLIP)
        self.algo_combo.setVisible(False)
        
        # キャッシュ削除ボタン
        self.clear_cache_btn = QPushButton("🗑️ キャッシュを削除")
        self.clear_cache_btn.setStyleSheet(
            "background-color: #c0392b; color: white; "
            "font-weight: bold; padding: 8px; border-radius: 4px;"
        )
        self.clear_cache_btn.setToolTip(
            "データベースに保存された画像情報を削除します\n"
            "次回スキャン時に全ファイルを再解析します"
        )
        self.clear_cache_btn.clicked.connect(self._on_clear_cache)
        layout.addWidget(self.clear_cache_btn)
        
        # 区切り線
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet("background-color: #4a4a4a;")
        layout.addWidget(sep3)
        
        # 閾値設定セクション (CLIPモードデフォルト)
        self.threshold_section = QLabel("🎚️ 類似度閾値 (類似度%)")
        self.threshold_section.setObjectName("sectionLabel")
        layout.addWidget(self.threshold_section)

        
        # スライダーと値表示 (CLIPモード: 50-99%)
        slider_layout = QHBoxLayout()
        slider_layout.setSpacing(12)
        
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(50, 99)
        self.threshold_slider.setValue(85)
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.setTickInterval(10)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        slider_layout.addWidget(self.threshold_slider)
        
        self.threshold_value_label = QLabel("85%")
        self.threshold_value_label.setFixedWidth(40)
        self.threshold_value_label.setAlignment(Qt.AlignCenter)
        self.threshold_value_label.setStyleSheet(
            "background-color: #00ffff; color: #1e1e1e; "
            "font-weight: bold; border-radius: 4px; padding: 4px;"
        )
        slider_layout.addWidget(self.threshold_value_label)
        
        layout.addLayout(slider_layout)
        
        # 閾値説明
        self.threshold_desc = QLabel("標準 (85%以上を類似とみなす)")
        self.threshold_desc.setStyleSheet("color: #808080; font-size: 11px;")
        layout.addWidget(self.threshold_desc)
        
        # 区切り線
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet("background-color: #4a4a4a;")
        layout.addWidget(sep3)
        
        # スキャンボタン
        self.scan_btn = QPushButton("🔍 スキャン開始")
        self.scan_btn.setObjectName("scanButton")
        self.scan_btn.setMinimumHeight(48)
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self._on_start_scan)
        layout.addWidget(self.scan_btn)
        
        # 中止ボタン
        self.stop_btn = QPushButton("⏹ 中止")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setVisible(False)
        self.stop_btn.setStyleSheet(
            "background-color: #e74c3c; color: white; font-weight: bold;"
        )
        self.stop_btn.clicked.connect(self._on_stop_scan)
        layout.addWidget(self.stop_btn)
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        # 進捗ラベル
        self.progress_label = QLabel("準備完了")
        self.progress_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
        layout.addWidget(self.progress_label)
        
        # ログ表示エリア (普段は非表示)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(150)
        self.log_view.setStyleSheet("""
            background-color: #1a1a1a;
            color: #2ecc71;
            font-family: 'Consolas', monospace;
            font-size: 10px;
            border: 1px solid #333;
        """)
        self.log_view.setVisible(False)
        layout.addWidget(self.log_view)
        
        layout.addStretch()
        
        # 区切り線
        sep4 = QFrame()
        sep4.setFrameShape(QFrame.HLine)
        sep4.setStyleSheet("background-color: #4a4a4a;")
        layout.addWidget(sep4)
        
        # 削除セクション
        self.delete_count_label = QLabel("")
        self.delete_count_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        layout.addWidget(self.delete_count_label)
        
        self.delete_btn = QPushButton("🗑️ 選択した画像を削除")
        self.delete_btn.setObjectName("deleteButton")
        self.delete_btn.setMinimumHeight(44)
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete_files)
        layout.addWidget(self.delete_btn)
        
        return sidebar
    
    def _create_main_area(self) -> QWidget:
        """右メインエリアを作成"""
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ヘッダー（ツールバー）
        header = QWidget()
        header.setStyleSheet("background-color: #2b2b2b; border-bottom: 1px solid #4a4a4a;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 12, 20, 12)
        header_layout.setSpacing(16)
        
        # 表示モード切替ボタン
        self.view_similar_btn = QPushButton("📊 類似画像")
        self.view_similar_btn.setStyleSheet(
            "background-color: #00ffff; color: #1e1e1e; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
        )
        self.view_similar_btn.setCheckable(True)
        self.view_similar_btn.setChecked(True)
        self.view_similar_btn.clicked.connect(lambda: self._switch_view("similar"))
        header_layout.addWidget(self.view_similar_btn)
        
        self.view_blurred_btn = QPushButton("📷 ブレ画像")
        self.view_blurred_btn.setStyleSheet(
            "background-color: #4a4a4a; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
        )
        self.view_blurred_btn.setCheckable(True)
        self.view_blurred_btn.setChecked(False)
        self.view_blurred_btn.setToolTip("鮮明度スコアが低い（ブレている）画像を\n降順に表示します")
        self.view_blurred_btn.clicked.connect(lambda: self._switch_view("blurred"))
        header_layout.addWidget(self.view_blurred_btn)
        
        header_layout.addSpacing(20)
        
        # スマート自動選択ボタン（類似画像モード用）
        self.smart_select_btn = QPushButton("⚡ 全グループをスマート選択")
        self.smart_select_btn.setStyleSheet(
            "background-color: #9b59b6; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
        )
        self.smart_select_btn.setToolTip(
            "全グループで品質（解像度・鮮明度・サイズ）に基づいて\n"
            "最良の画像を残し、他を削除対象に自動選択します"
        )
        self.smart_select_btn.setEnabled(False)
        self.smart_select_btn.clicked.connect(self._on_smart_select_all)
        header_layout.addWidget(self.smart_select_btn)
        
        # ブレ画像用ボタン（ブレ画像モード時のみ表示）
        self.select_all_blurred_btn = QPushButton("✓ 全選択")
        self.select_all_blurred_btn.setStyleSheet(
            "background-color: #e74c3c; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
        )
        self.select_all_blurred_btn.setToolTip("現在ページの全画像を削除対象に選択")
        self.select_all_blurred_btn.setVisible(False)
        self.select_all_blurred_btn.clicked.connect(self._on_select_all_blurred)
        header_layout.addWidget(self.select_all_blurred_btn)
        
        self.clear_blurred_btn = QPushButton("✕ 選択解除")
        self.clear_blurred_btn.setStyleSheet(
            "background-color: #4a4a4a; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
        )
        self.clear_blurred_btn.setVisible(False)
        self.clear_blurred_btn.clicked.connect(self._on_clear_blurred_selection)
        header_layout.addWidget(self.clear_blurred_btn)
        
        header_layout.addStretch()
        
        self.status_label = QLabel("フォルダを追加してスキャンを開始してください")
        self.status_label.setStyleSheet("color: #808080;")
        header_layout.addWidget(self.status_label)
        
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
            # ボタン表示切替
            self.smart_select_btn.setVisible(True)
            self.select_all_blurred_btn.setVisible(False)
            self.clear_blurred_btn.setVisible(False)
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
            # ボタン表示切替
            self.smart_select_btn.setVisible(False)
            self.select_all_blurred_btn.setVisible(True)
            self.clear_blurred_btn.setVisible(True)
            
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
    
    @Slot()
    def _on_add_folder(self):
        """フォルダ追加"""
        folder = QFileDialog.getExistingDirectory(self, "スキャン対象フォルダを選択")
        if folder:
            path = Path(folder)
            if path not in self.current_folders:
                self.current_folders.append(path)
                item = QListWidgetItem(path.name)
                item.setToolTip(str(path))
                item.setData(Qt.UserRole, path)
                self.folder_list.addItem(item)
                self.scan_btn.setEnabled(True)
    
    @Slot()
    def _on_remove_folder(self):
        """選択フォルダ削除"""
        current = self.folder_list.currentItem()
        if current:
            path = current.data(Qt.UserRole)
            if path in self.current_folders:
                self.current_folders.remove(path)
            self.folder_list.takeItem(self.folder_list.row(current))
            
            if not self.current_folders:
                self.scan_btn.setEnabled(False)
    
    @Slot(int)
    def _on_threshold_changed(self, value: int):
        """閾値変更"""
        self.threshold_value_label.setText(f"{value}%")
        
        if value >= 95:
            desc = "厳密 (ほぼ同一画像のみ)"
        elif value >= 90:
            desc = "やや厳密 (高い類似度)"
        elif value >= 80:
            desc = "標準 (同一画像の異なるバージョン)"
        elif value >= 70:
            desc = "緩い (類似した構図)"
        else:
            desc = "非常に緩い (要注意)"
        
        self.threshold_desc.setText(desc)
    
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
        self.add_folder_btn.setEnabled(False)
        self.remove_folder_btn.setEnabled(False)
        self.algo_combo.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.smart_select_btn.setEnabled(False)
        self.image_grid.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        threshold = self.threshold_slider.value()
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
        self.add_folder_btn.setEnabled(True)
        self.remove_folder_btn.setEnabled(True)
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
        self.add_folder_btn.setEnabled(True)
        self.remove_folder_btn.setEnabled(True)
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
