@echo off
rem Build: dist\PDFKoubou\PDFKoubou.exe
cd /d %~dp0
"%~dp0.venv\Scripts\python.exe" -m PyInstaller --noconfirm --windowed --name PDFKoubou --icon pdf_koubou\icon.ico ^
  --add-data "pdf_koubou\icon.ico;." ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtCharts ^
  run.py
copy /y pdf_koubou\icon.ico dist\PDFKoubou\PDFKoubou.ico >nul
xcopy /y /i /q licenses dist\PDFKoubou\licenses >nul
copy /y LICENSE dist\PDFKoubou\LICENSE.txt >nul
