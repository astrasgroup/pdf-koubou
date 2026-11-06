"""PDF工房 メイン画面。"""
from __future__ import annotations

import copy
import itertools
import os
import shutil
import sys
import tempfile

import fitz
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QColor, QIcon, QImage, QKeySequence,
                           QPainterPath, QPixmap, QPolygonF)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidgetItem,
                               QMainWindow, QMessageBox, QProgressDialog, QPushButton,
                               QRadioButton, QSlider, QSpinBox, QSplitter, QStackedWidget, QToolBar,
                               QToolButton,
                               QVBoxLayout, QWidget)

from . import convert, pagedialogs, pdfcore, theme
from .canvas import PageView
from .thumbs import ThumbList

APP_NAME = "PDF工房"
VERSION = "1.3"
_ver_counter = itertools.count(1)
WINDOWS: list["MainWindow"] = []
UNDO_LIMIT = 30

PRESET_COLORS = [("赤", "#d00000"), ("黒", "#000000"), ("青", "#1d4ed8"), ("緑", "#15803d"),
                 ("黄（マーカー向け）", "#f5d000"), ("白", "#ffffff")]

TOOLS = [
    # key, 表示名, ショートカット文字, 説明
    ("select", "選択", "V", "書き込みをクリックで選択・ドラッグで移動。ダブルクリックで文字を修正。Delete で削除。"),
    ("pan", "手のひら", "H", "ドラッグでページを動かします。"),
    ("text", "テキスト", "T", "クリックした場所にそのまま入力できます。外をクリックで確定、続けて別の場所をクリックで次の入力。"),
    ("pen", "ペン", "P", "ドラッグで手書きの線を引きます。"),
    ("rect", "四角", "R", "ドラッグで四角形を描きます。"),
    ("ellipse", "丸", "O", "ドラッグで丸（楕円）を描きます。"),
    ("hl", "マーカー", "M", "ドラッグした範囲に半透明の色を塗ります。"),
    ("stamp", "画像", "I", "ハンコなどの画像を置きます。クリックで置く、ドラッグで大きさ指定。"),
    ("eraser", "消しゴム", "E", "なぞった所を紙の色で塗って消します（スキャン画像の手書き向け）。"),
    ("erase_rect", "範囲消去□", "D", "四角で囲んだ中の文字・図・画像・注釈をデータごと消します。"),
    ("erase_ellipse", "範囲消去○", "F", "丸で囲んだ中を紙の色で塗りつぶし、注釈も消します。"),
    ("erase_lasso", "投げ縄消去", "L", "自由に囲んだ中を紙の色で塗りつぶし、注釈も消します。"),
    ("crop", "トリミング", "C", "残したい範囲をドラッグで囲みます。"),
]


