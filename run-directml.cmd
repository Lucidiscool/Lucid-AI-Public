@echo off
setlocal
set "LUCID_PYTHON=%~dp0.venv-directml\Scripts\python.exe"
if not exist "%LUCID_PYTHON%" (
    echo DirectML environment missing. See DIRECTML.md for setup instructions.
    exit /b 1
)
"%LUCID_PYTHON%" "%~dp0lucid.py" %*
exit /b %errorlevel%
