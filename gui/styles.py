# -*- coding: utf-8 -*-
"""
SpectraMatch - Styles Module
ダークモードテーマ (Fusion style) とQSSスタイルシートを定義
アクセントカラー: シアン (#00ffff) / パープル系
"""


class DarkTheme:
    """ダークモードテーマの定義"""
    
    COLORS = {
        # 背景色
        "bg_primary": "#1e1e1e",
        "bg_secondary": "#2b2b2b",
        "bg_tertiary": "#3c3c3c",
        "bg_card": "#2d2d2d",
        "bg_hover": "#404040",
        
        # テキスト色
        "text_primary": "#ffffff",
        "text_secondary": "#b0b0b0",
        "text_muted": "#808080",
        
        # アクセントカラー (シアン / パープル)
        "accent_primary": "#00ffff",
        "accent_secondary": "#9b59b6",
        "accent_hover": "#00cccc",
        "accent_success": "#2ecc71",
        "accent_warning": "#f39c12",
        "accent_danger": "#e74c3c",
        
        # ボーダー
        "border": "#4a4a4a",
        "border_focus": "#00ffff",
        
        # 特殊
        "exact_match": "#e74c3c",
        "similar": "#3498db",
        "selected_keep": "#2ecc71",
        "selected_delete": "#e74c3c",
    }
    
    @classmethod
    def get_stylesheet(cls) -> str:
        c = cls.COLORS
        return f"""
        /* ===== グローバル ===== */
        QMainWindow {{
            background-color: {c["bg_primary"]};
        }}
        
        QWidget {{
            background-color: {c["bg_primary"]};
            color: {c["text_primary"]};
            font-family: "Segoe UI", "Yu Gothic UI", "Meiryo", sans-serif;
            font-size: 13px;
        }}
        
        /* ===== サイドバー ===== */
        QWidget#sidebarWidget {{
            background-color: {c["bg_secondary"]};
            border-right: 1px solid {c["border"]};
        }}
        
        /* ===== ボタン ===== */
        QPushButton {{
            background-color: {c["bg_tertiary"]};
            color: {c["text_primary"]};
            border: 1px solid {c["border"]};
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
            min-height: 32px;
        }}
        
        QPushButton:hover {{
            background-color: {c["accent_primary"]};
            color: {c["bg_primary"]};
            border-color: {c["accent_primary"]};
        }}
        
        QPushButton:pressed {{
            background-color: {c["accent_hover"]};
        }}
        
        QPushButton:disabled {{
            background-color: {c["bg_tertiary"]};
            color: {c["text_muted"]};
        }}
        
        QPushButton#scanButton {{
            background-color: {c["accent_primary"]};
            color: {c["bg_primary"]};
            font-size: 14px;
        }}
        
        QPushButton#scanButton:hover {{
            background-color: {c["accent_hover"]};
        }}
        
        QPushButton#deleteButton {{
            background-color: {c["accent_danger"]};
            border-color: {c["accent_danger"]};
        }}
        
        QPushButton#deleteButton:hover {{
            background-color: #c0392b;
        }}
        
        /* ===== スライダー ===== */
        QSlider::groove:horizontal {{
            height: 6px;
            background: {c["bg_tertiary"]};
            border-radius: 3px;
        }}
        
        QSlider::handle:horizontal {{
            background: {c["accent_primary"]};
            width: 18px;
            height: 18px;
            margin: -6px 0;
            border-radius: 9px;
        }}
        
        QSlider::handle:horizontal:hover {{
            background: {c["accent_hover"]};
        }}
        
        QSlider::sub-page:horizontal {{
            background: {c["accent_primary"]};
            border-radius: 3px;
        }}
        
        /* ===== プログレスバー ===== */
        QProgressBar {{
            background-color: {c["bg_tertiary"]};
            border: none;
            border-radius: 4px;
            height: 8px;
            text-align: center;
        }}
        
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {c["accent_primary"]}, stop:1 {c["accent_secondary"]});
            border-radius: 4px;
        }}
        
        /* ===== リストウィジェット ===== */
        QListWidget {{
            background-color: {c["bg_tertiary"]};
            border: 1px solid {c["border"]};
            border-radius: 4px;
            padding: 4px;
        }}
        
        QListWidget::item {{
            padding: 8px;
            border-radius: 4px;
        }}
        
        QListWidget::item:selected {{
            background-color: {c["accent_primary"]};
            color: {c["bg_primary"]};
        }}
        
        QListWidget::item:hover {{
            background-color: {c["bg_hover"]};
        }}
        
        /* ===== スクロールエリア ===== */
        QScrollArea {{
            border: none;
            background-color: {c["bg_primary"]};
        }}
        
        QScrollBar:vertical {{
            background: {c["bg_secondary"]};
            width: 10px;
            border-radius: 5px;
        }}
        
        QScrollBar::handle:vertical {{
            background: {c["bg_tertiary"]};
            border-radius: 5px;
            min-height: 30px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background: {c["accent_primary"]};
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        
        QScrollBar:horizontal {{
            background: {c["bg_secondary"]};
            height: 10px;
            border-radius: 5px;
        }}
        
        QScrollBar::handle:horizontal {{
            background: {c["bg_tertiary"]};
            border-radius: 5px;
            min-width: 30px;
        }}
        
        QScrollBar::handle:horizontal:hover {{
            background: {c["accent_primary"]};
        }}
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}
        
        /* ===== ラベル ===== */
        QLabel {{
            color: {c["text_primary"]};
            background-color: transparent;
        }}
        
        QLabel#titleLabel {{
            font-size: 20px;
            font-weight: bold;
            color: {c["accent_primary"]};
        }}
        
        QLabel#sectionLabel {{
            font-size: 14px;
            font-weight: bold;
            color: {c["text_secondary"]};
            padding: 8px 0;
        }}
        
        /* ===== グループボックス ===== */
        QGroupBox {{
            background-color: {c["bg_secondary"]};
            border: 1px solid {c["border"]};
            border-radius: 6px;
            margin-top: 12px;
            padding: 12px;
            font-weight: bold;
        }}
        
        QGroupBox::title {{
            color: {c["text_primary"]};
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 2px 8px;
            background-color: {c["bg_tertiary"]};
            border-radius: 4px;
        }}
        
        /* ===== チェックボックス ===== */
        QCheckBox {{
            color: {c["text_primary"]};
            spacing: 6px;
        }}
        
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 2px solid {c["border"]};
            border-radius: 3px;
            background-color: {c["bg_tertiary"]};
        }}
        
        QCheckBox::indicator:checked {{
            background-color: {c["accent_danger"]};
            border-color: {c["accent_danger"]};
        }}
        
        QCheckBox::indicator:hover {{
            border-color: {c["accent_primary"]};
        }}
        
        /* ===== スプリッター ===== */
        QSplitter::handle {{
            background-color: {c["border"]};
        }}
        
        QSplitter::handle:horizontal {{
            width: 2px;
        }}
        
        QSplitter::handle:hover {{
            background-color: {c["accent_primary"]};
        }}
        
        /* ===== フレーム ===== */
        QFrame#imageCard {{
            background-color: {c["bg_card"]};
            border: 2px solid {c["border"]};
            border-radius: 6px;
        }}
        
        QFrame#imageCard:hover {{
            border-color: {c["accent_primary"]};
        }}
        
        QFrame#groupFrame {{
            background-color: {c["bg_secondary"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
        }}
        
        QFrame#exactMatchGroup {{
            background-color: {c["bg_secondary"]};
            border-left: 4px solid {c["exact_match"]};
        }}
        
        QFrame#similarGroup {{
            background-color: {c["bg_secondary"]};
            border-left: 4px solid {c["similar"]};
        }}
        """
    
    @classmethod
    def get_card_style(cls, state: str = "normal") -> str:
        c = cls.COLORS
        if state == "keep":
            return f"background-color: {c['bg_card']}; border: 3px solid {c['selected_keep']}; border-radius: 6px;"
        elif state == "delete":
            return f"background-color: {c['bg_card']}; border: 3px solid {c['selected_delete']}; border-radius: 6px;"
        return f"background-color: {c['bg_card']}; border: 2px solid {c['border']}; border-radius: 6px;"
