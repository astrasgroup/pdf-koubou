"""ページの回転・トリミング・トリミング解除のダイアログ（ページ範囲＋奇数/偶数の指定つき）。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget)

MM = 72 / 25.4  # 1 mm の pt

PARITY_ITEMS = [("both", "偶数および奇数ページ"), ("odd", "奇数ページのみ"), ("even", "偶数ページのみ")]
ORIENT_ITEMS = [("any", "任意の向きのページ"), ("portrait", "縦向きのページのみ"), ("landscape", "横向きのページのみ")]

UNITS = {"mm": ("ミリ", MM, 1), "pt": ("ポイント", 1.0, 1), "inch": ("インチ", 72.0, 2)}


def filter_rows(rows, parity="both", orient="any", sizes=None):
    """rows（0 始まり）を、ページ番号（1 始まり）の奇数・偶数と、ページの向きで絞り込む。"""
    out = []
    for r in rows:
        n = r + 1
        if parity == "odd" and n % 2 == 0:
            continue
        if parity == "even" and n % 2 == 1:
            continue
        if orient != "any" and sizes is not None:
            w, h = sizes[r]
            if orient == "portrait" and w > h:
                continue
            if orient == "landscape" and h >= w:
                continue
        out.append(r)
    return out


class PageRangeBox(QGroupBox):
    """ページ範囲（すべて／選択したページ／開始〜終了）と、適用先（奇数・偶数）。"""
    changed = Signal()

    def __init__(self, n_pages, current, selected, sizes=None, with_orient=False, parent=None):
        super().__init__("ページ範囲", parent)
        self.n = n_pages
        self.selected = sorted(selected)
        self.sizes = sizes
        g = QGridLayout(self)
        self.r_all = QRadioButton("すべて(&A)")
        self.r_sel = QRadioButton(f"選択したページ(&S)（{len(self.selected)} ページ）")
        self.r_rng = QRadioButton("ページ(&P)")
        grp = QButtonGroup(self)
        for b in (self.r_all, self.r_sel, self.r_rng):
            grp.addButton(b)
            b.toggled.connect(self._sync)
        self.r_sel.setEnabled(len(self.selected) > 1)
        self.sp_from = QSpinBox()
        self.sp_to = QSpinBox()
        for sp in (self.sp_from, self.sp_to):
            sp.setRange(1, n_pages)
            sp.setMinimumWidth(70)
            sp.valueChanged.connect(self._sync)
        self.sp_from.setValue(current + 1)
        self.sp_to.setValue(current + 1)
        g.addWidget(self.r_all, 0, 0, 1, 4)
        g.addWidget(self.r_sel, 1, 0, 1, 4)
        g.addWidget(self.r_rng, 2, 0)
        rng = QHBoxLayout()
        rng.addWidget(QLabel("開始ページ(&F)："))
        rng.addWidget(self.sp_from)
        rng.addSpacing(12)
        rng.addWidget(QLabel("終了ページ(&T)："))
        rng.addWidget(self.sp_to)
        rng.addWidget(QLabel(f"/ {n_pages}"))
        rng.addStretch(1)
        g.addLayout(rng, 2, 1, 1, 3)
        g.addWidget(QLabel("適用先(&Y)："), 3, 0)
        self.cb_parity = QComboBox()
        for key, label in PARITY_ITEMS:
            self.cb_parity.addItem(label, key)
        self.cb_parity.currentIndexChanged.connect(self._sync)
        g.addWidget(self.cb_parity, 3, 1, 1, 3)
        self.cb_orient = None
        if with_orient:
            self.cb_orient = QComboBox()
            for key, label in ORIENT_ITEMS:
                self.cb_orient.addItem(label, key)
            self.cb_orient.currentIndexChanged.connect(self._sync)
            g.addWidget(self.cb_orient, 4, 1, 1, 3)
        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet("font-weight: bold;")
        g.addWidget(self.lbl_count, 5, 0, 1, 4)
        (self.r_sel if len(self.selected) > 1 else self.r_rng).setChecked(True)
        self._sync()

    def base_rows(self):
        if self.r_all.isChecked():
            return list(range(self.n))
        if self.r_sel.isChecked():
            return list(self.selected)
        a, b = sorted((self.sp_from.value(), self.sp_to.value()))
        return list(range(a - 1, b))

    def rows(self):
        orient = self.cb_orient.currentData() if self.cb_orient else "any"
        return filter_rows(self.base_rows(), self.cb_parity.currentData(), orient, self.sizes)

    def _sync(self, *_):
        on = self.r_rng.isChecked()
        self.sp_from.setEnabled(on)
        self.sp_to.setEnabled(on)
        k = len(self.rows())
        self.lbl_count.setText(f"対象：{k} ページ" if k else "対象のページがありません")
        self.changed.emit()


def _buttons(dlg, ok_text="OK"):
    bb = QDialogButtonBox()
    ok = bb.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
    bb.addButton("キャンセル", QDialogButtonBox.ButtonRole.RejectRole)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb, ok


class RotateDialog(QDialog):
    """ページの回転。direction() は 90 / -90 / 180。"""

    def __init__(self, n_pages, current, selected, sizes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ページの回転")
        v = QVBoxLayout(self)
        h = QHBoxLayout()
        h.addWidget(QLabel("方向(&D)："))
        self.cb_dir = QComboBox()
        for deg, label in ((-90, "左 90° 回転（反時計回り）"), (90, "右 90° 回転（時計回り）"), (180, "180° 回転")):
            self.cb_dir.addItem(label, deg)
        h.addWidget(self.cb_dir)
        h.addStretch(1)
        v.addLayout(h)
        self.range = PageRangeBox(n_pages, current, selected, sizes, with_orient=True)
        v.addWidget(self.range)
        bb, self.ok = _buttons(self)
        v.addWidget(bb)
        self.range.changed.connect(lambda: self.ok.setEnabled(bool(self.range.rows())))
        self.ok.setEnabled(bool(self.range.rows()))

    def direction(self):
        return self.cb_dir.currentData()

    def rows(self):
        return self.range.rows()


class CropPreview(QWidget):
    """ページの縮小画像に、トリミング後の範囲を枠で重ねる。"""

    def __init__(self, pixmap: QPixmap, page_w, page_h, parent=None):
        super().__init__(parent)
        self.pm = pixmap
        self.pw, self.ph = page_w, page_h
        self.margins = (0, 0, 0, 0)  # 上・下・左・右（pt）
        self.setMinimumSize(240, 300)

    def set_margins(self, top, bottom, left, right):
        self.margins = (top, bottom, left, right)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        W, H = self.width() - 16, self.height() - 16
        s = min(W / self.pw, H / self.ph)
        w, h = self.pw * s, self.ph * s
        x0, y0 = (self.width() - w) / 2, (self.height() - h) / 2
        p.drawPixmap(QRectF(x0, y0, w, h), self.pm, QRectF(self.pm.rect()))
        p.setPen(QPen(QColor("#888888"), 1))
        p.drawRect(QRectF(x0, y0, w, h))
        t, b, l, r = self.margins
        keep = QRectF(x0 + l * s, y0 + t * s, max(0.0, w - (l + r) * s), max(0.0, h - (t + b) * s))
        # 切り取られる部分を暗くする
        shade = QColor(0, 0, 0, 90)
        p.fillRect(QRectF(x0, y0, w, keep.top() - y0), shade)
        p.fillRect(QRectF(x0, keep.bottom(), w, y0 + h - keep.bottom()), shade)
        p.fillRect(QRectF(x0, keep.top(), keep.left() - x0, keep.height()), shade)
        p.fillRect(QRectF(keep.right(), keep.top(), x0 + w - keep.right(), keep.height()), shade)
        p.setPen(QPen(QColor("#1d4ed8"), 2))
        p.drawRect(keep)
        p.end()


class CropDialog(QDialog):
    """ページのトリミング：上下左右の余白を数値で指定し、ページ範囲・奇数/偶数を選んで適用。"""

    def __init__(self, n_pages, current, selected, page_w, page_h, preview: QPixmap,
                 auto_margins=None, init_margins=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ページのトリミング")
        self.page_w, self.page_h = page_w, page_h
        self.auto_margins = auto_margins  # 白い余白を除いたときの (上, 下, 左, 右) pt
        self.unit = "mm"
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        root.addLayout(top)

        box = QGroupBox("余白のトリミング（表示中のページの向きで、上下左右を指定）")
        top.addWidget(box, 1)
        g = QGridLayout(box)
        g.addWidget(QLabel("単位(&N)："), 0, 0)
        self.cb_unit = QComboBox()
        for key, (label, _, _) in UNITS.items():
            self.cb_unit.addItem(label, key)
        self.cb_unit.currentIndexChanged.connect(self._unit_changed)
        g.addWidget(self.cb_unit, 0, 1)
        self.ck_ratio = QCheckBox("上下・左右を同じ値にする(&P)")
        g.addWidget(self.ck_ratio, 1, 0, 1, 2)
        self.spins = {}
        for i, (key, label) in enumerate((("top", "上(&O)："), ("bottom", "下(&B)："),
                                          ("left", "左(&L)："), ("right", "右(&R)："))):
            sp = QDoubleSpinBox()
            sp.setDecimals(1)
            sp.setSingleStep(1.0)
            sp.setMinimumWidth(110)
            sp.valueChanged.connect(lambda _v, k=key: self._spin_changed(k))
            g.addWidget(QLabel(label), 2 + i, 0)
            g.addWidget(sp, 2 + i, 1)
            self.spins[key] = sp
        self.ck_auto = QCheckBox("白い余白を削除(&W)（表示中のページで検出）")
        self.ck_auto.setEnabled(auto_margins is not None)
        self.ck_auto.toggled.connect(self._auto_toggled)
        g.addWidget(self.ck_auto, 6, 0, 1, 2)
        b_zero = QPushButton("ゼロに設定(&Z)")
        b_zero.clicked.connect(lambda: self.set_margins_pt(0, 0, 0, 0))
        g.addWidget(b_zero, 7, 0)
        self.b_back = QPushButton("囲んだ範囲に戻す(&V)")
        self.b_back.setEnabled(init_margins is not None)
        self.b_back.clicked.connect(lambda: self.set_margins_pt(*init_margins))
        g.addWidget(self.b_back, 7, 1)
        g.setRowStretch(8, 1)

        right = QVBoxLayout()
        top.addLayout(right)
        self.preview = CropPreview(preview, page_w, page_h)
        right.addWidget(self.preview, 1)
        self.lbl_size = QLabel()
        self.lbl_size.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.lbl_size)

        self.range = PageRangeBox(n_pages, current, selected)
        root.addWidget(self.range)
        note = QLabel("ページごとの今の表示範囲から、指定した幅だけ切り取ります。"
                      "元に戻すには Ctrl+Z、または「ページ」→「トリミングを解除」。")
        note.setWordWrap(True)
        root.addWidget(note)
        bb, self.ok = _buttons(self)
        root.addWidget(bb)
        self.range.changed.connect(self._validate)

        self._busy = False
        self._apply_unit_range()
        self.set_margins_pt(*(init_margins or (0, 0, 0, 0)))

    # ---- 単位
    def _factor(self):
        return UNITS[self.unit][1]

    def _apply_unit_range(self):
        f = self._factor()
        dec = UNITS[self.unit][2]
        for key, sp in self.spins.items():
            limit = (self.page_h if key in ("top", "bottom") else self.page_w) / f
            sp.blockSignals(True)
            sp.setDecimals(dec)
            sp.setRange(0, round(limit, dec))
            sp.setSuffix(" " + UNITS[self.unit][0])
            sp.blockSignals(False)

    def _unit_changed(self, _):
        cur = self.margins_pt()
        self.unit = self.cb_unit.currentData()
        self._apply_unit_range()
        self.set_margins_pt(*cur)

    # ---- 値
    def margins_pt(self):
        f = self._factor()
        return tuple(self.spins[k].value() * f for k in ("top", "bottom", "left", "right"))

    def set_margins_pt(self, top, bottom, left, right):
        f = self._factor()
        self._busy = True
        for k, val in zip(("top", "bottom", "left", "right"), (top, bottom, left, right)):
            self.spins[k].setValue(max(0.0, val) / f)
        self._busy = False
        self._update_view()

    def _spin_changed(self, key):
        if self._busy:
            return
        if self.ck_ratio.isChecked():
            pair = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}[key]
            self._busy = True
            self.spins[pair].setValue(self.spins[key].value())
            self._busy = False
        if self.ck_auto.isChecked():
            self.ck_auto.blockSignals(True)
            self.ck_auto.setChecked(False)
            self.ck_auto.blockSignals(False)
        self._update_view()

    def _auto_toggled(self, on):
        if on and self.auto_margins:
            self.set_margins_pt(*self.auto_margins)
        elif not on:
            self.set_margins_pt(0, 0, 0, 0)

    def _update_view(self):
        t, b, l, r = self.margins_pt()
        self.preview.set_margins(t, b, l, r)
        w, h = self.page_w - l - r, self.page_h - t - b
        if w < 10 or h < 10:
            self.lbl_size.setText("余白が大きすぎます")
        else:
            self.lbl_size.setText(f"トリミング後のページサイズ：{w / MM:.1f} × {h / MM:.1f} mm")
        self._validate()

    def _validate(self):
        t, b, l, r = self.margins_pt()
        ok_size = (self.page_w - l - r) >= 10 and (self.page_h - t - b) >= 10
        self.ok.setEnabled(ok_size and bool(self.range.rows()))

    def rows(self):
        return self.range.rows()


class UncropDialog(QDialog):
    def __init__(self, n_pages, current, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("トリミングを解除")
        v = QVBoxLayout(self)
        lbl = QLabel("トリミングを解除して、ページを元の大きさに戻します。")
        v.addWidget(lbl)
        self.range = PageRangeBox(n_pages, current, selected)
        self.range.r_all.setChecked(True)
        v.addWidget(self.range)
        bb, self.ok = _buttons(self, "解除する")
        v.addWidget(bb)
        self.range.changed.connect(lambda: self.ok.setEnabled(bool(self.range.rows())))

    def rows(self):
        return self.range.rows()
