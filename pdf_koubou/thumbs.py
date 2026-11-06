"""ページのサムネイル一覧。ドラッグで並べ替え・複製・ファイルの差し込み・ページの書き出し。"""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget

MIME = "application/x-pdfkoubou-pages"

AUTOSCROLL_MARGIN = 40


class ThumbList(QListWidget):
    pagesMoved = Signal(list, int)      # rows, 差し込み位置
    pagesCopied = Signal(list, int)     # rows, 差し込み位置（Ctrl を押しながらドラッグ＝複製）
    filesDropped = Signal(list, int)    # paths, 差し込み位置
    contextRequested = Signal(QPoint)

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner  # MainWindow（ドラッグ書き出し用の一時PDFを作る）
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setWrapping(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setIconSize(QSize(130, 170))
        self.setGridSize(QSize(160, 200))
        self.setSpacing(4)
        self.setUniformItemSizes(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        # Movement.Static にすると、Qt が中身（viewport）のドロップ受け付けを切ってしまう。
        # 切れたままだと、一覧に落としたページがウィンドウ全体に渡り「最後に結合」になる。
        self.viewport().setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contextRequested)
        self._drop_row = None
        self._drop_label = ""
        self._scroll_dir = 0
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(30)
        self._scroll_timer.timeout.connect(self._autoscroll)
        self.setStyleSheet("QListWidget{border:none;}"
                           "QListWidget::item{padding:2px;}"
                           "QListWidget::item:selected{background:palette(highlight);color:palette(highlighted-text);border-radius:4px;}")

    def selected_rows(self):
        return sorted(self.row(it) for it in self.selectedItems())

    # ------------------------------------------------ ドラッグ開始
    def startDrag(self, actions):
        rows = self.selected_rows()
        if not rows:
            return
        mime = QMimeData()
        mime.setData(MIME, QByteArray(json.dumps(
            {"pid": os.getpid(), "win": id(self.owner), "rows": rows}).encode()))
        path = self.owner.export_pages_temp(rows)
        if path:
            mime.setUrls([QUrl.fromLocalFile(path)])
        drag = QDrag(self)
        drag.setMimeData(mime)
        icon = self.item(rows[0]).icon()
        pm = icon.pixmap(QSize(80, 104))
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(pm.width() // 2, pm.height() // 2))
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.CopyAction)
        self._end_drag_feedback()

    # ------------------------------------------------ ドロップ受け入れ
    def _is_internal(self, mime) -> list | None:
        """同じウィンドウからのドラッグなら、そのページ番号を返す。"""
        if mime.hasFormat(MIME):
            try:
                d = json.loads(bytes(mime.data(MIME)).decode())
            except Exception:
                return None
            if d.get("pid") == os.getpid() and d.get("win") == id(self.owner):
                return d["rows"]
        return None

    @staticmethod
    def _page_count_in(mime) -> int | None:
        if mime.hasFormat(MIME):
            try:
                return len(json.loads(bytes(mime.data(MIME)).decode())["rows"])
            except Exception:
                return None
        return None

    def _row_at(self, pos) -> int:
        it = self.itemAt(pos)
        if it is None:
            if self.count() and pos.y() < self.visualItemRect(self.item(0)).top():
                return 0
            # 項目の間のすき間：近い方の境目
            for r in range(self.count()):
                rect = self.visualItemRect(self.item(r))
                if pos.y() < rect.top():
                    return r
            return self.count()
        r = self.visualItemRect(it)
        row = self.row(it)
        return row + 1 if pos.y() > r.center().y() else row

    def _copy_requested(self, ev) -> bool:
        return bool(ev.modifiers() & Qt.KeyboardModifier.ControlModifier)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME) or ev.mimeData().hasUrls():
            ev.accept()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        md = ev.mimeData()
        if not (md.hasFormat(MIME) or md.hasUrls()):
            ev.ignore()
            return
        pos = ev.position().toPoint()
        self._drop_row = self._row_at(pos)
        internal = self._is_internal(md) is not None
        if internal and not self._copy_requested(ev):
            ev.setDropAction(Qt.DropAction.MoveAction)
            self._drop_label = "ここへ移動"
        else:
            ev.setDropAction(Qt.DropAction.CopyAction)
            n = self._page_count_in(md)
            if internal:
                self._drop_label = f"ここに複製（{n} ページ）" if n else "ここに複製"
            else:
                self._drop_label = f"ここに挿入（{n} ページ）" if n else "ここに挿入"
        ev.accept()
        # 端に近づいたら自動でスクロール
        h = self.viewport().height()
        self._scroll_dir = -1 if pos.y() < AUTOSCROLL_MARGIN else (1 if pos.y() > h - AUTOSCROLL_MARGIN else 0)
        if self._scroll_dir and not self._scroll_timer.isActive():
            self._scroll_timer.start()
        elif not self._scroll_dir:
            self._scroll_timer.stop()
        self.viewport().update()

    def _autoscroll(self):
        if not self._scroll_dir:
            self._scroll_timer.stop()
            return
        sb = self.verticalScrollBar()
        sb.setValue(sb.value() + self._scroll_dir * 18)
        p = self.viewport().mapFromGlobal(self.cursor().pos())
        self._drop_row = self._row_at(p)
        self.viewport().update()

    def _end_drag_feedback(self):
        self._drop_row = None
        self._scroll_dir = 0
        self._scroll_timer.stop()
        self.viewport().update()

    def dragLeaveEvent(self, ev):
        self._end_drag_feedback()

    def dropEvent(self, ev):
        md = ev.mimeData()
        dest = self._row_at(ev.position().toPoint())
        copy = self._copy_requested(ev)
        self._end_drag_feedback()
        rows = self._is_internal(md)
        if rows is not None:
            if copy:
                ev.setDropAction(Qt.DropAction.CopyAction)
                ev.accept()
                self.pagesCopied.emit(rows, dest)
            else:
                ev.setDropAction(Qt.DropAction.MoveAction)
                ev.accept()
                self.pagesMoved.emit(rows, dest)
            return
        paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        if paths:
            ev.setDropAction(Qt.DropAction.CopyAction)
            ev.accept()
            # ドロップ元（別のウィンドウ）の処理が終わってから差し込む
            QTimer.singleShot(0, lambda: self.filesDropped.emit(paths, dest))
        else:
            ev.ignore()

    # ------------------------------------------------ 差し込み位置の横線
    def drop_line_y(self) -> int | None:
        if self._drop_row is None:
            return None
        if self.count() == 0:
            return 12
        if self._drop_row < self.count():
            top = self.visualItemRect(self.item(self._drop_row)).top()
            if self._drop_row > 0:
                prev = self.visualItemRect(self.item(self._drop_row - 1)).bottom()
                return (prev + top) // 2
            return max(4, top - 3)
        return self.visualItemRect(self.item(self.count() - 1)).bottom() + 4

    def paintEvent(self, ev):
        super().paintEvent(ev)
        y = self.drop_line_y()
        if y is None:
            return
        col = self.palette().color(QPalette.ColorRole.Highlight)
        if col.lightness() > 200 or col.saturation() < 60:
            col = QColor("#2b6cb0")
        w = self.viewport().width()
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(col, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(10, y, w - 10, y)
        # 両端の三角
        for x, d in ((4, 1), (w - 4, -1)):
            tri = QPainterPath()
            tri.moveTo(x, y - 7)
            tri.lineTo(x + d * 9, y)
            tri.lineTo(x, y + 7)
            tri.closeSubpath()
            p.fillPath(tri, col)
        # ラベル
        if self._drop_label:
            f = QFont(self.font())
            f.setPointSizeF(max(8.0, f.pointSizeF() - 0.5))
            f.setBold(True)
            p.setFont(f)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(self._drop_label) + 14
            th = fm.height() + 4
            r = QRectF((w - tw) / 2, y - th / 2, tw, th)
            if r.top() < 0:
                r.moveTop(0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(r, th / 2, th / 2)
            p.setPen(QColor("white"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._drop_label)
        p.end()
