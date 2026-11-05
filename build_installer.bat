@echo off
rem Build app (dist) and then the installer (installer\output)
cd /d %~dp0
call "%~dp0build.bat"
if errorlevel 1 exit /b 1
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" /Qp "%~dp0installer\PDFKoubou.iss"
