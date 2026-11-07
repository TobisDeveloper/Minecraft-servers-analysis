@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup-Windows.cmd first.
  pause
  exit /b 1
)
if exist config.local.json (
  ".venv\Scripts\python.exe" -m trendfinder serve --config config.local.json --open
) else (
  ".venv\Scripts\python.exe" -m trendfinder serve --open
)
if errorlevel 1 pause
