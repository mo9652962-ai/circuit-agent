"""IPC-TM-650 2.4.22 / IPC-6012E §3.4.4 PCB Bow and Twist (Warpage & Flatness) Analyzer.

Industrial & Authoritative Standards:
- IPC-6012E §3.4.4 Table 3-3 (Maximum Allowable Percentage of Bow and Twist):
  Establishes mandatory bare-board and assembled PCBA flatness requirements:
    * Surface Mount Technology (SMT) assemblies: <= 0.75%
      (Excessive warpage >0.75% causes catastrophic BGA Head-in-Pillow (HiP) defects,
      bridging, tombstoning, and solder paste printing stencil separation leakage).
    * Through-Hole Technology (THT) only assemblies: <= 1.50%
      (Manual or wave insertion tolerates greater flexure).
- IPC-TM-650 2.4.22 (Bow and Twist Test Method):
  * Bow: Spherical or cylindrical curvature of the board with all four corners on a plane.
    Formula: Bow % = (H_bow / L_edge) × 100%
  * Twist: Cylindrical or helical deformation where one or more corners lift off the reference granite surface.
    Formula: Twist % = (H_twist / (2 × D_diagonal)) × 100%
- Thermomechanical Warpage Physics (Bimetallic Curvature Model):
  Warpage is driven by residual thermo-mechanical stress when cooling from 260°C lead-free reflow
  down through the glass transition temperature (Tg ≈ 140°C~170°C for FR-4):
    1. Dielectric Stackup Asymmetry: Unbalanced core and prepreg placements across the neutral axis.
    2. Copper Density Gradient: Imbalance between top-half copper volume and bottom-half copper volume
       (e.g., solid ground pour on Layer 2 without complementary pour on Layer 3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

MAX_BOW_TWIST_SMT_PCT = 0.75   # IPC-6012E Class 2/3 SMT standard (0.75%)
MAX_BOW_TWIST_THT_PCT = 1.50   # THT-only standard (1.50%)


@dataclass
class BowTwistResult:
    """Calculated PCB bow and twist percentages, flatness compliance, and BGA defect risk."""

    board_length_mm: float
    board_width_mm: float
    board_diagonal_mm: float
    board_thickness_mm: float
    has_smt_components: bool
    calculated_bow_pct: float
    calculated_twist_pct: float
    max_allowable_pct: float
    is_compliant: bool
    bga_head_in_pillow_risk: bool
    copper_imbalance_pct: float
    dielectric_asymmetry_pct: float
    recommendations: list[str] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "board_length_mm": round(self.board_length_mm, 1),
            "board_width_mm": round(self.board_width_mm, 1),
            "board_diagonal_mm": round(self.board_diagonal_mm, 1),
            "board_thickness_mm": round(self.board_thickness_mm, 2),
            "has_smt_components": self.has_smt_components,
            "calculated_bow_pct": round(self.calculated_bow_pct, 3),
            "calculated_twist_pct": round(self.calculated_twist_pct, 3),
            "max_allowable_pct": self.max_allowable_pct,
            "is_compliant": self.is_compliant,
            "bga_head_in_pillow_risk": self.bga_head_in_pillow_risk,
            "copper_imbalance_pct": round(self.copper_imbalance_pct, 1),
            "dielectric_asymmetry_pct": round(self.dielectric_asymmetry_pct, 1),
            "recommendations": self.recommendations,
            "standards_cited": self.standards_cited,
        }


def calculate_pcb_bow_and_twist(
    board_length_mm: float = 100.0,
    board_width_mm: float = 80.0,
    board_thickness_mm: float = 1.60,
    layer_count: int = 4,
    has_smt_components: bool = True,
    copper_balance_ratio_top_bottom: float = 1.0,
    dielectric_asymmetry_pct: float = 0.0,
    measured_bow_height_mm: float | None = None,
    measured_twist_height_mm: float | None = None,
) -> BowTwistResult:
    """Calculate and evaluate PCB bow and twist warpage per IPC-TM-650 2.4.22 & IPC-6012E.

    Args:
        board_length_mm: Board length along longest edge in mm (default: 100.0mm).
        board_width_mm: Board width along shortest edge in mm (default: 80.0mm).
        board_thickness_mm: Total finished PCB thickness in mm (default: 1.60mm).
        layer_count: Total copper layer count (default: 4).
        has_smt_components: True if assembly contains SMT parts (tight 0.75% limit) else 1.50%.
        copper_balance_ratio_top_bottom: Ratio of top-half copper volume to bottom-half (ideal 1.0).
        dielectric_asymmetry_pct: Percentage asymmetry of dielectric core/prepreg across neutral axis (default: 0.0%).
        measured_bow_height_mm: Optional dial-gauge measured bow deflection in mm.
        measured_twist_height_mm: Optional measured lifted corner height in mm.

    Returns:
        BowTwistResult: Bow/twist percentage, compliance verdict, and BGA defect risk.
    """
    recs: list[str] = []
    cited = [
        "IPC-6012E Qualification and Performance Specification for Rigid Printed Boards §3.4.4 Table 3-3",
        "IPC-TM-650 2.4.22 Bow and Twist Test Method",
        "IPC-2221B Generic Standard on Printed Board Design §10.1.1 Copper Balance",
    ]

    diag_mm = math.hypot(board_length_mm, board_width_mm)
    max_allowed = MAX_BOW_TWIST_SMT_PCT if has_smt_components else MAX_BOW_TWIST_THT_PCT

    # Copper imbalance percentage relative to 1.0
    cu_imbalance_pct = abs(copper_balance_ratio_top_bottom - 1.0) * 100.0

    if measured_bow_height_mm is not None:
        # IPC-TM-650 2.4.22 Bow % = (H_bow / L_edge) * 100%
        bow_pct = (measured_bow_height_mm / max(1.0, board_length_mm)) * 100.0
    else:
        # Thermo-mechanical predictive model based on bimetallic curvature:
        # Curvature kappa is proportional to copper imbalance, dielectric asymmetry, and (1 / thickness^2)
        # Thinner boards (0.8mm vs 1.6mm) warp 4x more severely for the same imbalance
        thickness_factor = (1.60 / max(0.40, board_thickness_mm)) ** 1.8
        base_bow_pct = 0.20 * thickness_factor  # Baseline intrinsic laminate residual bow
        induced_bow = (cu_imbalance_pct * 0.012 + dielectric_asymmetry_pct * 0.015) * thickness_factor
        bow_pct = base_bow_pct + induced_bow

    if measured_twist_height_mm is not None:
        # IPC-TM-650 2.4.22 Twist % = (H_twist / (2 * D_diag)) * 100%
        twist_pct = (measured_twist_height_mm / (2.0 * max(1.0, diag_mm))) * 100.0
    else:
        # Twist model: Driven by cross-diagonal copper distribution and board aspect ratio
        aspect_ratio = max(board_length_mm, board_width_mm) / max(1.0, min(board_length_mm, board_width_mm))
        twist_pct = bow_pct * 0.85 * min(1.5, max(0.8, aspect_ratio * 0.7))

    is_compliant = (bow_pct <= max_allowed) and (twist_pct <= max_allowed)
    hip_risk = has_smt_components and (bow_pct > MAX_BOW_TWIST_SMT_PCT or twist_pct > MAX_BOW_TWIST_SMT_PCT)

    if not is_compliant:
        recs.append(
            f"Warpage exceeds IPC-6012E {'SMT' if has_smt_components else 'THT'} limit ({max_allowed:.2f}%): "
            f"Calculated Bow={bow_pct:.2f}%, Twist={twist_pct:.2f}%."
        )
        if cu_imbalance_pct > 25.0:
            recs.append(
                f"Severe copper density imbalance ({cu_imbalance_pct:.1f}%): Add dummy copper thieving "
                "(non-functional cross-hatch or dot matrix) to lighter copper layers to equalize electroplating volume."
            )
        if dielectric_asymmetry_pct > 15.0:
            recs.append(
                f"Dielectric stackup asymmetry ({dielectric_asymmetry_pct:.1f}%): Rebalance core and prepreg thicknesses "
                "symmetrically about the horizontal stackup centerplane."
            )
        if hip_risk:
            recs.append("High BGA Head-in-Pillow (HiP) and solder bridging risk during reflow. Use reflow pallet carrier support or redesign stackup.")
    else:
        recs.append(f"Board flatness is compliant with IPC-6012E ({max_allowed:.2f}% max allowed). Low risk of reflow warpage defects.")

    return BowTwistResult(
        board_length_mm=board_length_mm,
        board_width_mm=board_width_mm,
        board_diagonal_mm=diag_mm,
        board_thickness_mm=board_thickness_mm,
        has_smt_components=has_smt_components,
        calculated_bow_pct=bow_pct,
        calculated_twist_pct=twist_pct,
        max_allowable_pct=max_allowed,
        is_compliant=is_compliant,
        bga_head_in_pillow_risk=hip_risk,
        copper_imbalance_pct=cu_imbalance_pct,
        dielectric_asymmetry_pct=dielectric_asymmetry_pct,
        recommendations=recs,
        standards_cited=cited,
    )
