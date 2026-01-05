# -*- coding: utf-8 -*-
"""
SpectraMatch - Image Grid Widget (v2 - Paginated)
類似画像グループを表示するグリッドウィジェット

4万枚規模対応:
- ページネーション（10グループ/ページ）
- サムネイルの非同期読み込み（QThreadPool）
- メモリ効率的なウィジェット管理
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Optional, Dict
from enum import Enum
import logging

from PySide6.QtCore import Qt, Signal, QSize, QRunnable, QThreadPool, QObject, Slot
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QCheckBox, QScrollArea, QPushButton,
    QGridLayout, QGroupBox, QSizePolicy
)
import cv2
import numpy as np

from core.comparator import SimilarityGroup, ImageInfo
from .styles import DarkTheme

logger = logging.getLogger(__name__)

# サムネイルキャッシュ（メモリ制限付き）
_thumbnail_cache: Dict[str, QPixmap] = {}
_CACHE_MAX_SIZE = 500


def format_file_size(size_bytes: int) -> str:
    """ファイルサイズを人間が読める形式に変換"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_sharpness_label(score: float) -> str:
    """
    鮮明度スコアを分かりやすいラベルに変換
    
    スコアは500px正規化されたLaplacian分散値
    - 低い値: ブレている、ぼやけている
    - 高い値: エッジがくっきり、鮮明
    """
    if score < 50:
        return "かなりブレ"
    elif score < 100:
        return "ブレ"
    elif score < 200:
        return "やや不鮮明"
    elif score < 500:
        return "普通"
    else:
        return "鮮明"


def clear_thumbnail_cache():
    """サムネイルキャッシュをクリア"""
    global _thumbnail_cache
    _thumbnail_cache.clear()


# グローバルスレッドプール
_thread_pool = QThreadPool.globalInstance()
_thread_pool.setMaxThreadCount(4)  # 同時読み込み数を制限


class ThumbnailSignals(QObject):
    """サムネイル読み込み完了シグナル"""
    finished = Signal(str, object)  # (path, QPixmap or None)


