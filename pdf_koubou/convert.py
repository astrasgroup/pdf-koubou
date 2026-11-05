"""いろいろな形式のファイルを PDF に変換する。

- Word / Excel / PowerPoint …… インストール済みの Microsoft Office で変換（なければ LibreOffice）
- 画像（JPG・PNG など）……… A4 に合わせて1枚1ページ
- テキスト（TXT・MD・CSV 以外のテキスト類）… 日本語フォントで A4 に組む
- XPS・EPUB・SVG など …… PyMuPDF で変換
"""
from __future__ import annotations

import glob
import os
import subprocess
import tempfile
import time

import fitz

from . import pdfcore

WORD_EXTS = {".doc", ".docx", ".docm", ".dot", ".dotx", ".rtf", ".odt", ".htm", ".html", ".mht", ".mhtml", ".wpd"}
EXCEL_EXTS = {".xls", ".xlsx", ".xlsm", ".xlsb", ".csv", ".ods"}
PPT_EXTS = {".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp"}
OFFICE_EXTS = WORD_EXTS | EXCEL_EXTS | PPT_EXTS
TEXT_EXTS = {".txt", ".md", ".log", ".ini", ".json", ".xml", ".yaml", ".yml", ".py", ".js", ".ts",
             ".css", ".bat", ".ps1", ".tsv", ".text"}
MUPDF_EXTS = {".xps", ".oxps", ".epub", ".cbz", ".fb2", ".mobi", ".svg"}

SUPPORTED_EXTS = {".pdf"} | pdfcore.IMAGE_EXTS | OFFICE_EXTS | TEXT_EXTS | MUPDF_EXTS

FILE_FILTER = ("対応するファイル (" + " ".join("*" + e for e in sorted(SUPPORTED_EXTS)) + ");;"
               "PDF (*.pdf);;"
               "Word (*.doc *.docx *.rtf *.odt);;Excel (*.xls *.xlsx *.csv *.ods);;"
               "PowerPoint (*.ppt *.pptx *.odp);;"
               "画像 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp);;"
               "テキスト (*.txt *.md *.log);;すべてのファイル (*)")


def ext_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def is_supported(path: str) -> bool:
    return os.path.isfile(path) and ext_of(path) in SUPPORTED_EXTS


def kind_label(path: str) -> str:
    e = ext_of(path)
    if e in WORD_EXTS:
        return "Word"
    if e in EXCEL_EXTS:
        return "Excel"
    if e in PPT_EXTS:
        return "PowerPoint"
    if e in pdfcore.IMAGE_EXTS:
        return "画像"
    if e in TEXT_EXTS:
        return "テキスト"
    return e.lstrip(".").upper()


class ConvertError(Exception):
    pass


# ------------------------------------------------------------------ Office
_PS_SCRIPT = r"""
param([string]$kind, [string]$src, [string]$dst)
$ErrorActionPreference = 'Stop'
$missing = [System.Reflection.Missing]::Value
$app = $null
try {
  if ($kind -eq 'word') {
    $app = New-Object -ComObject Word.Application
    $app.Visible = $false
    $app.DisplayAlerts = 0
    $doc = $app.Documents.Open($src, $false, $true, $false, 'x-no-password-x')
    $doc.ExportAsFixedFormat($dst, 17)
    $doc.Close(0)
    if ($app.Documents.Count -eq 0) { $app.Quit() }
  } elseif ($kind -eq 'excel') {
    $app = New-Object -ComObject Excel.Application
    $app.Visible = $false
    $app.DisplayAlerts = $false
    $wb = $app.Workbooks.Open($src, 0, $true, $missing, 'x-no-password-x')
    $wb.ExportAsFixedFormat(0, $dst)
    $wb.Close($false)
    if ($app.Workbooks.Count -eq 0) { $app.Quit() }
  } elseif ($kind -eq 'ppt') {
    $app = New-Object -ComObject PowerPoint.Application
    $pres = $app.Presentations.Open($src, -1, 0, 0)
    $pres.SaveAs($dst, 32)
    $pres.Close()
    if ($app.Presentations.Count -eq 0) { $app.Quit() }
  }
  exit 0
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  try { if ($app -ne $null -and $kind -ne 'ppt') { $app.Quit() } } catch {}
  exit 1
}
"""


def _wait(proc: subprocess.Popen, timeout: float, tick=None):
    t0 = time.time()
    while proc.poll() is None:
        if tick:
            tick()
        if time.time() - t0 > timeout:
            proc.kill()
            raise ConvertError("変換に時間がかかりすぎたため中止しました")
        time.sleep(0.1)


def _office_has(progid: str) -> bool:
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid))
        return True
    except OSError:
        return False


def _find_soffice() -> str | None:
    for pat in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        for p in glob.glob(pat):
            return p
    return None


