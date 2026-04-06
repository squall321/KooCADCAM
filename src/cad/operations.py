"""Shape operations: fillet, chamfer, boolean operations."""

from __future__ import annotations

import cadquery as cq


def apply_fillet(
    solid: cq.Workplane,
    radius: float,
    edge_selector: str | None = None,
) -> cq.Workplane:
    """Apply fillet to edges of a solid.

    Args:
        solid: Input CadQuery workplane.
        radius: Fillet radius.
        edge_selector: CQ edge selector string (e.g., "|Z", ">Z", "<Z").
                       None = all edges.
    """
    if edge_selector:
        return solid.edges(edge_selector).fillet(radius)
    return solid.edges().fillet(radius)


def apply_chamfer(
    solid: cq.Workplane,
    distance: float,
    edge_selector: str | None = None,
) -> cq.Workplane:
    """Apply chamfer to edges of a solid.

    Args:
        solid: Input CadQuery workplane.
        distance: Chamfer distance.
        edge_selector: CQ edge selector string. None = all edges.
    """
    if edge_selector:
        return solid.edges(edge_selector).chamfer(distance)
    return solid.edges().chamfer(distance)


def boolean_cut(base: cq.Workplane, tool: cq.Workplane) -> cq.Workplane:
    """Boolean subtraction: base - tool."""
    return base.cut(tool)


def boolean_union(a: cq.Workplane, b: cq.Workplane) -> cq.Workplane:
    """Boolean union: a + b."""
    return a.union(b)


def boolean_intersect(a: cq.Workplane, b: cq.Workplane) -> cq.Workplane:
    """Boolean intersection: a ∩ b."""
    return a.intersect(b)
