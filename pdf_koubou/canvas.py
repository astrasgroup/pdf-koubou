"""ページ表示と書き込み（オーバーレイ）のキャンバス。シーン座標 = 表示座標(pt)。"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QCursor, QFont, QImage, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem,
                               QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
                               QGraphicsTextItem, QGraphicsView)

from . import pdfcore

OVERLAY_ROLE = 1  # data(0) にこの値を入れて書き込みアイテムを識別


def qfont(size: int) -> QFont:
    f = QFont(pdfcore.FONT_FAMILY)
    f.setPixelSize(max(1, int(size)))
    return f


def pen_of(color: str, width: float, dash=False) -> QPen:
    p = QPen(QColor(color), width)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if dash:
        p.setStyle(Qt.PenStyle.DashLine)
        p.setCosmetic(True)
    return p


# ------------------------------------------------------------------ 書き込みアイテム
class OverlayMixin:
    def setup_overlay(self):
        self.setData(0, OVERLAY_ROLE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)


class TextItem(QGraphicsTextItem, OverlayMixin):
    kind = "text"

    def __init__(self, text="", size=14, color="#000000", on_empty=None):
        super().__init__(text)
        self.setup_overlay()
        self.size = size
        self.color = color
        self.on_empty = on_empty
        self.document().setDocumentMargin(0)
        self.setFont(qfont(size))
        self.setDefaultTextColor(QColor(color))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    def set_style(self, size=None, color=None):
        if size is not None:
            self.size = size
            self.setFont(qfont(size))
        if color is not None:
            self.color = color
            self.setDefaultTextColor(QColor(color))

    def editing(self) -> bool:
        return bool(self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction)

    def start_edit(self, cursor_end=True):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if cursor_end:
            c = self.textCursor()
            c.movePosition(c.MoveOperation.End)
            self.setTextCursor(c)

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        c = self.textCursor()
        c.clearSelection()
        self.setTextCursor(c)
        if not self.toPlainText().strip() and self.on_empty:
            QTimer.singleShot(0, lambda: self.on_empty(self))

    def boundingRect(self):
        r = super().boundingRect()
        if r.width() < self.size:
            r.setWidth(self.size)
        return r

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.editing():
            painter.setPen(pen_of("#2b6cb0", 1, dash=True))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2, -2, 2, 2))

    def to_record(self) -> dict:
        lines = []
        doc = self.document()
        lay = doc.documentLayout()
        block = doc.begin()
        while block.isValid():
            top = lay.blockBoundingRect(block).y()
            bl = block.layout()
            for i in range(bl.lineCount()):
                ln = bl.lineAt(i)
                seg = block.text()[ln.textStart(): ln.textStart() + ln.textLength()]
                lines.append([seg, ln.x(), top + ln.y() + ln.ascent()])
            block = block.next()
        br = super().boundingRect()
        return {"kind": "text", "x": self.pos().x(), "y": self.pos().y(),
                "w": br.width(), "h": br.height(), "text": self.toPlainText(),
                "size": self.size, "color": self.color, "lines": lines}


class PenItem(QGraphicsPathItem, OverlayMixin):
    kind = "pen"

    def __init__(self, pts, color, width):
        super().__init__()
        self.setup_overlay()
        self.pts = [QPointF(x, y) for x, y in pts]
        self.color, self.width = color, width
        self.setPen(pen_of(color, width))
        self._rebuild()

    def add_point(self, p: QPointF):
        self.pts.append(p)
        self._rebuild()

    def _rebuild(self):
        path = QPainterPath()
        if self.pts:
            path.moveTo(self.pts[0])
            for p in self.pts[1:]:
                path.lineTo(p)
        self.setPath(path)

    def to_record(self):
        o = self.pos()
        return {"kind": "pen", "pts": [[p.x() + o.x(), p.y() + o.y()] for p in self.pts],
                "color": self.color, "width": self.width}


class BoxItem(QGraphicsRectItem, OverlayMixin):
    """四角・マーカー。kind = 'rect' | 'hl'"""

    def __init__(self, kind, x, y, w, h, color, width=2):
        super().__init__(0, 0, w, h)
        self.setup_overlay()
        self.kind, self.color, self.width = kind, color, width
        self.setPos(x, y)
        self.apply_style()

    def apply_style(self):
        if self.kind == "hl":
            c = QColor(self.color)
            c.setAlphaF(0.35)
            self.setBrush(QBrush(c))
            self.setPen(Qt.PenStyle.NoPen)
        else:
            self.setBrush(Qt.BrushStyle.NoBrush)
            self.setPen(pen_of(self.color, self.width))

    def to_record(self):
        r = self.rect()
        return {"kind": self.kind, "x": self.pos().x(), "y": self.pos().y(),
                "w": r.width(), "h": r.height(), "color": self.color, "width": self.width}


class OvalItem(QGraphicsEllipseItem, OverlayMixin):
    kind = "ellipse"

    def __init__(self, x, y, w, h, color, width=2):
        super().__init__(0, 0, w, h)
        self.setup_overlay()
        self.color, self.width = color, width
        self.setPos(x, y)
        self.setPen(pen_of(color, width))

    def to_record(self):
        r = self.rect()
        return {"kind": "ellipse", "x": self.pos().x(), "y": self.pos().y(),
                "w": r.width(), "h": r.height(), "color": self.color, "width": self.width}


class ImageItem(QGraphicsPixmapItem, OverlayMixin):
    kind = "img"

    def __init__(self, data: bytes, x, y, w, h):
        super().__init__()
        self.setup_overlay()
        self.data_bytes = data
        img = QImage.fromData(data)
        self.setPixmap(QPixmap.fromImage(img))
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.w, self.h = w, h
        if img.width() and img.height():
            self.setTransform(self.transform().fromScale(w / img.width(), h / img.height()))
        self.setPos(x, y)

    def to_record(self):
        return {"kind": "img", "x": self.pos().x(), "y": self.pos().y(),
                "w": self.w, "h": self.h, "data": self.data_bytes}


def item_from_record(rec: dict, on_empty=None):
    k = rec["kind"]
    if k == "text":
        it = TextItem(rec["text"], rec["size"], rec["color"], on_empty)
        it.setPos(rec["x"], rec["y"])
        return it
    if k == "pen":
        return PenItem(rec["pts"], rec["color"], rec["width"])
    if k in ("rect", "hl"):
        return BoxItem(k, rec["x"], rec["y"], rec["w"], rec["h"], rec["color"], rec.get("width", 2))
    if k == "ellipse":
        return OvalItem(rec["x"], rec["y"], rec["w"], rec["h"], rec["color"], rec.get("width", 2))
    if k == "img":
        return ImageItem(rec["data"], rec["x"], rec["y"], rec["w"], rec["h"])
    raise ValueError(k)


# ------------------------------------------------------------------ カーソル
def eraser_cursor(diameter_px: float, dpr: float) -> QCursor:
    """実際に消える大きさの円＋右下に小さな消しゴムの絵。中心がクリック位置。"""
    d = max(6.0, min(diameter_px, 240.0))
    pad = 22
    size = int(d + pad * 2)
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = size / 2
    r = d / 2
    p.setBrush(QColor(229, 62, 62, 30))
    p.setPen(QPen(QColor("#ffffff"), 3))
    p.drawEllipse(QPointF(c, c), r, r)
    p.setPen(QPen(QColor("#c53030"), 1.4))
    p.drawEllipse(QPointF(c, c), r, r)
    p.setPen(QPen(QColor("#c53030"), 1))
    p.drawLine(QPointF(c - 2, c), QPointF(c + 2, c))
    p.drawLine(QPointF(c, c - 2), QPointF(c, c + 2))
    # 消しゴムの絵（右下）
    p.translate(c + r * 0.72 + 2, c + r * 0.72 + 2)
    p.rotate(-35)
    p.setPen(QPen(QColor("#333333"), 1))
    p.setBrush(QColor("#f48fb1"))
    p.drawRoundedRect(QRectF(0, 0, 9, 14), 2, 2)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(0, 9, 9, 5), 1.5, 1.5)
    p.end()
    return QCursor(pm, int(c), int(c))


def lasso_cursor(dpr: float) -> QCursor:
    """投げ縄の絵。縄の先（左下）がクリック位置。"""
    size = 32
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(QRectF(9, 3, 20, 13))
    rope = QPainterPath(QPointF(2, 29))
    rope.cubicTo(QPointF(4, 22), QPointF(12, 22), QPointF(14, 15))
    for w, col in ((4, "#ffffff"), (1.8, "#222222")):
        p.setPen(QPen(QColor(col), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.drawPath(rope)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#c53030"))
    p.drawEllipse(QPointF(2, 29), 2, 2)
    p.end()
    return QCursor(pm, 2, 29)


# ------------------------------------------------------------------ ビュー
DRAG_TOOLS = {"rect", "ellipse", "hl", "erase_rect", "erase_ellipse", "crop", "stamp"}


class PageView(QGraphicsView):
    """ツールごとのマウス操作を受け持つ。実際の PDF 変更は MainWindow に通知して行う。"""
    # 通知
    aboutToChange = Signal()            # 書き込みを変更する直前（元に戻す用）
    changed = Signal()                  # 書き込みが変わった
    regionChosen = Signal(str, QRectF, object)   # tool, 範囲, 多角形(list) / 筆跡
    pageFlip = Signal(int)              # +1 / -1
    moveBegin = Signal()                # 移動の開始（元に戻す候補を作る）
    moveCommit = Signal()               # 実際に動いたので確定
    eraserResize = Signal(int)          # [ ] キー・Alt+ホイールでの大きさ変更（増減）
    toolKey = Signal(int)               # 文字入力中でないときのキー（ツール切替）
    zoomStep = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
                            | QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QColor("#5f6670"))
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.tool = "select"
        self.color = "#d00000"
        self.width_ = 2.0
        self.font_size = 14
        self.eraser_width = 16.0
        self.stamp_data: bytes | None = None
        self.stamp_size = (1, 1)
        self.page_rect = QRectF()
        self.page_item = None
        self._drag_start = None
        self._preview = None
        self._pen = None
        self._lasso = None
        self._move_snapshot_pending = False
        self._move_positions = None
        self._wheel_acc = 0
        self._last_mouse = None
        self.viewport().setMouseTracking(True)

    # ---------------------------------------------------------- 表示
    def show_page(self, qimage: QImage, scale: float, page_w: float, page_h: float, records):
        sc = self.scene()
        sc.clear()
        self._preview = self._pen = self._lasso = None
        self.page_rect = QRectF(0, 0, page_w, page_h)
        shadow = sc.addRect(QRectF(3, 3, page_w, page_h), Qt.PenStyle.NoPen, QBrush(QColor(0, 0, 0, 70)))
        shadow.setZValue(-2)
        self.page_item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
        self.page_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.page_item.setScale(1 / scale)
        self.page_item.setZValue(-1)
        sc.addItem(self.page_item)
        for rec in records:
            self.add_overlay(item_from_record(rec, self._remove_empty_text))
        m = 24
        sc.setSceneRect(QRectF(-m, -m, page_w + 2 * m, page_h + 2 * m))
        self.apply_tool_flags()

    def replace_page_image(self, qimage: QImage, scale: float):
        if self.page_item is not None:
            self.page_item.setPixmap(QPixmap.fromImage(qimage))
            self.page_item.setScale(1 / scale)

    def add_overlay(self, item):
        self.scene().addItem(item)
        self._set_item_flags(item)
        return item

    def overlay_items(self):
        return [it for it in self.scene().items(Qt.SortOrder.AscendingOrder) if it.data(0) == OVERLAY_ROLE]

    def records(self):
        return [it.to_record() for it in self.overlay_items()]

    def set_zoom(self, z: float):
        self.resetTransform()
        self.scale(z, z)
        if self.tool == "eraser":
            self.update_cursor()

    # ---------------------------------------------------------- ツール
    def set_eraser_width(self, w: float):
        self.eraser_width = w
        self.update_cursor()

    def update_cursor(self):
        t = self.tool
        dpr = self.devicePixelRatioF()
        if t == "eraser":
            cur = eraser_cursor(self.eraser_width * self.transform().m11(), dpr)
        elif t == "erase_lasso":
            cur = lasso_cursor(dpr)
        else:
            shapes = {"select": Qt.CursorShape.ArrowCursor, "text": Qt.CursorShape.IBeamCursor,
                      "pan": Qt.CursorShape.OpenHandCursor}
            cur = QCursor(shapes.get(t, Qt.CursorShape.CrossCursor))
        self.viewport().setCursor(cur)

    def set_tool(self, tool: str):
        self.end_text_edit()
        self.tool = tool
        self.apply_tool_flags()
        self.update_cursor()
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if tool == "pan"
                         else QGraphicsView.DragMode.NoDrag)

    def apply_tool_flags(self):
        for it in self.overlay_items():
            self._set_item_flags(it)

    def _set_item_flags(self, it):
        movable = self.tool == "select"
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable or self.tool == "text")

    def end_text_edit(self):
        fi = self.scene().focusItem()
        if isinstance(fi, TextItem):
            fi.clearFocus()

    def editing_text(self) -> bool:
        fi = self.scene().focusItem()
        return isinstance(fi, TextItem) and fi.editing()

    def _remove_empty_text(self, item):
        if item.scene() is self.scene() and not item.toPlainText().strip():
            self.scene().removeItem(item)
            self.changed.emit()

    def delete_selected(self) -> bool:
        items = [it for it in self.scene().selectedItems() if it.data(0) == OVERLAY_ROLE]
        if not items:
            return False
        self.aboutToChange.emit()
        for it in items:
            self.scene().removeItem(it)
        self.changed.emit()
        return True

    def apply_style_to_selected(self, color=None, width=None, size=None):
        items = [it for it in self.scene().selectedItems() if it.data(0) == OVERLAY_ROLE]
        fi = self.scene().focusItem()
        if isinstance(fi, TextItem) and fi not in items:
            items.append(fi)
        if not items:
            return
        self.aboutToChange.emit()
        for it in items:
            if isinstance(it, TextItem):
                it.set_style(size=size, color=color)
            elif isinstance(it, PenItem):
                if color: it.color = color
                if width: it.width = width
                it.setPen(pen_of(it.color, it.width))
            elif isinstance(it, BoxItem):
                if color: it.color = color
                if width: it.width = width
                it.apply_style()
            elif isinstance(it, OvalItem):
                if color: it.color = color
                if width: it.width = width
                it.setPen(pen_of(it.color, it.width))
        self.changed.emit()

    def _clamp(self, p: QPointF) -> QPointF:
        r = self.page_rect
        return QPointF(min(max(p.x(), r.left()), r.right()), min(max(p.y(), r.top()), r.bottom()))

    # ---------------------------------------------------------- マウス
    def mousePressEvent(self, ev):
        if self.page_item is None:
            return super().mousePressEvent(ev)
        if ev.button() == Qt.MouseButton.MiddleButton:
            self._pan_from = ev.position()
            return
        if ev.button() != Qt.MouseButton.LeftButton or self.tool == "pan":
            return super().mousePressEvent(ev)
        p = self.mapToScene(ev.position().toPoint())
        t = self.tool
        if t == "select":
            it = self.itemAt(ev.position().toPoint())
            if it is not None and it.data(0) == OVERLAY_ROLE:
                self._move_snapshot_pending = True
                self.moveBegin.emit()
            super().mousePressEvent(ev)
            self._move_positions = {id(x): QPointF(x.pos()) for x in self.overlay_items()}
            return
        if t == "text":
            it = self.itemAt(ev.position().toPoint())
            if isinstance(it, TextItem):
                if not it.editing():
                    self.aboutToChange.emit()
                    it.start_edit(cursor_end=False)
                return super().mousePressEvent(ev)
            if self.editing_text():
                # 入力中に外をクリック → 確定するだけ（次のクリックで新しい文字）
                self.end_text_edit()
                return
            if not self.page_rect.contains(p):
                return
            self.aboutToChange.emit()
            item = TextItem("", self.font_size, self.color, self._remove_empty_text)
            item.setPos(p.x(), p.y() - self.font_size * 0.6)
            self.add_overlay(item)
            item.start_edit()
            self.changed.emit()
            return
        p = self._clamp(p)
        if t in ("pen", "eraser"):
            if t == "pen":
                self._pen = PenItem([(p.x(), p.y())], self.color, self.width_)
            else:
                self._pen = PenItem([(p.x(), p.y())], "#ff4fa3", self.eraser_width)
                self._pen.setOpacity(0.45)
            self.scene().addItem(self._pen)
            return
        if t == "erase_lasso":
            self._lasso = [p]
            self._preview = self.scene().addPath(QPainterPath(), pen_of("#e53e3e", 1, dash=True),
                                                 QBrush(QColor(229, 62, 62, 40)))
            return
        if t in DRAG_TOOLS:
            self._drag_start = p
            ellipse = t in ("ellipse", "erase_ellipse")
            brush = QBrush(QColor(229, 62, 62, 40)) if t.startswith("erase") else \
                QBrush(QColor(43, 108, 176, 30)) if t == "crop" else Qt.BrushStyle.NoBrush
            pen = pen_of("#e53e3e" if t.startswith("erase") else "#2b6cb0", 1, dash=True)
            self._preview = (self.scene().addEllipse if ellipse else self.scene().addRect)(
                QRectF(p, p), pen, brush)
            return

    def mouseMoveEvent(self, ev):
        if getattr(self, "_pan_from", None) is not None:
            d = ev.position() - self._pan_from
            self._pan_from = ev.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        self._last_mouse = self.mapToScene(ev.position().toPoint())
        p = self._clamp(self._last_mouse)
        if self._pen is not None:
            last = self._pen.pts[-1]
            if math.hypot(p.x() - last.x(), p.y() - last.y()) > 0.6:
                self._pen.add_point(p)
            return
        if self._lasso is not None:
            self._lasso.append(p)
            path = QPainterPath()
            path.addPolygon(QPolygonF(self._lasso))
            path.closeSubpath()
            self._preview.setPath(path)
            return
        if self._drag_start is not None and self._preview is not None:
            r = QRectF(self._drag_start, p).normalized()
            if self.tool == "stamp" and self.stamp_data:
                iw, ih = self.stamp_size
                r.setHeight(r.width() * ih / max(iw, 1))
            self._preview.setRect(r)
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.MiddleButton:
            self._pan_from = None
            return
        if self._pen is not None:
            pen, self._pen = self._pen, None
            if self.tool == "eraser":
                self.scene().removeItem(pen)
                pts = [(q.x(), q.y()) for q in pen.pts]
                self.regionChosen.emit("eraser", QRectF(), pts)
                return
            if len(pen.pts) < 2:
                pen.add_point(pen.pts[0] + QPointF(0.5, 0.5))
            self.scene().removeItem(pen)
            self.aboutToChange.emit()
            self.add_overlay(pen)
            self.changed.emit()
            return
        if self._lasso is not None:
            pts, self._lasso = self._lasso, None
            self.scene().removeItem(self._preview)
            self._preview = None
            if len(pts) >= 3:
                poly = QPolygonF(pts)
                self.regionChosen.emit("erase_lasso", poly.boundingRect(), [(q.x(), q.y()) for q in pts])
            return
        if self._drag_start is not None and self._preview is not None:
            r = self._preview.rect()
            self.scene().removeItem(self._preview)
            self._preview, self._drag_start = None, None
            self._finish_drag(r)
            return
        super().mouseReleaseEvent(ev)
        if self.tool == "select" and self._move_snapshot_pending:
            self._move_snapshot_pending = False
            moved = any(id(x) in (self._move_positions or {}) and
                        x.pos() != self._move_positions[id(x)] for x in self.overlay_items())
            if moved:
                self.moveCommit.emit()

    def _finish_drag(self, r: QRectF):
        t = self.tool
        small = r.width() < 3 and r.height() < 3
        if t == "stamp":
            if not self.stamp_data:
                return
            iw, ih = self.stamp_size
            if small:
                w = 90.0
                r = QRectF(r.x() - w / 2, r.y() - w * ih / iw / 2, w, w * ih / iw)
            self.aboutToChange.emit()
            self.add_overlay(ImageItem(self.stamp_data, r.x(), r.y(), r.width(), r.height()))
            self.changed.emit()
            return
        if small:
            return
        if t in ("rect", "hl"):
            self.aboutToChange.emit()
            self.add_overlay(BoxItem(t, r.x(), r.y(), r.width(), r.height(), self.color, self.width_))
            self.changed.emit()
        elif t == "ellipse":
            self.aboutToChange.emit()
            self.add_overlay(OvalItem(r.x(), r.y(), r.width(), r.height(), self.color, self.width_))
            self.changed.emit()
        elif t in ("erase_rect", "erase_ellipse", "crop"):
            poly = None
            if t == "erase_ellipse":
                path = QPainterPath()
                path.addEllipse(r)
                poly = [(q.x(), q.y()) for q in path.toFillPolygon()]
            else:
                poly = [(r.left(), r.top()), (r.right(), r.top()), (r.right(), r.bottom()), (r.left(), r.bottom())]
            self.regionChosen.emit(t, r, poly)

    def mouseDoubleClickEvent(self, ev):
        if self.tool == "select":
            it = self.itemAt(ev.position().toPoint())
            if isinstance(it, TextItem):
                self.aboutToChange.emit()
                it.start_edit()
                return
        super().mouseDoubleClickEvent(ev)

    def remove_overlays_in(self, path: QPainterPath) -> int:
        n = 0
        for it in self.overlay_items():
            if path.contains(it.sceneBoundingRect().center()):
                self.scene().removeItem(it)
                n += 1
        return n

    # ---------------------------------------------------------- ホイール・キー
    def wheelEvent(self, ev):
        if self.tool == "eraser" and ev.modifiers() & Qt.KeyboardModifier.AltModifier:
            d = ev.angleDelta().y() or ev.angleDelta().x()
            self.eraserResize.emit(2 if d > 0 else -2)
            return
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoomStep.emit(1 if ev.angleDelta().y() > 0 else -1)
            return
        vs = self.verticalScrollBar()
        dy = ev.angleDelta().y()
        if (dy < 0 and vs.value() >= vs.maximum()) or (dy > 0 and vs.value() <= vs.minimum()):
            self._wheel_acc += dy
            if abs(self._wheel_acc) >= 240:
                self.pageFlip.emit(-1 if self._wheel_acc > 0 else 1)
                self._wheel_acc = 0
            return
        self._wheel_acc = 0
        super().wheelEvent(ev)

    def keyPressEvent(self, ev):
        if self.editing_text():
            if ev.key() == Qt.Key.Key_Escape:
                self.end_text_edit()
                return
            return super().keyPressEvent(ev)
        if ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.delete_selected():
                return
        if ev.key() in (Qt.Key.Key_PageDown,):
            self.pageFlip.emit(1); return
        if ev.key() in (Qt.Key.Key_PageUp,):
            self.pageFlip.emit(-1); return
        if ev.key() in (Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight):
            self.eraserResize.emit(2 if ev.key() == Qt.Key.Key_BracketRight else -2)
            return
        if ev.key() == Qt.Key.Key_Escape:
            self.scene().clearSelection()
            self.toolKey.emit(int(ev.key()))
            return
        if not ev.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)                 and Qt.Key.Key_A <= ev.key() <= Qt.Key.Key_Z:
            self.toolKey.emit(int(ev.key()))
            return
        super().keyPressEvent(ev)
