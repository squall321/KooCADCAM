@echo off
REM KooCADCAM - Windows Environment Setup
REM Usage: setup.bat

echo ============================================
echo   KooCADCAM - Environment Setup (Windows)
echo ============================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.12+ from python.org
    pause
    exit /b 1
)

python --version

if not exist "venv" (
    echo [..] Creating virtual environment...
    python -m venv venv
    echo [OK] venv created
) else (
    echo [OK] venv already exists
)

call venv\Scripts\activate.bat

echo [..] Installing dependencies...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo [OK] Dependencies installed

if not exist "output\step" mkdir output\step
if not exist "output\gcode" mkdir output\gcode
if not exist "output\images" mkdir output\images
echo [OK] Output directories ready

echo.
echo ============================================
echo   Setup complete!
echo.
echo   Run CLI:  run_cli.bat
echo   Run GUI:  run_gui.bat
echo   Run Sim:  run_sim.bat
echo ============================================
pause
