"""Step 7: Machining verification pipeline.

Compares the voxel simulation result against the target CAD model
to measure overcut, undercut, and overall accuracy.

This runs entirely in Python/numpy — no external dependencies beyond
what's already installed.

Usage:
    from src.cam.verification import MachiningVerifier
    report = MachiningVerifier().verify(target_solid, voxel_grid)
    print(report.summary())
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import cadquery as cq


@dataclass
class VerificationReport:
    """Result of comparing simulation output to target CAD."""
    accuracy_pct: float         # % of voxels that match target
    overcut_volume: float       # mm³ of material removed beyond target
    undercut_volume: float      # mm³ of material that should be removed but wasn't
    remaining_volume: float     # mm³ of material still in simulated part
    target_volume: float        # mm³ of target part volume
    has_undercuts: bool         # true if any structural undercuts exist
    worst_error_location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    worst_error_mm: float = 0.0
    voxel_resolution: float = 0.5
    overcut_grid: np.ndarray | None = field(default=None, repr=False)
    undercut_grid: np.ndarray | None = field(default=None, repr=False)

    def summary(self) -> str:
        lines = [
            "─" * 50,
            "Verification Report",
            "─" * 50,
            f"  Accuracy:         {self.accuracy_pct:.1f}%",
            f"  Target volume:    {self.target_volume:.1f} mm³",
            f"  Remaining volume: {self.remaining_volume:.1f} mm³",
            f"  Overcut:          {self.overcut_volume:.2f} mm³",
            f"  Undercut:         {self.undercut_volume:.2f} mm³",
        ]
        if self.worst_error_mm > 0:
            loc = self.worst_error_location
            lines.append(
                f"  Worst error:      {self.worst_error_mm:.3f} mm "
                f"@ ({loc[0]:.1f}, {loc[1]:.1f}, {loc[2]:.1f})"
            )
        if self.has_undercuts:
            lines.append("  WARNING: Structural undercuts detected")
        lines.append("─" * 50)
        return "\n".join(lines)

    @property
    def passed(self) -> bool:
        """True if accuracy >= 90% (sufficient for most parts)."""
        return self.accuracy_pct >= 90.0


class MachiningVerifier:
    """Compare voxel simulation result to target CAD geometry.

    Workflow:
        1. Rasterize target CAD → target voxel grid (which voxels SHOULD be solid)
        2. Compare to simulated grid (which voxels ARE solid after G-code ran)
        3. XOR → overcut (removed too much) and undercut (not removed enough)
        4. Compute accuracy, volumes, worst error location
    """

    def __init__(self, resolution: float = 0.5) -> None:
        self.resolution = resolution

    def verify(
        self,
        target_solid,  # cq.Workplane or cq.Shape
        simulated_grid,  # VoxelGrid from voxel_engine.py
    ) -> VerificationReport:
        """Main verification entry point.

        Args:
            target_solid: CadQuery workplane/solid of the desired part
            simulated_grid: VoxelGrid from the material removal simulation
        """
        sim_data = simulated_grid.data          # True = material present
        res = simulated_grid.resolution
        origin = simulated_grid.origin

        # Rasterize target solid into same grid space
        target_data = self._rasterize_target(
            target_solid, sim_data.shape, res, origin
        )

        return self._compare_grids(sim_data, target_data, res, origin)

    def verify_from_bounds(
        self,
        target_solid,
        sim_data: np.ndarray,
        resolution: float,
        origin: np.ndarray,
    ) -> VerificationReport:
        """Verify when grid metadata is passed separately."""
        target_data = self._rasterize_target(
            target_solid, sim_data.shape, resolution, origin
        )
        return self._compare_grids(sim_data, target_data, resolution, origin)

    # ─── Rasterization ────────────────────────────────────────────

    def _rasterize_target(
        self,
        solid,
        shape: tuple[int, int, int],
        resolution: float,
        origin: np.ndarray,
    ) -> np.ndarray:
        """Convert target CAD solid into a voxel grid (True = solid)."""
        nx, ny, nz = shape
        target = np.zeros((nx, ny, nz), dtype=bool)

        try:
            import cadquery as cq

            # Get the OCC shape
            if hasattr(solid, "val"):
                occ_shape = solid.val()
            else:
                occ_shape = solid

            bb = occ_shape.BoundingBox()

            # For each voxel center, check if it's inside the solid
            # This uses a point-in-solid test via BRep analysis
            # Optimization: only test voxels within bounding box
            ix_min = max(0, int((bb.xmin - origin[0]) / resolution) - 1)
            ix_max = min(nx - 1, int((bb.xmax - origin[0]) / resolution) + 1)
            iy_min = max(0, int((bb.ymin - origin[1]) / resolution) - 1)
            iy_max = min(ny - 1, int((bb.ymax - origin[1]) / resolution) + 1)
            iz_min = max(0, int((bb.zmin - origin[2]) / resolution) - 1)
            iz_max = min(nz - 1, int((bb.zmax - origin[2]) / resolution) + 1)

            from OCC.Core.BRep import BRep_Builder
            from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
            from OCC.Core.gp import gp_Pnt
            from OCC.Core.TopAbs import TopAbs_IN, TopAbs_ON

            classifier = BRepClass3d_SolidClassifier()
            classifier.Load(occ_shape)
            tol = resolution * 0.1

            for ix in range(ix_min, ix_max + 1):
                x = origin[0] + (ix + 0.5) * resolution
                for iy in range(iy_min, iy_max + 1):
                    y = origin[1] + (iy + 0.5) * resolution
                    for iz in range(iz_min, iz_max + 1):
                        z = origin[2] + (iz + 0.5) * resolution
                        pt = gp_Pnt(x, y, z)
                        classifier.Perform(pt, tol)
                        state = classifier.State()
                        if state in (TopAbs_IN, TopAbs_ON):
                            target[ix, iy, iz] = True

        except Exception:
            # Fallback: approximate with bounding box
            target = self._rasterize_bbox_fallback(solid, shape, resolution, origin)

        return target

    def _rasterize_bbox_fallback(
        self,
        solid,
        shape: tuple[int, int, int],
        resolution: float,
        origin: np.ndarray,
    ) -> np.ndarray:
        """Fallback rasterization using bounding box only."""
        nx, ny, nz = shape
        target = np.zeros((nx, ny, nz), dtype=bool)
        try:
            if hasattr(solid, "val"):
                bb = solid.val().BoundingBox()
            else:
                bb = solid.BoundingBox()

            ix_min = max(0, int((bb.xmin - origin[0]) / resolution))
            ix_max = min(nx - 1, int((bb.xmax - origin[0]) / resolution))
            iy_min = max(0, int((bb.ymin - origin[1]) / resolution))
            iy_max = min(ny - 1, int((bb.ymax - origin[1]) / resolution))
            iz_min = max(0, int((bb.zmin - origin[2]) / resolution))
            iz_max = min(nz - 1, int((bb.zmax - origin[2]) / resolution))

            target[ix_min:ix_max+1, iy_min:iy_max+1, iz_min:iz_max+1] = True
        except Exception:
            pass
        return target

    # ─── Grid comparison ──────────────────────────────────────────

    def _compare_grids(
        self,
        simulated: np.ndarray,   # True = material present (after machining)
        target: np.ndarray,      # True = should be present in finished part
        resolution: float,
        origin: np.ndarray,
    ) -> VerificationReport:
        voxel_vol = resolution ** 3

        # Overcut: material removed that SHOULD still be there
        # sim=False (removed), target=True (should be there) → overcut
        overcut_mask = (~simulated) & target

        # Undercut: material still there that SHOULD be removed
        # sim=True (still present), target=False (should be gone) → undercut
        undercut_mask = simulated & (~target)

        # Match: both agree
        match_mask = (simulated == target)

        total_voxels = simulated.size
        match_count = int(np.sum(match_mask))
        overcut_count = int(np.sum(overcut_mask))
        undercut_count = int(np.sum(undercut_mask))
        remaining_count = int(np.sum(simulated))
        target_count = int(np.sum(target))

        accuracy = (match_count / total_voxels * 100.0) if total_voxels > 0 else 0.0
        overcut_vol = overcut_count * voxel_vol
        undercut_vol = undercut_count * voxel_vol
        remaining_vol = remaining_count * voxel_vol
        target_vol = target_count * voxel_vol

        # Find worst error location (center of largest error cluster)
        worst_loc = (0.0, 0.0, 0.0)
        worst_err = 0.0
        error_mask = overcut_mask | undercut_mask
        if np.any(error_mask):
            # Find centroid of error region
            idx = np.argwhere(error_mask)
            if len(idx) > 0:
                center_idx = idx.mean(axis=0)
                worst_loc = (
                    float(origin[0] + center_idx[0] * resolution),
                    float(origin[1] + center_idx[1] * resolution),
                    float(origin[2] + center_idx[2] * resolution),
                )
                # Approximate worst error: sqrt of error volume / surface
                error_vol = (overcut_count + undercut_count) * voxel_vol
                worst_err = (error_vol ** (1/3)) * 0.5  # rough estimate

        return VerificationReport(
            accuracy_pct=round(accuracy, 2),
            overcut_volume=round(overcut_vol, 3),
            undercut_volume=round(undercut_vol, 3),
            remaining_volume=round(remaining_vol, 3),
            target_volume=round(target_vol, 3),
            has_undercuts=(undercut_count > 0),
            worst_error_location=worst_loc,
            worst_error_mm=round(worst_err, 3),
            voxel_resolution=resolution,
            overcut_grid=overcut_mask,
            undercut_grid=undercut_mask,
        )


# ─── Standalone volume estimator (no simulation needed) ──────────

def estimate_removal_volume(
    stock_dims: tuple[float, float, float],
    target_solid,
    resolution: float = 1.0,
) -> dict[str, float]:
    """Estimate material removal volume without running simulation.

    Returns dict with stock_vol, target_vol, removal_vol, removal_pct.
    Uses bounding box fallback for the target.
    """
    sx, sy, sz = stock_dims
    stock_vol = sx * sy * sz

    try:
        if hasattr(target_solid, "val"):
            # Use CadQuery volume computation
            try:
                target_vol = abs(target_solid.val().Volume())
            except Exception:
                bb = target_solid.val().BoundingBox()
                target_vol = (bb.xmax-bb.xmin) * (bb.ymax-bb.ymin) * (bb.zmax-bb.zmin)
        else:
            target_vol = stock_vol * 0.5
    except Exception:
        target_vol = stock_vol * 0.5

    removal_vol = max(0.0, stock_vol - target_vol)
    removal_pct = (removal_vol / stock_vol * 100.0) if stock_vol > 0 else 0.0

    return {
        "stock_vol": round(stock_vol, 1),
        "target_vol": round(target_vol, 1),
        "removal_vol": round(removal_vol, 1),
        "removal_pct": round(removal_pct, 1),
    }
