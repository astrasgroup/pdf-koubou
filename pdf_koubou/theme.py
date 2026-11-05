"""日本語化と外観（色味）の切り替え。"""
from __future__ import annotations

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, Qt, QTranslator
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# 名前: (ウィンドウ, 入力欄, 文字, ボタン, 強調, ページ背景, 薄い文字)
THEMES = {
    "light": ("ライト", "#f3f4f6", "#ffffff", "#1f2328", "#e9ebef", "#2b6cb0", "#8a929c", "#6b7280"),
    "dark": ("ダーク", "#202226", "#2a2d32", "#e6e8eb", "#2f3237", "#4a8fe0", "#3a3d43", "#9aa1aa"),
    "beige": ("やわらかい（ベージュ）", "#f4efe6", "#fbf8f2", "#3b3329", "#e8e0d2", "#b0703a", "#a89c88", "#7a6f60"),
    "bluegray": ("ブルーグレー", "#e7edf3", "#f6f9fc", "#1d2a38", "#d6e0ea", "#2f6f9f", "#7d8fa3", "#5d6b7a"),
    "green": ("グリーン", "#e9f1ea", "#f7fbf7", "#1f2e22", "#d7e6d9", "#2f7d4a", "#86a08b", "#5b6e5f"),
    "contrast": ("見やすさ重視（高コントラスト）", "#ffffff", "#ffffff", "#000000", "#e6e6e6", "#0040c0", "#505050", "#333333"),
}
THEME_ORDER = ["system", "light", "dark", "beige", "bluegray", "green", "contrast"]
THEME_LABELS = {"system": "Windows の設定に合わせる", **{k: v[0] for k, v in THEMES.items()}}

_translators = []


def install_japanese(app: QApplication):
    """OK / キャンセル / 保存 などの Qt 標準の文言を日本語にする。"""
    QLocale.setDefault(QLocale(QLocale.Language.Japanese, QLocale.Country.Japan))
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name in ("qtbase_ja", "qt_ja"):
        tr = QTranslator(app)
        if tr.load(name, path):
            app.installTranslator(tr)
            _translators.append(tr)


def settings() -> QSettings:
    return QSettings("PDFKoubou", "PDFKoubou")


def saved_theme() -> str:
    t = settings().value("theme", "system")
    return t if t in THEME_LABELS else "system"


def resolve(name: str) -> str:
    if name != "system":
        return name
    scheme = QApplication.styleHints().colorScheme()
    return "dark" if scheme == Qt.ColorScheme.Dark else "light"


def apply_theme(app: QApplication, name: str) -> dict:
    """テーマを適用し、ページ背景などの色を返す。"""
    settings().setValue("theme", name)
    key = resolve(name)
    _, window, base, text, button, hl, page_bg, muted = THEMES[key]
    dark = QColor(window).lightness() < 128
    app.setStyle("Fusion")
    p = QPalette()
    W, B, T, BT, H = QColor(window), QColor(base), QColor(text), QColor(button), QColor(hl)
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        p.setColor(group, QPalette.ColorRole.Window, W)
        p.setColor(group, QPalette.ColorRole.WindowText, T)
        p.setColor(group, QPalette.ColorRole.Base, B)
        p.setColor(group, QPalette.ColorRole.AlternateBase, BT)
        p.setColor(group, QPalette.ColorRole.Text, T)
        p.setColor(group, QPalette.ColorRole.Button, BT)
        p.setColor(group, QPalette.ColorRole.ButtonText, T)
        p.setColor(group, QPalette.ColorRole.Highlight, H)
        p.setColor(group, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        p.setColor(group, QPalette.ColorRole.ToolTipBase, B)
        p.setColor(group, QPalette.ColorRole.ToolTipText, T)
        p.setColor(group, QPalette.ColorRole.PlaceholderText, QColor(muted))
        p.setColor(group, QPalette.ColorRole.Link, H)
        p.setColor(group, QPalette.ColorRole.Light, W.lighter(130))
        p.setColor(group, QPalette.ColorRole.Midlight, W.lighter(115) if dark else W.darker(105))
        p.setColor(group, QPalette.ColorRole.Mid, W.lighter(160) if dark else W.darker(130))
        p.setColor(group, QPalette.ColorRole.Dark, W.darker(150))
        p.setColor(group, QPalette.ColorRole.Shadow, QColor("#000000"))
    dis = QColor(muted)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, dis)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, W)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, BT)
    app.setPalette(p)
    app.setStyleSheet(
        f"QToolBar{{border:none;spacing:2px;padding:2px;}}"
        f"QToolButton{{padding:4px 8px;border-radius:4px;}}"
        f"QToolButton:hover{{background:{H.name()}33;}}"
        f"QToolButton:checked{{background:{H.name()};color:#ffffff;}}"
        f"QStatusBar{{color:{muted};}}")
    return {"page_bg": page_bg, "highlight": hl, "window": window, "text": text, "muted": muted,
            "dark": dark}
