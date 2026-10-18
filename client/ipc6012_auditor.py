"""IPC-6012E & IPC-A-600J Rigid PCB Qualification & Class 1/2/3 Acceptance Criteria Auditor.

Industrial & Authoritative Standards:
- IPC-6012E (Qualification and Performance Specification for Rigid Printed Boards):
  Establishes performance and qualification requirements for rigid printed boards (single-sided,
  double-sided, and multilayer). Classifies product requirements into three distinct classes:
    * Class 1 - General Electronic Products (consumer gadgets, toys, uncritical functions)
    * Class 2 - Dedicated Service Electronic Products (standard industrial, telecom, computers)
    * Class 3 - High Reliability Electronic Products (aerospace, defense, medical, automotive life-support)
- IPC-A-600J (Acceptability of Printed Boards):
  Defines visual and dimensional acceptance criteria for bare boards:
    * Minimum Annular Ring:
        - Class 1: 180° breakout allowed as long as conductor junction retains 30% width.
        - Class 2: 90° breakout allowed (external min annular ring >= 0.0mm at tangency).
        - Class 3: Strictly NO BREAKOUT permitted (external >= 0.050mm / 2.0 mil, internal >= 0.025mm / 1.0 mil).
    * Plated Through-Hole (PTH) Copper Barrel Thickness:
        - Class 1: Average >= 18 μm, minimum thin-point >= 15 μm.
        - Class 2: Average >= 20 μm, minimum thin-point >= 18 μm.
        - Class 3: Average >= 25 μm, minimum thin-point >= 20 μm.
    * Conductor Width & Spacing Reduction (due to etch defects/nicks):
        - Class 1: Max 30% reduction from nominal.
        - Class 2: Max 20% reduction from nominal.
        - Class 3: Max 10% reduction from nominal.
    * Solder Mask Bridge / Dam:
        - Class 1: Min 0.050 mm (2.0 mil).
        - Class 2: Min 0.075 mm (3.0 mil).
        - Class 3: Min 0.100 mm (4.0 mil).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ClassThreshold:
    """Thresholds for a specific IPC-6012E classification level."""

    min_ext_annular_ring_mm: float
    min_int_annular_ring_mm: float
    allow_breakout: bool
    max_breakout_angle_deg: float
    min_avg_barrel_cu_um: float
    min_thin_point_cu_um: float
    max_conductor_reduction_pct: float
    min_solder_mask_dam_mm: float


IPC_CLASS_CRITERIA: dict[str, ClassThreshold] = {
    "Class 1": ClassThreshold(
        min_ext_annular_ring_mm=0.000,
        min_int_annular_ring_mm=0.000,
        allow_breakout=True,
        max_breakout_angle_deg=180.0,
        min_avg_barrel_cu_um=18.0,
        min_thin_point_cu_um=15.0,
        max_conductor_reduction_pct=30.0,
        min_solder_mask_dam_mm=0.050,
    ),
    "Class 2": ClassThreshold(
        min_ext_annular_ring_mm=0.000,
        min_int_annular_ring_mm=0.000,
        allow_breakout=True,
        max_breakout_angle_deg=90.0,
        min_avg_barrel_cu_um=20.0,
        min_thin_point_cu_um=18.0,
        max_conductor_reduction_pct=20.0,
        min_solder_mask_dam_mm=0.075,
    ),
    "Class 3": ClassThreshold(
        min_ext_annular_ring_mm=0.050,  # 2.0 mil strictly required
        min_int_annular_ring_mm=0.025,  # 1.0 mil strictly required
        allow_breakout=False,  # Zero breakout allowed!
        max_breakout_angle_deg=0.0,
        min_avg_barrel_cu_um=25.0,
        min_thin_point_cu_um=20.0,
        max_conductor_reduction_pct=10.0,
        min_solder_mask_dam_mm=0.100,
    ),
}


@dataclass
class IPC6012Violation:
    """A single IPC-6012E / IPC-A-600J requirement violation."""

    criterion: str
    severity: str  # 'error' | 'warning'
    actual_value: Any
    required_value: Any
    unit: str
    description: str
    ipc_reference: str


@dataclass
class IPC6012AuditReport:
    """Comprehensive compliance evaluation report for IPC-6012E & IPC-A-600J."""

    target_class: str
    is_compliant: bool
    violations_count: int
    violations: list[IPC6012Violation] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_class": self.target_class,
            "is_compliant": self.is_compliant,
            "violations_count": self.violations_count,
            "violations": [asdict(v) for v in self.violations],
            "recommendations": self.recommendations,
            "standards_cited": self.standards_cited,
        }


def audit_ipc6012_class_compliance(
    target_class: str = "Class 2",
    external_annular_ring_mm: float = 0.125,
    internal_annular_ring_mm: float = 0.100,
    has_hole_breakout: bool = False,
    breakout_angle_deg: float = 0.0,
    avg_copper_barrel_um: float = 22.0,
    min_copper_barrel_um: float = 19.0,
    conductor_width_reduction_pct: float = 5.0,
    min_solder_mask_dam_mm: float = 0.090,
) -> IPC6012AuditReport:
    """Audit board physical parameters against IPC-6012E / IPC-A-600J Class 1/2/3 acceptance criteria.

    Args:
        target_class: Target reliability class ('Class 1', 'Class 2', or 'Class 3')
        external_annular_ring_mm: Minimum external annular ring width
        internal_annular_ring_mm: Minimum internal annular ring width
        has_hole_breakout: True if drill hole breakout from annular ring is observed
        breakout_angle_deg: Angle of hole breakout in degrees (if any)
        avg_copper_barrel_um: Average electroplated copper thickness in PTH barrels
        min_copper_barrel_um: Minimum measured thin-point copper thickness in PTH barrels
        conductor_width_reduction_pct: Maximum conductor width reduction from etching/nicks
        min_solder_mask_dam_mm: Minimum solder mask bridge width between adjacent pads

    Returns:
        IPC6012AuditReport: Compliance evaluation, violations, and manufacturing recommendations
    """
    cls_key = "Class 3" if "3" in str(target_class) else ("Class 1" if "1" in str(target_class) else "Class 2")
    crit = IPC_CLASS_CRITERIA[cls_key]

    violations: list[IPC6012Violation] = []
    recs: list[str] = []
    cited = [
        "IPC-6012E Qualification and Performance Specification for Rigid Printed Boards §3.3-§3.6",
        "IPC-A-600J Acceptability of Printed Boards §2.8 & §3.1",
    ]

    # 1. External Annular Ring
    if external_annular_ring_mm < crit.min_ext_annular_ring_mm:
        violations.append(
            IPC6012Violation(
                criterion="external_annular_ring",
                severity="error",
                actual_value=round(external_annular_ring_mm, 3),
                required_value=crit.min_ext_annular_ring_mm,
                unit="mm",
                description=(
                    f"External annular ring ({external_annular_ring_mm:.3f}mm) is below {cls_key} requirement "
                    f"({crit.min_ext_annular_ring_mm:.3f}mm / {crit.min_ext_annular_ring_mm * 39.37:.1f} mil)."
                ),
                ipc_reference="IPC-6012E §3.6.2.1 Table 3-5 & IPC-A-600J §2.8.1",
            )
        )
        recs.append(f"Increase via pad outer diameter or enlarge teardrop fillet to meet {crit.min_ext_annular_ring_mm:.3f}mm annular ring.")

    # 2. Internal Annular Ring
    if internal_annular_ring_mm < crit.min_int_annular_ring_mm:
        violations.append(
            IPC6012Violation(
                criterion="internal_annular_ring",
                severity="error",
                actual_value=round(internal_annular_ring_mm, 3),
                required_value=crit.min_int_annular_ring_mm,
                unit="mm",
                description=(
                    f"Internal annular ring ({internal_annular_ring_mm:.3f}mm) is below {cls_key} requirement "
                    f"({crit.min_int_annular_ring_mm:.3f}mm / {crit.min_int_annular_ring_mm * 39.37:.1f} mil)."
                ),
                ipc_reference="IPC-6012E §3.6.2.2 & IPC-A-600J §2.8.2",
            )
        )

    # 3. Hole Breakout
    if has_hole_breakout:
        if not crit.allow_breakout:
            violations.append(
                IPC6012Violation(
                    criterion="hole_breakout_forbidden",
                    severity="error",
                    actual_value=f"Breakout {breakout_angle_deg:.1f}°",
                    required_value="0° (Zero Breakout Permitted)",
                    unit="deg",
                    description=f"{cls_key} strictly prohibits any annular ring breakout (90° tangency breakout is only allowed in Class 2).",
                    ipc_reference="IPC-6012E §3.6.2.1 & IPC-A-600J §2.8.1.3 Class 3 Acceptability",
                )
            )
            recs.append("Zero drill breakout is mandatory for Class 3. Check CNC drill registration tolerance and shrink drill diameter.")
        elif breakout_angle_deg > crit.max_breakout_angle_deg:
            violations.append(
                IPC6012Violation(
                    criterion="hole_breakout_exceeded",
                    severity="error",
                    actual_value=round(breakout_angle_deg, 1),
                    required_value=crit.max_breakout_angle_deg,
                    unit="deg",
                    description=(
                        f"Annular ring breakout angle ({breakout_angle_deg:.1f}°) exceeds {cls_key} allowable limit "
                        f"({crit.max_breakout_angle_deg:.0f}°)."
                    ),
                    ipc_reference="IPC-A-600J §2.8.1.2 Class 2 Tangency Limits",
                )
            )

    # 4. Copper Barrel Plating Thickness
    if avg_copper_barrel_um < crit.min_avg_barrel_cu_um:
        violations.append(
            IPC6012Violation(
                criterion="copper_barrel_avg_thickness",
                severity="error",
                actual_value=round(avg_copper_barrel_um, 1),
                required_value=crit.min_avg_barrel_cu_um,
                unit="um",
                description=(
                    f"Average PTH copper plating thickness ({avg_copper_barrel_um:.1f}μm) is below {cls_key} minimum "
                    f"({crit.min_avg_barrel_cu_um:.0f}μm)."
                ),
                ipc_reference="IPC-6012E §3.6.2 Table 3-4 & IPC-A-600J §3.1.1",
            )
        )
        recs.append(f"Request {crit.min_avg_barrel_cu_um:.0f}μm copper plating thickness from PCB fab for {cls_key} qualification.")

    if min_copper_barrel_um < crit.min_thin_point_cu_um:
        violations.append(
            IPC6012Violation(
                criterion="copper_barrel_min_thin_point",
                severity="error",
                actual_value=round(min_copper_barrel_um, 1),
                required_value=crit.min_thin_point_cu_um,
                unit="um",
                description=(
                    f"Minimum thin-point PTH copper plating ({min_copper_barrel_um:.1f}μm) is below {cls_key} requirement "
                    f"({crit.min_thin_point_cu_um:.0f}μm)."
                ),
                ipc_reference="IPC-6012E §3.6.2 Table 3-4 & IPC-A-600J §3.1.2",
            )
        )

    # 5. Conductor Width Reduction
    if conductor_width_reduction_pct > crit.max_conductor_reduction_pct:
        violations.append(
            IPC6012Violation(
                criterion="conductor_width_reduction",
                severity="warning" if cls_key != "Class 3" else "error",
                actual_value=round(conductor_width_reduction_pct, 1),
                required_value=crit.max_conductor_reduction_pct,
                unit="%",
                description=(
                    f"Conductor width reduction from etch defects/nicks ({conductor_width_reduction_pct:.1f}%) exceeds "
                    f"{cls_key} tolerance window ({crit.max_conductor_reduction_pct:.0f}%)."
                ),
                ipc_reference="IPC-6012E §3.5.1 & IPC-A-600J §2.5.1",
            )
        )

    # 6. Solder Mask Dam
    if min_solder_mask_dam_mm < crit.min_solder_mask_dam_mm:
        violations.append(
            IPC6012Violation(
                criterion="solder_mask_dam_width",
                severity="warning",
                actual_value=round(min_solder_mask_dam_mm, 3),
                required_value=crit.min_solder_mask_dam_mm,
                unit="mm",
                description=(
                    f"Solder mask bridge / dam width ({min_solder_mask_dam_mm:.3f}mm) is narrower than {cls_key} requirement "
                    f"({crit.min_solder_mask_dam_mm:.3f}mm / {crit.min_solder_mask_dam_mm * 39.37:.1f} mil)."
                ),
                ipc_reference="IPC-SM-840E & IPC-6012E §3.7.2",
            )
        )
        recs.append(f"Ensure >= {crit.min_solder_mask_dam_mm:.3f}mm solder mask dam between fine-pitch IC pins to prevent solder bridging.")

    return IPC6012AuditReport(
        target_class=cls_key,
        is_compliant=len([v for v in violations if v.severity == "error"]) == 0,
        violations_count=len(violations),
        violations=violations,
        recommendations=recs,
        standards_cited=cited,
    )
