"""PDF 処理（画面に依存しない部分）。

座標の約束:
  「表示座標」= 回転を反映した、画面に見えている向きのページ座標（単位 pt、左上原点）。
  書き込み（オーバーレイ）はすべて表示座標で持ち、保存時にページへ焼き込む。
"""
from __future__ import annotations

import os
import statistics

import fitz  # PyMuPDF

# 日本語フォント（Windows 標準）。Qt 側の表示と同じフォントを使う。
FONT_CANDIDATES = [
    ("C:/Windows/Fonts/BIZ-UDGothicR.ttc", "BIZ UDGothic"),
    ("C:/Windows/Fonts/YuGothM.ttc", "Yu Gothic"),
    ("C:/Windows/Fonts/meiryo.ttc", "Meiryo"),
    ("C:/Windows/Fonts/msgothic.ttc", "MS Gothic"),
]


def pick_font():
    for path, family in FONT_CANDIDATES:
        if os.path.exists(path):
            return path, family
    return None, "sans-serif"


FONT_FILE, FONT_FAMILY = pick_font()
PDF_FONT_NAME = "KoubouJP"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
A4 = fitz.paper_rect("a4")


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def is_pdf(path: str) -> bool:
    return os.path.splitext(path)[1].lower() == ".pdf"


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


# ---------------------------------------------------------------- 画像 → PDF
def image_to_pdf_doc(path: str, fit_a4: bool = True) -> fitz.Document:
    """画像1枚を1ページのPDFにする。fit_a4 なら A4（縦横は画像に合わせる）に収める。"""
    img = fitz.open(path)
    rect = img[0].rect
    out = fitz.open()
    if fit_a4:
        page_rect = A4 if rect.height >= rect.width else fitz.Rect(0, 0, A4.height, A4.width)
    else:
        # 画像の大きさ（96dpi 相当）
        page_rect = fitz.Rect(0, 0, rect.width * 72 / 96, rect.height * 72 / 96)
    page = out.new_page(width=page_rect.width, height=page_rect.height)
    page.insert_image(page.rect, filename=path, keep_proportion=True)
    img.close()
    return out


def open_as_pdf(path: str, password_cb=None) -> fitz.Document | None:
    """PDF または画像を PDF ドキュメントとして開く（メモリ上）。"""
    if is_image(path):
        return image_to_pdf_doc(path)
    with open(path, "rb") as f:
        data = f.read()
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.needs_pass:
        ok = False
        while password_cb is not None:
            pw = password_cb(os.path.basename(path))
            if pw is None:
                break
            if doc.authenticate(pw):
                ok = True
                break
        if not ok:
            return None
        # 編集のためパスワードを外したコピーで扱う
        doc = fitz.open(stream=doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE), filetype="pdf")
    return doc


# ---------------------------------------------------------------- 書き込みの焼き込み
def burn_overlays(page: fitz.Page, records: list[dict]):
    """表示座標の書き込みをページ本体に描き込む。"""
    if not records:
        return
    rot = page.rotation
    derot = page.derotation_matrix

    def P(x, y):
        return fitz.Point(x, y) * derot

    def R(x, y, w, h):
        r = fitz.Rect(x, y, x + w, y + h) * derot
        r.normalize()
        return r

    font_ok = FONT_FILE is not None
    for rec in records:
        k = rec["kind"]
        color = hex_to_rgb(rec.get("color", "#000000"))
        if k == "text":
            for text, dx, by in rec["lines"]:
                if not text.strip():
                    continue
                kw = dict(fontsize=rec["size"], color=color, rotate=rot)
                if font_ok:
                    kw.update(fontname=PDF_FONT_NAME, fontfile=FONT_FILE)
                else:
                    kw.update(fontname="japan")
                page.insert_text(P(rec["x"] + dx, rec["y"] + by), text, **kw)
        elif k == "pen":
            pts = [P(x, y) for x, y in rec["pts"]]
            if len(pts) >= 2:
                page.draw_polyline(pts, color=color, width=rec.get("width", 2),
                                   lineCap=1, lineJoin=1)
        elif k == "rect":
            page.draw_rect(R(rec["x"], rec["y"], rec["w"], rec["h"]), color=color,
                           width=rec.get("width", 2))
        elif k == "ellipse":
            page.draw_oval(R(rec["x"], rec["y"], rec["w"], rec["h"]), color=color,
                           width=rec.get("width", 2))
        elif k == "hl":
            page.draw_rect(R(rec["x"], rec["y"], rec["w"], rec["h"]), color=None,
                           fill=color, fill_opacity=0.35, width=0)
        elif k == "img":
            page.insert_image(R(rec["x"], rec["y"], rec["w"], rec["h"]), stream=rec["data"],
                              keep_proportion=False, rotate=(-rot) % 360)


