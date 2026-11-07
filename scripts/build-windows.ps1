$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$Python = ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) { throw "Run Setup-Windows.cmd first." }
& $Python -m pip install "pyinstaller>=6.10,<7"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed" }
& $Python -m PyInstaller --noconfirm --clean --onedir --name CZSK-Trendfinder --collect-all trendfinder --collect-all reportlab --collect-all pytrends --collect-all yt_dlp scripts/desktop_entry.py
if ($LASTEXITCODE -ne 0) { throw "Executable build failed" }
Write-Host "Run dist\CZSK-Trendfinder\CZSK-Trendfinder.exe. Distribute the whole folder."
