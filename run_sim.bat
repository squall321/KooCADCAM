@echo off
REM KooCADCAM - Material Removal Simulation (Windows)
cd /d "%~dp0"

if not exist "venv" (
    echo [ERROR] venv not found. Run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo ============================================
echo   KooCADCAM - Cutting Simulation
echo ============================================
echo.
echo   3D window will open with real-time cutting.
echo   Close the window when done viewing.
echo.

python -c "from src.sim.playback_sim import play_simulation; play_simulation()"