def build_output(doc: fitz.Document, overlays: list[list[dict]], rows=None) -> fitz.Document:
    """保存・抽出用のドキュメントを作る（元の doc は変更しない）。"""
    if rows is None:
        out = fitz.open(stream=doc.tobytes(), filetype="pdf")
        for i, recs in enumerate(overlays):
            burn_overlays(out[i], recs)
    else:
        out = fitz.open()
        for r in rows:
            out.insert_pdf(doc, from_page=r, to_page=r)
            burn_overlays(out[-1], overlays[r])
    if any(rec["kind"] == "text" for i in (rows if rows is not None else range(len(overlays)))
           for rec in overlays[i]):
        try:
            out.subset_fonts()
        except Exception:
            pass
    return out


def save_doc(doc: fitz.Document, path: str):
    tmp = path + ".koubou-tmp"
    doc.save(tmp, garbage=3, deflate=True)
    os.replace(tmp, path)


# ---------------------------------------------------------------- 範囲指定
def parse_ranges(text: str, n: int) -> list[list[int]]:
    """'1-3, 5, 7-' → [[0,1,2],[4],[6..n-1]]（0始まり）。"""
    groups = []
    for part in text.replace("，", ",").replace("、", ",").replace("～", "-").replace("〜", "-").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a.strip() else 1
            b = int(b) if b.strip() else n
        else:
            a = b = int(part)
        if a < 1 or b > n or a > b:
            raise ValueError(f"「{part}」はページの範囲外です（1～{n}）")
        groups.append(list(range(a - 1, b)))
    if not groups:
        raise ValueError("ページ範囲が入力されていません")
    return groups


def rows_label(rows: list[int]) -> str:
    rows = sorted(rows)
    if len(rows) == 1:
        return f"p{rows[0] + 1}"
    if rows == list(range(rows[0], rows[-1] + 1)):
        return f"p{rows[0] + 1}-{rows[-1] + 1}"
    return f"p{rows[0] + 1}ほか{len(rows)}ページ"


# ---------------------------------------------------------------- 消去
def sample_background(page: fitz.Page, pts) -> tuple:
    """範囲の境界上の色の中央値（紙の地の色に合わせる）。pts は表示座標。"""
    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), annots=False, alpha=False)
    rs, gs, bs = [], [], []
    for x, y in pts:
        ix, iy = int(x), int(y)
        if 0 <= ix < pix.width and 0 <= iy < pix.height:
            c = pix.pixel(ix, iy)
            rs.append(c[0]); gs.append(c[1]); bs.append(c[2])
    if not rs:
        return (1, 1, 1)
    return (statistics.median(rs) / 255, statistics.median(gs) / 255, statistics.median(bs) / 255)


def delete_annots_in(page: fitz.Page, contains) -> int:
    """表示座標で中心が範囲内にある注釈（ペン書き・コメント等）を削除。"""
    rotm = page.rotation_matrix
    xrefs = []
    for a in page.annots():
        c = ((a.rect.tl + a.rect.br) / 2) * rotm
        if contains(c.x, c.y):
            xrefs.append(a.xref)
    for x in xrefs:
        page.delete_annot(page.load_annot(x))
    return len(xrefs)


def erase_region(page: fitz.Page, shape: str, bbox, polygon, fill):
    """shape: 'rect' はデータごと削除（墨消し機能）、'ellipse' / 'lasso' は塗りつぶし。
    bbox=(x,y,w,h) 表示座標, polygon=[(x,y),...] 表示座標。"""
    derot = page.derotation_matrix
    x, y, w, h = bbox
    r = fitz.Rect(x, y, x + w, y + h) * derot
    r.normalize()
    if shape == "rect":
        page.add_redact_annot(r, fill=fill)
        page.apply_redactions(images=2, graphics=1, text=0)
    elif shape == "ellipse":
        page.draw_oval(r, color=None, fill=fill, width=0)
    else:
        pts = [fitz.Point(px, py) * derot for px, py in polygon]
        if len(pts) >= 3:
            page.draw_polyline(pts, color=None, fill=fill, closePath=True, width=0)


