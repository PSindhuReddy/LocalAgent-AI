@echo off
cd /d %~dp0
curl -s http://localhost:11434 >nul 2>&1 || (start "" /min ollama serve & timeout /t 4 >nul)
python server.py