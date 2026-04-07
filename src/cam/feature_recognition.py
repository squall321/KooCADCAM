"""Step 1: BREP-based feature recognition for AutoCAM.

Analyzes CadQuery geometry at the face/edge level instead of
just bounding boxes, enabling accurate pocket, hole, undercut,
and fillet detection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import cadquery as cq


@dataclass
class RecognizedFace:
    """A single analyzed BREP face."""
    geom_type: str          # PLANE, CYLINDER, SPHERE, TORUS, BSPLINE, etc.
    normal: tuple[float, float, float] | None  # face normal (for planes)
    center: tuple[float, float, float]
    area: float
    bounds: dict[str, float]   # x_min/max, y_min/max, z_min/max


@dataclass
class PocketFeature:
    """A recognized pocket (concave region machined from top)."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_top: float        # entry Z
    z_bottom: float     # floor Z
    depth: float
    shape: str          # "rectangular", "circular", "freeform"
    floor_radius: float = 0.0   # corner radius if rectangular
    islands: list[dict] = field(default_factory=list)  # inner protrusions


@dataclass
class HoleFeature:
    """A recognized cylindrical hole."""
    x: float
    y: float
    diameter: float
    z_top: float
    z_bottom: float
    depth: float
    is_through: bool = True


@dataclass
class FilletFeature:
    """A recognized fillet or chamfer edge."""
    radius: float
    edge_count: int
    is_chamfer: bool = False


@dataclass
class FreeformSurface:
    """A non-planar, non-cylindrical surface requiring 3D toolpath."""
    geom_type: str
    z_min: float
    z_max: float
    z_span: float


@dataclass
class BrepAnalysisResult:
    """Complete BREP analysis of a target solid."""
    bounding_box: dict[str, float]
    faces: list[RecognizedFace] = field(default_factory=list)
    pockets: list[PocketFeature] = field(default_factory=list)
    holes: list[HoleFeature] = field(default_factory=list)
    fillets: list[FilletFeature] = field(default_factory=list)
    freeform_surfaces: list[FreeformSurface] = field(default_factory=list)
    has_undercuts: bool = False
    undercut_warning: str = ""
    accessible_from_top: bool = True

    @property
    def has_pockets(self) -> bool:
        return bool(self.pockets)

    @property
    def has_holes(self) -> bool:
        return bool(self.holes)

    @property
    def has_fillets(self) -> bool:
        return bool(self.fillets)

    @property
    def has_freeform(self) -> bool:
        return bool(self.freeform_surfaces)

    def summary(self) -> str:
        lines = ["BREP Analysis:"]
        lines.append(f"  Faces analyzed: {len(self.faces)}")
        lines.append(f"  Pockets: {len(self.pockets)}")
        lines.append(f"  Holes: {len(self.holes)}")
        lines.append(f"  Fillets/chamfers: {len(self.fillets)}")
        lines.append(f"  Freeform surfaces: {len(self.freeform_surfaces)}")
        if self.has_undercuts:
            lines.append(f"  WARNING: {self.undercut_warning}")
        return "\n".join(lines)


