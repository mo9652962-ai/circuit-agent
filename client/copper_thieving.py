"""IPC-2221B Section 10.1.1 Copper Balancing & Thieving Pattern Generator.

Industrial benchmark & standards:
- IPC-2221B Section 10.1.1: Non-Functional Copper Distribution (Copper Thieving).
  Uneven copper distribution between top and bottom layers causes differential thermal
  expansion, resulting in severe PCB warpage (Bow and Twist) exceeding the IPC-TM-650 2.4.22
  0.75% limit during reflow and wave soldering.
- Galvanic Electroplating Equilibrium:
  Large isolated void areas starve adjacent fine traces of electroplating current (current crowding),
  causing uneven copper thickness. Adding dummy copper thieving dots or cross-hatched grids
  equalizes current density in the copper plating bath.
- Standard Thieving Features:
  * Dot Pattern: Solid circular dots (Φ1.0mm) spaced at 2.54mm (100 mil) pitch.
  * Cross-hatch Grid: 0.3mm track with 1.27mm opening pitch.
  * Keepout Clearance: Minimum 1.5mm clearance to functional traces, pads, and board edges.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ThievingFeature:
    x_mm: float
    y_mm: float
    feature_type: str  # "dot" or "cross_hatch"
    diameter_mm: float = 1.0


@dataclass
class CopperThievingReport:
    board_width_mm: float
    board_height_mm: float
    top_copper_density_pct: float
    bot_copper_density_pct: float
    density_imbalance_pct: float
    warpage_risk: str  # "LOW", "MEDIUM", "HIGH"
    thieving_features_count: int
    features: list[ThievingFeature] = field(default_factory=list)
    ipc_standard: str = "IPC-2221B Section 10.1.1 / IPC-TM-650 2.4.22"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["features"] = [asdict(f) for f in self.features]
        return d


def calculate_copper_thieving_balance(
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    top_copper_area_mm2: float | None = None,
    bot_copper_area_mm2: float | None = None,
    keepout_margin_mm: float = 2.0,
    pattern_pitch_mm: float = 2.54,
    dot_diameter_mm: float = 1.0,
) -> CopperThievingReport:
    """Calculate layer copper balance and generate dummy copper thieving grid to prevent PCB warpage."""
    total_area = board_width_mm * board_height_mm
    # Default estimated copper density if not provided (e.g. 25% top, 65% bot solid ground)
    top_area = top_copper_area_mm2 if top_copper_area_mm2 is not None else (total_area * 0.25)
    bot_area = bot_copper_area_mm2 if bot_copper_area_mm2 is not None else (total_area * 0.65)

    top_pct = round((top_area / max(1.0, total_area)) * 100.0, 1)
    bot_pct = round((bot_area / max(1.0, total_area)) * 100.0, 1)
    diff_pct = round(abs(top_pct - bot_pct), 1)

    if diff_pct > 35.0:
        risk = "HIGH"
    elif diff_pct > 20.0:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    # Generate thieving dots across low-density regions
    features: list[ThievingFeature] = []
    x_start = keepout_margin_mm + 1.0
    y_start = keepout_margin_mm + 1.0
    x_end = board_width_mm - keepout_margin_mm - 1.0
    y_end = board_height_mm - keepout_margin_mm - 1.0

    cur_x = x_start
    while cur_x <= x_end:
        cur_y = y_start
        while cur_y <= y_end:
            features.append(ThievingFeature(x_mm=round(cur_x, 2), y_mm=round(cur_y, 2), feature_type="dot", diameter_mm=dot_diameter_mm))
            cur_y += pattern_pitch_mm
        cur_x += pattern_pitch_mm

    return CopperThievingReport(
        board_width_mm=board_width_mm,
        board_height_mm=board_height_mm,
        top_copper_density_pct=top_pct,
        bot_copper_density_pct=bot_pct,
        density_imbalance_pct=diff_pct,
        warpage_risk=risk,
        thieving_features_count=len(features),
        features=features,
    )
