"""JESD22-B111 / JESD22-B110A Board-Level Drop & Mechanical Shock Reliability Assessor.

Industrial & Authorive Standards:
- JESD22-B111 (Board Level Drop Test Method for Handheld Electronic Products):
  The JEDEC standard drop test for portable devices: 1500 G peak, 0.5 ms half-sine
  pulse, 30 drops at 1 drop/s, board horizontal component-face-down. Failure is
  detected by resistance shift or event detection (intermittent contact).
- JESD22-B110A (Subassembly Mechanical Shock):
  extends the same methodology to subassemblies and mounting conditions.
- Physics of board-level drop failure (Intel/Amkor published studies):
  During impact the PCB flexes in its fundamental mode; peak strain concentrates
  at the board corners. Failure sequence for BGA packages:
    1. Board corner region sees maximum bending strain (longest DNP from neutral axis).
    2. Solder joints at the package's outermost corner rows crack (brittle interfacial
       failure, aggravated by ENIG black-pad and thick IMC).
    3. Large heavy components (transformers, shield cans, large electrolytics) overload
       their joints through inertial force F = m·a:  a 50 g shield at 1500 G loads its
       4 joints with ~750 N total.
- Mitigation hierarchy (industry practice):
  * Place heavy/large components near board center, away from corner flexure zones
  * Add support/border rings (stiffener rails) and screw bosses to raise board
    natural frequency above the excitation band
  * Underfill corner rows of large BGAs; use dual-side reinforcement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DROP_TEST_G = 1500.0
DROP_PULSE_MS = 0.5
GRAVITY_M_S2 = 9.81


@dataclass
class DropComponentRisk:
    """One component's drop-shock risk verdict."""

    ref: str
    mass_g: float
    joint_count: int
    corner_distance_mm: float
    inertial_force_n: float
    per_joint_load_n: float
    risk_level: str  # 'low' | 'moderate' | 'high'
    mitigation: str


@dataclass
class DropShockResult:
    """Board-level drop reliability assessment summary."""

    board_mass_g: float
    board_diagonal_mm: float
    est_natural_freq_hz: float
    summary: str
    components: list[DropComponentRisk] = field(default_factory=list)
    high_risk_count: int = 0
    corner_zone_clear: bool = True
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "board_mass_g": round(self.board_mass_g, 1),
            "board_diagonal_mm": round(self.board_diagonal_mm, 1),
            "est_natural_freq_hz": round(self.est_natural_freq_hz, 0),
            "components": [
                {
                    "ref": c.ref,
                    "mass_g": round(c.mass_g, 2),
                    "corner_distance_mm": round(c.corner_distance_mm, 1),
                    "per_joint_load_n": round(c.per_joint_load_n, 1),
                    "risk_level": c.risk_level,
                    "mitigation": c.mitigation,
                }
                for c in self.components
            ],
            "high_risk_count": self.high_risk_count,
            "corner_zone_clear": self.corner_zone_clear,
            "summary": self.summary,
            "standards_cited": self.standards_cited,
        }


# Per-joint sustained load capability (N) for SMT attachments before interface
# cracking risk becomes credible (empirical BGA/QFN range with safety factor).
JOINT_LOAD_LIMIT_N = 150.0


