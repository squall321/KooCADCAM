#!/bin/bash
# KooCADCAM - GUI 앱 실행
# Usage: ./run_gui.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# venv 활성화
if [ ! -d "venv" ]; then
    echo "[ERROR] venv not found. Run ./setup.sh first."
    exit 1
fi
source venv/bin/activate

# Qt 플랫폼 설정 (headless 서버에서 xcb 오류 방지)
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

echo "============================================"
echo "  KooCADCAM GUI - Starting..."
echo "  Platform: $QT_QPA_PLATFORM"
echo "============================================"

python run_gui.py
