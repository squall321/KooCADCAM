"""Parametric primitive shape generators using CadQuery."""

from __future__ import annotations

import cadquery as cq


def create_box(lx: float, ly: float, lz: float, center: bool = True) -> cq.Workplane:
    """Create a rectangular box (cuboid).

    Args:
        lx, ly, lz: Dimensions in X, Y, Z.
        center: If True, center on origin. If False, corner at origin.
    """
    wp = cq.Workplane("XY").box(lx, ly, lz, centered=(center, center, False))
    return wp


def create_cylinder(radius: float, height: float, center: bool = True) -> cq.Workplane:
    """Create a cylinder along Z axis.

    Args:
        radius: Cylinder radius.
        height: Cylinder height.
        center: If True, center XY on origin.
    """
    wp = cq.Workplane("XY").cylinder(height, radius, centered=(center, center, False))
    return wp


def create_plate(lx: float, ly: float, thickness: float) -> cq.Workplane:
    """Create a flat plate (thin box) sitting on Z=0."""
    return create_box(lx, ly, thickness, center=True)


def create_cone(
    r_bottom: float, r_top: float, height: float, center: bool = True
) -> cq.Workplane:
    """Create a cone or truncated cone along Z axis.

    Args:
        r_bottom: Bottom radius.
        r_top: Top radius (0 for a full cone).
        height: Height.
    """
    wp = cq.Workplane("XY")
    cone = (
        wp.circle(r_bottom)
        .workplane(offset=height)
        .circle(r_top if r_top > 0 else 0.001)
        .loft()
    )
    if not center:
        return cone
    return cone
