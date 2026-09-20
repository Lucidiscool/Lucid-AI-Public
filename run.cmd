@echo off
setlocal
set "LUCID_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%LUCID_PYTHON%" goto run
set "LUCID_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%LUCID_PYTHON%" goto run
echo Python was not found. Install Python and dependencies, then run: python lucid.py %*
exit /b 1
:run
"%LUCID_PYTHON%" "%~dp0lucid.py" %*
exit /b %errorlevel%