def color_icon(hexc: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(QColor(hexc))
    return QIcon(pm)


def pix_to_qimage(pix: fitz.Pixmap) -> QImage:
    fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
    return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()


def ask_password(name: str):
    pw, ok = QInputDialog.getText(None, APP_NAME, f"「{name}」はパスワードで保護されています。\nパスワードを入力してください。",
                                  QLineEdit.EchoMode.Password)
    return pw if ok else None


class MainWindow(QMainWindow):
    def __init__(self, paths=None, doc=None):
        super().__init__()
        WINDOWS.append(self)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.doc: fitz.Document | None = None
        self.path: str | None = None
        self.overlays: list[list[dict]] = []
        self.cur = 0
        self.undo_stack, self.redo_stack = [], []
        self.modified = False
        self.doc_ver = 0
        self._bytes_cache = (None, None)
        self._pending_move = None
        self.zoom_mode = "width"
        self.zoom = 1.0
        self._thumb_queue = []
        self.tmpdir = tempfile.mkdtemp(prefix="pdfkoubou_")
        self.last_dir = os.path.join(os.path.expanduser("~"), "Documents")

        self.resize(1280, 860)
        self._build_ui()
        self.apply_colors(CURRENT_COLORS)
        self._update_title()
        self.setAcceptDrops(True)

        if doc is not None:
            self.set_document(doc, None, modified=True)
        elif paths:
            QTimer.singleShot(0, lambda: self.open_paths(paths))

    # ================================================================ UI
    def _build_ui(self):
        self.view = PageView()
        self.view.setAcceptDrops(False)
        self.view.viewport().setAcceptDrops(False)
        self.thumbs = ThumbList(self)
        self.thumbs.setMinimumWidth(170)
        self.thumbs.currentRowChanged.connect(self._thumb_clicked)
        self.thumbs.pagesMoved.connect(self.move_pages)
        self.thumbs.filesDropped.connect(self.insert_files)
        self.thumbs.contextRequested.connect(self._thumb_menu)

        self.welcome = QLabel("PDF・Word・Excel・PowerPoint・画像・テキストのファイルを、ここにドラッグしてください。\n"
                              "PDF 以外のファイルは、自動で PDF に変換して開きます。\n\n"
                              "または「開く」（Ctrl+O）からファイルを選びます。")
        self.welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome.setStyleSheet("QLabel{font-size:16px;background:palette(base);"
                                   "border:2px dashed palette(mid);margin:40px;border-radius:12px;}")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.view)

        split = QSplitter()
        split.addWidget(self.thumbs)
        split.addWidget(self.stack)
        split.setStretchFactor(1, 1)
        split.setSizes([190, 1090])
        self.setCentralWidget(split)

        v = self.view
        v.aboutToChange.connect(self._overlay_about_to_change)
        v.changed.connect(self._overlay_changed)
        v.moveBegin.connect(self._move_begin)
        v.moveCommit.connect(self._move_commit)
        v.regionChosen.connect(self._region_chosen)
        v.pageFlip.connect(lambda d: self.goto(self.cur + d))
        v.zoomStep.connect(self.zoom_step)
        v.toolKey.connect(self._tool_key)

        self._resize_timer = QTimer(self, singleShot=True, interval=150, timeout=self._refit)
        self._thumb_timer = QTimer(self, interval=0, timeout=self._render_thumb_batch)

        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self.statusBar().showMessage("ファイルを開いてください。")

    def _act(self, text, slot, shortcut=None, tip=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setStatusTip(tip)
        return a

    def _build_actions(self):
        A = self._act
        self.a_open = A("開く…", self.open_dialog, "Ctrl+O")
        self.a_newwin = A("新しいウィンドウ", lambda: MainWindow().show(), "Ctrl+N")
        self.a_from_images = A("画像からPDFを作成…", self.create_from_images)
        self.a_convert = A("ファイルをPDFに変換…", self.convert_dialog, "Ctrl+Shift+O",
                           "Word・Excel・PowerPoint・画像・テキストなどを PDF にします")
        self.a_save = A("上書き保存", self.save, "Ctrl+S")
        self.a_saveas = A("名前を付けて保存…", self.save_as, "Ctrl+Shift+S")
        self.a_print = A("印刷…", self.print_doc, "Ctrl+P")
        self.a_close = A("閉じる", self.close, "Ctrl+W")
        self.a_undo = A("元に戻す", self.undo, "Ctrl+Z")
        self.a_redo = A("やり直し", self.redo, "Ctrl+Y")
        self.a_del_overlay = A("選んだ書き込みを削除", lambda: self.view.delete_selected())
        self.a_rot_r = A("右に回転", lambda: self.rotate_pages(90), "Ctrl+R")
        self.a_rot_l = A("左に回転", lambda: self.rotate_pages(-90), "Ctrl+L")
        self.a_rot_dlg = A("ページの回転…", self.rotate_dialog, "Ctrl+Shift+R",
                           "方向・ページ範囲・奇数／偶数ページを指定して回転します")
        self.a_crop_dlg = A("ページのトリミング…", self.crop_dialog, "Ctrl+Shift+T",
                            "上下左右の余白・ページ範囲・奇数／偶数ページを指定してトリミングします")
        self.a_del_pages = A("ページを削除", self.delete_pages, "Ctrl+D")
        self.a_extract = A("ページを抽出…", self.extract_pages, "Ctrl+E")
        self.a_split = A("分割…", self.split_dialog)
        self.a_insert = A("PDF・画像を挿入（結合）…", self.insert_dialog, "Ctrl+I")
        self.a_blank = A("空白ページを挿入", self.insert_blank)
        self.a_uncrop = A("トリミングを解除…", self.uncrop)
        self.a_export_img = A("画像（PNG/JPEG）として書き出し…", self.export_images)
        self.a_ink = A("色ペンの書き込みを消す（赤・青など）…", self.remove_colored_ink)
        self.a_del_ink = A("手書き注釈（ペン）を削除…", lambda: self.delete_annots(True))
        self.a_del_annots = A("すべての注釈を削除…", lambda: self.delete_annots(False))
        self.a_prev = A("前のページ", lambda: self.goto(self.cur - 1), "Left")
        self.a_next = A("次のページ", lambda: self.goto(self.cur + 1), "Right")
        self.a_zin = A("拡大", lambda: self.zoom_step(1), "Ctrl++")
        self.a_zout = A("縮小", lambda: self.zoom_step(-1), "Ctrl+-")
        self.a_fitw = A("幅に合わせる", lambda: self.set_zoom_mode("width"), "Ctrl+1")
        self.a_fitp = A("ページ全体", lambda: self.set_zoom_mode("page"), "Ctrl+0")
        self.a_help = A("使い方", self.show_help, "F1")
        self.a_about = A("バージョン情報とライセンス", self.show_about)
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        for key in theme.THEME_ORDER:
            a = QAction(theme.THEME_LABELS[key], self, checkable=True)
            a.triggered.connect(lambda _=False, k=key: set_theme(k))
            self.theme_group.addAction(a)
            self.theme_actions[key] = a
        self.theme_actions[theme.saved_theme()].setChecked(True)

        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        for key, name, sc, tip in TOOLS:
            a = QAction(f"{name}", self, checkable=True)
            a.setToolTip(f"{name}（{sc}）\n{tip}")
            a.setStatusTip(tip)
            a.triggered.connect(lambda _=False, k=key: self.set_tool(k))
            self.tool_group.addAction(a)
            self.tool_actions[key] = a
        self.tool_actions["select"].setChecked(True)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("ファイル(&F)")
        for a in (self.a_open, self.a_newwin, None, self.a_convert, self.a_from_images, None, self.a_save, self.a_saveas,
                  None, self.a_export_img, self.a_print, None, self.a_close):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("編集(&E)")
        for a in (self.a_undo, self.a_redo, None, self.a_del_overlay):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("ページ(&P)")
        for a in (self.a_rot_dlg, self.a_rot_r, self.a_rot_l, None, self.a_crop_dlg, self.a_uncrop, None,
                  self.a_insert, self.a_blank, self.a_extract, self.a_split, self.a_del_pages):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("ツール(&T)")
        for key, *_ in TOOLS:
            m.addAction(self.tool_actions[key])
        m = mb.addMenu("消去(&R)")
        for k in ("eraser", "erase_rect", "erase_ellipse", "erase_lasso"):
            m.addAction(self.tool_actions[k])
        m.addSeparator()
        for a in (self.a_ink, self.a_del_ink, self.a_del_annots):
            m.addAction(a)
        m = mb.addMenu("表示(&V)")
        for a in (self.a_prev, self.a_next, None, self.a_zin, self.a_zout, self.a_fitw, self.a_fitp):
            m.addSeparator() if a is None else m.addAction(a)
        m.addSeparator()
        sub = m.addMenu("外観（色味）")
        for key in theme.THEME_ORDER:
            sub.addAction(self.theme_actions[key])
        m = mb.addMenu("ヘルプ(&H)")
        m.addAction(self.a_help)
        m.addSeparator()
        m.addAction(self.a_about)

    def _build_toolbars(self):
        tb = QToolBar("基本")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)
        for a in (self.a_open, self.a_save, None, self.a_undo, self.a_redo, None,
                  self.a_rot_l, self.a_rot_r, self.a_insert, self.a_extract, self.a_split,
                  self.a_del_pages, None, self.a_prev):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.valueChanged.connect(lambda v: self.goto(v - 1))
        tb.addWidget(self.page_spin)
        self.page_total = QLabel(" / 0 ")
        tb.addWidget(self.page_total)
        tb.addAction(self.a_next)
        tb.addSeparator()
        tb.addAction(self.a_zout)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.addItems(["幅に合わせる", "ページ全体", "50%", "75%", "100%", "125%", "150%", "200%", "300%"])
        self.zoom_combo.setMinimumWidth(110)
        self.zoom_combo.textActivated.connect(self._zoom_combo_changed)
        tb.addWidget(self.zoom_combo)
        tb.addAction(self.a_zin)

        self.addToolBarBreak()
        tb2 = QToolBar("ツール")
        tb2.setMovable(False)
        tb2.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb2)
        for key, *_ in TOOLS:
            if key in ("eraser", "crop"):
                tb2.addSeparator()
            tb2.addAction(self.tool_actions[key])

        # 3段目：書き込み・消しゴムの設定（幅が狭くても隠れないよう別の段に置く）
        self.addToolBarBreak()
        tb2 = QToolBar("設定")
        tb2.setMovable(False)
        self.addToolBar(tb2)
        tb2.addWidget(QLabel(" 色 "))
        self.color_combo = QComboBox()
        for name, hx in PRESET_COLORS:
            self.color_combo.addItem(color_icon(hx), name, hx)
        self.color_combo.addItem("その他…", "custom")
        self.color_combo.activated.connect(self._color_chosen)
        tb2.addWidget(self.color_combo)
        tb2.addWidget(QLabel(" 文字 "))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 96)
        self.size_spin.setValue(14)
        self.size_spin.setSuffix(" pt")
        self.size_spin.valueChanged.connect(self._size_changed)
        tb2.addWidget(self.size_spin)
        tb2.addWidget(QLabel(" 線 "))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.5, 20)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.setValue(2)
        self.width_spin.valueChanged.connect(self._width_changed)
        tb2.addWidget(self.width_spin)
        tb2.addSeparator()
        tb2.addWidget(QLabel(" 消しゴムの大きさ "))
        self.eraser_slider = QSlider(Qt.Orientation.Horizontal)
        self.eraser_slider.setRange(2, 100)
        self.eraser_slider.setFixedWidth(140)
        self.eraser_slider.setToolTip("消しゴムの大きさ（[ と ] キー、Alt＋ホイールでも変えられます）")
        tb2.addWidget(self.eraser_slider)
        self.eraser_spin = QSpinBox()
        self.eraser_spin.setRange(2, 100)
        self.eraser_spin.setSuffix(" pt")
        tb2.addWidget(self.eraser_spin)
        for label, val in (("小", 8), ("中", 20), ("大", 45)):
            b = QToolButton()
            b.setText(label)
            b.setToolTip(f"消しゴム：{label}（{val} pt）")
            b.clicked.connect(lambda _=False, v=val: self.set_eraser_size(v))
            tb2.addWidget(b)
        self.eraser_slider.valueChanged.connect(self.set_eraser_size)
        self.eraser_spin.valueChanged.connect(self.set_eraser_size)
        self.view.eraserResize.connect(lambda d: self.set_eraser_size(self.eraser_spin.value() + d))
        tb2.addWidget(QLabel("  消す色 "))
        self.fill_combo = QComboBox()
        self.fill_combo.addItems(["周りの紙の色で消す", "白で消す"])
        self.fill_combo.setToolTip("消しゴム・範囲消去で塗る色")
        tb2.addWidget(self.fill_combo)
        self.set_eraser_size(int(theme.settings().value("eraser_size", 16)))

    def set_eraser_size(self, v):
        v = max(2, min(100, int(v)))
        for wdg in (self.eraser_slider, self.eraser_spin):
            if wdg.value() != v:
                wdg.blockSignals(True)
                wdg.setValue(v)
                wdg.blockSignals(False)
        self.view.set_eraser_width(float(v))
        theme.settings().setValue("eraser_size", v)
        if self.view.tool == "eraser":
            self.statusBar().showMessage(f"消しゴムの大きさ：{v} pt", 1500)

    def apply_colors(self, colors):
        if not colors:
            return
        self.view.setBackgroundBrush(QColor(colors["page_bg"]))
        for k, a in self.theme_actions.items():
            a.setChecked(k == theme.saved_theme())

    # ================================================================ 状態
    def _update_title(self):
        name = os.path.basename(self.path) if self.path else ("無題" if self.doc else "")
        mark = " *" if self.modified else ""
        self.setWindowTitle(f"{name}{mark} - {APP_NAME}" if name else APP_NAME)
        has = self.doc is not None
        for a in (self.a_save, self.a_saveas, self.a_print, self.a_rot_r, self.a_rot_l, self.a_rot_dlg,
                  self.a_crop_dlg, self.a_del_pages,
                  self.a_extract, self.a_split, self.a_insert, self.a_blank, self.a_uncrop,
                  self.a_export_img, self.a_ink, self.a_del_ink, self.a_del_annots):
            a.setEnabled(has)
        self.a_undo.setEnabled(bool(self.undo_stack))
        self.a_redo.setEnabled(bool(self.redo_stack))

    def set_modified(self):
        self.modified = True
        self._update_title()

    def harvest(self):
        if self.doc is not None and self.view.page_item is not None and 0 <= self.cur < len(self.overlays):
            self.overlays[self.cur] = self.view.records()

    def _doc_bytes(self):
        ver, data = self._bytes_cache
        if ver != self.doc_ver:
            data = self.doc.tobytes()
            self._bytes_cache = (self.doc_ver, data)
        return data

    def make_snapshot(self):
        self.harvest()
        return (self._doc_bytes(), copy.deepcopy(self.overlays), self.cur, self.doc_ver)

    def push_undo(self, snap=None):
        self.undo_stack.append(snap or self.make_snapshot())
        if len(self.undo_stack) > UNDO_LIMIT:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._update_title()

    def doc_changed(self):
        self.doc_ver = next(_ver_counter)
        self.set_modified()

    def _restore(self, snap):
        data, ov, cur, ver = snap
        if ver != self.doc_ver:
            self.doc = fitz.open(stream=data, filetype="pdf")
            self.doc_ver = ver
            self._bytes_cache = (ver, data)
        self.overlays = ov
        self.cur = min(cur, len(self.doc) - 1)
        self.modified = True
        self.refresh_all()

    def undo(self):
        if self.view.editing_text():
            self.view.end_text_edit()
        if not self.undo_stack:
            return
        cur = self.make_snapshot()
        self.redo_stack.append(cur)
        self._restore(self.undo_stack.pop())
        self.statusBar().showMessage("元に戻しました。", 2000)

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.make_snapshot())
        self._restore(self.redo_stack.pop())
        self.statusBar().showMessage("やり直しました。", 2000)

    # 書き込みの変更通知
    def _overlay_about_to_change(self):
        self.push_undo()

    def _overlay_changed(self):
        self.set_modified()

    def _move_begin(self):
        self._pending_move = self.make_snapshot()

    def _move_commit(self):
        if self._pending_move:
            self.push_undo(self._pending_move)
            self._pending_move = None
            self.set_modified()

    # ================================================================ 開く・保存
    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "開く", self.last_dir, convert.FILE_FILTER)
        if paths:
            self.open_paths(paths)

    def _filter_supported(self, paths):
        ok = [p for p in paths if convert.is_supported(p)]
        ng = [os.path.basename(p) for p in paths if not convert.is_supported(p)]
        if ng:
            QMessageBox.information(self, APP_NAME,
                                    "次のファイルは PDF に変換できない形式のため、読み込みませんでした。\n\n"
                                    + "\n".join(ng[:10]) + ("\n…" if len(ng) > 10 else "")
                                    + "\n\n対応：PDF、Word、Excel、PowerPoint、画像（JPG・PNG など）、"
                                      "テキスト（TXT など）、XPS、EPUB、SVG")
        return ok

    def load_any(self, path):
        """どの形式でも PDF にして読み込む。Office とテキストは変換中の表示を出す。"""
        prog = None
        e = convert.ext_of(path)
        if e in convert.OFFICE_EXTS or e in convert.TEXT_EXTS:
            prog = QProgressDialog(f"{convert.kind_label(path)} のファイルを PDF に変換しています…\n"
                                   f"{os.path.basename(path)}", None, 0, 0, self)
            prog.setWindowTitle(APP_NAME)
            prog.setWindowModality(Qt.WindowModality.WindowModal)
            prog.setMinimumDuration(0)
            prog.show()
            QApplication.processEvents()
        try:
            return convert.to_pdf_doc(path, ask_password, tick=QApplication.processEvents)
        except Exception as ex:
            if prog:
                prog.close()
                prog = None
            QMessageBox.warning(self, APP_NAME, f"PDF にできませんでした。\n{os.path.basename(path)}\n\n{ex}")
            return None
        finally:
            if prog:
                prog.close()

    def open_paths(self, paths):
        paths = self._filter_supported(paths)
        if not paths:
            return
        if self.doc is not None:
            w = MainWindow(paths)
            w.show()
            return
        first = paths[0]
        doc = self.load_any(first)
        if doc is None:
            return
        self.last_dir = os.path.dirname(first)
        is_pdf = convert.ext_of(first) == ".pdf"
        self.set_document(doc, first if is_pdf else None, modified=not is_pdf)
        if not is_pdf:
            self.suggest_path = os.path.splitext(first)[0] + ".pdf"
            self.statusBar().showMessage(
                f"{convert.kind_label(first)} のファイルを PDF に変換しました。保存すると PDF ファイルになります。", 8000)
        if len(paths) > 1:
            self.insert_files(paths[1:], len(self.doc), snapshot=False)
            self.set_modified()

    def set_document(self, doc, path, modified=False):
        self.doc = doc
        self.path = path
        self.suggest_path = None
        self.overlays = [[] for _ in range(len(doc))]
        self.cur = 0
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.doc_ver = next(_ver_counter)
        self.modified = modified
        self.stack.setCurrentWidget(self.view)
        self.refresh_all()
        self.statusBar().showMessage(f"{len(doc)} ページ", 3000)

    def save(self) -> bool:
        if self.doc is None:
            return False
        if not self.path:
            return self.save_as()
        return self._write(self.path)

    def save_as(self) -> bool:
        if self.doc is None:
            return False
        base = self.path or getattr(self, "suggest_path", None) or os.path.join(self.last_dir, "無題.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "名前を付けて保存", base, "PDF (*.pdf)")
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        return self._write(path)

    def _write(self, path) -> bool:
        self.view.end_text_edit()
        self.harvest()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            out = pdfcore.build_output(self.doc, self.overlays)
            pdfcore.save_doc(out, path)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP_NAME, f"保存できませんでした。\n{e}\n\n"
                                "ほかのソフトでファイルを開いている場合は閉じてから保存してください。")
            return False
        QApplication.restoreOverrideCursor()
        self.path = path
        self.last_dir = os.path.dirname(path)
        self.modified = False
        self._update_title()
        self.statusBar().showMessage(f"保存しました：{path}", 4000)
        return True

    def export_pages_temp(self, rows) -> str | None:
        """サムネイルを外へドラッグしたときの一時PDF。"""
        try:
            self.harvest()
            out = pdfcore.build_output(self.doc, self.overlays, rows)
            stem = os.path.splitext(os.path.basename(self.path))[0] if self.path else "無題"
            d = tempfile.mkdtemp(dir=self.tmpdir)
            p = os.path.join(d, f"{stem}_{pdfcore.rows_label(rows)}.pdf")
            out.save(p, garbage=3, deflate=True)
            return p
        except Exception:
            return None

    def print_doc(self):
        self.harvest()
        p = os.path.join(tempfile.mkdtemp(dir=self.tmpdir), "印刷用.pdf")
        pdfcore.build_output(self.doc, self.overlays).save(p, garbage=3, deflate=True)
        try:
            os.startfile(p, "print")
            self.statusBar().showMessage("印刷を、PDF の既定のアプリに送りました。", 5000)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"印刷できませんでした。\n{e}")

    def closeEvent(self, ev):
        self.view.end_text_edit()
        if self.doc is not None and self.modified:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(APP_NAME)
            box.setText("変更が保存されていません。保存しますか？")
            b_save = box.addButton("保存する", QMessageBox.ButtonRole.AcceptRole)
            b_discard = box.addButton("保存しない", QMessageBox.ButtonRole.DestructiveRole)
            b_cancel = box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(b_save)
            box.setEscapeButton(b_cancel)
            box.exec()
            c = box.clickedButton()
            if c is b_cancel or (c is b_save and not self.save()) or c not in (b_save, b_discard):
                ev.ignore()
                return
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        if self in WINDOWS:
            WINDOWS.remove(self)
        ev.accept()

    # ドラッグ&ドロップ（ウィンドウ全体）
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        ev.acceptProposedAction()
        if self.doc is None:
            self.open_paths(paths)
            return
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setText(f"{len(paths)} 個のファイルをどうしますか？")
        b_join = box.addButton("この文書の最後に結合", QMessageBox.ButtonRole.AcceptRole)
        b_new = box.addButton("新しいウィンドウで開く", QMessageBox.ButtonRole.ActionRole)
        box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is b_join:
            self.insert_files(paths, len(self.doc))
        elif box.clickedButton() is b_new:
            MainWindow(paths).show()

    # ================================================================ 表示
    def refresh_all(self):
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, len(self.doc)))
        self.page_spin.setValue(self.cur + 1)
        self.page_spin.blockSignals(False)
        self.page_total.setText(f" / {len(self.doc)} ")
        self.rebuild_thumbs()
        self.render_page(harvest=False)
        self._update_title()

    def _calc_zoom(self):
        if self.doc is None:
            return 1.0
        r = self.doc[self.cur].rect
        vp = self.view.viewport().size()
        if self.zoom_mode == "width":
            return max(0.1, (vp.width() - 50) / r.width)
        if self.zoom_mode == "page":
            return max(0.1, min((vp.width() - 50) / r.width, (vp.height() - 50) / r.height))
        return self.zoom_mode

    def render_page(self, harvest=True, keep_scroll=False):
        if self.doc is None:
            return
        if harvest:
            self.harvest()
        sv = (self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value())
        page = self.doc[self.cur]
        self.zoom = self._calc_zoom()
        s = self.zoom * self.devicePixelRatioF()
        s = min(s, 6000 / max(page.rect.width, page.rect.height))
        pix = page.get_pixmap(matrix=fitz.Matrix(s, s), annots=True, alpha=False)
        self.view.show_page(pix_to_qimage(pix), s, page.rect.width, page.rect.height, self.overlays[self.cur])
        self.view.set_zoom(self.zoom)
        if keep_scroll:
            self.view.horizontalScrollBar().setValue(sv[0])
            self.view.verticalScrollBar().setValue(sv[1])
        else:
            self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().minimum())
        self.zoom_combo.setEditText(f"{round(self.zoom * 100)}%" if not isinstance(self.zoom_mode, str)
                                    else ("幅に合わせる" if self.zoom_mode == "width" else "ページ全体"))
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(self.cur + 1)
        self.page_spin.blockSignals(False)
        self.thumbs.blockSignals(True)
        if self.thumbs.currentRow() != self.cur:
            self.thumbs.setCurrentRow(self.cur)
        self.thumbs.blockSignals(False)

    def goto(self, i):
        if self.doc is None:
            return
        i = max(0, min(i, len(self.doc) - 1))
        if i == self.cur:
            return
        self.view.end_text_edit()
        self.harvest()
        self.cur = i
        self.render_page(harvest=False)

    def _thumb_clicked(self, row):
        if row >= 0 and self.doc is not None and row != self.cur:
            self.goto(row)

    def set_zoom_mode(self, mode):
        self.zoom_mode = mode
        self.render_page(keep_scroll=True)

    def zoom_step(self, d):
        steps = [0.25, 0.33, 0.5, 0.67, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5]
        z = self.zoom
        if d > 0:
            nz = next((s for s in steps if s > z + 0.01), steps[-1])
        else:
            nz = next((s for s in reversed(steps) if s < z - 0.01), steps[0])
        self.set_zoom_mode(nz)

    def _zoom_combo_changed(self, text):
        if text == "幅に合わせる":
            self.set_zoom_mode("width")
        elif text == "ページ全体":
            self.set_zoom_mode("page")
        else:
            try:
                v = float(text.replace("%", "").strip()) / 100
                self.set_zoom_mode(max(0.1, min(v, 8)))
            except ValueError:
                pass

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._resize_timer.start()

    def _refit(self):
        if self.doc is not None and isinstance(self.zoom_mode, str):
            self.render_page(keep_scroll=True)

    # サムネイル
    def rebuild_thumbs(self):
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        ph = QPixmap(100, 130)
        ph.fill(QColor("#ffffff"))
        for i in range(len(self.doc)):
            it = QListWidgetItem(QIcon(ph), str(i + 1))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.thumbs.addItem(it)
        self.thumbs.setCurrentRow(self.cur)
        self.thumbs.blockSignals(False)
        self._thumb_queue = list(range(len(self.doc)))
        self._thumb_timer.start()

    def _render_thumb_batch(self):
        for _ in range(4):
            if not self._thumb_queue or self.doc is None:
                self._thumb_timer.stop()
                return
            i = self._thumb_queue.pop(0)
            self.refresh_thumb(i)

    def refresh_thumb(self, i):
        if self.doc is None or i >= len(self.doc) or i >= self.thumbs.count():
            return
        page = self.doc[i]
        s = 130 * self.devicePixelRatioF() / max(page.rect.width, page.rect.height * 0.77)
        pix = page.get_pixmap(matrix=fitz.Matrix(s, s), annots=True, alpha=False)
        pm = QPixmap.fromImage(pix_to_qimage(pix))
        pm.setDevicePixelRatio(self.devicePixelRatioF())
        self.thumbs.item(i).setIcon(QIcon(pm))

    def _thumb_menu(self, pos):
        if self.doc is None:
            return
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        for a in (self.a_rot_r, self.a_rot_l, self.a_rot_dlg, None, self.a_crop_dlg, None,
                  self.a_extract, self.a_del_pages, None, self.a_insert, self.a_blank, None, self.a_export_img):
            m.addSeparator() if a is None else m.addAction(a)
        m.exec(self.thumbs.mapToGlobal(pos))

    # ================================================================ ツール
    def set_tool(self, key):
        if key == "stamp" and not self.view.stamp_data:
            if not self._choose_stamp():
                self.tool_actions[self.view.tool].setChecked(True)
                return
        elif key == "stamp" and self.view.tool == "stamp":
            self._choose_stamp()
        self.view.set_tool(key)
        self.tool_actions[key].setChecked(True)
        tip = next(t for k, _, _, t in TOOLS if k == key)
        self.statusBar().showMessage(tip)

    def _tool_key(self, key):
        if key == int(Qt.Key.Key_Escape):
            self.set_tool("select")
            return
        ch = chr(key)
        for k, _, sc, _ in TOOLS:
            if sc == ch:
                self.set_tool(k)
                return

    def _choose_stamp(self) -> bool:
        p, _ = QFileDialog.getOpenFileName(self, "置く画像を選ぶ（ハンコなど）", self.last_dir,
                                           "画像 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not p:
            return False
        with open(p, "rb") as f:
            data = f.read()
        img = QImage.fromData(data)
        if img.isNull():
            QMessageBox.warning(self, APP_NAME, "画像を読み込めませんでした。")
            return False
        self.view.stamp_data = data
        self.view.stamp_size = (img.width(), img.height())
        return True

    def _color_chosen(self, idx):
        hx = self.color_combo.itemData(idx)
        if hx == "custom":
            c = QColorDialog.getColor(QColor(self.view.color), self, "色を選ぶ")
            if not c.isValid():
                return
            hx = c.name()
            self.color_combo.insertItem(idx, color_icon(hx), hx, hx)
            self.color_combo.setCurrentIndex(idx)
        self.view.color = hx
        self.view.apply_style_to_selected(color=hx)

    def _size_changed(self, v):
        self.view.font_size = v
        self.view.apply_style_to_selected(size=v)

    def _width_changed(self, v):
        self.view.width_ = v
        self.view.apply_style_to_selected(width=v)

    # ================================================================ ページ操作
    def target_rows(self):
        rows = self.thumbs.selected_rows()
        return rows if rows else [self.cur]

    def rotate_pages(self, deg, rows=None):
        if self.doc is None:
            return
        if rows is None:
            rows = self.target_rows()
        if not rows:
            return
        self.harvest()
        self.push_undo()
        for r in rows:
            page = self.doc[r]
            W, H = page.rect.width, page.rect.height
            if deg == 90:
                fn = lambda x, y, H=H: (H - y, x)
            elif deg == 180:
                fn = lambda x, y, W=W, H=H: (W - x, H - y)
            else:
                fn = lambda x, y, W=W: (y, W - x)
            self.overlays[r] = [pdfcore.transform_record(rec, fn) for rec in self.overlays[r]]
            page.set_rotation((page.rotation + deg) % 360)
        self.doc_changed()
        for r in rows:
            self.refresh_thumb(r)
        self.render_page(harvest=False)
        return len(rows)

    def _page_sizes(self):
        return [(pg.rect.width, pg.rect.height) for pg in self.doc]

    def rotate_dialog(self):
        if self.doc is None:
            return
        dlg = pagedialogs.RotateDialog(len(self.doc), self.cur, self.thumbs.selected_rows(),
                                       self._page_sizes(), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rows = dlg.rows()
        n = self.rotate_pages(dlg.direction(), rows)
        if n:
            self.statusBar().showMessage(f"{n} ページを回転しました。元に戻すには Ctrl+Z。", 5000)

    def crop_dialog(self, init_rect: QRectF | None = None):
        if self.doc is None:
            return
        self.harvest()
        page = self.doc[self.cur]
        W, H = page.rect.width, page.rect.height
        init = None
        if init_rect is not None:
            r = init_rect.intersected(QRectF(0, 0, W, H))
            init = (r.top(), H - r.bottom(), r.left(), W - r.right())
        pix = page.get_pixmap(matrix=fitz.Matrix(0.6, 0.6), annots=True)
        preview = QPixmap.fromImage(pix_to_qimage(pix))
        try:
            auto = pdfcore.content_margins(page)
        except Exception:
            auto = None
        dlg = pagedialogs.CropDialog(len(self.doc), self.cur, self.thumbs.selected_rows(), W, H, preview,
                                     auto_margins=auto, init_margins=init, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        top, bottom, left, right = dlg.margins_pt()
        rows = dlg.rows()
        if not rows or (top, bottom, left, right) == (0, 0, 0, 0):
            return
        self.push_undo()
        done, skipped = 0, 0
        for r in rows:
            pg = self.doc[r]
            try:
                pdfcore.crop_margins(pg, top, bottom, left, right)
            except ValueError:
                skipped += 1
                continue
            done += 1
            self.overlays[r] = [pdfcore.transform_record(rec, lambda x, y: (x - left, y - top))
                                for rec in self.overlays[r]]
        self.doc_changed()
        self.refresh_all()
        msg = f"{done} ページをトリミングしました。"
        if skipped:
            msg += f"（{skipped} ページは小さすぎるため見送り）"
        self.statusBar().showMessage(msg + "元に戻すには Ctrl+Z。", 6000)

    def delete_pages(self):
        if self.doc is None:
            return
        rows = self.target_rows()
        if len(rows) >= len(self.doc):
            QMessageBox.information(self, APP_NAME, "すべてのページは削除できません。1ページ以上残してください。")
            return
        self.push_undo()
        self.doc.delete_pages(rows)
        for r in sorted(rows, reverse=True):
            del self.overlays[r]
        self.cur = min(max(0, rows[0] - (1 if rows[0] >= len(self.doc) else 0)), len(self.doc) - 1)
        self.doc_changed()
        self.refresh_all()
        self.statusBar().showMessage(f"{len(rows)} ページを削除しました。", 3000)

    def move_pages(self, rows, dest):
        n = len(self.doc)
        rows = sorted(set(rows))
        rest = [i for i in range(n) if i not in rows]
        d = dest - sum(1 for r in rows if r < dest)
        order = rest[:d] + rows + rest[d:]
        if order == list(range(n)):
            return
        self.push_undo()
        self.doc.select(order)
        self.overlays = [self.overlays[i] for i in order]
        self.cur = order.index(self.cur)
        self.doc_changed()
        self.refresh_all()
        self.thumbs.blockSignals(True)
        for k in range(d, d + len(rows)):
            self.thumbs.item(k).setSelected(True)
        self.thumbs.blockSignals(False)

    def insert_files(self, paths, dest, snapshot=True):
        if self.doc is None:
            self.open_paths(paths)
            return
        paths = self._filter_supported(paths)
        if not paths:
            return
        self.harvest()
        if snapshot:
            self.push_undo()
        added = 0
        for p in paths:
            src = self.load_any(p)
            if src is None:
                continue
            at = dest if dest < len(self.doc) else -1
            self.doc.insert_pdf(src, start_at=at)
            k = len(src)
            pos = dest if dest < len(self.overlays) else len(self.overlays)
            self.overlays[pos:pos] = [[] for _ in range(k)]
            dest = pos + k
            added += k
        if added:
            self.doc_changed()
            self.refresh_all()
            self.statusBar().showMessage(f"{added} ページを結合しました。", 4000)

    def insert_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "挿入するファイル（PDF 以外は変換して挿入）", self.last_dir,
                                                convert.FILE_FILTER)
        if not paths:
            return
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setText("どこに挿入しますか？")
        b_after = box.addButton(f"表示中のページ（{self.cur + 1}）の後ろ", QMessageBox.ButtonRole.AcceptRole)
        b_end = box.addButton("最後", QMessageBox.ButtonRole.ActionRole)
        b_first = box.addButton("最初", QMessageBox.ButtonRole.ActionRole)
        box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        c = box.clickedButton()
        dest = {b_after: self.cur + 1, b_end: len(self.doc), b_first: 0}.get(c)
        if dest is not None:
            self.insert_files(paths, dest)

    def insert_blank(self):
        self.push_undo()
        page = self.doc[self.cur]
        r = page.rect
        self.doc.new_page(self.cur + 1, width=r.width, height=r.height)
        self.overlays.insert(self.cur + 1, [])
        self.cur += 1
        self.doc_changed()
        self.refresh_all()

    def extract_pages(self):
        rows = self.target_rows()
        stem = os.path.splitext(os.path.basename(self.path))[0] if self.path else "無題"
        default = os.path.join(self.last_dir, f"{stem}_{pdfcore.rows_label(rows)}.pdf")
        text, ok = QInputDialog.getText(self, "ページを抽出",
                                        f"抽出するページ（例：1-3, 5）\n全 {len(self.doc)} ページ",
                                        text=", ".join(str(r + 1) for r in rows) if len(rows) < 2 or
                                        rows != list(range(rows[0], rows[-1] + 1))
                                        else f"{rows[0] + 1}-{rows[-1] + 1}")
        if not ok:
            return
        try:
            groups = pdfcore.parse_ranges(text, len(self.doc))
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        rows = [r for g in groups for r in g]
        default = os.path.join(self.last_dir, f"{stem}_{pdfcore.rows_label(rows)}.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "抽出したページの保存先", default, "PDF (*.pdf)")
        if not path:
            return
        self.harvest()
        try:
            pdfcore.save_doc(pdfcore.build_output(self.doc, self.overlays, rows), path)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"保存できませんでした。\n{e}")
            return
        self.statusBar().showMessage(f"{len(rows)} ページを抽出しました：{path}", 5000)
        uniq = sorted(set(rows))
        if len(uniq) < len(self.doc):
            r = QMessageBox.question(self, APP_NAME, "抽出したページを、この文書から削除しますか？",
                                     defaultButton=QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes:
                self.thumbs.clearSelection()
                self.push_undo()
                self.doc.delete_pages(uniq)
                for x in reversed(uniq):
                    del self.overlays[x]
                self.cur = min(self.cur, len(self.doc) - 1)
                self.doc_changed()
                self.refresh_all()

    def split_dialog(self):
        n = len(self.doc)
        dlg = QDialog(self)
        dlg.setWindowTitle("分割")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"全 {n} ページを、いくつかの PDF に分けて保存します。"))
        r1 = QRadioButton("1 ページずつ")
        r2 = QRadioButton("ページ数ごと：")
        r3 = QRadioButton("範囲を指定：")
        grp = QButtonGroup(dlg)
        for r in (r1, r2, r3):
            grp.addButton(r)
        r2.setChecked(True)
        spin = QSpinBox()
        spin.setRange(1, max(1, n))
        spin.setValue(min(2, n))
        spin.setSuffix(" ページごと")
        edit = QLineEdit()
        edit.setPlaceholderText("例：1-3, 4-6, 7-")
        lay.addWidget(r1)
        h = QHBoxLayout(); h.addWidget(r2); h.addWidget(spin); h.addStretch(); lay.addLayout(h)
        h = QHBoxLayout(); h.addWidget(r3); h.addWidget(edit); lay.addLayout(h)
        folder = os.path.dirname(self.path) if self.path else self.last_dir
        fl = QLabel(folder)
        fl.setWordWrap(True)
        b = QPushButton("保存先を変更…")
        b.clicked.connect(lambda: fl.setText(QFileDialog.getExistingDirectory(dlg, "保存先", fl.text()) or fl.text()))
        h = QHBoxLayout(); h.addWidget(QLabel("保存先：")); h.addWidget(fl, 1); h.addWidget(b); lay.addLayout(h)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if r1.isChecked():
                groups = [[i] for i in range(n)]
            elif r2.isChecked():
                k = spin.value()
                groups = [list(range(i, min(i + k, n))) for i in range(0, n, k)]
            else:
                groups = pdfcore.parse_ranges(edit.text(), n)
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.harvest()
        stem = os.path.splitext(os.path.basename(self.path))[0] if self.path else "無題"
        out_dir = fl.text()
        written = []
        for g in groups:
            p = os.path.join(out_dir, f"{stem}_{pdfcore.rows_label(g)}.pdf")
            try:
                pdfcore.save_doc(pdfcore.build_output(self.doc, self.overlays, g), p)
                written.append(p)
            except Exception as e:
                QMessageBox.warning(self, APP_NAME, f"保存できませんでした。\n{p}\n\n{e}")
                break
        if written:
            r = QMessageBox.question(self, APP_NAME, f"{len(written)} 個の PDF に分割しました。\n保存先のフォルダを開きますか？")
            if r == QMessageBox.StandardButton.Yes:
                os.startfile(out_dir)

    def uncrop(self):
        if self.doc is None:
            return
        dlg = pagedialogs.UncropDialog(len(self.doc), self.cur, self.thumbs.selected_rows(), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.harvest()
        self.push_undo()
        n = 0
        for i in dlg.rows():
            off = pdfcore.uncrop_page(self.doc[i])
            if off is None:
                continue
            n += 1
            dx, dy = off
            self.overlays[i] = [pdfcore.transform_record(rec, lambda x, y: (x + dx, y + dy))
                                for rec in self.overlays[i]]
        self.doc_changed()
        self.refresh_all()
        self.statusBar().showMessage(f"{n} ページのトリミングを解除しました。" if n
                                     else "トリミングされたページはありませんでした。", 5000)

    # ================================================================ 範囲操作（消去・トリミング）
    def _region_chosen(self, tool, rect: QRectF, poly):
        if self.doc is None:
            return
        if tool == "crop":
            return self._crop(rect)
        page = self.doc[self.cur]
        auto = self.fill_combo.currentIndex() == 0
        if tool == "eraser":
            self.push_undo()
            w = self.view.eraser_width
            if auto:
                ring = []
                for x, y in poly[::max(1, len(poly) // 40)]:
                    for k in range(12):
                        import math
                        a = k * math.pi / 6
                        ring.append((x + math.cos(a) * (w / 2 + 4), y + math.sin(a) * (w / 2 + 4)))
                fill = pdfcore.sample_background(page, ring)
            else:
                fill = (1, 1, 1)
            # 消しゴムでなぞった書き込み（このアプリで書いたもの）も消す
            path = QPainterPath()
            for x, y in poly:
                path.addEllipse(QPointF(x, y), w / 2, w / 2)
            self.view.remove_overlays_in(path)
            self.harvest()
            pdfcore.erase_stroke(page, poly, w, fill)
            self._after_page_edit()
            return
        shape = {"erase_rect": "rect", "erase_ellipse": "ellipse", "erase_lasso": "lasso"}[tool]
        self.push_undo()
        qpath = QPainterPath()
        qpath.addPolygon(QPolygonF([QPointF(x, y) for x, y in poly]))
        qpath.closeSubpath()
        self.view.remove_overlays_in(qpath)
        self.harvest()
        n_annot = pdfcore.delete_annots_in(page, lambda x, y: qpath.contains(QPointF(x, y)))
        if auto:
            pts = []
            for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
                seg = max(1, int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / 2))
                pts += [(x0 + (x1 - x0) * t / seg, y0 + (y1 - y0) * t / seg) for t in range(seg)]
            fill = pdfcore.sample_background(page, pts)
        else:
            fill = (1, 1, 1)
        try:
            pdfcore.erase_region(page, shape, (rect.x(), rect.y(), rect.width(), rect.height()), poly, fill)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"消去できませんでした。\n{e}")
        self._after_page_edit()
        msg = "選んだ範囲を消しました。"
        if n_annot:
            msg += f"（注釈 {n_annot} 件を削除）"
        self.statusBar().showMessage(msg + "　元に戻すには Ctrl+Z。", 5000)

    def _after_page_edit(self):
        self.doc_changed()
        self.render_page(harvest=False, keep_scroll=True)
        self.refresh_thumb(self.cur)

    def _crop(self, rect: QRectF):
        return self.crop_dialog(rect)

    # ================================================================ 消去メニュー
    def _scope_dialog(self, title, extra=None):
        """対象ページ（このページ/選択/すべて）と追加の選択肢を聞く。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        form = QFormLayout(dlg)
        scope = QComboBox()
        scope.addItem(f"このページ（{self.cur + 1}）", "this")
        if len(self.thumbs.selected_rows()) > 1:
            scope.addItem(f"選択中のページ（{len(self.thumbs.selected_rows())} ページ）", "sel")
        scope.addItem(f"すべてのページ（{len(self.doc)} ページ）", "all")
        form.addRow("対象", scope)
        ex = None
        if extra:
            label, items, note = extra
            ex = QComboBox()
            for t, d in items:
                ex.addItem(t, d)
            form.addRow(label, ex)
            if note:
                lb = QLabel(note)
                lb.setWordWrap(True)
                lb.setStyleSheet("color:#555;")
                form.addRow(lb)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        s = scope.currentData()
        rows = [self.cur] if s == "this" else self.thumbs.selected_rows() if s == "sel" else list(range(len(self.doc)))
        return rows, (ex.currentData() if ex else None)

    def remove_colored_ink(self):
        res = self._scope_dialog("色ペンの書き込みを消す", (
            "消す色", [("赤ペン（赤・ピンク・オレンジ系）", "red"), ("青ペン（青系）", "blue"),
                      ("色の付いたものすべて", "color")],
            "黒い印刷や鉛筆は残ります。処理したページは画像になり、文字の検索や選択はできなくなります。"
            "色付きの印刷（カラーの図や見出し）も消える場合があるので、結果を確認してください。"))
        if not res:
            return
        rows, target = res
        self.view.end_text_edit()
        self.push_undo()
        prog = QProgressDialog("書き込みを消しています…", "中止", 0, len(rows), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(300)
        done, notfound = 0, 0
        for k, r in enumerate(rows):
            prog.setValue(k)
            QApplication.processEvents()
            if prog.wasCanceled():
                break
            try:
                pdfcore.remove_colored_ink(self.doc, r, target)
                done += 1
            except LookupError:
                notfound += 1
        prog.setValue(len(rows))
        if done:
            self.doc_changed()
            self.refresh_all()
        else:
            self.undo_stack.pop()
            self._update_title()
        msg = f"{done} ページで色の書き込みを消しました。"
        if notfound:
            msg += f"（{notfound} ページは該当なし）"
        QMessageBox.information(self, APP_NAME, msg + ("\n元に戻すには Ctrl+Z。" if done else ""))

    def delete_annots(self, ink_only):
        title = "手書き注釈（ペン）を削除" if ink_only else "すべての注釈を削除"
        res = self._scope_dialog(title)
        if not res:
            return
        rows, _ = res
        self.push_undo()
        n = sum(pdfcore.delete_annots(self.doc[r], ink_only) for r in rows)
        if n:
            self.doc_changed()
            self.refresh_all()
        else:
            self.undo_stack.pop()
            self._update_title()
        QMessageBox.information(self, APP_NAME, f"注釈を {n} 件削除しました。" if n else
                                "削除する注釈は見つかりませんでした。\n"
                                "（スキャンした紙の手書きは注釈ではないため、消しゴムや範囲消去、色ペン消去を使います）")

    # ================================================================ 変換
    def export_images(self):
        res = self._scope_dialog("画像として書き出し", (
            "画質", [("標準（150dpi）PNG", (150, "png")), ("高画質（300dpi）PNG", (300, "png")),
                    ("標準（150dpi）JPEG・軽い", (150, "jpg")), ("高画質（300dpi）JPEG", (300, "jpg"))], None))
        if not res:
            return
        rows, (dpi, fmt) = res
        folder = QFileDialog.getExistingDirectory(self, "書き出し先のフォルダ",
                                                  os.path.dirname(self.path) if self.path else self.last_dir)
        if not folder:
            return
        self.harvest()
        out = pdfcore.build_output(self.doc, self.overlays, rows)
        stem = os.path.splitext(os.path.basename(self.path))[0] if self.path else "無題"
        prog = QProgressDialog("書き出しています…", "中止", 0, len(rows), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(300)
        for k, r in enumerate(rows):
            prog.setValue(k)
            QApplication.processEvents()
            if prog.wasCanceled():
                break
            pix = out[k].get_pixmap(dpi=dpi, alpha=False)
            p = os.path.join(folder, f"{stem}_p{r + 1:03d}.{fmt}")
            if fmt == "jpg":
                pix.save(p, jpg_quality=90)
            else:
                pix.save(p)
        prog.setValue(len(rows))
        r = QMessageBox.question(self, APP_NAME, f"{len(rows)} 枚の画像を書き出しました。\nフォルダを開きますか？")
        if r == QMessageBox.StandardButton.Yes:
            os.startfile(folder)

    def convert_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "PDF に変換するファイルを選ぶ（複数可）", self.last_dir,
                                                convert.FILE_FILTER)
        paths = self._filter_supported(paths)
        if not paths:
            return
        self.last_dir = os.path.dirname(paths[0])
        box = QMessageBox(self)
        box.setWindowTitle("ファイルを PDF に変換")
        box.setText(f"{len(paths)} 個のファイルを PDF にします。どのようにしますか？")
        box.setInformativeText("「1つずつ保存」は、元のファイルと同じフォルダに同じ名前の PDF を作ります。")
        b_open = box.addButton("変換して開く（編集できます）", QMessageBox.ButtonRole.AcceptRole)
        b_each = box.addButton("1つずつ PDF で保存", QMessageBox.ButtonRole.ActionRole)
        b_one = box.addButton("1つの PDF にまとめて保存", QMessageBox.ButtonRole.ActionRole) if len(paths) > 1 else None
        box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        c = box.clickedButton()
        if c is b_open:
            self.open_paths(paths)
        elif c is b_each:
            self._convert_each(paths)
        elif b_one is not None and c is b_one:
            self._convert_combined(paths)

    @staticmethod
    def _unique_path(path):
        if not os.path.exists(path):
            return path
        stem, ext = os.path.splitext(path)
        k = 2
        while os.path.exists(f"{stem}({k}){ext}"):
            k += 1
        return f"{stem}({k}){ext}"

    def _convert_each(self, paths):
        done, failed = [], []
        for p in paths:
            if convert.ext_of(p) == ".pdf":
                continue
            doc = self.load_any(p)
            if doc is None:
                failed.append(os.path.basename(p))
                continue
            out = self._unique_path(os.path.splitext(p)[0] + ".pdf")
            try:
                pdfcore.save_doc(doc, out)
                done.append(out)
            except Exception as ex:
                failed.append(f"{os.path.basename(p)}（{ex}）")
        msg = f"{len(done)} 個のファイルを PDF にしました。"
        if failed:
            msg += "\n\n変換できなかったもの：\n" + "\n".join(failed)
        if done:
            r = QMessageBox.question(self, APP_NAME, msg + "\n\n保存先のフォルダを開きますか？")
            if r == QMessageBox.StandardButton.Yes:
                os.startfile(os.path.dirname(done[0]))
        else:
            QMessageBox.information(self, APP_NAME, msg)

    def _convert_combined(self, paths):
        default = os.path.join(self.last_dir, os.path.splitext(os.path.basename(paths[0]))[0] + "_まとめ.pdf")
        out, _ = QFileDialog.getSaveFileName(self, "まとめた PDF の保存先", default, "PDF (*.pdf)")
        if not out:
            return
        combined = fitz.open()
        failed = []
        for p in paths:
            doc = self.load_any(p)
            if doc is None:
                failed.append(os.path.basename(p))
                continue
            combined.insert_pdf(doc)
        if len(combined) == 0:
            return
        try:
            pdfcore.save_doc(combined, out)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"保存できませんでした。\n{ex}")
            return
        msg = f"{len(paths) - len(failed)} 個のファイルを 1 つの PDF（{len(combined)} ページ）にまとめました。"
        if failed:
            msg += "\n\n変換できなかったもの：\n" + "\n".join(failed)
        r = QMessageBox.question(self, APP_NAME, msg + "\n\nこの PDF を開きますか？")
        if r == QMessageBox.StandardButton.Yes:
            self.open_paths([out])

    def create_from_images(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "PDF にする画像を選ぶ（複数可・名前順に並びます）", self.last_dir,
                                                "画像 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)")
        if not paths:
            return
        paths.sort()
        item, ok = QInputDialog.getItem(self, "画像から PDF を作成", "ページの大きさ",
                                        ["A4 に合わせる（おすすめ）", "画像の大きさのまま"], 0, False)
        if not ok:
            return
        fit = item.startswith("A4")
        doc = fitz.open()
        for p in paths:
            try:
                doc.insert_pdf(pdfcore.image_to_pdf_doc(p, fit))
            except Exception as e:
                QMessageBox.warning(self, APP_NAME, f"読み込めませんでした。\n{p}\n\n{e}")
        if len(doc) == 0:
            return
        self.last_dir = os.path.dirname(paths[0])
        if self.doc is None:
            self.set_document(doc, None, modified=True)
        else:
            MainWindow(doc=doc).show()

    # ================================================================ ヘルプ
    @staticmethod
    def licenses_dir():
        if getattr(sys, "frozen", False):
            return os.path.join(os.path.dirname(sys.executable), "licenses")
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "licenses")

    def show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle(f"{APP_NAME} について")
        box.setIconPixmap(self.windowIcon().pixmap(64, 64))
        box.setText(f"<b>{APP_NAME}</b>　バージョン {VERSION}<br>Copyright (C) 2026 Astras Group")
        box.setInformativeText(
            "PDF のページ操作・書き込み・消去・変換ができる、無料の PDF アプリです。<br>"
            "ファイルはこの PC の中だけで処理し、インターネットには送りません。<br><br>"
            "このソフトウェアは GNU Affero General Public License v3.0（AGPL-3.0）で公開しています。"
            "ライセンスの条件に従って、自由に使う・配る・改変することができます。"
            "ソースコードは、配布物に同梱の「PDF工房_ソースコード」の zip ファイルにあります。<br><br>"
            "このソフトウェアは<b>無保証</b>です。使用によって生じた損害について、作者は責任を負いません。<br><br>"
            "PDF の処理に PyMuPDF / MuPDF（AGPL-3.0）、画面に Qt / PySide6（LGPL-3.0）を使っています。"
            "使用しているソフトウェアの一覧とライセンスは、「ライセンスを開く」で確認できます。<br><br>"
            "連絡先：Astras Group<br>"
            "ウェブサイト：<a href=\"https://astras-tokushima.com/\">https://astras-tokushima.com/</a><br>"
            "メール：info@astras-tokushima.com")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        b_lic = box.addButton("ライセンスを開く", QMessageBox.ButtonRole.ActionRole)
        box.addButton("閉じる", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is b_lic:
            d = self.licenses_dir()
            if os.path.isdir(d):
                os.startfile(d)
            else:
                QMessageBox.information(self, APP_NAME, "licenses フォルダが見つかりませんでした。")

    def show_help(self):
        QMessageBox.information(self, f"{APP_NAME} の使い方", (
            "■ 開く・結合\n"
            "・PDF、Word、Excel、PowerPoint、画像、テキストをウィンドウにドラッグすると開きます（PDF 以外は自動で変換）\n"
            "・「ファイル」→「ファイルをPDFに変換」で、まとめて PDF にできます\n"
            "・左のページ一覧にファイルをドラッグすると、その位置に結合されます。\n\n"
            "■ ページ操作（左の一覧で選択。Ctrl / Shift で複数選択）\n"
            "・一覧の中でドラッグ → 並べ替え\n"
            "・一覧からデスクトップやフォルダへドラッグ → そのページだけの PDF ができます（抽出）\n"
            "・ウィンドウを2つ開けば、ページを別の PDF へドラッグで移せます\n"
            "・右クリックで 回転・抽出・削除 など\n"
            "・「ページの回転」（Ctrl+Shift+R）・「ページのトリミング」（Ctrl+Shift+T）では、\n"
            "　ページ範囲と「奇数ページのみ」「偶数ページのみ」を指定できます\n\n"
            "■ 書き込み\n"
            "・テキスト（T）：クリックした場所にそのまま入力。外をクリックで確定\n"
            "・選択（V）：書き込みを動かす・Delete で削除・ダブルクリックで文字を修正\n"
            "・書き込みは保存するまで何度でも動かせます。保存するとページに書き込まれます\n\n"
            "■ 消す\n"
            "・消しゴム（E）：なぞった所を紙の色で塗って消す\n"
            "・範囲消去□（D）：囲んだ中の文字や図をデータごと消す\n"
            "・範囲消去○（F）・投げ縄（L）：囲んだ中を紙の色で塗りつぶす\n"
            "・「消去」メニュー：赤ペン・青ペンの書き込みを自動で消す／PDF のペン注釈を削除\n\n"
            "■ キー\n"
            "・Ctrl+Z 元に戻す／Ctrl+Y やり直し／← → ページ移動／Ctrl+ホイール 拡大縮小\n"
            "・Esc で選択ツールに戻ります"))


CURRENT_COLORS: dict = {}


def set_theme(name):
    app = QApplication.instance()
    CURRENT_COLORS.clear()
    CURRENT_COLORS.update(theme.apply_theme(app, name))
    for w in list(WINDOWS):
        w.apply_colors(CURRENT_COLORS)


def _system_scheme_changed(*_):
    if theme.saved_theme() == "system":
        set_theme("system")


def main():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    f = app.font()
    f.setFamily("Yu Gothic UI")
    f.setPointSize(10)
    app.setFont(f)
    theme.install_japanese(app)
    set_theme(theme.saved_theme())
    app.styleHints().colorSchemeChanged.connect(_system_scheme_changed)
    icon_path = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(__file__)), "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    w = MainWindow([a for a in sys.argv[1:] if os.path.exists(a)])
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
