"""Step 5: Material × tool cutting parameters database.

Provides recommended spindle RPM, feed rate, depth-per-pass, and
stepover for common material–tool combinations.

Lookup is by (material, tool_type, diameter_mm).
If the exact diameter isn't in the table, the closest diameter is used
with linear interpolation on SFM (surface feet/min) scaling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .tools import ToolType


@dataclass
class CutParams:
    """Recommended cutting parameters for one material/tool/size combo."""
    spindle_rpm: int
    feed_rate: float        # mm/min
    plunge_rate: float      # mm/min
    depth_per_pass: float   # mm (axial depth of cut, ap)
    stepover_ratio: float   # fraction of diameter (radial ae/D)
    finish_rpm: int = 0
    finish_feed: float = 0.0
    finish_stepover: float = 0.1

    def __post_init__(self) -> None:
        if self.finish_rpm == 0:
            self.finish_rpm = int(self.spindle_rpm * 1.25)
        if self.finish_feed == 0.0:
            self.finish_feed = self.feed_rate * 0.5


# ─── Database ─────────────────────────────────────────────────────
# Key: (material_key, tool_type_str, diameter_mm)
# Values: CutParams

_DB: dict[tuple[str, str, float], CutParams] = {

    # ── Aluminum 6061 ──────────────────────────────────────────────
    ("al6061", "flat_endmill", 6.0):  CutParams(10000, 500, 200, 2.0, 0.45),
    ("al6061", "flat_endmill", 10.0): CutParams(8000,  600, 250, 3.0, 0.50),
    ("al6061", "flat_endmill", 12.0): CutParams(7000,  650, 250, 3.5, 0.50),
    ("al6061", "flat_endmill", 20.0): CutParams(5000,  800, 300, 4.0, 0.50),
    ("al6061", "ball_endmill", 3.0):  CutParams(12000, 300, 150, 1.0, 0.12),
    ("al6061", "ball_endmill", 6.0):  CutParams(10000, 400, 180, 1.5, 0.12),
    ("al6061", "ball_endmill", 10.0): CutParams(8000,  500, 200, 2.0, 0.12),
    ("al6061", "drill",        5.0):  CutParams(4000,  150,  80, 0.0, 0.0),
    ("al6061", "drill",        8.0):  CutParams(3000,  120,  60, 0.0, 0.0),

    # ── Aluminum 7075 (harder, slightly slower) ────────────────────
    ("al7075", "flat_endmill", 6.0):  CutParams(9000,  450, 180, 1.8, 0.45),
    ("al7075", "flat_endmill", 10.0): CutParams(7000,  550, 220, 2.5, 0.50),
    ("al7075", "flat_endmill", 20.0): CutParams(4500,  700, 280, 3.5, 0.50),
    ("al7075", "ball_endmill", 6.0):  CutParams(9000,  350, 160, 1.2, 0.12),

    # ── Steel 1045 (medium carbon) ─────────────────────────────────
    ("steel1045", "flat_endmill", 6.0):  CutParams(4500,  200, 80,  0.8, 0.35),
    ("steel1045", "flat_endmill", 10.0): CutParams(3000,  200, 80,  1.0, 0.35),
    ("steel1045", "flat_endmill", 12.0): CutParams(2800,  220, 90,  1.2, 0.35),
    ("steel1045", "flat_endmill", 20.0): CutParams(2000,  250, 100, 1.5, 0.35),
    ("steel1045", "ball_endmill", 6.0):  CutParams(4000,  150,  70, 0.5, 0.10),
    ("steel1045", "drill",        5.0):  CutParams(2000,   80,  40, 0.0, 0.0),
    ("steel1045", "drill",        8.0):  CutParams(1500,   70,  35, 0.0, 0.0),

    # ── Stainless 316L ─────────────────────────────────────────────
    ("ss316l", "flat_endmill", 6.0):  CutParams(3500,  150, 60,  0.6, 0.30),
    ("ss316l", "flat_endmill", 10.0): CutParams(2500,  150, 60,  0.8, 0.30),
    ("ss316l", "flat_endmill", 20.0): CutParams(1800,  180, 70,  1.0, 0.30),
    ("ss316l", "ball_endmill", 6.0):  CutParams(3000,  100,  50, 0.4, 0.10),
    ("ss316l", "drill",        5.0):  CutParams(1500,   60,  30, 0.0, 0.0),

    # ── Titanium Ti-6Al-4V ─────────────────────────────────────────
    ("ti6al4v", "flat_endmill", 6.0):  CutParams(2000,  100, 40,  0.4, 0.25),
    ("ti6al4v", "flat_endmill", 10.0): CutParams(1500,   90, 40,  0.5, 0.25),
    ("ti6al4v", "flat_endmill", 20.0): CutParams(1000,  100, 40,  0.6, 0.25),
    ("ti6al4v", "ball_endmill", 6.0):  CutParams(1800,   80,  35, 0.3, 0.08),
    ("ti6al4v", "drill",        5.0):  CutParams( 800,   40,  20, 0.0, 0.0),

    # ── Mild Steel (S235 / A36) ────────────────────────────────────
    ("mild_steel", "flat_endmill", 6.0):  CutParams(5000,  250, 100, 1.0, 0.38),
    ("mild_steel", "flat_endmill", 10.0): CutParams(3500,  250, 100, 1.2, 0.38),
    ("mild_steel", "flat_endmill", 20.0): CutParams(2500,  280, 110, 1.5, 0.38),
    ("mild_steel", "ball_endmill", 6.0):  CutParams(4500,  180,  80, 0.6, 0.10),
    ("mild_steel", "drill",        5.0):  CutParams(2200,  100,  50, 0.0, 0.0),
    ("mild_steel", "drill",        8.0):  CutParams(1700,   85,  42, 0.0, 0.0),

    # ── Brass (C260) ──────────────────────────────────────────────
    ("brass", "flat_endmill", 6.0):  CutParams(10000, 600, 250, 2.5, 0.50),
    ("brass", "flat_endmill", 10.0): CutParams(8000,  700, 280, 3.0, 0.50),
    ("brass", "ball_endmill", 6.0):  CutParams(9000,  450, 200, 1.5, 0.12),
    ("brass", "drill",        5.0):  CutParams(5000,  200, 100, 0.0, 0.0),

    # ── Delrin / Acetal (POM) ──────────────────────────────────────
    ("pom", "flat_endmill", 6.0):  CutParams(12000, 800, 300, 3.0, 0.50),
    ("pom", "flat_endmill", 10.0): CutParams(10000, 900, 350, 4.0, 0.50),
    ("pom", "ball_endmill", 6.0):  CutParams(11000, 600, 250, 2.0, 0.12),

    # ── HDPE / Nylon ──────────────────────────────────────────────
    ("plastic", "flat_endmill", 6.0):  CutParams(12000, 1000, 400, 4.0, 0.50),
    ("plastic", "flat_endmill", 10.0): CutParams(10000, 1200, 450, 5.0, 0.50),
}


# ─── Material name aliases ─────────────────────────────────────────
_MATERIAL_ALIASES: dict[str, str] = {
    "aluminum 6061": "al6061",
    "aluminum6061": "al6061",
    "al 6061": "al6061",
    "al6061": "al6061",
    "aluminium 6061": "al6061",
    "aluminum": "al6061",
    "aluminium": "al6061",

    "aluminum 7075": "al7075",
    "al7075": "al7075",

    "steel 1045": "steel1045",
    "steel1045": "steel1045",
    "c45": "steel1045",
    "1045 steel": "steel1045",

    "steel": "mild_steel",
    "mild steel": "mild_steel",
    "a36": "mild_steel",
    "s235": "mild_steel",

    "stainless steel": "ss316l",
    "stainless": "ss316l",
    "ss316l": "ss316l",
    "316l": "ss316l",
    "316 stainless": "ss316l",

    "titanium": "ti6al4v",
    "ti-6al-4v": "ti6al4v",
    "ti6al4v": "ti6al4v",
    "titanium ti-6al-4v": "ti6al4v",
    "titanium ti6al4v": "ti6al4v",
    "grade 5 titanium": "ti6al4v",

    "brass": "brass",
    "c260": "brass",

    "delrin": "pom",
    "acetal": "pom",
    "pom": "pom",

    "hdpe": "plastic",
    "nylon": "plastic",
    "plastic": "plastic",
    "abs": "plastic",
}

_TOOL_TYPE_ALIASES: dict[str, str] = {
    ToolType.FLAT_ENDMILL.value: "flat_endmill",
    ToolType.BALL_ENDMILL.value: "ball_endmill",
    ToolType.DRILL.value: "drill",
    ToolType.FACE_MILL.value: "flat_endmill",   # approximate
    ToolType.BULL_ENDMILL.value: "flat_endmill",
    ToolType.CHAMFER_MILL.value: "flat_endmill",
}


def lookup_params(
    material: str,
    tool_type: str | ToolType,
    diameter: float,
) -> CutParams:
    """Look up recommended cutting parameters.

    Args:
        material: material name string (case-insensitive, aliases accepted)
        tool_type: ToolType enum or string (e.g. "flat_endmill")
        diameter: tool diameter in mm

    Returns:
        CutParams with recommended values.
        Falls back gracefully: unknown material → al6061, unknown tool → flat_endmill.
    """
    # Normalize material
    mat_key = _MATERIAL_ALIASES.get(material.lower().strip(), "al6061")

    # Normalize tool type
    if isinstance(tool_type, ToolType):
        tt = _TOOL_TYPE_ALIASES.get(tool_type.value, "flat_endmill")
    else:
        tt = _TOOL_TYPE_ALIASES.get(str(tool_type), tool_type)

    # Try exact match first
    exact = _DB.get((mat_key, tt, float(diameter)))
    if exact:
        return exact

    # Find entries for same material+tool, different diameters
    candidates = {
        d: params
        for (m, t, d), params in _DB.items()
        if m == mat_key and t == tt
    }

    if not candidates:
        # Fall back to al6061 + flat_endmill
        candidates = {
            d: params
            for (m, t, d), params in _DB.items()
            if m == "al6061" and t == "flat_endmill"
        }

    if not candidates:
        return CutParams(8000, 500, 200, 2.0, 0.45)

    # Find closest diameter and scale RPM by D ratio (SFM-based scaling)
    closest_d = min(candidates, key=lambda d: abs(d - diameter))
    base = candidates[closest_d]

    if abs(closest_d - diameter) < 0.1:
        return base

    # Scale: RPM ∝ 1/D at constant SFM; feed = RPM × chipload × flutes
    ratio = closest_d / diameter if diameter > 0 else 1.0
    scaled_rpm = int(base.spindle_rpm * ratio)
    scaled_feed = base.feed_rate * ratio
    scaled_plunge = base.plunge_rate * ratio
    # Depth scales with diameter
    d_ratio = diameter / closest_d
    scaled_depth = base.depth_per_pass * d_ratio

    return CutParams(
        spindle_rpm=max(500, scaled_rpm),
        feed_rate=max(50.0, round(scaled_feed, 1)),
        plunge_rate=max(30.0, round(scaled_plunge, 1)),
        depth_per_pass=max(0.2, round(scaled_depth, 2)),
        stepover_ratio=base.stepover_ratio,
        finish_rpm=int(max(500, scaled_rpm) * 1.25),
        finish_feed=max(30.0, round(scaled_feed * 0.5, 1)),
        finish_stepover=base.finish_stepover,
    )


def list_materials() -> list[str]:
    """Return list of canonical material keys in the database."""
    return sorted(set(m for m, _, _ in _DB))


def list_material_aliases() -> list[str]:
    """Return all accepted material name strings."""
    return sorted(_MATERIAL_ALIASES.keys())
