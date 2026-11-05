"""配布用フォルダ release\\<版> を作る。

中身：
  PDF工房_セットアップ_<版>.exe   … installer\\output から
  PDF工房_ソースコード_<版>.zip   … このリポジトリのソース一式（AGPL の義務として同梱）
  インストールの手引き.txt / 利用条件.txt / README.md / LICENSE.txt
"""
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDE_DIRS = {".venv", "build", "dist", "release", "__pycache__", ".git", "output"}
EXCLUDE_EXT = {".pyc", ".spec", ".log"}


def version():
    src = open(os.path.join(ROOT, "pdf_koubou", "app.py"), encoding="utf-8").read()
    v = re.search(r'^VERSION = "([^"]+)"', src, re.M).group(1)
    iss = open(os.path.join(ROOT, "installer", "PDFKoubou.iss"), encoding="utf-8-sig").read()
    v2 = re.search(r'#define AppVersion "([^"]+)"', iss).group(1)
    if v != v2:
        sys.exit(f"版が一致しません：app.py={v} / PDFKoubou.iss={v2}")
    return v


def make_source_zip(dst):
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(ROOT):
            dirs[:] = sorted(x for x in dirs if x not in EXCLUDE_DIRS)
            for f in sorted(files):
                if os.path.splitext(f)[1] in EXCLUDE_EXT:
                    continue
                full = os.path.join(d, f)
                rel = os.path.relpath(full, ROOT)
                z.write(full, os.path.join("pdf-koubou", rel))


def main():
    v = version()
    setup = os.path.join(ROOT, "installer", "output", f"PDF工房_セットアップ_{v}.exe")
    if not os.path.exists(setup):
        sys.exit(f"セットアップがありません。先に build_installer.bat を実行してください：{setup}")
    out = os.path.join(ROOT, "release", v)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    shutil.copy2(setup, out)
    make_source_zip(os.path.join(out, f"PDF工房_ソースコード_{v}.zip"))
    shutil.copy2(os.path.join(ROOT, "installer", "インストールの手引き.txt"), out)
    shutil.copy2(os.path.join(ROOT, "installer", "license_ja.txt"), os.path.join(out, "利用条件.txt"))
    shutil.copy2(os.path.join(ROOT, "README.md"), out)
    shutil.copy2(os.path.join(ROOT, "LICENSE"), os.path.join(out, "LICENSE.txt"))
    print(out)
    for f in sorted(os.listdir(out)):
        print(f"  {f}  {os.path.getsize(os.path.join(out, f)) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
