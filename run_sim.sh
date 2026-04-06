#!/bin/bash
# KooCADCAM - 소재 제거 시뮬레이션 실행
# Usage: ./run_sim.sh [gcode_file]
#
# 기본: output/gcode/plate_fillet.nc 를 시뮬레이션
# 3D 윈도우에서 공구가 움직이며 소재가 깎여나가는 과정을 실시간으로 봅니다.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "[ERROR] venv not found. Run ./setup.sh first."
    exit 1
fi
source venv/bin/activate

GCODE="${1:-output/gcode/plate_fillet.nc}"

if [ ! -f "$GCODE" ]; then
    echo "[ERROR] G-code file not found: $GCODE"
    echo "Run ./run_cli.sh first to generate G-code."
    exit 1
fi

echo "============================================"
echo "  KooCADCAM - Material Removal Simulation"
echo "  G-code: $GCODE"
echo "============================================"
echo ""
echo "  3D window will open with real-time cutting simulation."
echo "  - Yellow cylinder = tool"
echo "  - Blue solid = remaining stock"
echo "  - Orange trail = cutting path"
echo "  - Upper-left = progress + volume stats"
echo ""
echo "  Close the window when done viewing."
echo ""

python -c "
from src.sim.removal_animator import RemovalAnimator, AnimatorConfig
from src.sim.voxel_engine import ToolShape
from src.sim.time_estimator import TimeEstimator, estimate_distances
from src.sim.gcode_parser import GcodeParser
from pathlib import Path

gcode = Path('${GCODE}').read_text()
parsed = GcodeParser().parse_text(gcode)
print(f'  Loaded {len(parsed)} G-code segments')

# Time estimate
te = TimeEstimator()
est = te.estimate(parsed, num_tool_changes=1)
print(f'  Estimated cycle time: {est.format_time(est.total_time)}')
print()

config = AnimatorConfig(
    voxel_resolution=2.0,
    update_interval=3,
    show_toolpath_trail=True,
)
animator = RemovalAnimator(
    stock_dims=(100, 100, 20),
    tool_diameter=10.0,
    tool_shape=ToolShape.FLAT,
    config=config,
)
stats = animator.run(gcode)
print(f'  Removed: {stats[\"volume_removed\"]:.0f} mm3 ({stats[\"removal_pct\"]:.1f}%)')
print(f'  Remaining: {stats[\"volume_remaining\"]:.0f} mm3')
print('  Done!')
"
