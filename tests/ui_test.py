"""マウス・キー操作の確認（画面なし）。"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fitz
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pdf_koubou import app as A
from pdf_koubou.canvas import TextItem, PenItem, BoxItem

app = QApplication([])
d = fitz.open()
for i in range(3):
    d.new_page().insert_text((72, 72), f"P{i+1}")
w = A.MainWindow(doc=d); w.resize(1200, 900); w.show(); app.processEvents()
v = w.view; vp = v.viewport()
def at(x, y): return v.mapFromScene(x, y)
# テキスト：クリック → 入力 → 外をクリックで確定 → 別の場所クリックで次
w.set_tool("text")
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=at(100, 200)); QTest.keyClicks(vp, "abc"); app.processEvents()
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=at(300, 400)); app.processEvents()  # 確定
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=at(300, 400)); QTest.keyClicks(vp, "xyz"); app.processEvents()
QTest.keyClick(vp, Qt.Key.Key_Escape); app.processEvents()
texts = [it.toPlainText() for it in v.overlay_items() if isinstance(it, TextItem)]
print("texts:", texts); assert sorted(texts) == ["abc", "xyz"]
# ツールのキー切替（入力中でないとき）
QTest.keyClick(vp, Qt.Key.Key_R); assert v.tool == "rect", v.tool
QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=at(100, 500)); QTest.mouseMove(vp, at(150, 530)); QTest.mouseMove(vp, at(200, 560))
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=at(200, 560)); app.processEvents()
assert any(isinstance(it, BoxItem) for it in v.overlay_items())
# 選択して移動 → 元に戻す
QTest.keyClick(vp, Qt.Key.Key_V)
n_undo = len(w.undo_stack)
box = next(it for it in v.overlay_items() if isinstance(it, BoxItem))
QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=at(100, 530)); QTest.mouseMove(vp, at(140, 600)); QTest.mouseMove(vp, at(160, 630))
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=at(160, 630)); app.processEvents()
print("moved:", box.pos(), "undo +", len(w.undo_stack) - n_undo)
QTest.keyClick(vp, Qt.Key.Key_Delete); app.processEvents()
assert not any(isinstance(it, BoxItem) for it in v.overlay_items())
w.undo(); assert any(isinstance(it, BoxItem) for it in v.overlay_items())
# ページ移動で書き込みが保持される
w.goto(1); w.goto(0); assert len(v.overlay_items()) == 3, len(v.overlay_items())
# サムネイルの並べ替え（シグナル経由）
w.thumbs.pagesMoved.emit([0], 3); assert "P1" in w.doc[2].get_text() and len(w.overlays[2]) == 3
print("UI OK")
w.modified = False; w.close()