class ThumbnailLoader(QRunnable):
    """非同期サムネイル読み込みタスク"""
    
    def __init__(self, path: str, size: int = 120):
        super().__init__()
        self.path = path
        self.size = size
        self.signals = ThumbnailSignals()
        self.setAutoDelete(True)
    
    @Slot()
    def run(self):
        """バックグラウンドでサムネイルを読み込み"""
        try:
            # キャッシュチェック
            if self.path in _thumbnail_cache:
                self.signals.finished.emit(self.path, _thumbnail_cache[self.path])
                return
            
            # ファイル存在チェック
            if not Path(self.path).exists():
                logger.warning(f"サムネイル: ファイルが存在しません: {self.path}")
                self.signals.finished.emit(self.path, None)
                return
            
            # 日本語パス対応で読み込み
            stream = np.fromfile(self.path, dtype=np.uint8)
            if stream is None or len(stream) == 0:
                logger.warning(f"サムネイル: ファイル読み込み失敗: {self.path}")
                self.signals.finished.emit(self.path, None)
                return
            
            img = cv2.imdecode(stream, cv2.IMREAD_COLOR)
            if img is None:
                self.signals.finished.emit(self.path, None)
                return
            
            h, w = img.shape[:2]
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            scale = min(self.size / w, self.size / h)
            new_w, new_h = int(w * scale), int(h * scale)
            resized = cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
            # QImageに変換
            qimg = QImage(resized.data, new_w, new_h, new_w * 3, QImage.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(qimg)
            
            # キャッシュに保存
            if len(_thumbnail_cache) >= _CACHE_MAX_SIZE:
                oldest_key = next(iter(_thumbnail_cache))
                del _thumbnail_cache[oldest_key]
            _thumbnail_cache[self.path] = pixmap
            
            self.signals.finished.emit(self.path, pixmap)
            
        except Exception as e:
            logger.error(f"サムネイル読み込みエラー: {self.path} - {e}")
            self.signals.finished.emit(self.path, None)


def open_image_with_default_app(path: Path):
    """画像をOSのデフォルトアプリで開く"""
    try:
        path_str = str(path)
        if sys.platform == 'win32':
            os.startfile(path_str)
        elif sys.platform == 'darwin':  # macOS
            subprocess.run(['open', path_str], check=True)
        else:  # Linux
            subprocess.run(['xdg-open', path_str], check=True)
        logger.info(f"画像を開きました: {path_str}")
    except Exception as e:
        logger.error(f"画像を開けませんでした: {path} - {e}")


class ImageCard(QFrame):
    """個別画像カードウィジェット（軽量版）"""
    
    selection_changed = Signal(object, bool)
    clicked = Signal(object)  # image_info をシグナルで送信
    THUMBNAIL_SIZE = 120
    
    def __init__(self, image_info: ImageInfo, parent=None):
        super().__init__(parent)
        self.image_info = image_info
        self.is_marked_delete = False
        self.is_focused = False
        self._thumbnail_loaded = False
        self._setup_ui()
        # 非同期でサムネイルを読み込み開始
        self._start_thumbnail_load()
    

    
    def _setup_ui(self):
        self.setObjectName("imageCard")
        self.setFixedSize(180, 280)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        # サムネイルプレースホルダー（画像アイコン表示）
        ext = self.image_info.path.suffix.upper()
        self.thumbnail_label = QLabel(f"🖼️\n{ext}")
        self.thumbnail_label.setFixedSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet(
            "background-color: #3c3c3c; border-radius: 4px; border: 1px solid #4a4a4a; "
            "color: #808080; font-size: 24px;"
        )
        layout.addWidget(self.thumbnail_label, alignment=Qt.AlignCenter)
        
        # ファイル名
        filename = self.image_info.path.name
        if len(filename) > 20:
            filename = filename[:17] + "..."
        self.name_label = QLabel(filename)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.name_label.setToolTip(str(self.image_info.path))
        layout.addWidget(self.name_label)
        
        # 解像度
        res_str = f"{self.image_info.width} x {self.image_info.height}"
        self.resolution_label = QLabel(f"📐 {res_str}")
        self.resolution_label.setAlignment(Qt.AlignCenter)
        self.resolution_label.setStyleSheet("color: #b0b0b0; font-size: 10px;")
        layout.addWidget(self.resolution_label)
        
        # ファイルサイズ
        size_text = format_file_size(self.image_info.file_size)
        self.size_label = QLabel(f"💾 {size_text}")
        self.size_label.setAlignment(Qt.AlignCenter)
        self.size_label.setStyleSheet("color: #808080; font-size: 10px;")
        layout.addWidget(self.size_label)
        
        # 鮮明度スコア
        sharpness = self.image_info.sharpness_score
        sharpness_desc = get_sharpness_label(sharpness)
        
        if sharpness < 50:
            color = "#e74c3c"  # かなりブレ - 赤
        elif sharpness < 100:
            color = "#e67e22"  # ブレ - オレンジ
        elif sharpness < 200:
            color = "#f39c12"  # やや不鮮明 - 黄
        elif sharpness < 500:
            color = "#b0b0b0"  # 普通 - グレー
        else:
            color = "#2ecc71"  # 鮮明 - 緑
        
        self.sharpness_label = QLabel(f"🔍 {sharpness:.0f} ({sharpness_desc})")
        self.sharpness_label.setAlignment(Qt.AlignCenter)
        self.sharpness_label.setStyleSheet(f"color: {color}; font-size: 10px;")
        layout.addWidget(self.sharpness_label)
        
        # 削除チェックボックス
        self.delete_checkbox = QCheckBox("削除対象")
        self.delete_checkbox.setStyleSheet("font-size: 11px; margin-top: 4px;")
        self.delete_checkbox.stateChanged.connect(self._on_checkbox_changed)
        layout.addWidget(self.delete_checkbox, alignment=Qt.AlignCenter)
    
    def _start_thumbnail_load(self):
        """非同期でサムネイル読み込みを開始"""
        if self._thumbnail_loaded:
            return
        
        path_str = str(self.image_info.path)
        
        # キャッシュにあればすぐ表示
        if path_str in _thumbnail_cache:
            self.thumbnail_label.setPixmap(_thumbnail_cache[path_str])
            self._thumbnail_loaded = True
            return
        
        # 非同期タスクを開始
        loader = ThumbnailLoader(path_str, self.THUMBNAIL_SIZE)
        loader.signals.finished.connect(self._on_thumbnail_loaded, Qt.QueuedConnection)
        _thread_pool.start(loader)
    
    @Slot(str, object)
    def _on_thumbnail_loaded(self, path: str, pixmap):
        """サムネイル読み込み完了コールバック"""
        if pixmap is not None and str(self.image_info.path) == path:
            self.thumbnail_label.setPixmap(pixmap)
            self._thumbnail_loaded = True
        elif pixmap is None and str(self.image_info.path) == path:
            self.thumbnail_label.setText("読込失敗")
    
    def _on_checkbox_changed(self, state):
        # PySide6のstateChangedは整数を送信 (Checked=2, Unchecked=0)
        self.is_marked_delete = (state == Qt.CheckState.Checked.value)
        self._update_style()
        self.selection_changed.emit(self.image_info, self.is_marked_delete)
    
    def _update_style(self):
        if self.is_focused:
            # フォーカス時は背景白、文字黒、青枠
            # 既存のスタイルを上書き
            if self.is_marked_delete:
                # 削除対象かつフォーカスの場合
                self.setStyleSheet("""
                    #imageCard {
                        background-color: #ffdce0; /* 薄い赤 */
                        border: 3px solid #00ffff;
                        border-radius: 8px;
                    }
                    QLabel { color: black; }
                    QCheckBox { color: black; }
                """)
            else:
                # 通常フォーカス
                self.setStyleSheet("""
                    #imageCard {
                        background-color: white;
                        border: 3px solid #00ffff;
                        border-radius: 8px;
                    }
                    QLabel { color: black; }
                    QCheckBox { color: black; }
                """)
        elif self.is_marked_delete:
            self.setStyleSheet(DarkTheme.get_card_style("delete"))
        else:
            self.setStyleSheet(DarkTheme.get_card_style("normal"))
    
    def set_focused(self, focused: bool):
        """フォーカス状態を設定"""
        if self.is_focused != focused:
            self.is_focused = focused
            self._update_style()
    
    def set_delete(self, delete: bool):
        self.delete_checkbox.blockSignals(True)
        self.delete_checkbox.setChecked(delete)
        self.delete_checkbox.blockSignals(False)
        self.is_marked_delete = delete
        self._update_style()
    
    def mousePressEvent(self, event):
        """シングルクリックでプレビュー表示"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.image_info)
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """ダブルクリックで画像をデフォルトアプリで開く"""
        if event.button() == Qt.LeftButton:
            open_image_with_default_app(self.image_info.path)
        super().mouseDoubleClickEvent(event)


class SimilarityGroupWidget(QGroupBox):
    """類似グループ表示ウィジェット"""
    
    card_clicked = Signal(object)  # image_info
    
    def __init__(self, group: SimilarityGroup, parent=None):
        group_type = "完全一致" if group.is_exact_match else f"類似 (距離: {group.min_distance}-{group.max_distance})"
        title = f"グループ {group.group_id}: {group_type} - {group.count}枚"
        super().__init__(title, parent)
        
        self.group = group
        self.cards: List[ImageCard] = []
        self._setup_ui()
    
    def _setup_ui(self):
        if self.group.is_exact_match:
            self.setStyleSheet("QGroupBox { border-left: 4px solid #e74c3c; background-color: #2b2b2b; }")
        else:
            self.setStyleSheet("QGroupBox { border-left: 4px solid #3498db; background-color: #2b2b2b; }")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 20, 12, 12)
        main_layout.setSpacing(10)
        
        # 操作ボタン
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        smart_btn = QPushButton("⚡ スマート選択")
        smart_btn.setFixedHeight(28)
        smart_btn.setStyleSheet("background-color: #9b59b6;")
        smart_btn.clicked.connect(self._smart_auto_select)
        btn_layout.addWidget(smart_btn)
        
        select_except_first_btn = QPushButton("先頭以外を削除")
        select_except_first_btn.setFixedHeight(28)
        select_except_first_btn.clicked.connect(self._select_except_first)
        btn_layout.addWidget(select_except_first_btn)
        
        clear_btn = QPushButton("選択解除")
        clear_btn.setFixedHeight(28)
        clear_btn.clicked.connect(self._clear_selection)
        btn_layout.addWidget(clear_btn)
        
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)
        
        # 画像グリッド
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(310)
        scroll.setStyleSheet("background-color: transparent; border: none;")
        
        grid_container = QWidget()
        grid_container.setStyleSheet("background-color: transparent;")
        grid_layout = QHBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(10)
        
        # 表示画像数を制限（最大20枚）
        MAX_DISPLAY_IMAGES = 20
        images_to_show = self.group.images[:MAX_DISPLAY_IMAGES]
        remaining = len(self.group.images) - len(images_to_show)
        
        for image_info in images_to_show:
            card = ImageCard(image_info)
            card.clicked.connect(self.card_clicked)
            self.cards.append(card)
            grid_layout.addWidget(card)
        
        # 残り枚数表示
        if remaining > 0:
            more_label = QLabel(f"+{remaining}枚")
            more_label.setFixedSize(80, 120)
            more_label.setAlignment(Qt.AlignCenter)
            more_label.setStyleSheet(
                "background-color: #4a4a4a; border-radius: 8px; "
                "color: #ffffff; font-size: 14px; font-weight: bold;"
            )
            grid_layout.addWidget(more_label)
        
        grid_layout.addStretch()
        scroll.setWidget(grid_container)
        main_layout.addWidget(scroll)
    
    def _smart_auto_select(self):
        if not self.cards:
            return
        
        scored_cards = []
        for card in self.cards:
            info = card.image_info
            max_resolution = max(c.image_info.resolution for c in self.cards) or 1
            max_sharpness = max(c.image_info.sharpness_score for c in self.cards) or 1
            max_size = max(c.image_info.file_size for c in self.cards) or 1
            
            res_score = info.resolution / max_resolution
            sharp_score = info.sharpness_score / max_sharpness
            size_score = info.file_size / max_size
            total_score = (res_score * 0.4) + (sharp_score * 0.4) + (size_score * 0.2)
            scored_cards.append((card, total_score))
        
        scored_cards.sort(key=lambda x: x[1], reverse=True)
        
        for i, (card, _) in enumerate(scored_cards):
            card.set_delete(i > 0)
    
    def _select_except_first(self):
        for i, card in enumerate(self.cards):
            card.set_delete(i > 0)
    
    def _clear_selection(self):
        for card in self.cards:
            card.set_delete(False)
    
    def smart_select(self):
        self._smart_auto_select()
    
    def get_files_to_delete(self) -> List[Path]:
        return [card.image_info.path for card in self.cards if card.is_marked_delete]


class ImageGridWidget(QScrollArea):
    """
    類似グループ一覧表示ウィジェット（ページネーション対応）
    
    4万枚規模対応:
    - 5グループ/ページ（パフォーマンス優先）
    - ページ切り替えボタン
    - メモリ効率的なウィジェット管理
    """
    
    GROUPS_PER_PAGE = 5  # パフォーマンス優先で5グループに制限
    
    files_to_delete_changed = Signal(int)
    image_selected = Signal(object)  # image_info
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.group_widgets: List[SimilarityGroupWidget] = []
        self.all_groups: List[SimilarityGroup] = []
        self.current_page = 0
        self.total_pages = 0
        self._focus_index = -1
        self._setup_ui()
    
    def _setup_ui(self):
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.container = QWidget()
        self.container.setStyleSheet("background-color: #1e1e1e;")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(20)
        
        # 初期メッセージ
        self.empty_label = QLabel("スキャン結果がここに表示されます")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #808080; font-size: 16px; padding: 40px;")
        self.layout.addWidget(self.empty_label)
        
        # ページネーションコントロール（後で追加）
        self.pagination_widget = None
        
        self.layout.addStretch()
        self.setWidget(self.container)
    
    def _create_pagination_controls(self):
        """ページネーションコントロールを作成"""
        if self.pagination_widget:
            self.pagination_widget.deleteLater()
        
        self.pagination_widget = QWidget()
        self.pagination_widget.setStyleSheet("background-color: transparent;")
        
        self.pagination_layout = QHBoxLayout(self.pagination_widget)
        self.pagination_layout.setContentsMargins(0, 20, 0, 20)
        self.pagination_layout.setSpacing(10)
        self.pagination_layout.setAlignment(Qt.AlignCenter)
        
        return self.pagination_widget
    
    def _update_pagination_state(self):
        """ページネーション状態を更新（ボタン再生成）"""
        if not self.pagination_widget:
            return
            
        # 既存のボタンを削除
        while self.pagination_layout.count():
            item = self.pagination_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if self.total_pages <= 1:
            return
            
        # 前へボタン
        prev_btn = QPushButton("◀")
        prev_btn.setFixedSize(58, 40)
        prev_btn.setEnabled(self.current_page > 0)
        prev_btn.clicked.connect(self._go_prev_page)
        self.pagination_layout.addWidget(prev_btn)
        
        # ページ番号ボタン
        start_page = max(0, self.current_page - 2)
        end_page = min(self.total_pages - 1, self.current_page + 2)
        
        # 最初のページ
        if start_page > 0:
            self._add_page_button(0)
            if start_page > 1:
                lbl = QLabel("...")
                lbl.setStyleSheet("color: #888;")
                self.pagination_layout.addWidget(lbl)
        
        # 範囲内のページ
        for i in range(start_page, end_page + 1):
            self._add_page_button(i, i == self.current_page)
            
        # 最後のページ
        if end_page < self.total_pages - 1:
            if end_page < self.total_pages - 2:
                lbl = QLabel("...")
                lbl.setStyleSheet("color: #888;")
                self.pagination_layout.addWidget(lbl)
            self._add_page_button(self.total_pages - 1)
            
        # 次へボタン
        next_btn = QPushButton("▶")
        next_btn.setFixedSize(58, 40)
        next_btn.setEnabled(self.current_page < self.total_pages - 1)
        next_btn.clicked.connect(self._go_next_page)
        self.pagination_layout.addWidget(next_btn)
        
        # ラベル
        info_label = QLabel(f" {self.current_page + 1}/{self.total_pages} ")
        info_label.setStyleSheet("color: #aaa; margin-left: 10px; font-weight: bold;")
        self.pagination_layout.addWidget(info_label)

    def _add_page_button(self, page_index: int, is_current: bool = False):
        """ページ番号ボタンを追加"""
        btn = QPushButton(str(page_index + 1))
        btn.setFixedSize(58, 40)
        btn.setCheckable(True)
        btn.setChecked(is_current)
        if is_current:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #00ffff;
                    color: #1e1e1e;
                    font-weight: bold;
                    border: none;
                    border-radius: 8px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    color: #e0e0e0;
                    border: none;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
            """)
        # ラムダ式の変数キャプチャ問題を回避するためにデフォルト引数を使用
        btn.clicked.connect(lambda checked=False, idx=page_index: self._go_to_page(idx))
        self.pagination_layout.addWidget(btn)

    def _go_to_page(self, page_index: int):
        if 0 <= page_index < self.total_pages and page_index != self.current_page:
            self.current_page = page_index
            self._display_current_page()
    
    def _go_prev_page(self):
        """前のページに移動"""
        if self.current_page > 0:
            self.current_page -= 1
            self._display_current_page()
    
    def _go_next_page(self):
        """次のページに移動"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._display_current_page()
    
    def _display_current_page(self):
        """現在のページを表示"""
        # 既存ウィジェットをクリア
        for widget in self.group_widgets:
            widget.deleteLater()
        self.group_widgets.clear()
        
        # サムネイルキャッシュをクリア（メモリ解放）
        clear_thumbnail_cache()
        
        # ストレッチとページネーションを一時的に削除
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            if item.widget() and item.widget() != self.empty_label:
                if item.widget() != self.pagination_widget:
                    item.widget().deleteLater()
        
        self.empty_label.setVisible(False)
        
        # 現在ページのグループを取得
        start_idx = self.current_page * self.GROUPS_PER_PAGE
        end_idx = min(start_idx + self.GROUPS_PER_PAGE, len(self.all_groups))
        page_groups = self.all_groups[start_idx:end_idx]
        
        # フォーカスリセット
        self._focus_index = -1
        
        # グループウィジェットを作成
        for group in page_groups:
            widget = SimilarityGroupWidget(group)
            widget.card_clicked.connect(self._on_card_clicked_from_group)
            for card in widget.cards:
                card.selection_changed.connect(self._on_selection_changed)
            self.group_widgets.append(widget)
            self.layout.addWidget(widget)
        
        # ページネーションコントロールを追加
        pagination = self._create_pagination_controls()
        self.layout.addWidget(pagination)
        self._update_pagination_state()
        
        self.layout.addStretch()
        
        # スクロールを先頭に
        self.verticalScrollBar().setValue(0)
    
    def clear(self):
        """グリッドをクリア"""
        for widget in self.group_widgets:
            widget.deleteLater()
        self.group_widgets.clear()
        self.all_groups.clear()
        self.current_page = 0
        self.total_pages = 0
        clear_thumbnail_cache()
        self.empty_label.setVisible(True)
        
        if self.pagination_widget:
            self.pagination_widget.deleteLater()
            self.pagination_widget = None
    
    def set_groups(self, groups: List[SimilarityGroup]):
        """類似グループを設定"""
        self.clear()
        
        if not groups:
            self.empty_label.setText("類似画像は見つかりませんでした")
            return
        
        self.all_groups = groups
        self.total_pages = (len(groups) + self.GROUPS_PER_PAGE - 1) // self.GROUPS_PER_PAGE
        self.current_page = 0
        
        self._display_current_page()
    
    def _on_selection_changed(self, image_info, is_delete):
        """選択変更時"""
        count = sum(len(w.get_files_to_delete()) for w in self.group_widgets)
        self.files_to_delete_changed.emit(count)
    
    def smart_select_all(self):
        """現在ページの全グループでスマート自動選択を実行"""
        for widget in self.group_widgets:
            widget.smart_select()
        count = sum(len(w.get_files_to_delete()) for w in self.group_widgets)
        self.files_to_delete_changed.emit(count)
    
    def get_all_files_to_delete(self) -> List[Path]:
        """現在ページの削除対象ファイルを取得"""
        files = []
        for widget in self.group_widgets:
            files.extend(widget.get_files_to_delete())
        return files
    
    def remove_deleted_files(self, deleted_paths: List[Path]) -> int:
        """
        削除されたファイルをUIから即時除去
        
        Args:
            deleted_paths: 削除されたファイルパスのリスト
            
        Returns:
            削除されたグループ数
        """
        deleted_paths_set = {str(p) for p in deleted_paths}
        removed_groups = 0
        
        # all_groupsから削除されたファイルを除去
        groups_to_remove = []
        for group in self.all_groups:
            # グループ内の画像から削除されたものを除去
            group.images = [
                img for img in group.images 
                if str(img.path) not in deleted_paths_set
            ]
            # 1枚以下になったグループは削除対象
            if len(group.images) <= 1:
                groups_to_remove.append(group)
        
        # グループを削除
        for group in groups_to_remove:
            self.all_groups.remove(group)
            removed_groups += 1
        
        # ページ数を再計算
        if self.all_groups:
            self.total_pages = (len(self.all_groups) + self.GROUPS_PER_PAGE - 1) // self.GROUPS_PER_PAGE
            # 現在ページが範囲外になった場合は調整
            if self.current_page >= self.total_pages:
                self.current_page = max(0, self.total_pages - 1)
            # 現在ページを再表示
            self._display_current_page()
        else:
            self.clear()
            self.empty_label.setText("類似画像はありません")
            self.empty_label.setVisible(True)
        
        return removed_groups
    
    def _get_all_cards(self) -> List[ImageCard]:
        """現在のページの全カードを取得"""
        cards = []
        for widget in self.group_widgets:
            cards.extend(widget.cards)
        return cards
    
    def select_next_image(self):
        """次の画像を選択"""
        cards = self._get_all_cards()
        if not cards:
            return
        
        # 現在のフォーカスを解除
        if 0 <= self._focus_index < len(cards):
            cards[self._focus_index].set_focused(False)
        
        # インデックスを進める
        self._focus_index += 1
        if self._focus_index >= len(cards):
            # 次のページへ？とりあえずループさせたりせず止めるか、ページ送り機能を実装するか
            # ここでは現在のページの最後までいったら止める
            self._focus_index = len(cards) - 1
        
        self._update_focus(cards)
    
    def select_prev_image(self):
        """前の画像を選択"""
        cards = self._get_all_cards()
        if not cards:
            return
        
        # 現在のフォーカスを解除
        if 0 <= self._focus_index < len(cards):
            cards[self._focus_index].set_focused(False)
        
        # インデックスを戻す
        self._focus_index -= 1
        if self._focus_index < 0:
            self._focus_index = 0
        
        self._update_focus(cards)
    
    def _update_focus(self, cards: List[ImageCard]):
        """フォーカスを更新し、シグナルを発行"""
        if not cards or self._focus_index < 0 or self._focus_index >= len(cards):
            return
        
        card = cards[self._focus_index]
        card.set_focused(True)
        self.image_selected.emit(card.image_info)
        
        # 表示領域に入るようにスクロール
        self.ensureWidgetVisible(card)
    
    def _on_selection_changed(self, image_info, is_delete):
        """選択変更時"""
        count = sum(len(w.get_files_to_delete()) for w in self.group_widgets)
        self.files_to_delete_changed.emit(count)
        
        # クリックされたカードにフォーカス移動（もしクリック経由なら）
        # ここでは直接判定できないが、クリックイベントは別ルートで来る
    
    def _on_card_clicked_from_group(self, image_info):
        """グループからカードクリックシグナルを受信"""
        # フォーカスインデックスを更新
        cards = self._get_all_cards()
        for i, card in enumerate(cards):
            if card.image_info == image_info:
                # 古いフォーカス解除
                if 0 <= self._focus_index < len(cards):
                    cards[self._focus_index].set_focused(False)
                
                self._focus_index = i
                card.set_focused(True)
                break
        
        self.image_selected.emit(image_info)


class BlurredImageCard(QFrame):
    """ブレ画像用のカードウィジェット"""
    
    selection_changed = Signal(object, bool)
    clicked = Signal(object)  # image_info をシグナルで送信
    THUMBNAIL_SIZE = 120
    
    def __init__(self, image_info: ImageInfo, rank: int, parent=None):
        super().__init__(parent)
        self.image_info = image_info
        self.rank = rank  # 順位
        self.is_marked_delete = False
        self.is_focused = False

        self._thumbnail_loaded = False
        self._setup_ui()
        self._start_thumbnail_load()
    
    def _setup_ui(self):
        self.setObjectName("blurredImageCard")
        self.setFixedSize(200, 300)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        # 順位表示
        rank_label = QLabel(f"#{self.rank}")
        rank_label.setAlignment(Qt.AlignCenter)
        rank_label.setStyleSheet(
            "background-color: #e74c3c; color: white; font-weight: bold; "
            "font-size: 14px; padding: 4px 8px; border-radius: 4px;"
        )
        layout.addWidget(rank_label, alignment=Qt.AlignCenter)
        
        # サムネイルプレースホルダー
        ext = self.image_info.path.suffix.upper()
        self.thumbnail_label = QLabel(f"🖼️\n{ext}")
        self.thumbnail_label.setFixedSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet(
            "background-color: #3c3c3c; border-radius: 4px; border: 1px solid #4a4a4a; "
            "color: #808080; font-size: 24px;"
        )
        layout.addWidget(self.thumbnail_label, alignment=Qt.AlignCenter)
        
        # ファイル名
        filename = self.image_info.path.name
        if len(filename) > 22:
            filename = filename[:19] + "..."
        self.name_label = QLabel(filename)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.name_label.setToolTip(str(self.image_info.path))
        layout.addWidget(self.name_label)
        
        # 鮮明度スコア（大きく表示）
        sharpness = self.image_info.sharpness_score
        sharpness_desc = get_sharpness_label(sharpness)
        
        if sharpness < 50:
            color = "#e74c3c"  # かなりブレ - 赤
        elif sharpness < 100:
            color = "#e67e22"  # ブレ - オレンジ
        elif sharpness < 200:
            color = "#f39c12"  # やや不鮮明 - 黄
        elif sharpness < 500:
            color = "#b0b0b0"  # 普通 - グレー
        else:
            color = "#2ecc71"  # 鮮明 - 緑
        
        self.sharpness_label = QLabel(f"🔍 {sharpness:.0f}\n{sharpness_desc}")
        self.sharpness_label.setAlignment(Qt.AlignCenter)
        self.sharpness_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.sharpness_label)
        
        # 削除チェックボックス
        self.delete_checkbox = QCheckBox("削除対象")
        self.delete_checkbox.setStyleSheet("font-size: 11px; margin-top: 4px;")
        self.delete_checkbox.stateChanged.connect(self._on_checkbox_changed)
        layout.addWidget(self.delete_checkbox, alignment=Qt.AlignCenter)
    
    def _start_thumbnail_load(self):
        """非同期でサムネイル読み込みを開始"""
        if self._thumbnail_loaded:
            return
        
        path_str = str(self.image_info.path)
        
        if path_str in _thumbnail_cache:
            self.thumbnail_label.setPixmap(_thumbnail_cache[path_str])
            self._thumbnail_loaded = True
            return
        
        loader = ThumbnailLoader(path_str, self.THUMBNAIL_SIZE)
        loader.signals.finished.connect(self._on_thumbnail_loaded, Qt.QueuedConnection)
        _thread_pool.start(loader)
    
    @Slot(str, object)
    def _on_thumbnail_loaded(self, path: str, pixmap):
        if pixmap is not None and str(self.image_info.path) == path:
            self.thumbnail_label.setPixmap(pixmap)
            self._thumbnail_loaded = True
        elif pixmap is None and str(self.image_info.path) == path:
            self.thumbnail_label.setText("読込失敗")
    
    def _on_checkbox_changed(self, state):
        # PySide6のstateChangedは整数を送信 (Checked=2, Unchecked=0)
        self.is_marked_delete = (state == Qt.CheckState.Checked.value)
        self._update_style()
        self.selection_changed.emit(self.image_info, self.is_marked_delete)
    
    def _update_style(self):
        if self.is_focused:
            if self.is_marked_delete:
                self.setStyleSheet("""
                    #blurredImageCard {
                        background-color: #ffdce0; /* 薄い赤 */
                        border: 3px solid #00ffff;
                        border-radius: 8px;
                    }
                    QLabel { color: black; }
                    QCheckBox { color: black; }
                """)
            else:
                self.setStyleSheet("""
                    #blurredImageCard {
                        background-color: white;
                        border: 3px solid #00ffff;
                        border-radius: 8px;
                    }
                    QLabel { color: black; }
                    QCheckBox { color: black; }
                """)
        elif self.is_marked_delete:
            self.setStyleSheet(DarkTheme.get_card_style("delete"))
        else:
            self.setStyleSheet(DarkTheme.get_card_style("normal"))
    
    def set_focused(self, focused: bool):
        """フォーカス状態を設定"""
        if self.is_focused != focused:
            self.is_focused = focused
            self._update_style()
    
    def set_delete(self, delete: bool):
        self.delete_checkbox.blockSignals(True)
        self.delete_checkbox.setChecked(delete)
        self.delete_checkbox.blockSignals(False)
        self.is_marked_delete = delete
        self._update_style()
    
    def mousePressEvent(self, event):
        """シングルクリックでプレビュー表示"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.image_info)
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """ダブルクリックで画像をデフォルトアプリで開く"""
        if event.button() == Qt.LeftButton:
            open_image_with_default_app(self.image_info.path)
        super().mouseDoubleClickEvent(event)


