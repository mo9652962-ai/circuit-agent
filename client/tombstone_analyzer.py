"""IPC-A-610G / IPC-SM-782 SMT Chip Component Thermal Relief & Tombstoning Risk Auditor.

Industrial & Authoritative Standards:
- IPC-A-610G (Acceptability of Electronic Assemblies) §8.3.2.9:
  Defines "Tombstoning" (Drawbridging / Manhattan Effect) as a defect where a two-terminal
  surface-mount chip component (capacitor, resistor, ferrite bead) lifts on one end during
  reflow soldering, remaining vertically suspended with an open circuit.
- IPC-SM-782 / IPC-7351B Thermal Relief Guidelines:
  Tombstoning is physically caused by unequal thermal inertia and wetting kinetics:
    1. Pad 1 is connected to a narrow signal trace (e.g., 0.15mm ~ 0.25mm trace width),
       while Pad 2 is tied directly to a massive solid copper ground or power pour.
    2. During reflow, Pad 1 reaches solder liquidus temperature (217°C for SAC305) first;
       molten solder wets the termination and exerts surface tension capillary pull force.
    3. Pad 2 remains solid for several critical seconds because the solid copper plane
       acts as a massive thermal heat sink.
    4. The unbalanced surface tension torque (M = F_wetting × L_standoff) rotates the chip
       around the wetting pad, pulling the opposite end completely off the PCB.
- Prevention & Tolerance Limits:
  * Maximum thermal copper connection ratio R = Area_connected_1 / Area_connected_2 <= 2.0.
  * Direct solid connection of chip passive pads to solid planes is strictly forbidden:
    must use thermal relief spokes (standard 2 to 4 spokes, width 0.20mm ~ 0.30mm).
  * High-risk packages: 0402 and 0201 have minimal self-weight (< 0.5mg), making them
    5x ~ 10x more susceptible to surface tension torque flipping than larger 1206 parts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

MAX_THERMAL_IMBALANCE_RATIO = 2.0  # R <= 2.0 safe limit
HIGH_RISK_RATIO = 3.5              # R > 3.5 severe tombstone probability (>30%)

# Package susceptibility multipliers (smaller components have lower mass and tilt easily)
PACKAGE_TOMBSTONE_SUSCEPTIBILITY: dict[str, float] = {
    "01005": 3.5,
    "0201": 2.5,
    "0402": 1.8,
    "0603": 1.2,
    "0805": 1.0,
    "1206": 0.6,
    "1210": 0.4,
}


@dataclass
class TombstoneComponentRisk:
    """Tombstone evaluation for a single 2-terminal chip passive."""

    ref_des: str
    package: str
    pad1_connection_type: str  # 'trace' | 'thermal_relief' | 'solid_plane'
    pad2_connection_type: str
    pad1_effective_width_mm: float
    pad2_effective_width_mm: float
    thermal_imbalance_ratio: float
    risk_level: str  # 'low' | 'moderate' | 'high'
    recommendation: str


@dataclass
class TombstoneAuditReport:
    """Complete SMT tombstoning and thermal relief balance audit report."""

    total_passives_audited: int
    high_risk_count: int
    moderate_risk_count: int
    is_assembly_safe: bool
    at_risk_components: list[TombstoneComponentRisk] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_passives_audited": self.total_passives_audited,
            "high_risk_count": self.high_risk_count,
            "moderate_risk_count": self.moderate_risk_count,
            "is_assembly_safe": self.is_assembly_safe,
            "at_risk_components": [asdict(c) for c in self.at_risk_components],
            "recommendations": self.recommendations,
            "standards_cited": self.standards_cited,
        }


def audit_smt_tombstone_risk(
    components: list[dict[str, Any]] | None = None,
    default_trace_width_mm: float = 0.20,
) -> TombstoneAuditReport:
    """Audit 2-terminal SMT chip passives for thermal balance and tombstoning risk per IPC-A-610G.

    Args:
        components: List of chip component dicts:
            [{ref, package, pad1_type, pad2_type, pad1_width_mm, pad2_width_mm}]
            where type is 'trace', 'thermal_relief', or 'solid_plane'.
        default_trace_width_mm: Standard signal trace width in mm (default: 0.20mm).

    Returns:
        TombstoneAuditReport: High/moderate risk components and thermal relief spoke recommendations.
    """
    cited = [
        "IPC-A-610G Acceptability of Electronic Assemblies §8.3.2.9 Tombstoning",
        "IPC-SM-782 Surface Mount Design and Land Pattern Standard §3.1.2 Thermal Balance",
        "IPC-7351B Generic Requirements for Surface Mount Design and Land Pattern Standard",
    ]

    if not components:
        # Default nominal demo components
        components = [
            {"ref": "C1", "package": "0402", "pad1_type": "trace", "pad2_type": "trace", "pad1_width_mm": 0.20, "pad2_width_mm": 0.20},
            {"ref": "C2", "package": "0402", "pad1_type": "trace", "pad2_type": "solid_plane", "pad1_width_mm": 0.20, "pad2_width_mm": 2.50},
            {"ref": "R1", "package": "0603", "pad1_type": "trace", "pad2_type": "thermal_relief", "pad1_width_mm": 0.25, "pad2_width_mm": 0.40},
        ]

    risks: list[TombstoneComponentRisk] = []
    high_count = 0
    mod_count = 0
    recs: list[str] = []

    for comp in components:
        ref = str(comp.get("ref", "C?"))
        pkg = str(comp.get("package", "0402")).upper()
        p1_type = str(comp.get("pad1_type", "trace")).lower()
        p2_type = str(comp.get("pad2_type", "trace")).lower()

        # Effective thermal connection widths
        w1 = float(comp.get("pad1_width_mm", default_trace_width_mm))
        w2 = float(comp.get("pad2_width_mm", default_trace_width_mm))

        if p1_type == "solid_plane" and w1 < 1.0:
            w1 = 2.0  # Plane connection heat sink equivalent
        if p2_type == "solid_plane" and w2 < 1.0:
            w2 = 2.0

        if p1_type == "thermal_relief" and w1 > 0.5:
            w1 = 0.40  # 2 spokes of 0.20mm
        if p2_type == "thermal_relief" and w2 > 0.5:
            w2 = 0.40

        # Thermal imbalance ratio R = max(w1, w2) / min(w1, w2)
        ratio = max(w1, w2) / max(0.05, min(w1, w2))

        # Size susceptibility factor
        suscept = 1.0
        for p_key, factor in PACKAGE_TOMBSTONE_SUSCEPTIBILITY.items():
            if p_key in pkg:
                suscept = factor
                break

        weighted_ratio = ratio * (suscept ** 0.5)

        if weighted_ratio > HIGH_RISK_RATIO or (p1_type == "solid_plane" and p2_type == "trace" and "0402" in pkg):
            risk = "high"
            high_count += 1
            rec = "Severe tombstone risk: Pad tied directly to solid copper pour without thermal relief. Add 2~4 spoke thermal relief (spoke width 0.20mm) and equalize trace entry width."
        elif weighted_ratio > MAX_THERMAL_IMBALANCE_RATIO:
            risk = "moderate"
            mod_count += 1
            rec = f"Moderate thermal imbalance (R={ratio:.1f}). Balance conductor trace widths entering opposite pads to achieve R <= 2.0."
        else:
            risk = "low"
            rec = "Thermally balanced pads. Low tombstoning risk."

        if risk in ("high", "moderate"):
            risks.append(
                TombstoneComponentRisk(
                    ref_des=ref,
                    package=pkg,
                    pad1_connection_type=p1_type,
                    pad2_connection_type=p2_type,
                    pad1_effective_width_mm=round(w1, 2),
                    pad2_effective_width_mm=round(w2, 2),
                    thermal_imbalance_ratio=round(ratio, 2),
                    risk_level=risk,
                    recommendation=rec,
                )
            )

    if high_count > 0:
        recs.append(f"Detected {high_count} high-risk chip components subject to Manhattan tombstone lifting. Convert all direct solid plane connections to thermal relief spokes.")
    if mod_count > 0:
        recs.append(f"Detected {mod_count} moderately imbalanced passives. Symmetry of heat dissipation is critical for 0402 and 0201 reflow yields.")
    if not recs:
        recs.append("All passive land patterns demonstrate acceptable thermal symmetry (R <= 2.0).")

    return TombstoneAuditReport(
        total_passives_audited=len(components),
        high_risk_count=high_count,
        moderate_risk_count=mod_count,
        is_assembly_safe=high_count == 0,
        at_risk_components=risks,
        recommendations=recs,
        standards_cited=cited,
    )
