"""画面を出さずに主要機能を一通り動かす確認用スクリプト。"""
import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fitz
from PySide6.QtCore import QRectF, QPointF
from PySide6.QtWidgets import QApplication
from pdf_koubou import app as A, pdfcore
from pdf_koubou.canvas import TextItem, PenItem, BoxItem, ImageItem

out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.makedirs(out, exist_ok=True)
# 素材：印刷文字＋赤ペン注釈＋赤い手書き（ベクター）のPDF
src = fitz.open()
for i in range(4):
    p = src.new_page()
    p.insert_text((72, 100), f"Page {i+1} printed text", fontsize=20)
    p.draw_line((72, 140), (300, 160), color=(0.9, 0, 0), width=3)   # 赤ペン（画像化対象）
    a = p.add_ink_annot([[(100, 300), (150, 320), (200, 300)]]); a.set_colors(stroke=(0, 0, 1)); a.update()
src_path = os.path.join(out, "src.pdf"); src.save(src_path)
img_path = os.path.join(out, "stamp.png")
pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 30), False); pm.set_rect(pm.irect, (220, 0, 0)); pm.save(img_path)

app = QApplication([])
w = A.MainWindow(); w.show()
w.open_paths([src_path]); app.processEvents()
assert len(w.doc) == 4
v = w.view
# テキスト（日本語）・ペン・四角・画像
v.aboutToChange.emit()
t = TextItem("日本語のテキスト\n2行目", 16, "#d00000"); t.setPos(80, 400); v.add_overlay(t)
v.add_overlay(PenItem([(80, 500), (120, 520), (160, 500)], "#1d4ed8", 3))
v.add_overlay(BoxItem("rect", 300, 400, 100, 50, "#000000", 2))
v.add_overlay(BoxItem("hl", 70, 80, 200, 30, "#f5d000"))
v.add_overlay(ImageItem(open(img_path, "rb").read(), 400, 500, 60, 30))
v.changed.emit()
# 回転（書き込みも一緒に移る）
w.rotate_pages(90); assert w.doc[0].rotation == 90
# 元に戻す / やり直し
w.undo(); assert w.doc[0].rotation == 0; w.redo(); assert w.doc[0].rotation == 90
# 並べ替え：p3 を先頭へ
w.move_pages([2], 0); assert "Page 3" in w.doc[0].get_text()
# 結合（画像を末尾に）・空白ページ
w.insert_files([img_path, src_path], len(w.doc)); assert len(w.doc) == 9
# 範囲消去□（データごと） on page index 1 (= Page1? 回転なしページ)
w.goto(2)
w._region_chosen("erase_rect", QRectF(60, 70, 300, 50), [(60,70),(360,70),(360,120),(60,120)])
assert "printed" not in w.doc[2].get_text(), w.doc[2].get_text()
# 投げ縄で注釈を消す
before = len(list(w.doc[2].annots()))
w._region_chosen("erase_lasso", QRectF(90, 280, 120, 60), [(90,280),(210,280),(210,340),(90,340)])
assert len(list(w.doc[2].annots())) == before - 1
# 消しゴム
w._region_chosen("eraser", QRectF(), [(72,140),(300,160)])
# 色ペン消去（赤）
pdfcore.remove_colored_ink(w.doc, 3, "red"); w.doc_changed(); w.refresh_all()
# トリミング（このページ）
w.goto(0)
pdfcore.set_crop(w.doc[0], 20, 20, 400, 500)
# 保存・抽出・分割・画像書き出し
w.path = os.path.join(out, "result.pdf"); assert w._write(w.path)
res = fitz.open(w.path)
txt = res[0].get_text()
print("pages", len(res), "| p1 text:", txt.replace("\n", " / ")[:120])
ext = pdfcore.build_output(w.doc, w.overlays, [0, 1]); ext.save(os.path.join(out, "extract.pdf"))
for i, pg in enumerate(res):
    pg.get_pixmap(dpi=50).save(os.path.join(out, f"result_{i+1}.png"))
tmp = w.export_pages_temp([1, 2]); print("drag temp:", os.path.basename(tmp), len(fitz.open(tmp)))
print("ranges:", pdfcore.parse_ranges("1-3、5, 7-", 9))
w.modified = False; w.close()
print("OK")
