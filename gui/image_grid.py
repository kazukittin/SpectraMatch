# -*- coding: utf-8 -*-
"""
SpectraMatch - Image Grid Widget (v2 - Paginated)
類似画像グループを表示するグリッドウィジェット

4万枚規模対応:
- ページネーション（50グループ/ページ）
- サムネイルの遅延読み込み
- メモリ効率的なウィジェット管理
"""

from pathlib import Path
from typing import List, Optional, Dict
from enum import Enum

from PySide6.QtCore import Qt, Signal, QSize, QTimer
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
    """鮮明度スコアを分かりやすいラベルに変換"""
    if score < 100:
        return "ブレ"
    elif score < 300:
        return "やや不鮮明"
    elif score < 500:
        return "普通"
    else:
        return "鮮明"


def clear_thumbnail_cache():
    """サムネイルキャッシュをクリア"""
    global _thumbnail_cache
    _thumbnail_cache.clear()


class ImageCard(QFrame):
    """個別画像カードウィジェット（軽量版）"""
    
    selection_changed = Signal(object, bool)
    THUMBNAIL_SIZE = 140
    
    def __init__(self, image_info: ImageInfo, parent=None):
        super().__init__(parent)
        self.image_info = image_info
        self.is_marked_delete = False
        self._thumbnail_loaded = False
        self._setup_ui()
        # サムネイルは遅延読み込み
        QTimer.singleShot(50, self._load_thumbnail_deferred)
    
    def _setup_ui(self):
        self.setObjectName("imageCard")
        self.setFixedSize(180, 300)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        
        # サムネイルプレースホルダー
        self.thumbnail_label = QLabel("読込中...")
        self.thumbnail_label.setFixedSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet(
            "background-color: #3c3c3c; border-radius: 4px; border: 1px solid #4a4a4a; color: #808080;"
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
        
        if sharpness < 100:
            color = "#e74c3c"
        elif sharpness < 300:
            color = "#f39c12"
        elif sharpness < 500:
            color = "#b0b0b0"
        else:
            color = "#2ecc71"
        
        self.sharpness_label = QLabel(f"🔍 {sharpness:.0f} ({sharpness_desc})")
        self.sharpness_label.setAlignment(Qt.AlignCenter)
        self.sharpness_label.setStyleSheet(f"color: {color}; font-size: 10px;")
        layout.addWidget(self.sharpness_label)
        
        # 削除チェックボックス
        self.delete_checkbox = QCheckBox("削除対象")
        self.delete_checkbox.setStyleSheet("font-size: 11px; margin-top: 4px;")
        self.delete_checkbox.stateChanged.connect(self._on_checkbox_changed)
        layout.addWidget(self.delete_checkbox, alignment=Qt.AlignCenter)
    
    def _load_thumbnail_deferred(self):
        """遅延サムネイル読み込み"""
        if self._thumbnail_loaded:
            return
        self._load_thumbnail()
    
    def _load_thumbnail(self):
        """サムネイルを読み込み（キャッシュ対応・日本語パス対応）"""
        global _thumbnail_cache
        
        path_str = str(self.image_info.path)
        
        # キャッシュチェック
        if path_str in _thumbnail_cache:
            self.thumbnail_label.setPixmap(_thumbnail_cache[path_str])
            self._thumbnail_loaded = True
            return
        
        try:
            # 日本語パス対応: np.fromfile + cv2.imdecode
            stream = np.fromfile(path_str, dtype=np.uint8)
            if stream is None or len(stream) == 0:
                self.thumbnail_label.setText("読込失敗")
                return
            
            img = cv2.imdecode(stream, cv2.IMREAD_COLOR)
            if img is None:
                self.thumbnail_label.setText("読込失敗")
                return
            
            h, w = img.shape[:2]
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            scale = min(self.THUMBNAIL_SIZE / w, self.THUMBNAIL_SIZE / h)
            new_w, new_h = int(w * scale), int(h * scale)
            resized = cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
            qimg = QImage(resized.data, new_w, new_h, new_w * 3, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            
            # キャッシュに保存（上限チェック）
            if len(_thumbnail_cache) >= _CACHE_MAX_SIZE:
                oldest_key = next(iter(_thumbnail_cache))
                del _thumbnail_cache[oldest_key]
            
            _thumbnail_cache[path_str] = pixmap
            self.thumbnail_label.setPixmap(pixmap)
            self._thumbnail_loaded = True
            
        except Exception as e:
            self.thumbnail_label.setText("エラー")
    
    def _on_checkbox_changed(self, state):
        self.is_marked_delete = (state == Qt.Checked)
        self._update_style()
        self.selection_changed.emit(self.image_info, self.is_marked_delete)
    
    def _update_style(self):
        if self.is_marked_delete:
            self.setStyleSheet(DarkTheme.get_card_style("delete"))
        else:
            self.setStyleSheet(DarkTheme.get_card_style("normal"))
    
    def set_delete(self, delete: bool):
        self.delete_checkbox.blockSignals(True)
        self.delete_checkbox.setChecked(delete)
        self.delete_checkbox.blockSignals(False)
        self.is_marked_delete = delete
        self._update_style()


class SimilarityGroupWidget(QGroupBox):
    """類似グループ表示ウィジェット"""
    
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
        scroll.setFixedHeight(330)
        scroll.setStyleSheet("background-color: transparent; border: none;")
        
        grid_container = QWidget()
        grid_container.setStyleSheet("background-color: transparent;")
        grid_layout = QHBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(12)
        
        for image_info in self.group.images:
            card = ImageCard(image_info)
            self.cards.append(card)
            grid_layout.addWidget(card)
        
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
    - 50グループ/ページ
    - ページ切り替えボタン
    - メモリ効率的なウィジェット管理
    """
    
    GROUPS_PER_PAGE = 50
    
    files_to_delete_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.group_widgets: List[SimilarityGroupWidget] = []
        self.all_groups: List[SimilarityGroup] = []
        self.current_page = 0
        self.total_pages = 0
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
        self.pagination_widget.setStyleSheet("background-color: #2b2b2b; border-radius: 8px; padding: 10px;")
        
        layout = QHBoxLayout(self.pagination_widget)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(20)
        
        # 前のページボタン
        self.prev_btn = QPushButton("◀ 前のページ")
        self.prev_btn.setFixedHeight(36)
        self.prev_btn.clicked.connect(self._go_prev_page)
        layout.addWidget(self.prev_btn)
        
        layout.addStretch()
        
        # ページ情報
        self.page_label = QLabel()
        self.page_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.page_label)
        
        layout.addStretch()
        
        # 次のページボタン
        self.next_btn = QPushButton("次のページ ▶")
        self.next_btn.setFixedHeight(36)
        self.next_btn.clicked.connect(self._go_next_page)
        layout.addWidget(self.next_btn)
        
        return self.pagination_widget
    
    def _update_pagination_state(self):
        """ページネーション状態を更新"""
        if not self.pagination_widget:
            return
        
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.page_label.setText(
            f"ページ {self.current_page + 1} / {self.total_pages} "
            f"(全{len(self.all_groups)}グループ)"
        )
    
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
        
        # グループウィジェットを作成
        for group in page_groups:
            widget = SimilarityGroupWidget(group)
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
