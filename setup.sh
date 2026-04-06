#!/bin/bash
# KooCADCAM - 초기 환경 설정
# Usage: ./setup.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  KooCADCAM - Environment Setup"
echo "============================================"

# Python 버전 확인
PYTHON=""
for py in python3.12 python3; do
    if command -v "$py" &>/dev/null; then
        ver=$("$py" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 12 ]; then
            PYTHON="$py"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.12+ required but not found."
    exit 1
fi
echo "[OK] Python: $($PYTHON --version)"

# venv 생성
if [ ! -d "venv" ]; then
    echo "[..] Creating virtual environment..."
    $PYTHON -m venv venv
    echo "[OK] venv created"
else
    echo "[OK] venv already exists"
fi

source venv/bin/activate

# 의존성 설치
echo "[..] Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "[OK] Dependencies installed"

# 출력 디렉토리 생성
mkdir -p output/{step,gcode,images}
echo "[OK] Output directories ready"

echo ""
echo "============================================"
echo "  Setup complete!"
echo ""
echo "  Run CLI:  ./run_cli.sh"
echo "  Run GUI:  ./run_gui.sh"
echo "============================================"
