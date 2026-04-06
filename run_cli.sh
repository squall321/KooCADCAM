#!/bin/bash
# KooCADCAM - CLI 파이프라인 실행 (예제 1: 평판 필렛)
# Usage: ./run_cli.sh [config.yaml]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# venv 활성화
if [ ! -d "venv" ]; then
    echo "[ERROR] venv not found. Run ./setup.sh first."
    exit 1
fi
source venv/bin/activate

# config 파일 결정
CONFIG="${1:-examples/01_plate_fillet/config.yaml}"

if [ ! -f "$CONFIG" ]; then
    echo "[ERROR] Config file not found: $CONFIG"
    exit 1
fi

echo "============================================"
echo "  KooCADCAM CLI - Pipeline Runner"
echo "  Config: $CONFIG"
echo "============================================"

python examples/01_plate_fillet/run.py

echo ""
echo "Output files:"
ls -lh output/step/ output/gcode/ 2>/dev/null
