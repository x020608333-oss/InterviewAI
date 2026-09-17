#!/usr/bin/env bash
cd "$(dirname "$0")/backend"
PORT="${PORT:-8765}"
echo "============================================"
echo "  InterviewAI starting at http://127.0.0.1:${PORT}"
echo "  demo account: demo / demo1234"
echo "============================================"
python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
