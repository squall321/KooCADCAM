"""Slot module library: T-slot, dovetail, keyway."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cadquery as cq

from .base import CadModule


@dataclass
class TSlot(CadModule):
    """T-slot profile extruded along X axis."""
    slot_width: float = 10.0
    slot_depth: float = 8.0
    head_width: float = 18.0
    head_depth: float = 4.0
    length: float = 100.0

    def build(self) -> cq.Workplane:
        # Build T-profile as 2D sketch then extrude
        hw = self.head_width / 2
        sw = self.slot_width / 2
        sd = self.slot_depth
        hd = self.head_depth

        pts = [
            (-sw, 0), (sw, 0),
            (sw, sd - hd), (hw, sd - hd),
            (hw, sd), (-hw, sd),
            (-hw, sd - hd), (-sw, sd - hd),
        ]
        wp = (
            cq.Workplane("YZ")
            .polyline(pts)
            .close()
            .extrude(self.length)
        )
        return wp

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "slot_width": {"type": "float", "min": 2, "max": 50, "default": 10.0, "unit": "mm"},
            "slot_depth": {"type": "float", "min": 2, "max": 50, "default": 8.0, "unit": "mm"},
            "head_width": {"type": "float", "min": 5, "max": 100, "default": 18.0, "unit": "mm"},
            "head_depth": {"type": "float", "min": 1, "max": 30, "default": 4.0, "unit": "mm"},
            "length": {"type": "float", "min": 5, "max": 2000, "default": 100.0, "unit": "mm"},
        }


@dataclass
class Dovetail(CadModule):
    """Dovetail slot profile extruded along X axis."""
    width_top: float = 20.0
    width_bottom: float = 14.0
    depth: float = 10.0
    length: float = 100.0

    def build(self) -> cq.Workplane:
        wt = self.width_top / 2
        wb = self.width_bottom / 2
        d = self.depth

        pts = [
            (-wb, 0), (wb, 0),
            (wt, d), (-wt, d),
        ]
        wp = (
            cq.Workplane("YZ")
            .polyline(pts)
            .close()
            .extrude(self.length)
        )
        return wp

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "width_top": {"type": "float", "min": 5, "max": 200, "default": 20.0, "unit": "mm"},
            "width_bottom": {"type": "float", "min": 3, "max": 150, "default": 14.0, "unit": "mm"},
            "depth": {"type": "float", "min": 2, "max": 100, "default": 10.0, "unit": "mm"},
            "length": {"type": "float", "min": 5, "max": 2000, "default": 100.0, "unit": "mm"},
        }


@dataclass
class KeySlot(CadModule):
    """Keyway slot (rectangular with rounded ends)."""
    width: float = 6.0
    depth: float = 3.5
    length: float = 25.0

    def build(self) -> cq.Workplane:
        # Obround cross-section extruded downward
        wp = (
            cq.Workplane("XY")
            .slot2D(self.length, self.width, angle=0)
            .extrude(self.depth)
        )
        return wp

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "width": {"type": "float", "min": 2, "max": 50, "default": 6.0, "unit": "mm"},
            "depth": {"type": "float", "min": 1, "max": 30, "default": 3.5, "unit": "mm"},
            "length": {"type": "float", "min": 5, "max": 500, "default": 25.0, "unit": "mm"},
        }
