"""ページの回転・トリミング・解除ダイアログの動作テスト（画面なし）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
from PySide6.QtCore import QRectF, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from pdf_koubou import app as A
from pdf_koubou import pagedialogs as P

qa = QApplication.instance() or QApplication(sys.argv)
OUT = os.environ.get("PAGEDLG_OUT")


def make_doc(n=6):
    d = fitz.open()
    for i in range(n):
        w, h = (842, 595) if i == 4 else (595, 842)
        pg = d.new_page(width=w, height=h)
        pg.draw_rect(fitz.Rect(80, 80, w - 80, h - 80), color=(0, 0, 0))
        pg.insert_text((100, 120), f"page {i + 1}")
    return d


# ---- 絞り込み
assert P.filter_rows(range(6), "odd") == [0, 2, 4]
assert P.filter_rows(range(6), "even") == [1, 3, 5]
sizes = [(595, 842)] * 4 + [(842, 595)] + [(595, 842)]
assert P.filter_rows(range(6), "both", "landscape", sizes) == [4]
assert P.filter_rows(range(6), "odd", "portrait", sizes) == [0, 2]

w = A.MainWindow(doc=make_doc())
w.show()


def run_dialog(cls_name, setup):
    """次に開くダイアログを setup してから OK を押す。"""
    def poke():
        for top in qa.topLevelWidgets():
            if top.__class__.__name__ == cls_name and top.isVisible():
                setup(top)
                if OUT:
                    top.grab().save(os.path.join(OUT, cls_name + ".png"))
                top.accept()
                return
        QTimer.singleShot(50, poke)
    QTimer.singleShot(50, poke)


# ---- 回転：すべてのページの奇数ページだけ 180°
def rot_setup(d):
    d.cb_dir.setCurrentIndex(2)          # 180°
    d.range.r_all.setChecked(True)
    d.range.cb_parity.setCurrentIndex(1)  # 奇数
    assert d.rows() == [0, 2, 4], d.rows()


run_dialog("RotateDialog", rot_setup)
w.rotate_dialog()
rots = [pg.rotation for pg in w.doc]
assert rots == [180, 0, 180, 0, 180, 0], rots
print("rotate odd 180:", rots)

# ---- 回転：2〜6 ページの横向きだけ 右 90°
def rot2_setup(d):
    d.cb_dir.setCurrentIndex(1)
    d.range.r_rng.setChecked(True)
    d.range.sp_from.setValue(2)
    d.range.sp_to.setValue(6)
    d.range.cb_orient.setCurrentIndex(2)  # 横向き
    assert d.rows() == [4], d.rows()


run_dialog("RotateDialog", rot2_setup)
w.rotate_dialog()
assert w.doc[4].rotation == 270, w.doc[4].rotation
print("rotate landscape only: page5 =", w.doc[4].rotation)

# ---- トリミング：偶数ページだけ 上下左右 10 mm
before = [(pg.rect.width, pg.rect.height) for pg in w.doc]


def crop_setup(d):
    d.range.r_all.setChecked(True)
    d.range.cb_parity.setCurrentIndex(2)  # 偶数
    d.set_margins_pt(*(10 * P.MM,) * 4)
    assert d.ok.isEnabled()


run_dialog("CropDialog", crop_setup)
w.crop_dialog()
after = [(round(pg.rect.width, 1), round(pg.rect.height, 1)) for pg in w.doc]
for i, ((bw, bh), (aw, ah)) in enumerate(zip(before, after)):
    if i % 2 == 1:
        assert abs((bw - aw) - 20 * P.MM) < 0.5 and abs((bh - ah) - 20 * P.MM) < 0.5, (i, before[i], after[i])
    else:
        assert (round(bw, 1), round(bh, 1)) == (aw, ah), i
print("crop even 10mm:", after)

# ---- 白い余白の検出と、ツールで囲んだ範囲からの起動
w.goto(0)


def crop2_setup(d):
    assert d.ck_auto.isEnabled()
    d.ck_auto.setChecked(True)
    t, b, l, r = d.margins_pt()
    assert all(60 < v < 90 for v in (t, b, l, r)), (t, b, l, r)
    d.range.r_rng.setChecked(True)  # このページだけ
    d.cb_unit.setCurrentIndex(1)     # pt に切り替えても値が保たれる
    t2, *_ = d.margins_pt()
    assert abs(t - t2) < 0.2, (t, t2)


run_dialog("CropDialog", crop2_setup)
w.crop_dialog(QRectF(50, 60, 300, 400))
print("auto margins page1:", w.doc[0].rect)

# ---- 解除：すべて
def un_setup(d):
    assert d.range.r_all.isChecked()


run_dialog("UncropDialog", un_setup)
w.uncrop()
assert all(pg.cropbox == pg.mediabox for pg in w.doc)
print("uncrop all OK")

# ---- 元に戻す
w.undo()
assert w.doc[1].cropbox != w.doc[1].mediabox
print("undo OK")
w.doc_modified = False
w.modified = False
print("PAGEDLG OK")
