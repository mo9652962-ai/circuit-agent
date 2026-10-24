"""IPC-9701 / IPC-D-279 Solder Joint Thermal Cycling Fatigue Life Estimator.

Industrial & Authoritative Standards:
- IPC-9701A (Performance Test Methods and Qualification Requirements for Surface Mount
  Solder Attachments): Defines the standard thermal cycling test conditions used to
  qualify SMT solder attachments:
    * TC1: 0 °C to +100 °C   (consumer, mild)
    * TC2: -25 °C to +125 °C (general industrial)
    * TC3: -40 °C to +125 °C (automotive grade, default for this tool)
    * TC4: -55 °C to +125 °C (aerospace / harsh)
  with 1-2.5 cycles/hour and the NTC (cycles-to-63.2%-failure) Weibull metric.
- IPC-D-279 / Engelmaier fatigue model:
  Board-level solder joint strain range driven by CTE mismatch between package
  (substrate or leadframe) and PCB, acting over the component's distance from the
  board neutral point (DNP):
      Δε_t = F · (Δα · ΔT · L_DNP) / (2 · h_j)      (total shear strain range)
      N_f(63.5%) = 0.5 · (Δε_t / (2 · ε'_f))^(1/c)
      c = -0.442 - 6·10⁻⁴·T̄_sj + 1.74·10⁻²·ln(1 + t_d/60)
  where ε'_f = 0.625 (fatigue ductility coefficient), T̄_sj is the cyclic mean joint
  temperature, and t_d the hot dwell in minutes — the creep-aware cycle exponent that
  makes long hot dwells (automotive under-hood) far more damaging than fast lab cycles.
- IPC-SM-785 / J-STD-001: BGA/LGA packages with large DNP and low standoff are the
  classic victims; 0.3 mm DNP-per-millimeter rule of thumb for strain accumulation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# Standard IPC-9701 test condition bands
IPC9701_CONDITIONS: dict[str, tuple[float, float]] = {
    "TC1": (0.0, 100.0),
    "TC2": (-25.0, 125.0),
    "TC3": (-40.0, 125.0),
    "TC4": (-55.0, 125.0),
}

# CTE reference values (ppm/K) below Tg
CTE_TABLE: dict[str, float] = {
    "fr4_pcb": 15.0,        # FR-4 in-plane below Tg
    "bt_substrate": 14.0,   # BGA BT laminate substrate
    "fr4_substrate": 15.0,  # plastic BGA on FR-4 substrate
    "cu_leadframe": 16.5,   # copper leadframe (QFP/SOP)
    "ceramic": 6.5,         # alumina ceramic package (CLCC/CQFP)
    "leadless_lga": 10.0,   # molded LGA (≈Si-filled)
}


@dataclass
class ThermalFatigueResult:
    """Engelmaier/IPC-9701 fatigue life estimate for one critical component."""

    condition: str
    temp_min_c: float
    temp_max_c: float
    delta_t_c: float
    mean_joint_temp_c: float
    hot_dwell_min: float
    component: str
    dnp_mm: float
    joint_height_mm: float
    strain_range: float
    cycle_exponent_c: float
    cycles_to_failure_ntf: float
    required_cycles: float
    meets_requirement: bool
    derating_note: str
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "temp_min_c": self.temp_min_c,
            "temp_max_c": self.temp_max_c,
            "delta_t_c": self.delta_t_c,
            "mean_joint_temp_c": self.mean_joint_temp_c,
            "hot_dwell_min": self.hot_dwell_min,
            "component": self.component,
            "dnp_mm": self.dnp_mm,
            "joint_height_mm": self.joint_height_mm,
            "strain_range": round(self.strain_range, 6),
            "cycle_exponent_c": round(self.cycle_exponent_c, 4),
            "cycles_to_failure_ntf": round(self.cycles_to_failure_ntf, 0),
            "required_cycles": self.required_cycles,
            "meets_requirement": self.meets_requirement,
            "derating_note": self.derating_note,
            "standards_cited": self.standards_cited,
        }


def estimate_solder_joint_thermal_fatigue(
    component: str = "U1_BGA256",
    dnp_mm: float = 15.0,
    joint_height_mm: float = 0.10,
    condition: str = "TC3",
    temp_min_c: float | None = None,
    temp_max_c: float | None = None,
    hot_dwell_min: float = 10.0,
    pcb_cte_ppm: float = 15.0,
    package_cte_ppm: float = 14.0,
    compliance_factor_f: float = 0.5,
    required_cycles: float = 3000.0,
) -> ThermalFatigueResult:
    """Estimate thermal-cycling solder joint life with the Engelmaier (IPC-9701) model.

    Args:
        component: Ref/designation of the worst-case component (for the report).
        dnp_mm: Distance from board neutral point to the farthest solder joint (mm).
        joint_height_mm: Solder joint standoff height (mm); BGA balls ~0.10-0.45, QFN ~0.05.
        condition: IPC-9701 profile key ('TC1'..'TC4') used when explicit temps omitted.
        temp_min_c: Explicit cycle minimum (°C); overrides the condition preset.
        temp_max_c: Explicit cycle maximum (°C); overrides the condition preset.
        hot_dwell_min: Hot dwell time per cycle in minutes (creep exponent input).
        pcb_cte_ppm: PCB in-plane CTE (ppm/K), FR-4 ≈ 15.
        package_cte_ppm: Package substrate/leadframe CTE (ppm/K).
        compliance_factor_f: Diagonal-FF joint compliance factor (0.5 typical, 1.0 stiff).
        required_cycles: Service requirement (cycles) the attachment must survive.

    Returns:
        ThermalFatigueResult: Strain range, cycle exponent, Nf, and pass/fail verdict.
    """
    lo, hi = IPC9701_CONDITIONS.get(condition.upper(), IPC9701_CONDITIONS["TC3"])
    t_min = lo if temp_min_c is None else float(temp_min_c)
    t_max = hi if temp_max_c is None else float(temp_max_c)
    delta_t = max(1.0, t_max - t_min)
    mean_joint = (t_min + t_max) / 2.0

    # Total shear strain range (board-level Engelmaier form).
    d_alpha = abs(pcb_cte_ppm - package_cte_ppm) * 1e-6  # 1/K
    # Δα·ΔT·L over joint height, halved (2 joints share), compliance F applied.
    strain = compliance_factor_f * (d_alpha * delta_t * dnp_mm) / (2.0 * max(0.02, joint_height_mm))

    # Cycle exponent c — dwell-time and mean-temperature dependent (creep).
    # Both higher mean joint temperature and longer hot dwell aggravate creep
    # strain, deepening the exponent (more negative c ⇒ fewer cycles to fail).
    exponent_c = -0.442 - 6.0e-4 * mean_joint - 1.74e-2 * math.log1p(max(0.0, hot_dwell_min) / 60.0)

    # Engelmaier Weibull characteristic life at 63.5% failure.
    eps_f = 0.625
    ratio = strain / (2.0 * eps_f)
    if ratio <= 0:
        n_f = float("inf")
    else:
        n_f = 0.5 * ratio ** (1.0 / exponent_c)

    meets = n_f >= required_cycles

    if not meets:
        note = (
            f"预测寿命 {n_f:,.0f} 循环 < 要求 {required_cycles:,.0f}。降低 ΔT（散热/布局远离热源）、"
            "缩短 DNP（旋转器件让对角贴近板中心）、或改用高_standoff 可延寿；"
            "陶瓷封装对 FR-4 的 Δα≈8.5ppm/K 尤其危险，考虑欠填充 (underfill)。"
        )
    elif n_f < required_cycles * 1.5:
        note = "裕量不足 1.5 倍，量产批次建议按 IPC-9701 加测温度循环板级验证。"
    else:
        note = "疲劳寿命满足要求，按 IPC-9701 抽样验证即可。"

    cited = [
        "IPC-9701A Performance Test Methods for Surface Mount Solder Attachments",
        "IPC-D-279 Design Guidelines for Reliable Surface Mount Technology",
        "Engelmaier, W., Fatigue Life and Life Prediction of Solder Joints, IPC-TP-797",
    ]

    return ThermalFatigueResult(
        condition=condition.upper(),
        temp_min_c=t_min,
        temp_max_c=t_max,
        delta_t_c=delta_t,
        mean_joint_temp_c=mean_joint,
        hot_dwell_min=hot_dwell_min,
        component=component,
        dnp_mm=dnp_mm,
        joint_height_mm=joint_height_mm,
        strain_range=strain,
        cycle_exponent_c=exponent_c,
        cycles_to_failure_ntf=n_f,
        required_cycles=required_cycles,
        meets_requirement=meets,
        derating_note=note,
        standards_cited=cited,
    )