class BlurredImagesGridWidget(QScrollArea):
    """
    ブレ画像一覧表示ウィジェット（ページネーション対応）
    
    類似画像とは関係なく、鮮明度スコアが低い（ブレている）画像を
    降順に並べて表示する
    """
    
    IMAGES_PER_PAGE = 50
    
    files_to_delete_changed = Signal(int)
    image_selected = Signal(object)  # image_info
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: List[BlurredImageCard] = []
        self.all_images: List[ImageInfo] = []
        self.current_page = 0
        self.total_pages = 0
        self._focus_index = -1
        self._setup_ui()
    
    def _setup_ui(self):
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.container = QWidget()
        self.container.setStyleSheet("background-color: #1e1e1e;")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(10)
        
        # 初期メッセージ
        self.empty_label = QLabel("ブレ画像がここに表示されます")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #808080; font-size: 16px; padding: 40px;")
        self.layout.addWidget(self.empty_label)
        
        self.pagination_widget = None
        self.grid_widget = None
        
        self.layout.addStretch()
        self.setWidget(self.container)
    
    def _create_pagination_controls(self):
        """ページネーションコントロールを作成"""
        if self.pagination_widget:
            self.pagination_widget.deleteLater()
        
        self.pagination_widget = QWidget()
        self.pagination_widget.setStyleSheet("background-color: transparent;")
        
        self.pagination_layout = QHBoxLayout(self.pagination_widget)
        self.pagination_layout.setContentsMargins(0, 20, 0, 20)
        self.pagination_layout.setSpacing(10)
        self.pagination_layout.setAlignment(Qt.AlignCenter)
        
        return self.pagination_widget
    
    def _update_pagination_state(self):
        """ページネーション状態を更新"""
        if not self.pagination_widget:
            return
        
        # 既存のボタンを削除
        while self.pagination_layout.count():
            item = self.pagination_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if self.total_pages <= 1:
            return
            
        # 前へボタン
        prev_btn = QPushButton("◀")
        prev_btn.setFixedSize(58, 40)
        prev_btn.setEnabled(self.current_page > 0)
        prev_btn.clicked.connect(self._go_prev_page)
        self.pagination_layout.addWidget(prev_btn)
        
        # ページ番号ボタン
        start_page = max(0, self.current_page - 2)
        end_page = min(self.total_pages - 1, self.current_page + 2)
        
        # 最初のページ
        if start_page > 0:
            self._add_page_button(0)
            if start_page > 1:
                lbl = QLabel("...")
                lbl.setStyleSheet("color: #888;")
                self.pagination_layout.addWidget(lbl)
        
        # 範囲内のページ
        for i in range(start_page, end_page + 1):
            self._add_page_button(i, i == self.current_page)
            
        # 最後のページ
        if end_page < self.total_pages - 1:
            if end_page < self.total_pages - 2:
                lbl = QLabel("...")
                lbl.setStyleSheet("color: #888;")
                self.pagination_layout.addWidget(lbl)
            self._add_page_button(self.total_pages - 1)
            
        # 次へボタン
        next_btn = QPushButton("▶")
        next_btn.setFixedSize(58, 40)
        next_btn.setEnabled(self.current_page < self.total_pages - 1)
        next_btn.clicked.connect(self._go_next_page)
        self.pagination_layout.addWidget(next_btn)
        
        # ラベル
        info_label = QLabel(f" {self.current_page + 1}/{self.total_pages} ")
        info_label.setStyleSheet("color: #aaa; margin-left: 10px; font-weight: bold;")
        self.pagination_layout.addWidget(info_label)

    def _add_page_button(self, page_index: int, is_current: bool = False):
        """ページ番号ボタンを追加"""
        btn = QPushButton(str(page_index + 1))
        btn.setFixedSize(58, 40)
        btn.setCheckable(True)
        btn.setChecked(is_current)
        if is_current:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #00ffff;
                    color: #1e1e1e;
                    font-weight: bold;
                    border: none;
                    border-radius: 8px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    color: #e0e0e0;
                    border: none;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
            """)
        btn.clicked.connect(lambda checked=False, idx=page_index: self._go_to_page(idx))
        self.pagination_layout.addWidget(btn)

    def _go_to_page(self, page_index: int):
        if 0 <= page_index < self.total_pages and page_index != self.current_page:
            self.current_page = page_index
            self._display_current_page()
    
    def _go_prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._display_current_page()
    
    def _go_next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._display_current_page()
    
    def _display_current_page(self):
        """現在のページを表示"""
        # 既存ウィジェットをクリア
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()
        
        clear_thumbnail_cache()
        
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            if item.widget() and item.widget() != self.empty_label:
                if item.widget() != self.pagination_widget:
                    item.widget().deleteLater()
        
        self.empty_label.setVisible(False)
        
        # 現在ページの画像を取得
        start_idx = self.current_page * self.IMAGES_PER_PAGE
        end_idx = min(start_idx + self.IMAGES_PER_PAGE, len(self.all_images))
        page_images = self.all_images[start_idx:end_idx]
        
        # フォーカスリセット
        self._focus_index = -1
        
        # グリッドレイアウトで表示
        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background-color: transparent;")
        grid_layout = QGridLayout(self.grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(15)
        
        cols = 5  # 1行あたりのカード数
        for i, image_info in enumerate(page_images):
            rank = start_idx + i + 1  # 全体での順位
            card = BlurredImageCard(image_info, rank)
            card.clicked.connect(self._on_card_clicked)
            card.selection_changed.connect(self._on_selection_changed)
            self.cards.append(card)
            row = i // cols
            col = i % cols
            grid_layout.addWidget(card, row, col, alignment=Qt.AlignTop | Qt.AlignLeft)
        
        self.layout.addWidget(self.grid_widget)
        
        # ページネーションコントロールを追加
        pagination = self._create_pagination_controls()
        self.layout.addWidget(pagination)
        self._update_pagination_state()
        
        self.layout.addStretch()
        
        self.verticalScrollBar().setValue(0)
    
    def clear(self):
        """グリッドをクリア"""
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()
        self.all_images.clear()
        self.current_page = 0
        self.total_pages = 0
        clear_thumbnail_cache()
        self.empty_label.setVisible(True)
        
        if self.pagination_widget:
            self.pagination_widget.deleteLater()
            self.pagination_widget = None
        if self.grid_widget:
            self.grid_widget.deleteLater()
            self.grid_widget = None
    
    def set_images(self, images: List[ImageInfo]):
        """ブレ画像を設定（既に鮮明度昇順にソートされていること）"""
        self.clear()
        
        if not images:
            self.empty_label.setText("ブレ画像は見つかりませんでした")
            return
        
        self.all_images = images
        self.total_pages = (len(images) + self.IMAGES_PER_PAGE - 1) // self.IMAGES_PER_PAGE
        self.current_page = 0
        
        self._display_current_page()
    
    def _on_selection_changed(self, image_info, is_delete):
        """選択変更時"""
        count = sum(1 for card in self.cards if card.is_marked_delete)
        self.files_to_delete_changed.emit(count)
    
    def select_all(self):
        """現在ページの全画像を削除対象に選択"""
        for card in self.cards:
            card.set_delete(True)
        count = sum(1 for card in self.cards if card.is_marked_delete)
        self.files_to_delete_changed.emit(count)
    
    def clear_selection(self):
        """選択を解除"""
        for card in self.cards:
            card.set_delete(False)
        self.files_to_delete_changed.emit(0)
    
    def get_all_files_to_delete(self) -> List[Path]:
        """削除対象ファイルを取得"""
        return [card.image_info.path for card in self.cards if card.is_marked_delete]
    
    def remove_deleted_files(self, deleted_paths: List[Path]):
        """
        削除されたファイルをUIから即時除去
        
        Args:
            deleted_paths: 削除されたファイルパスのリスト
        """
        deleted_paths_set = {str(p) for p in deleted_paths}
        
        # all_imagesから削除されたファイルを除去
        self.all_images = [
            img for img in self.all_images 
            if str(img.path) not in deleted_paths_set
        ]
        
        # ページ数を再計算
        if self.all_images:
            self.total_pages = (len(self.all_images) + self.IMAGES_PER_PAGE - 1) // self.IMAGES_PER_PAGE
            # 現在ページが範囲外になった場合は調整
            if self.current_page >= self.total_pages:
                self.current_page = max(0, self.total_pages - 1)
            # 現在ページを再表示
            self._display_current_page()
        else:
            self.clear()
            self.empty_label.setText("ブレ画像はありません")
            self.empty_label.setVisible(True)
        
        return removed_count

    def select_next_image(self):
        """次の画像を選択"""
        if not self.cards:
            return
        
        # 現在のフォーカスを解除
        if 0 <= self._focus_index < len(self.cards):
            self.cards[self._focus_index].set_focused(False)
        
        # インデックスを進める
        self._focus_index += 1
        if self._focus_index >= len(self.cards):
            self._focus_index = len(self.cards) - 1
        
        self._update_focus()
    
    def select_prev_image(self):
        """前の画像を選択"""
        if not self.cards:
            return
        
        # 現在のフォーカスを解除
        if 0 <= self._focus_index < len(self.cards):
            self.cards[self._focus_index].set_focused(False)
        
        # インデックスを戻す
        self._focus_index -= 1
        if self._focus_index < 0:
            self._focus_index = 0
        
        self._update_focus()
    
    def _update_focus(self):
        """フォーカスを更新し、シグナルを発行"""
        if not self.cards or self._focus_index < 0 or self._focus_index >= len(self.cards):
            return
        
        card = self.cards[self._focus_index]
        card.set_focused(True)
        self.image_selected.emit(card.image_info)
        
        # 表示領域に入るようにスクロール
        self.ensureWidgetVisible(card)

    def _on_card_clicked(self, image_info):
        """カードクリック時の処理"""
        # フォーカスインデックスを更新
        for i, card in enumerate(self.cards):
            if card.image_info == image_info:
                # 古いフォーカス解除
                if 0 <= self._focus_index < len(self.cards):
                    self.cards[self._focus_index].set_focused(False)
                
                self._focus_index = i
                card.set_focused(True)
                break
        
        self.image_selected.emit(image_info)

