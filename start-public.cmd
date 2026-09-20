@echo off
cd /d "%~dp0"
set "LUCID_PYTHON=%~dp0.venv-directml\Scripts\python.exe"
if not exist "%LUCID_PYTHON%" set "LUCID_PYTHON=%~dp0..\lucid ai v5 web\.venv-directml\Scripts\python.exe"
"%LUCID_PYTHON%" -u host_public.py --publish
pause
