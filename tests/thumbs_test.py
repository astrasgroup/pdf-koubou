"""ページ一覧：ドロップの受け付け・複製・挿入後の選択のテスト（画面なし）。
別ウィンドウ間の本物のドラッグは、手元で2つのウィンドウを開いて確認する。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile

import fitz
from PySide6.QtWidgets import QApplication

from pdf_koubou import app as A

qa = QApplication.instance() or QApplication(sys.argv)


def make(prefix, n):
    d = fitz.open()
    for i in range(n):
        d.new_page(width=595, height=842).insert_text((100, 200), f"{prefix}{i + 1}", fontsize=60)
    return d


def labels(doc):
    return [pg.get_text().strip() for pg in doc]


w = A.MainWindow(doc=make("A", 4))
w.show()

# 一覧の中身（viewport）がドロップを受け付けること（これが切れていると一覧に落としても「最後に結合」になる）
assert w.thumbs.viewport().acceptDrops(), "thumbs viewport must accept drops"

# 複製：2ページ目を 4ページ目の後ろへ（書き込みも複製される）
w.overlays[1] = [{"kind": "rect", "x": 10, "y": 10, "w": 50, "h": 50, "color": "#d00000", "width": 2}]
w.copy_pages([1], 4)
assert labels(w.doc) == ["A1", "A2", "A3", "A4", "A2"], labels(w.doc)
assert w.overlays[4] == w.overlays[1] and w.overlays[4] is not w.overlays[1]
assert w.thumbs.selected_rows() == [4] and w.cur == 4
print("copy:", labels(w.doc))

# メニューの「ページを複製」：選んだページのすぐ後ろ
w.select_rows([0])
w.duplicate_pages()
assert labels(w.doc) == ["A1", "A1", "A2", "A3", "A4", "A2"], labels(w.doc)
print("duplicate:", labels(w.doc))

# 別の PDF のページを、指定した位置へ挿入（別ウィンドウからのドロップと同じ処理）
src = make("B", 3)
tmp = os.path.join(tempfile.mkdtemp(), "B_p2.pdf")
one = fitz.open()
one.insert_pdf(src, from_page=1, to_page=1)
one.save(tmp)
w.insert_files([tmp], 2)
assert labels(w.doc) == ["A1", "A1", "B2", "A2", "A3", "A4", "A2"], labels(w.doc)
assert w.thumbs.selected_rows() == [2] and w.cur == 2
print("insert:", labels(w.doc))

# 元に戻す
w.undo()
assert labels(w.doc) == ["A1", "A1", "A2", "A3", "A4", "A2"], labels(w.doc)
print("undo OK")
w.modified = False
print("THUMBS OK")
