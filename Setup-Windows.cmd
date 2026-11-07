@echo off
setlocal
cd /d "%~dp0"
echo CZ/SK Minecraft Trendfinder - setup
py -3 -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required'"
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
if not exist config.local.json ".venv\Scripts\python.exe" -m trendfinder init-config
if errorlevel 1 goto failed
echo.
echo Ready. Double-click Start-Windows.cmd to open your local dashboard.
pause
exit /b 0
:failed
echo.
echo Setup failed. Install Python 3.11+ from python.org with the Windows launcher.
echo Read the error above for network or package installation problems.
pause
exit /b 1
