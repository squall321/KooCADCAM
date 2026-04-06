"""Modular assembly system for combining parametric modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import cadquery as cq

if TYPE_CHECKING:
    from .library.base import CadModule


@dataclass
class Placement:
    """Describes position and rotation of a module."""
    module: CadModule
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)  # degrees around X, Y, Z


class ModularAssembly:
    """Combines multiple CadModule instances into a single solid.

    Usage:
        assy = ModularAssembly()
        assy.add_module(pocket_module, position=(10, 20, 0))
        assy.add_module(hole_module, position=(50, 50, 0))
        # Apply all modules as cuts to a base solid
        result = assy.apply_to(base_solid)
    """

    def __init__(self) -> None:
        self._placements: list[Placement] = []

    def add_module(
        self,
        module: CadModule,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> ModularAssembly:
        self._placements.append(Placement(module, position, rotation))
        return self

    def linear_pattern(
        self,
        module: CadModule,
        direction: tuple[float, float, float],
        count: int,
        spacing: float,
        start: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> ModularAssembly:
        """Place modules in a linear pattern."""
        dx, dy, dz = direction
        mag = (dx**2 + dy**2 + dz**2) ** 0.5
        if mag == 0:
            raise ValueError("Direction vector cannot be zero")
        ux, uy, uz = dx / mag, dy / mag, dz / mag
        for i in range(count):
            pos = (
                start[0] + ux * spacing * i,
                start[1] + uy * spacing * i,
                start[2] + uz * spacing * i,
            )
            self.add_module(module, position=pos)
        return self

    def grid_pattern(
        self,
        module: CadModule,
        nx: int,
        ny: int,
        sx: float,
        sy: float,
        origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> ModularAssembly:
        """Place modules in a 2D grid pattern."""
        for ix in range(nx):
            for iy in range(ny):
                pos = (
                    origin[0] + ix * sx,
                    origin[1] + iy * sy,
                    origin[2],
                )
                self.add_module(module, position=pos)
        return self

    def apply_to(self, base: cq.Workplane) -> cq.Workplane:
        """Apply all placed modules as boolean cuts to a base solid.

        Each module's build() produces a tool shape that is subtracted
        from the base at the specified position and rotation.
        """
        result = base
        for pl in self._placements:
            tool = pl.module.build()
            # Translate tool to placement position
            x, y, z = pl.position
            rx, ry, rz = pl.rotation
            if rx != 0 or ry != 0 or rz != 0:
                tool = tool.rotate((0, 0, 0), (1, 0, 0), rx)
                tool = tool.rotate((0, 0, 0), (0, 1, 0), ry)
                tool = tool.rotate((0, 0, 0), (0, 0, 1), rz)
            tool = tool.translate((x, y, z))
            result = result.cut(tool)
        return result

    @property
    def placements(self) -> list[Placement]:
        return list(self._placements)
