@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
echo ======================================================
echo Video Converter Installer for Windows
echo ======================================================

where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Warning: FFmpeg is not found in your PATH.
    echo     You can install it easily with winget:
    echo     winget install Gyan.FFmpeg
    echo.
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo         Please download and install Python from https://www.python.org/
    pause
    exit /b 1
)

echo [*] Setting up Python virtual environment...
if not exist "%SCRIPT_DIR%venv" (
    python -m venv "%SCRIPT_DIR%venv"
)

echo [*] Installing dependencies (Flask, Rich)...
"%SCRIPT_DIR%venv\Scripts\pip.exe" install -q -r "%SCRIPT_DIR%requirements.txt"

echo [*] Creating Desktop Shortcut via PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1"

echo.
echo ======================================================
echo [OK] Installation completed successfully!
echo ======================================================
echo You can run Video Converter via:
echo   1. Desktop Shortcut: 'Video Converter'
echo   2. Command Line: vid.bat input.webm
echo   3. Web GUI: vid-gui.bat
echo ======================================================
pause
