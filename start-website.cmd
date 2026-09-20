@echo off
"%~dp0.venv-directml\Scripts\python.exe" -u "%~dp0website_server.py" %*
if errorlevel 1 pause
