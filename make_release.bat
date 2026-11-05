@echo off
rem Build exe + installer, then make release\<version> (setup + source zip + docs)
cd /d %~dp0
call "%~dp0build_installer.bat" || exit /b 1
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\make_release.py"
