"""IPC-A-600J / IPC-6012E / IPC-A-610G Castellated Hole (Edge Plating) Geometry & Manufacturability Solver.

Industrial & Authoritative Standards:
- IPC-A-600J §2.9 (Plated Holes Bordering on Board Edges - Castellations):
  Castellated holes (half-holes / plated edge notches) are Plated Through-Holes (PTH) routed
  in half during final board depaneling. Used extensively for surface-mount daughter modules
  (Wi-Fi/BLE modules, ESP32, RP2040, LoRa stamps, sensor breakout carriers).
  Key manufacturing defect modes:
    1. Copper Barrel Tear-out / Delamination: Router bit catches thin copper foil (<20μm)
       or small-diameter holes (<0.8mm) and pulls the semi-cylindrical barrel away from the hole wall.
    2. Copper Burrs / Slivers: Misaligned routing cuts (>0.05mm off-center) leave ragged copper
       tags that cause solder bridges during module-to-motherboard surface mount assembly.
    3. Weak Solder Fillet: Insufficient inward pad extension (<0.50mm) reduces wetting area,
       failing IPC-A-610G §8.3.15 minimum end-joint width and side-fillet height requirements.
- IPC-6012E §3.6.3 (Edge Plating & Castellation Performance):
  * Minimum finished hole diameter: drill diameter >= 0.80mm (recommended 1.00mm ~ 1.20mm).
  * Centerline alignment with routed edge cuts: deviation |delta| <= 0.05mm.
  * Minimum inward pad extension: >= 0.50mm past the rout line.
  * Minimum pad pitch: >= 1.27mm (50 mil) to prevent inter-pad bridging during reflow.
  * Minimum copper barrel plating: >= 20.0μm (recommended 25.0μm).
  * Solder mask clearance: >= 0.075mm (3.0 mil) to expose side castellation for capillary wetting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

MIN_CASTELLATED_HOLE_DRILL_MM = 0.80     # Minimum drill diameter for router bit pass
RECOMMENDED_HOLE_DRILL_MM = 1.00         # Industry standard recommended drill
MAX_CENTERLINE_OFFSET_MM = 0.05          # Maximum routing cut offset from hole center
MIN_PAD_INWARD_LENGTH_MM = 0.50          # Minimum pad extension onto board surface
MIN_PAD_PITCH_MM = 1.27                  # 50 mil minimum pitch
MIN_COPPER_PLATING_UM = 20.0             # 20μm minimum hole barrel copper
MIN_MASK_CLEARANCE_MM = 0.075            # 3 mil solder mask relief for wettable fillet


@dataclass
class CastellatedHoleSpec:
    """Design parameters for a set of castellated pads along an edge."""

    hole_count: int
    hole_drill_diameter_mm: float
    center_to_edge_offset_mm: float
    pad_inward_length_mm: float
    pad_width_mm: float
    pad_pitch_mm: float
    copper_plating_thickness_um: float
    solder_mask_clearance_mm: float


@dataclass
class CastellatedPadAuditResult:
    """Comprehensive DFM audit and manufacturability assessment for castellated holes."""

    hole_drill_diameter_mm: float
    pad_inward_length_mm: float
    pad_pitch_mm: float
    centerline_offset_mm: float
    copper_plating_um: float
    is_manufacturable: bool
    is_pitch_compliant: bool
    is_plating_compliant: bool
    tearout_risk_level: str  # 'low' | 'moderate' | 'high'
    burr_risk_level: str     # 'low' | 'moderate' | 'high'
    estimated_solder_joint_shear_strength_n: float
    violations: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hole_drill_diameter_mm": round(self.hole_drill_diameter_mm, 2),
            "pad_inward_length_mm": round(self.pad_inward_length_mm, 2),
            "pad_pitch_mm": round(self.pad_pitch_mm, 2),
            "centerline_offset_mm": round(self.centerline_offset_mm, 3),
            "copper_plating_um": round(self.copper_plating_um, 1),
            "is_manufacturable": self.is_manufacturable,
            "is_pitch_compliant": self.is_pitch_compliant,
            "is_plating_compliant": self.is_plating_compliant,
            "tearout_risk_level": self.tearout_risk_level,
            "burr_risk_level": self.burr_risk_level,
            "estimated_solder_joint_shear_strength_n": round(self.estimated_solder_joint_shear_strength_n, 1),
            "violations": self.violations,
            "recommendations": self.recommendations,
            "standards_cited": self.standards_cited,
        }


def calculate_castellated_pad_geometry(
    hole_drill_diameter_mm: float = 1.00,
    center_to_edge_offset_mm: float = 0.00,
    pad_inward_length_mm: float = 0.80,
    pad_width_mm: float = 0.80,
    pad_pitch_mm: float = 2.00,
    copper_plating_thickness_um: float = 25.0,
    solder_mask_clearance_mm: float = 0.080,
) -> CastellatedPadAuditResult:
    """Audit castellated hole geometry and calculate routing cut tolerances per IPC-A-600J & IPC-6012E.

    Args:
        hole_drill_diameter_mm: Finished drill diameter before edge milling in mm (default: 1.00mm).
        center_to_edge_offset_mm: Cutter path offset from hole center in mm (default: 0.00mm, ideal 50/50 split).
        pad_inward_length_mm: Inward annular pad extension from board edge onto surface (default: 0.80mm).
        pad_width_mm: Pad width along the board perimeter in mm (default: 0.80mm).
        pad_pitch_mm: Center-to-center pitch between adjacent castellated holes in mm (default: 2.00mm).
        copper_plating_thickness_um: Electroplated copper thickness inside the hole barrel (default: 25.0μm).
        solder_mask_clearance_mm: Solder mask relief opening margin in mm (default: 0.080mm).

    Returns:
        CastellatedPadAuditResult: Manufacturing compliance, burr/tearout risks, and recommendations.
    """
    violations: list[str] = []
    recs: list[str] = []

    cited = [
        "IPC-A-600J Acceptability of Printed Boards §2.9 Edge Plating & Castellation Holes",
        "IPC-6012E Qualification and Performance Specification for Rigid Printed Boards §3.6.3",
        "IPC-A-610G Acceptability of Electronic Assemblies §8.3.15 Castellated Terminations",
    ]

    # 1. Hole drill diameter check
    if hole_drill_diameter_mm < MIN_CASTELLATED_HOLE_DRILL_MM:
        violations.append(
            f"Castellated hole drill ({hole_drill_diameter_mm:.2f}mm) is smaller than {MIN_CASTELLATED_HOLE_DRILL_MM:.2f}mm minimum. "
            "High router bit deflection will crush or rip copper barrel plating off the laminate wall."
        )
        recs.append(f"Enlarge castellated drill diameter to >= {RECOMMENDED_HOLE_DRILL_MM:.2f}mm to ensure rigid mechanical support during edge routing.")
    elif hole_drill_diameter_mm < RECOMMENDED_HOLE_DRILL_MM:
        recs.append(f"Drill diameter {hole_drill_diameter_mm:.2f}mm meets minimum but >= {RECOMMENDED_HOLE_DRILL_MM:.2f}mm is recommended for high assembly yields.")

    # 2. Centerline alignment check
    abs_offset = abs(center_to_edge_offset_mm)
    if abs_offset > MAX_CENTERLINE_OFFSET_MM:
        violations.append(
            f"Routing cutter path offset (|{center_to_edge_offset_mm:.3f}mm|) exceeds {MAX_CENTERLINE_OFFSET_MM:.3f}mm allowable tolerance. "
            "Off-center milling leaves residual copper burrs (under-cut) or destroys the side castellation barrel (over-cut)."
        )
        recs.append("Align the board outline (Edge.Cuts) exactly coincident with the center of the castellated hole row.")

    # 3. Inward pad extension check
    if pad_inward_length_mm < MIN_PAD_INWARD_LENGTH_MM:
        violations.append(
            f"Inward pad extension ({pad_inward_length_mm:.2f}mm) is less than {MIN_PAD_INWARD_LENGTH_MM:.2f}mm minimum. "
            "Insufficient surface pad area results in weak solder joint shear strength and copper pad peeling during handling."
        )
        recs.append(f"Extend surface land pattern inward to >= {MIN_PAD_INWARD_LENGTH_MM:.2f}mm (recommended >= 0.80mm) to guarantee solder fillet wetting.")

    # 4. Pad pitch check
    pitch_ok = pad_pitch_mm >= MIN_PAD_PITCH_MM
    if not pitch_ok:
        violations.append(
            f"Castellated hole pitch ({pad_pitch_mm:.2f}mm) is tighter than {MIN_PAD_PITCH_MM:.2f}mm (50 mil) limit. "
            "High risk of molten solder bridging between adjacent castellated pins during motherboard reflow."
        )
        recs.append(f"Increase castellated hole pitch to >= {MIN_PAD_PITCH_MM:.2f}mm or add solder mask dams between pads.")

    # 5. Copper plating thickness check
    plating_ok = copper_plating_thickness_um >= MIN_COPPER_PLATING_UM
    if not plating_ok:
        violations.append(
            f"Barrel copper thickness ({copper_plating_thickness_um:.1f}μm) is below {MIN_COPPER_PLATING_UM:.1f}μm minimum. "
            "Thin copper plating flakes off easily under CNC routing shear force."
        )
        recs.append(f"Specify >= {MIN_COPPER_PLATING_UM:.1f}μm (preferably 25.0μm Class 3) copper plating for castellated board orders.")

    # 6. Solder mask clearance check
    if solder_mask_clearance_mm < MIN_MASK_CLEARANCE_MM:
        recs.append(
            f"Solder mask clearance ({solder_mask_clearance_mm * 1000:.0f}μm) is tighter than {MIN_MASK_CLEARANCE_MM * 1000:.0f}μm. "
            "Mask encroachment onto the castellation rim will prevent side-wall solder meniscus formation."
        )

    # Risk evaluation
    if hole_drill_diameter_mm < MIN_CASTELLATED_HOLE_DRILL_MM or copper_plating_thickness_um < 18.0:
        tearout_risk = "high"
    elif hole_drill_diameter_mm < RECOMMENDED_HOLE_DRILL_MM or copper_plating_thickness_um < MIN_COPPER_PLATING_UM:
        tearout_risk = "moderate"
    else:
        tearout_risk = "low"

    if abs_offset > MAX_CENTERLINE_OFFSET_MM:
        burr_risk = "high"
    elif abs_offset > 0.025:
        burr_risk = "moderate"
    else:
        burr_risk = "low"

    # Estimate mechanical solder joint shear strength (empirical SAC305: ~35 MPa shear strength)
    # Area = Surface pad area (pad_inward_length_mm * pad_width_mm) + Side barrel inner cylinder area (pi * D/2 * PCB_T / 2)
    # Standard 1.6mm PCB assumed for estimation
    surface_area_mm2 = pad_inward_length_mm * pad_width_mm
    barrel_area_mm2 = (math.pi * (hole_drill_diameter_mm / 2.0) * 1.60) / 2.0
    total_wetting_area_mm2 = surface_area_mm2 + barrel_area_mm2
    est_shear_force_n = total_wetting_area_mm2 * 35.0  # ~35 N/mm²

    is_compliant = len(violations) == 0

    if is_compliant:
        recs.append("Castellated hole geometry is fully compliant with IPC-A-600J & IPC-6012E manufacturing standards.")

    return CastellatedPadAuditResult(
        hole_drill_diameter_mm=hole_drill_diameter_mm,
        pad_inward_length_mm=pad_inward_length_mm,
        pad_pitch_mm=pad_pitch_mm,
        centerline_offset_mm=center_to_edge_offset_mm,
        copper_plating_um=copper_plating_thickness_um,
        is_manufacturable=is_compliant,
        is_pitch_compliant=pitch_ok,
        is_plating_compliant=plating_ok,
        tearout_risk_level=tearout_risk,
        burr_risk_level=burr_risk,
        estimated_solder_joint_shear_strength_n=est_shear_force_n,
        violations=violations,
        recommendations=recs,
        standards_cited=cited,
    )
