@echo off
rem 啟動本機預覽：雙擊本檔，瀏覽器開 http://127.0.0.1:8000/ ；關閉此視窗即停止
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
start "" http://127.0.0.1:8000/
".venv\Scripts\python.exe" -m mkdocs serve -a 127.0.0.1:8000 --livereload
pause
