@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
set PORT=8765
echo ============================================
echo   InterviewAI starting at http://127.0.0.1:%PORT%
echo   demo account: demo / demo1234
echo ============================================
start "" http://127.0.0.1:%PORT%
python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
