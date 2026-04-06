@echo off
REM KooCADCAM - GUI App (Windows)
cd /d "%~dp0"

if not exist "venv" (
    echo [ERROR] venv not found. Run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python run_gui.py
