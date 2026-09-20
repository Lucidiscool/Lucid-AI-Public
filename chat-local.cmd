@echo off
cd /d "%~dp0"
"%~dp0.venv-directml\Scripts\python.exe" "%~dp0dev_chat.py" %*
pause
