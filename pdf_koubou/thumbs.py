"""ページのサムネイル一覧。ドラッグで並べ替え・ファイルの差し込み・ページの書き出し。"""
from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget

MIME = "application/x-pdfkoubou-pages"


class ThumbList(QListWidget):
    pagesMoved = Signal(list, int)      # rows, 差し込み位置
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
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contextRequested)
        self._drop_row = None
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
        mime.setData(MIME, QByteArray(json.dumps({"win": id(self.owner), "rows": rows}).encode()))
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
        self._drop_row = None
        self.viewport().update()

    # ------------------------------------------------ ドロップ受け入れ
    def _is_internal(self, mime) -> list | None:
        if mime.hasFormat(MIME):
            try:
                d = json.loads(bytes(mime.data(MIME)).decode())
            except Exception:
                return None
            if d.get("win") == id(self.owner):
                return d["rows"]
        return None

    def _row_at(self, pos) -> int:
        it = self.itemAt(pos)
        if it is None:
            # 最後の項目より下なら末尾
            if self.count() and pos.y() < self.visualItemRect(self.item(0)).top():
                return 0
            return self.count()
        r = self.visualItemRect(it)
        row = self.row(it)
        return row + 1 if pos.y() > r.center().y() else row

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
        self._drop_row = self._row_at(ev.position().toPoint())
        ev.setDropAction(Qt.DropAction.MoveAction if self._is_internal(md) is not None
                         else Qt.DropAction.CopyAction)
        ev.accept()
        self.viewport().update()

    def dragLeaveEvent(self, ev):
        self._drop_row = None
        self.viewport().update()

    def dropEvent(self, ev):
        md = ev.mimeData()
        dest = self._row_at(ev.position().toPoint())
        self._drop_row = None
        self.viewport().update()
        rows = self._is_internal(md)
        if rows is not None:
            ev.setDropAction(Qt.DropAction.MoveAction)
            ev.accept()
            self.pagesMoved.emit(rows, dest)
            return
        paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        if paths:
            ev.setDropAction(Qt.DropAction.CopyAction)
            ev.accept()
            self.filesDropped.emit(paths, dest)
        else:
            ev.ignore()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._drop_row is None or self.count() == 0:
            return
        if self._drop_row < self.count():
            y = self.visualItemRect(self.item(self._drop_row)).top() - 3
        else:
            y = self.visualItemRect(self.item(self.count() - 1)).bottom() + 3
        p = QPainter(self.viewport())
        p.setPen(QPen(QColor("#2b6cb0"), 3))
        p.drawLine(8, y, self.viewport().width() - 8, y)
        p.end()
