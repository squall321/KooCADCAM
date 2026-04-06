"""Voxel-based material removal simulation engine.

Uses a 3D boolean voxel grid to represent stock material.
Tool geometry sweeps along the toolpath, subtracting voxels.
Provides real-time removal visualization and gouge detection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from .gcode_parser import PathSegment, PathType


class ToolShape(Enum):
    FLAT = "flat"       # Flat endmill (cylinder)
    BALL = "ball"       # Ball endmill (hemisphere + cylinder)
    BULL = "bull"       # Bull endmill (torus + cylinder)


@dataclass
class VoxelGrid:
    """3D boolean voxel grid representing material presence.

    True = material present, False = material removed.
    """
    data: np.ndarray
    resolution: float
    origin: np.ndarray  # (x_min, y_min, z_min)

    @classmethod
    def from_stock(
        cls,
        x_min: float, x_max: float,
        y_min: float, y_max: float,
        z_min: float, z_max: float,
        resolution: float = 0.5,
    ) -> VoxelGrid:
        """Create a filled voxel grid matching stock dimensions."""
        nx = int(math.ceil((x_max - x_min) / resolution))
        ny = int(math.ceil((y_max - y_min) / resolution))
        nz = int(math.ceil((z_max - z_min) / resolution))
        data = np.ones((nx, ny, nz), dtype=bool)
        origin = np.array([x_min, y_min, z_min])
        return cls(data=data, resolution=resolution, origin=origin)

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.data.shape

    @property
    def total_voxels(self) -> int:
        return int(self.data.size)

    @property
    def filled_voxels(self) -> int:
        return int(np.sum(self.data))

    @property
    def removed_voxels(self) -> int:
        return self.total_voxels - self.filled_voxels

    @property
    def volume_total(self) -> float:
        """Total stock volume in mm^3."""
        return self.total_voxels * self.resolution ** 3

    @property
    def volume_remaining(self) -> float:
        """Remaining material volume in mm^3."""
        return self.filled_voxels * self.resolution ** 3

    @property
    def volume_removed(self) -> float:
        """Removed material volume in mm^3."""
        return self.removed_voxels * self.resolution ** 3

    def world_to_voxel(self, x: float, y: float, z: float) -> tuple[int, int, int]:
        """Convert world coordinates to voxel indices."""
        ix = int((x - self.origin[0]) / self.resolution)
        iy = int((y - self.origin[1]) / self.resolution)
        iz = int((z - self.origin[2]) / self.resolution)
        return (ix, iy, iz)

    def voxel_to_world(self, ix: int, iy: int, iz: int) -> tuple[float, float, float]:
        """Convert voxel indices to world coordinates (center of voxel)."""
        x = self.origin[0] + (ix + 0.5) * self.resolution
        y = self.origin[1] + (iy + 0.5) * self.resolution
        z = self.origin[2] + (iz + 0.5) * self.resolution
        return (x, y, z)


@dataclass
class RemovalResult:
    """Result of a single tool sweep removal."""
    voxels_removed: int = 0
    gouge_detected: bool = False
    gouge_voxels: int = 0


class VoxelEngine:
    """Material removal simulation engine.

    Sweeps a tool shape along toolpath segments,
    removing voxels from the stock grid.

    Usage:
        engine = VoxelEngine(grid, tool_diameter=10.0, tool_shape=ToolShape.FLAT)
        for segment in parsed_segments:
            result = engine.remove_segment(segment)
            print(f"Removed {result.voxels_removed} voxels")
        mesh = engine.to_mesh()  # Export for visualization
    """

    def __init__(
        self,
        grid: VoxelGrid,
        tool_diameter: float,
        tool_shape: ToolShape = ToolShape.FLAT,
        corner_radius: float = 0.0,
        target_grid: VoxelGrid | None = None,
    ) -> None:
        """
        Args:
            grid: Voxel grid representing current stock.
            tool_diameter: Tool cutting diameter.
            tool_shape: Tool geometry type.
            corner_radius: Corner radius for bull endmill.
            target_grid: Optional target shape grid for gouge detection.
        """
        self.grid = grid
        self.tool_radius = tool_diameter / 2
        self.tool_shape = tool_shape
        self.corner_radius = corner_radius
        self.target_grid = target_grid
        self._step_count = 0

    def remove_segment(self, segment: PathSegment, steps_per_mm: float = 2.0) -> RemovalResult:
        """Remove material along a path segment.

        Args:
            segment: A parsed G-code segment.
            steps_per_mm: Interpolation density along the path.
        """
        if segment.path_type == PathType.RAPID:
            return RemovalResult()  # No cutting on rapids

        result = RemovalResult()

        dx = segment.x_end - segment.x_start
        dy = segment.y_end - segment.y_start
        dz = segment.z_end - segment.z_start
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        if dist < 1e-9:
            return result

        n_steps = max(1, int(dist * steps_per_mm))

        for i in range(n_steps + 1):
            t = i / n_steps
            cx = segment.x_start + dx * t
            cy = segment.y_start + dy * t
            cz = segment.z_start + dz * t

            removed = self._remove_at_position(cx, cy, cz)
            result.voxels_removed += removed

            # Gouge detection against target grid
            if self.target_grid is not None:
                gouge = self._check_gouge(cx, cy, cz)
                if gouge > 0:
                    result.gouge_detected = True
                    result.gouge_voxels += gouge

        self._step_count += 1
        return result

    def _remove_at_position(self, cx: float, cy: float, cz: float) -> int:
        """Remove voxels within tool envelope at given position.

        For a flat endmill at position (cx, cy, cz):
        - cz is the tool TIP (bottom of flutes)
        - The tool cuts everything ABOVE cz within its XY radius
        - Material below cz is NOT cut (tool can't reach below its tip)

        So we remove all voxels where:
        - XY distance from (cx, cy) <= tool_radius
        - Z >= cz (everything from tool tip upward is cleared)
        """
        r = self.tool_radius
        res = self.grid.resolution
        grid = self.grid

        # XY bounding box of tool
        ix_min = max(0, int((cx - r - grid.origin[0]) / res))
        ix_max = min(grid.shape[0] - 1, int((cx + r - grid.origin[0]) / res))
        iy_min = max(0, int((cy - r - grid.origin[1]) / res))
        iy_max = min(grid.shape[1] - 1, int((cy + r - grid.origin[1]) / res))

        # Z range: from tool tip (cz) up to top of stock
        iz_min = max(0, int((cz - grid.origin[2]) / res))
        iz_max = grid.shape[2] - 1  # up to the top

        if ix_min > ix_max or iy_min > iy_max or iz_min > iz_max:
            return 0

        # Voxel center coordinates
        ix_range = np.arange(ix_min, ix_max + 1)
        iy_range = np.arange(iy_min, iy_max + 1)
        iz_range = np.arange(iz_min, iz_max + 1)

        xx = grid.origin[0] + (ix_range + 0.5) * res
        yy = grid.origin[1] + (iy_range + 0.5) * res
        zz = grid.origin[2] + (iz_range + 0.5) * res

        XX, YY, ZZ = np.meshgrid(xx, yy, zz, indexing="ij")

        # XY distance from tool axis
        dist_xy = np.sqrt((XX - cx) ** 2 + (YY - cy) ** 2)

        if self.tool_shape == ToolShape.FLAT:
            # Flat endmill: cylinder from tool tip upward
            # Everything within radius and above cz is removed
            mask = (dist_xy <= r) & (ZZ >= cz)

        elif self.tool_shape == ToolShape.BALL:
            # Ball endmill: hemisphere at tip + cylinder above
            # Hemisphere center is at (cx, cy, cz + r)
            dist_sphere = np.sqrt((XX - cx)**2 + (YY - cy)**2 + (ZZ - (cz + r))**2)
            hemisphere = (dist_sphere <= r) & (ZZ <= cz + r)
            cylinder_above = (dist_xy <= r) & (ZZ > cz + r)
            mask = hemisphere | cylinder_above

        elif self.tool_shape == ToolShape.BULL:
            # Bull endmill: simplified as flat
            mask = (dist_xy <= r) & (ZZ >= cz)

        else:
            mask = (dist_xy <= r) & (ZZ >= cz)

        # Apply removal
        sub = grid.data[ix_min:ix_max+1, iy_min:iy_max+1, iz_min:iz_max+1]
        removable = sub & mask
        count = int(np.sum(removable))
        sub[mask] = False

        return count

    def _check_gouge(self, cx: float, cy: float, cz: float) -> int:
        """Check if tool cuts into target geometry (gouge)."""
        if self.target_grid is None:
            return 0

        r = self.tool_radius
        res = self.grid.resolution
        tg = self.target_grid

        ix_min = max(0, int((cx - r - tg.origin[0]) / res))
        ix_max = min(tg.shape[0] - 1, int((cx + r - tg.origin[0]) / res))
        iy_min = max(0, int((cy - r - tg.origin[1]) / res))
        iy_max = min(tg.shape[1] - 1, int((cy + r - tg.origin[1]) / res))
        iz_min = max(0, int((cz - tg.origin[2]) / res))
        iz_max = min(tg.shape[2] - 1, int((cz + r - tg.origin[2]) / res))

        if ix_min > ix_max or iy_min > iy_max or iz_min > iz_max:
            return 0

        # Check if any target voxels would be removed
        sub = tg.data[ix_min:ix_max + 1, iy_min:iy_max + 1, iz_min:iz_max + 1]
        return int(np.sum(sub))

    def simulate_all(self, segments: list[PathSegment]) -> dict[str, Any]:
        """Run full simulation on all segments.

        Returns statistics dict.
        """
        total_removed = 0
        total_gouge = 0

        for seg in segments:
            result = self.remove_segment(seg)
            total_removed += result.voxels_removed
            total_gouge += result.gouge_voxels

        return {
            "total_voxels": self.grid.total_voxels,
            "removed_voxels": total_removed,
            "remaining_voxels": self.grid.filled_voxels,
            "volume_total": self.grid.volume_total,
            "volume_removed": self.grid.volume_removed,
            "volume_remaining": self.grid.volume_remaining,
            "gouge_voxels": total_gouge,
            "removal_pct": 100.0 * total_removed / max(self.grid.total_voxels, 1),
        }

    def to_mesh(self):
        """Convert current voxel state to a PyVista mesh for visualization.

        Returns a pyvista.UniformGrid with scalar field.
        """
        import pyvista as pv

        grid = pv.ImageData(
            dimensions=np.array(self.grid.shape) + 1,
            spacing=(self.grid.resolution,) * 3,
            origin=self.grid.origin,
        )
        # Flatten in Fortran order to match VTK
        grid.cell_data["material"] = self.grid.data.ravel(order="F").astype(float)

        # Threshold to extract only filled voxels
        mesh = grid.threshold(0.5, scalars="material")
        return mesh
