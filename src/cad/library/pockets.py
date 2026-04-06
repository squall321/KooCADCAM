"""Pocket module library: rectangular, circular, obround."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cadquery as cq

from .base import CadModule


@dataclass
class RectPocket(CadModule):
    """Rectangular pocket with optional corner radius."""
    lx: float = 30.0
    ly: float = 20.0
    depth: float = 5.0
    corner_radius: float = 3.0

    def build(self) -> cq.Workplane:
        wp = cq.Workplane("XY")
        if self.corner_radius > 0:
            wp = wp.rect(self.lx, self.ly).extrude(self.depth)
            wp = wp.edges("|Z").fillet(self.corner_radius)
        else:
            wp = wp.rect(self.lx, self.ly).extrude(self.depth)
        return wp

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "lx": {"type": "float", "min": 1, "max": 500, "default": 30.0, "unit": "mm"},
            "ly": {"type": "float", "min": 1, "max": 500, "default": 20.0, "unit": "mm"},
            "depth": {"type": "float", "min": 0.1, "max": 200, "default": 5.0, "unit": "mm"},
            "corner_radius": {"type": "float", "min": 0, "max": 50, "default": 3.0, "unit": "mm"},
        }


@dataclass
class CircularPocket(CadModule):
    """Circular pocket."""
    diameter: float = 20.0
    depth: float = 5.0

    def build(self) -> cq.Workplane:
        return cq.Workplane("XY").circle(self.diameter / 2).extrude(self.depth)

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "diameter": {"type": "float", "min": 1, "max": 500, "default": 20.0, "unit": "mm"},
            "depth": {"type": "float", "min": 0.1, "max": 200, "default": 5.0, "unit": "mm"},
        }


@dataclass
class ObroundPocket(CadModule):
    """Obround (stadium-shaped) pocket."""
    lx: float = 40.0
    ly: float = 15.0
    depth: float = 5.0

    def build(self) -> cq.Workplane:
        r = min(self.lx, self.ly) / 2
        wp = cq.Workplane("XY")
        # Stadium shape: rect with fully rounded ends on short axis
        wp = wp.slot2D(self.lx, self.ly, angle=0).extrude(self.depth)
        return wp

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "lx": {"type": "float", "min": 5, "max": 500, "default": 40.0, "unit": "mm"},
            "ly": {"type": "float", "min": 3, "max": 200, "default": 15.0, "unit": "mm"},
            "depth": {"type": "float", "min": 0.1, "max": 200, "default": 5.0, "unit": "mm"},
        }