def assess_drop_shock_reliability(
    board_width_mm: float = 80.0,
    board_height_mm: float = 50.0,
    board_mass_g: float = 60.0,
    components: list[dict[str, Any]] | None = None,
    test_g: float = DROP_TEST_G,
    has_border_ring_stiffener: bool = False,
) -> DropShockResult:
    """Assess component-level drop shock survival per JESD22-B111 physics.

    Args:
        board_width_mm / board_height_mm: PCB dimensions.
        board_mass_g: Total assembled board mass (g).
        components: [{ref, mass_g, x_mm, y_mm, joint_count}] — coordinates relative
            to board center (0,0), e.g. from CPL placement data.
        test_g: Peak shock level in G (default 1500 per JESD22-B111).
        has_border_ring_stiffener: True when the product has a mid-frame/border ring
            that anchors the board edge (raises natural frequency, halves corner strain).

    Returns:
        DropShockResult: Per-component risk, corner-zone clearance, and summary.
    """
    diag = (board_width_mm**2 + board_height_mm**2) ** 0.5
    half_w, half_h = board_width_mm / 2.0, board_height_mm / 2.0

    # Fundamental frequency estimate for a clamped-edge rectangular PCB (empirical):
    # stiffener ring roughly doubles it.
    f0 = 220.0 * (1.6 / max(0.6, board_width_mm / 50.0))
    if has_border_ring_stiffener:
        f0 *= 2.0

    comp_risks: list[DropComponentRisk] = []
    corner_zone_clear = True
    corner_limit = 0.25  # components whose center sits in outer 25% corner squares

    for c in components or []:
        ref = str(c.get("ref", "U?"))
        mass = max(0.01, float(c.get("mass_g", 0.5)))
        joints = max(2, int(c.get("joint_count", 4)))
        x, y = float(c.get("x_mm", 0.0)), float(c.get("y_mm", 0.0))
        corner_dist = ((abs(x) / max(1.0, half_w)) ** 2 + (abs(y) / max(1.0, half_h)) ** 2) ** 0.5

        inertial = mass / 1000.0 * test_g * GRAVITY_M_S2
        per_joint = inertial / joints

        in_corner = corner_dist >= 0.85
        heavy = mass >= 5.0
        overload = per_joint >= JOINT_LOAD_LIMIT_N

        if overload or (heavy and in_corner):
            risk = "high"
        elif heavy or in_corner or per_joint >= 0.5 * JOINT_LOAD_LIMIT_N:
            risk = "moderate"
        else:
            risk = "low"

        if risk == "high":
            mit = "欠填充外圈焊球 + 迁移至板中心低应变区，或加螺柱/局部加强筋卸载惯性力。"
        elif risk == "moderate":
            mit = "远离板角高应变带；大件建议底部点胶补强。"
        else:
            mit = "布局合规。"
        if in_corner and corner_dist >= 1.0 - corner_limit:
            corner_zone_clear = False

        comp_risks.append(
            DropComponentRisk(
                ref=ref, mass_g=mass, joint_count=joints,
                corner_distance_mm=corner_dist * min(half_w, half_h),
                inertial_force_n=inertial, per_joint_load_n=per_joint,
                risk_level=risk, mitigation=mit,
            )
        )

    high = sum(1 for r in comp_risks if r.risk_level == "high")
    worst = max(comp_risks, key=lambda r: r.per_joint_load_n) if comp_risks else None

    if high > 0:
        summary = (
            f"{high} 个器件在 {test_g:.0f}G 跌落脉冲下高风险"
            + (f"（最恶劣 {worst.ref} 单点 {worst.per_joint_load_n:.0f}N/焊点）" if worst else "")
            + "——按 JESD22-B111 建议整改后复测 30 连跌。"
        )
    elif comp_risks:
        summary = f"全部 {len(comp_risks)} 器件跌落风险评估通过；板基频估计 {f0:.0f}Hz。"
    else:
        summary = "未提供器件明细——按 JESD22-B111 流程做 1500G/0.5ms 30 连跌摸底。"

    cited = [
        "JEDEC JESD22-B111 Board Level Drop Test Method for Handheld Electronic Products",
        "JEDEC JESD22-B110A Subassembly Mechanical Shock",
    ]

    return DropShockResult(
        board_mass_g=board_mass_g,
        board_diagonal_mm=diag,
        est_natural_freq_hz=f0,
        summary=summary,
        components=comp_risks,
        high_risk_count=high,
        corner_zone_clear=corner_zone_clear,
        standards_cited=cited,
    )
