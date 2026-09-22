@echo off
cd /d "%~dp0"
set "LUCID_PYTHON=%~dp0.venv-directml\Scripts\python.exe"
if not exist "%LUCID_PYTHON%" set "LUCID_PYTHON=%~dp0..\lucid ai v5 web\.venv-directml\Scripts\python.exe"
if not exist "%LUCID_PYTHON%" (
  echo Python environment missing. Follow ADMIN.md to set up the local host.
  pause
  exit /b 1
)
"%LUCID_PYTHON%" -u host_public.py --admin
pause