def set_crop(page: fitz.Page, x, y, w, h):
    """表示座標の矩形でトリミング（CropBox 設定）。"""
    r = fitz.Rect(x, y, x + w, y + h) & page.rect
    r = r * page.derotation_matrix
    r.normalize()
    cb = page.cropbox
    r = fitz.Rect(r.x0 + cb.x0, r.y0 + cb.y0, r.x1 + cb.x0, r.y1 + cb.y0) & page.mediabox
    if r.width < 10 or r.height < 10:
        raise ValueError("トリミング範囲が小さすぎます")
    page.set_cropbox(r)


# ---------------------------------------------------------------- 書き込みの座標変換
def transform_record(rec: dict, fn) -> dict:
    """fn(x, y) -> (x', y') で書き込みを移す（回転・トリミング時）。文字と画像は向きを保つ。"""
    rec = dict(rec)
    k = rec["kind"]
    if k == "pen":
        rec["pts"] = [list(fn(x, y)) for x, y in rec["pts"]]
        return rec
    x, y, w, h = rec["x"], rec["y"], rec.get("w", 0), rec.get("h", 0)
    if k in ("text", "img"):
        cx, cy = fn(x + w / 2, y + h / 2)
        rec["x"], rec["y"] = cx - w / 2, cy - h / 2
    else:
        x0, y0 = fn(x, y)
        x1, y1 = fn(x + w, y + h)
        rec["x"], rec["y"] = min(x0, x1), min(y0, y1)
        rec["w"], rec["h"] = abs(x1 - x0), abs(y1 - y0)
    return rec


def erase_stroke(page: fitz.Page, pts, width, fill):
    """消しゴムブラシ：なぞった線を背景色で塗る。pts は表示座標。"""
    derot = page.derotation_matrix
    P = [fitz.Point(x, y) * derot for x, y in pts]
    if len(P) == 1:
        P = [P[0], P[0] + (0.01, 0.01)]
    page.draw_polyline(P, color=fill, width=width, lineCap=1, lineJoin=1)


def delete_annots(page: fitz.Page, ink_only: bool) -> int:
    """手書き注釈（Ink）または全注釈を削除。リンクとフォーム欄は残す。"""
    xrefs = [a.xref for a in page.annots()
             if not ink_only or a.type[0] == fitz.PDF_ANNOT_INK]
    for x in xrefs:
        page.delete_annot(page.load_annot(x))
    return len(xrefs)


def remove_colored_ink(doc: fitz.Document, index: int, target: str, dpi: int = 200) -> None:
    """色の付いた書き込み（赤ペン・青ペン等）を画像処理で消す。
    ページは表示どおりの向きで画像化され、1枚の画像ページに置き換わる。
    target: 'red' / 'blue' / 'color'（色付きすべて）"""
    import numpy as np

    page = doc[index]
    disp = page.rect
    pix = page.get_pixmap(dpi=dpi, annots=True, alpha=False)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    a = a.astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    sat = (mx - mn)
    colored = (sat > 60) & (mx > 60)
    if target == "red":
        mask = colored & (r >= g + 40) & (r >= b + 25)
    elif target == "blue":
        mask = colored & (b >= r + 30) & (b >= g + 5)
    else:
        mask = colored
    # 線のふちのにじみも拾うため1画素広げる
    m = mask.copy()
    m[1:, :] |= mask[:-1, :]; m[:-1, :] |= mask[1:, :]
    m[:, 1:] |= mask[:, :-1]; m[:, :-1] |= mask[:, 1:]
    mask = m
    if not mask.any():
        raise LookupError("該当する色の書き込みが見つかりませんでした")
    paper = ~colored & (mx > 170)
    if paper.any():
        bg = np.median(a[paper], axis=0)
    else:
        bg = np.array([255, 255, 255])
    out = a.copy()
    out[mask] = bg.astype(np.int16)
    out = out.astype(np.uint8)
    newpix = fitz.Pixmap(fitz.csRGB, pix.width, pix.height, out.tobytes(), False)
    img_bytes = newpix.tobytes("jpeg", jpg_quality=88)
    newpage = doc.new_page(index, width=disp.width, height=disp.height)
    newpage.insert_image(newpage.rect, stream=img_bytes)
    doc.delete_page(index + 1)
