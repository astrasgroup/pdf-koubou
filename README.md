# PDF工房

PDF のページ操作・書き込み・消去・変換ができる、Windows 用の無料の PDF アプリです。
ファイルは PC の中だけで処理し、インターネットには送りません。

## 動く環境

- Windows 10 / 11（64ビット）
- Word・Excel・PowerPoint のファイルを PDF にするには、Microsoft Office（または LibreOffice）が必要です。ほかの機能は Office なしで使えます。

## インストール

1. `PDF工房_セットアップ_<版>.exe` を実行します。管理者権限は要りません。
2. 「Windows によって PC が保護されました」という青い画面が出たら、「詳細情報」→「実行」で進めます。くわしくは「インストールの手引き.txt」を見てください。

アンインストールは、Windows の「設定 → アプリ」か、スタートメニューの「PDF工房 をアンインストール」から行います。

## できること

| 分類 | 機能 |
|---|---|
| ページ | 並べ替え（一覧でドラッグ）、回転、削除、抽出、分割、空白ページの挿入、トリミング・解除 |
| 回転・トリミングの指定 | 「ページの回転」「ページのトリミング」で、ページ範囲・奇数ページのみ・偶数ページのみ・縦向き/横向きのページを指定。トリミングは上下左右の余白を mm で指定、白い余白の自動検出も可 |
| 結合 | 一覧へ PDF・画像などをドラッグすると、その位置に結合。ウィンドウ2つの間でページを移動 |
| 抽出 | 一覧からデスクトップやフォルダへドラッグすると、そのページだけの PDF ができる |
| 書き込み | テキスト（クリックして入力）、ペン、四角、丸、マーカー、画像（ハンコ） |
| 消去 | 消しゴム、範囲消去（四角＝データごと削除／丸・投げ縄＝紙の色で塗りつぶし） |
| 手書きの自動消去 | 赤ペン・青ペンの書き込みを色で見分けて消す、PDF のペン注釈を一括削除 |
| PDF に変換 | Word・Excel・PowerPoint、画像、テキスト（TXT・MD など）、XPS・EPUB・SVG。1つずつ保存／1つにまとめて保存 |
| 書き出し | ページを PNG / JPEG で書き出し、印刷 |
| 外観 | 色味の切り替え（ライト・ダーク・ベージュなど） |

書き込みは、保存するまでは何度でも動かしたり直したりできます。保存するとページに書き込まれ、ほかの PDF ソフトでも同じように表示されます。

## 注意

- 大切なファイルを編集するときは、元のファイルを別に残しておいてください。
- 「色ペンの書き込みを消す」を使ったページは画像になり、そのページの文字は検索・選択できなくなります。
- 黒の鉛筆やボールペンの手書きは、印刷の文字と自動では区別できません。消しゴムか範囲消去で消してください。
- パスワード付きの PDF は、パスワードを入力すると開けます。保存したファイルには、パスワードがかかりません。

## ライセンス

Copyright (C) 2026 Astras Group

PDF工房 は [GNU Affero General Public License v3.0](LICENSE)（AGPL-3.0）で公開しています。
自由に使う・配る・改変することができます。改変したものを配る場合は、そのソースコードも同じライセンスで公開してください。

使用しているソフトウェアとそのライセンスは [licenses/THIRD_PARTY.txt](licenses/THIRD_PARTY.txt) にあります。PDF の処理には PyMuPDF（AGPL-3.0）、画面には Qt / PySide6（LGPL-3.0）を使っています。

このソフトウェアは無保証です。使用によって生じた損害について、作者は責任を負いません。

Microsoft Office、Word、Excel、PowerPoint、Windows は、米国 Microsoft Corporation の商標です。

## 連絡先

Astras Group
- ウェブサイト：https://astras-tokushima.com/
- メール：info@astras-tokushima.com

## 開発

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py                 # そのまま起動
.venv\Scripts\python tests\smoke_test.py    # 機能テスト（画面なし）
.venv\Scripts\python tests\ui_test.py       # 操作テスト（画面なし）
build.bat                                   # exe を作る（dist\PDFKoubou）
build_installer.bat                         # インストーラーを作る（installer\output）
make_release.bat                            # 配布用フォルダを作る（release\<版>）
```

- 版を上げるときは、`pdf_koubou/app.py` の `VERSION` と `installer/PDFKoubou.iss` の `AppVersion` を両方変えます。
- インストーラーの作成には Inno Setup 6 が必要です。

構成：`pdf_koubou/pdfcore.py`（PDF 処理）、`convert.py`（PDF への変換）、`canvas.py`（ページ表示と書き込み）、`thumbs.py`（ページ一覧）、`theme.py`（外観）、`app.py`（画面とメニュー）。