def office_to_pdf(src: str, dst: str, tick=None):
    e = ext_of(src)
    kind, progid, name = (("word", "Word.Application", "Word") if e in WORD_EXTS else
                          ("excel", "Excel.Application", "Excel") if e in EXCEL_EXTS else
                          ("ppt", "PowerPoint.Application", "PowerPoint"))
    src = os.path.abspath(src)
    dst = os.path.abspath(dst)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if _office_has(progid):
        script = os.path.join(tempfile.gettempdir(), "pdfkoubou_office2pdf.ps1")
        with open(script, "w", encoding="utf-8-sig") as f:
            f.write(_PS_SCRIPT)
        proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-File", script, kind, src, dst],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
        _wait(proc, 300, tick)
        err = proc.stderr.read().decode("cp932", "replace").strip()
        if proc.returncode != 0 or not os.path.exists(dst):
            if "password" in err.lower() or "パスワード" in err:
                raise ConvertError(f"パスワードが設定されているため変換できません。{name} で開いて解除してから変換してください。")
            raise ConvertError(f"{name} で変換できませんでした。\n{err[:300]}")
        return
    soffice = _find_soffice()
    if soffice:
        outdir = tempfile.mkdtemp(prefix="pdfkoubou_lo_")
        proc = subprocess.Popen([soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, src],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
        _wait(proc, 300, tick)
        out = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
        if not os.path.exists(out):
            raise ConvertError("LibreOffice で変換できませんでした。")
        os.replace(out, dst)
        return
    raise ConvertError(f"{name} が見つからないため変換できません。Microsoft Office か LibreOffice が必要です。")


# ------------------------------------------------------------------ テキスト
def read_text(path: str) -> str:
    data = open(path, "rb").read()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    for enc in ("utf-8-sig", "cp932", "euc_jp"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def text_to_pdf_doc(path: str, fontsize: float = 10.5) -> fitz.Document:
    text = read_text(path).replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    font = fitz.Font(fontfile=pdfcore.FONT_FILE) if pdfcore.FONT_FILE else fitz.Font("japan")
    margin_x, margin_top, margin_bottom = 56, 60, 56
    width = pdfcore.A4.width - margin_x * 2
    lh = fontsize * 1.65
    widths: dict[str, float] = {}

    def w(ch):
        v = widths.get(ch)
        if v is None:
            v = widths[ch] = font.text_length(ch, fontsize=fontsize)
        return v

    lines = []
    for raw in text.split("\n"):
        cur, cw = "", 0.0
        for ch in raw:
            cwid = w(ch)
            if cw + cwid > width and cur:
                lines.append(cur)
                cur, cw = "", 0.0
            cur += ch
            cw += cwid
        lines.append(cur)
    per_page = int((pdfcore.A4.height - margin_top - margin_bottom) // lh)
    doc = fitz.open()
    total = max(1, -(-len(lines) // per_page))
    title = os.path.basename(path)
    for pi in range(total):
        page = doc.new_page(width=pdfcore.A4.width, height=pdfcore.A4.height)
        tw = fitz.TextWriter(page.rect)
        y = margin_top
        for ln in lines[pi * per_page:(pi + 1) * per_page]:
            if ln:
                tw.append((margin_x, y), ln, font=font, fontsize=fontsize)
            y += lh
        foot = f"{title}　{pi + 1} / {total}"
        tw.append((margin_x, pdfcore.A4.height - 28), foot, font=font, fontsize=8)
        tw.write_text(page, color=(0, 0, 0))
    try:
        doc.subset_fonts()
    except Exception:
        pass
    return doc


# ------------------------------------------------------------------ 画像（MuPDF が読めない形式は Qt で）
def image_to_pdf_doc(path: str) -> fitz.Document:
    try:
        return pdfcore.image_to_pdf_doc(path)
    except Exception:
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QImage
        img = QImage(path)
        if img.isNull():
            raise ConvertError("画像を読み込めませんでした")
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        tmp = os.path.join(tempfile.mkdtemp(prefix="pdfkoubou_img_"), "img.png")
        with open(tmp, "wb") as f:
            f.write(bytes(buf.data()))
        return pdfcore.image_to_pdf_doc(tmp)


# ------------------------------------------------------------------ まとめ
def to_pdf_doc(path: str, password_cb=None, tick=None) -> fitz.Document | None:
    """どの形式でも PDF ドキュメント（メモリ上）にして返す。"""
    e = ext_of(path)
    if e == ".pdf":
        return pdfcore.open_as_pdf(path, password_cb)
    if e in pdfcore.IMAGE_EXTS:
        return image_to_pdf_doc(path)
    if e in OFFICE_EXTS:
        tmp = os.path.join(tempfile.mkdtemp(prefix="pdfkoubou_conv_"), "out.pdf")
        office_to_pdf(path, tmp, tick)
        with open(tmp, "rb") as f:
            return fitz.open(stream=f.read(), filetype="pdf")
    if e in TEXT_EXTS:
        return text_to_pdf_doc(path)
    if e in MUPDF_EXTS:
        src = fitz.open(path)
        return fitz.open(stream=src.convert_to_pdf(), filetype="pdf")
    raise ConvertError(f"この形式（{e or '拡張子なし'}）には対応していません")