class BrepAnalyzer:
    """Analyzes CadQuery solids using BREP face/edge geometry.

    Replaces bounding-box-only feature recognition with actual
    geometric analysis of the solid's topology.
    """

    # Tolerance for classifying face normals as vertical/horizontal
    NORMAL_TOL = 0.1

    def __init__(self, solid: cq.Workplane) -> None:
        self._solid = solid
        self._val = solid.val()
        bb = self._val.BoundingBox()
        self._bb = {
            "x_min": bb.xmin, "x_max": bb.xmax,
            "y_min": bb.ymin, "y_max": bb.ymax,
            "z_min": bb.zmin, "z_max": bb.zmax,
            "lx": bb.xmax - bb.xmin,
            "ly": bb.ymax - bb.ymin,
            "lz": bb.zmax - bb.zmin,
        }

    def analyze(self) -> BrepAnalysisResult:
        result = BrepAnalysisResult(bounding_box=self._bb)

        try:
            result.faces = self._analyze_faces()
        except Exception:
            pass

        try:
            result.holes = self._detect_holes(result.faces)
        except Exception:
            pass

        try:
            result.pockets = self._detect_pockets(result.faces)
        except Exception:
            pass

        try:
            result.fillets = self._detect_fillets()
        except Exception:
            pass

        try:
            result.freeform_surfaces = self._detect_freeform(result.faces)
        except Exception:
            pass

        try:
            self._check_undercuts(result)
        except Exception:
            pass

        return result

    # ─── Face analysis ────────────────────────────────────────────

    def _analyze_faces(self) -> list[RecognizedFace]:
        faces = []
        for face in self._val.Faces():
            try:
                geom = face.geomType()
                center = face.Center()
                bb = face.BoundingBox()
                area = face.Area()

                normal = None
                if geom == "PLANE":
                    try:
                        n = face.normalAt(center)
                        normal = (round(n.x, 4), round(n.y, 4), round(n.z, 4))
                    except Exception:
                        pass

                faces.append(RecognizedFace(
                    geom_type=geom,
                    normal=normal,
                    center=(center.x, center.y, center.z),
                    area=area,
                    bounds={
                        "x_min": bb.xmin, "x_max": bb.xmax,
                        "y_min": bb.ymin, "y_max": bb.ymax,
                        "z_min": bb.zmin, "z_max": bb.zmax,
                    }
                ))
            except Exception:
                continue
        return faces

    # ─── Hole detection ────────────────────────────────────────────

    def _detect_holes(self, faces: list[RecognizedFace]) -> list[HoleFeature]:
        holes = []
        for face in faces:
            if face.geom_type != "CYLINDER":
                continue
            try:
                b = face.bounds
                dx = b["x_max"] - b["x_min"]
                dy = b["y_max"] - b["y_min"]
                radius = min(dx, dy) / 2.0
                if radius < 0.5:
                    continue

                cx = (b["x_min"] + b["x_max"]) / 2
                cy = (b["y_min"] + b["y_max"]) / 2
                z_top = b["z_max"]
                z_bottom = b["z_min"]
                depth = z_top - z_bottom

                # Must have substantial depth compared to radius
                # (fillet arcs have very small depth relative to radius)
                if depth < radius * 0.5 or depth < 2.0:
                    continue  # likely a fillet arc, not a drillable hole

                # Cylinder must span a significant portion of the part Z
                # (holes span most of the part height)
                part_z_span = self._bb["lz"]
                if depth < part_z_span * 0.3 and depth < 5.0:
                    continue  # too shallow to be a drillable hole

                duplicate = any(
                    abs(h.x - cx) < 1.0 and abs(h.y - cy) < 1.0
                    for h in holes
                )
                if not duplicate:
                    holes.append(HoleFeature(
                        x=cx, y=cy,
                        diameter=radius * 2,
                        z_top=z_top,
                        z_bottom=z_bottom,
                        depth=depth,
                        is_through=(abs(z_bottom - self._bb["z_min"]) < 1.0),
                    ))
            except Exception:
                continue
        return holes

    # ─── Pocket detection ──────────────────────────────────────────

    def _detect_pockets(self, faces: list[RecognizedFace]) -> list[PocketFeature]:
        """Detect pockets: horizontal floors below top surface."""
        pockets = []
        top_z = self._bb["z_max"]

        # Collect all upward-facing horizontal planes that are NOT the top surface
        floor_faces = []
        for face in faces:
            if face.geom_type != "PLANE":
                continue
            n = face.normal
            if n is None:
                continue
            # Upward-facing (normal ~= +Z)
            if n[2] > 1.0 - self.NORMAL_TOL:
                z_floor = face.center[2]
                if abs(z_floor - top_z) > 0.5:   # not the top face
                    floor_faces.append(face)

        for floor in floor_faces:
            b = floor.bounds
            depth = top_z - floor.center[2]
            if depth < 0.2:
                continue

            # Check shape: compare pocket XY span to floor area
            pocket_lx = b["x_max"] - b["x_min"]
            pocket_ly = b["y_max"] - b["y_min"]
            rect_area = pocket_lx * pocket_ly

            if rect_area < 1.0:
                continue

            if abs(floor.area - rect_area) / rect_area < 0.15:
                shape = "rectangular"
            else:
                # Check if approximately circular
                r = min(pocket_lx, pocket_ly) / 2
                circ_area = math.pi * r * r
                if abs(floor.area - circ_area) / circ_area < 0.2:
                    shape = "circular"
                else:
                    shape = "freeform"

            pockets.append(PocketFeature(
                x_min=b["x_min"], x_max=b["x_max"],
                y_min=b["y_min"], y_max=b["y_max"],
                z_top=top_z,
                z_bottom=floor.center[2],
                depth=depth,
                shape=shape,
            ))

        return pockets

    # ─── Fillet/chamfer detection ──────────────────────────────────

    def _detect_fillets(self) -> list[FilletFeature]:
        fillets = []
        curved_edges = []

        try:
            for edge in self._val.Edges():
                if edge.geomType() != "LINE":
                    curved_edges.append(edge)
        except Exception:
            return fillets

        if not curved_edges:
            return fillets

        # Separate torus edges (fillets) from cylinder edges (holes)
        radii = []
        for edge in curved_edges:
            try:
                r = edge.radius()
                if 0.1 < r < 50.0:   # plausible fillet range
                    radii.append(r)
            except Exception:
                pass

        if radii:
            # Most common radius = fillet radius
            from collections import Counter
            rounded = [round(r, 1) for r in radii]
            common_r = Counter(rounded).most_common(1)[0][0]
            fillets.append(FilletFeature(
                radius=common_r,
                edge_count=len(curved_edges),
                is_chamfer=False,
            ))
        elif curved_edges:
            fillets.append(FilletFeature(
                radius=1.0,
                edge_count=len(curved_edges),
                is_chamfer=False,
            ))

        return fillets

    # ─── Freeform surface detection ────────────────────────────────

    def _detect_freeform(self, faces: list[RecognizedFace]) -> list[FreeformSurface]:
        freeform = []
        non_prismatic = {"SPHERE", "TORUS", "BSPLINE", "BEZIER", "CONE",
                         "REVOLUTION", "EXTRUSION", "OTHER"}

        for face in faces:
            if face.geom_type in non_prismatic:
                b = face.bounds
                freeform.append(FreeformSurface(
                    geom_type=face.geom_type,
                    z_min=b["z_min"],
                    z_max=b["z_max"],
                    z_span=b["z_max"] - b["z_min"],
                ))

        # Also flag: non-horizontal, non-vertical planes (angled surfaces)
        for face in faces:
            if face.geom_type != "PLANE":
                continue
            n = face.normal
            if n is None:
                continue
            nz = abs(n[2])
            # Not purely horizontal (z≈1) or vertical (z≈0)
            if self.NORMAL_TOL < nz < 1.0 - self.NORMAL_TOL:
                b = face.bounds
                freeform.append(FreeformSurface(
                    geom_type="ANGLED_PLANE",
                    z_min=b["z_min"],
                    z_max=b["z_max"],
                    z_span=b["z_max"] - b["z_min"],
                ))
                break  # one is enough to flag

        return freeform

    # ─── Undercut detection ────────────────────────────────────────

    def _check_undercuts(self, result: BrepAnalysisResult) -> None:
        """Flag faces whose normal points significantly downward (undercut from top).

        Excludes:
        - The bottom face (z ≈ z_min) — that's just the stock bottom
        - Faces with very small area (tiny transitional faces from fillets)
        - Angled faces that are mostly facing sideways (e.g., chamfer ≤30°)
        """
        undercut_faces = []
        z_bottom = self._bb["z_min"]
        min_area_threshold = 1.0   # mm² — ignore tiny transitional faces

        for face in result.faces:
            if face.geom_type != "PLANE":
                continue
            n = face.normal
            if n is None:
                continue
            # Must be pointing significantly downward (not just a tiny tilt)
            if n[2] >= -0.5:   # normal must be mostly downward (>30° below horizontal)
                continue
            # Exclude bottom face
            if abs(face.center[2] - z_bottom) < self.NORMAL_TOL * 10:
                continue
            # Exclude tiny faces (fillet/chamfer artifacts)
            if face.area < min_area_threshold:
                continue
            undercut_faces.append(face)

        if undercut_faces:
            result.has_undercuts = True
            result.accessible_from_top = False
            result.undercut_warning = (
                f"{len(undercut_faces)} undercut face(s) detected. "
                "3-axis machining cannot reach these surfaces. "
                "Consider 5-axis or repositioning."
            )
