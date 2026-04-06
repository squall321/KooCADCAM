@echo off
REM KooCADCAM - CLI Pipeline (Windows)
cd /d "%~dp0"

if not exist "venv" (
    echo [ERROR] venv not found. Run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python examples\01_plate_fillet\run.py
pause
