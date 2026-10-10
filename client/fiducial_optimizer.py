"""J-STD-020 / IPC-2221B Optical Fiducial Layout Optimizer (Vision Alignment Targets).

Industrial benchmark & standards:
- IPC-2221B Section 12 & JEDEC J-STD-020 / IPC-A-610G Assembly Vision Guidance:
  Automated optical alignment (pick-and-place, SPI, AOI) requires machine-readable fiducial targets:
  * Global fiducials: minimum 3 per board/panel, laid out in an ASYMMETRIC L-shape
    (one quadrant intentionally omitted) to make 180° rotation mathematically unambiguous.
  * Local fiducials: 2 per fine-pitch component (pitch <= 0.5mm QFP/QFN/BGA), placed on the
    diagonal, to correct per-component placement drift.
  * Fiducial geometry: copper pad Φ1.0mm exposed, solder mask opening Φ3.0mm (2x ring),
    flatness/reflectivity requirements per IPC OP1 (polished vs matte).
- Placement rules:
  * Fiducial center >= 5.0mm from board edge (conveyor clamp + rail clearance).
  * Fiducial center >= 2.5mm from any trace/pad (visual background contrast).
  * Global fiducial diagonal span should cover >= 70% of board diagonal.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FiducialPoint:
    x_mm: float
    y_mm: float
    pad_dia_mm: float = 1.0
    mask_opening_mm: float = 3.0
    fiducial_type: str = "global"  # "global" / "local"
    owner: str = "BOARD"  # component ref for local fiducials

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FiducialLayoutReport:
    board_width_mm: float
    board_height_mm: float
    board_diagonal_mm: float
    global_fiducial_count: int
    local_fiducial_count: int
    coverage_pct: float
    is_asymmetric: bool
    fine_pitch_refs_without_local: list[str] = field(default_factory=list)
    fiducials: list[FiducialPoint] = field(default_factory=list)
    ipc_standard: str = "IPC-2221B Section 12 / JEDEC J-STD-020"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["fiducials"] = [asdict(f) for f in self.fiducials]
        return d


def calculate_fiducial_layout(
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    fine_pitch_components: list[dict] | None = None,
    edge_clearance_mm: float = 5.0,
    fine_pitch_threshold_mm: float = 0.5,
) -> FiducialLayoutReport:
    """Generate asymmetric 3-point global fiducial layout and per-component local fiducials."""
    bw = max(10.0, float(board_width_mm))
    bh = max(10.0, float(board_height_mm))
    diag = math.hypot(bw, bh)
    edge = max(3.0, float(edge_clearance_mm))

    fiducials: list[FiducialPoint] = []

    # Asymmetric L-shape: BL, BR, TL — TR quadrant intentionally empty (breaks 180° symmetry)
    fiducials.append(FiducialPoint(x_mm=round(edge, 2), y_mm=round(edge, 2), fiducial_type="global"))
    fiducials.append(FiducialPoint(x_mm=round(bw - edge, 2), y_mm=round(edge, 2), fiducial_type="global"))
    fiducials.append(FiducialPoint(x_mm=round(edge, 2), y_mm=round(bh - edge, 2), fiducial_type="global"))

    # Global span coverage across the board diagonal
    span = math.hypot((bw - 2 * edge), (bh - 2 * edge))
    coverage = round((span / diag) * 100.0, 1)

    # Local fiducials for fine-pitch components (2 per component, diagonal placement)
    missing_local: list[str] = []
    local_count = 0
    for comp in fine_pitch_components or []:
        ref = str(comp.get("ref", "U?"))
        pitch = float(comp.get("pitch_mm", 1.0))
        cx = float(comp.get("x_mm", bw / 2.0))
        cy = float(comp.get("y_mm", bh / 2.0))
        half = float(comp.get("half_diagonal_mm", 3.0))

        if pitch <= fine_pitch_threshold_mm:
            if not comp.get("has_local_fiducials", False):
                missing_local.append(ref)
            fiducials.append(FiducialPoint(x_mm=round(cx - half, 2), y_mm=round(cy - half, 2), fiducial_type="local", owner=ref))
            fiducials.append(FiducialPoint(x_mm=round(cx + half, 2), y_mm=round(cy + half, 2), fiducial_type="local", owner=ref))
            local_count += 2

    return FiducialLayoutReport(
        board_width_mm=bw,
        board_height_mm=bh,
        board_diagonal_mm=round(diag, 2),
        global_fiducial_count=3,
        local_fiducial_count=local_count,
        coverage_pct=coverage,
        is_asymmetric=True,
        fine_pitch_refs_without_local=sorted(set(missing_local)),
        fiducials=fiducials,
    )
