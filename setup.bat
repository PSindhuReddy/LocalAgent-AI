@echo off
cd /d %~dp0
echo [1/3] Installing Python packages...
pip install -r requirements.txt
echo [2/3] Pulling local models (needs Ollama installed)...
ollama pull llama3.2
ollama pull nomic-embed-text
echo [3/3] Checking files...
if not exist credentials.json echo NOTE: credentials.json missing - Gmail/Drive/Calendar/Tasks will not work until you add it.
echo.
echo Setup done. Edit permissions.json after the first run, then use start.bat
pause