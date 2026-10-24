"""IPC-CC-830C / IPC-A-610 §10 Conformal Coating Selection & Masking Keepout Planner.

Industrial & Authoritative Standards:
- IPC-CC-830C (Qualification and Performance of Electrical Insulating Compound
  (Conformal Coating) for Printed Board Assemblies):
  Qualifies the four material families plus parylene. Types and IPC-A-610G §10
  thickness windows (measured on masked witness coupons):
    * Type AR (Acrylic):     30 ~ 130 μm — easy rework (solvent strip), moderate moisture
    * Type ER (Epoxy):       30 ~ 130 μm — chemical/moisture armor, very hard rework
    * Type UR (Urethane):    30 ~ 130 μm — abrasion & chemical resistance, hard rework
    * Type SR (Silicone):    50 ~ 210 μm — widest temp range, CTE stress relief, VW-1
    * Type XY (Parylene):    10 ~  50 μm — CVD vapor deposition, pinhole-free,
      finest build; effectively impossible to rework, needs masking BEFORE deposition
- IPC-A-610G §10.4 Keep-out (masking) requirements:
  Coating must NOT cover: connector contacts, switch actuators, test points,
  programming/debug headers, adjustable inductors/pots, LEDs (unless optically clear
  verified), fans/heatsink interfaces, RF shields, mounting hardware, and any
  designated rework site. Coating ingress into sockets creates intermittent contact
  failures that pass ICT and fail in the field — masking keepouts must be declared
  before selective-coating program generation.
- IPC-WP-825 / UL 746E: flame, fungal, and dielectric-withstand context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

COATING_TYPES: dict[str, dict[str, Any]] = {
    "AR": {"name": "Acrylic (Type AR)", "min_um": 30.0, "max_um": 130.0,
           "rework": "easy", "moisture": "moderate", "note": "溶剂可剥离，返修友好"},
    "ER": {"name": "Epoxy (Type ER)", "min_um": 30.0, "max_um": 130.0,
           "rework": "very_hard", "moisture": "excellent",
           "note": "化学品/湿气防护最强，返修近似不可行"},
    "UR": {"name": "Urethane (Type UR)", "min_um": 30.0, "max_um": 130.0,
           "rework": "hard", "moisture": "excellent", "note": "耐磨耐化学，返修难"},
    "SR": {"name": "Silicone (Type SR)", "min_um": 50.0, "max_um": 210.0,
           "rework": "moderate", "moisture": "good",
           "note": "宽温域与 CTE 缓冲，高湿高振车规模组首选"},
    "XY": {"name": "Parylene (Type XY)", "min_um": 10.0, "max_um": 50.0,
           "rework": "impossible", "moisture": "excellent",
           "note": "CVD 气相沉积无针孔均匀涂覆，涂前必须完成全部掩膜"},
}

# Component kinds that must be masked off before coating
MASK_REQUIRED_KINDS = {
    "CONNECTOR", "HEADER", "SOCKET", "SWITCH", "TESTPOINT", "FIDUCIAL",
    "POTENTIOMETER", "INDICATOR", "FAN", "SENSOR_OPEN", "REWORK_SITE",
}


@dataclass
class CoatingPlanResult:
    """Coating material verdict, thickness compliance, and masking keepout list."""

    coating_type: str
    coating_type_name: str
    measured_thickness_um: float
    min_um: float
    max_um: float
    is_thickness_compliant: bool
    rework_level: str
    reworkability_conflict: bool
    summary: str
    mask_keepouts: list[dict[str, Any]] = field(default_factory=list)
    unmasked_contact_risk: list[dict[str, Any]] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "coating_type": self.coating_type,
            "coating_type_name": self.coating_type_name,
            "measured_thickness_um": round(self.measured_thickness_um, 1),
            "thickness_window_um": [self.min_um, self.max_um],
            "is_thickness_compliant": self.is_thickness_compliant,
            "rework_level": self.rework_level,
            "reworkability_conflict": self.reworkability_conflict,
            "mask_keepouts": self.mask_keepouts,
            "unmasked_contact_risk": self.unmasked_contact_risk,
            "summary": self.summary,
            "standards_cited": self.standards_cited,
        }


def plan_conformal_coating(
    coating_type: str = "AR",
    measured_thickness_um: float = 75.0,
    modules: dict[str, dict[str, Any]] | None = None,
    requires_field_rework: bool = False,
) -> CoatingPlanResult:
    """Validate coating thickness/type selection and enumerate masking keepouts per IPC-CC-830C.

    Args:
        coating_type: One of 'AR', 'ER', 'UR', 'SR', 'XY'.
        measured_thickness_um: Witness-coupon measured dry film thickness (μm).
        modules: Optional BOM modules ({ref: {kind, package}}) — connectors/switches/test
            points found here become masking keepouts; anything mask-required but
            un-flagged surfaces as contact-contamination risk.
        requires_field_rework: True when the product must be repairable in service.

    Returns:
        CoatingPlanResult: Thickness verdict, reworkability conflict, and keepout plan.
    """
    key = coating_type.upper().strip()
    spec = COATING_TYPES.get(key, COATING_TYPES["AR"])

    thickness_ok = spec["min_um"] <= measured_thickness_um <= spec["max_um"]

    keepouts: list[dict[str, Any]] = []
    risk: list[dict[str, Any]] = []
    if modules:
        for ref, m in modules.items():
            if ref == "__meta__":
                continue
            kind = str(m.get("kind", "")).upper()
            pkg = str(m.get("package", ""))
            maskable = any(k in kind for k in MASK_REQUIRED_KINDS) or (
                "TESTPOINT" in ref.upper().split("_")[0] or ref.upper().startswith("TP_")
            )
            if not maskable:
                continue
            entry = {"ref": ref, "kind": kind or "TESTPOINT", "package": pkg,
                     "action": "mask_before_coating"}
            keepouts.append(entry)
            # A mask-required part the caller flagged as intentionally NOT masked
            # is a contact-failure in waiting.
            if bool(m.get("coating_exempt", False)) and not bool(m.get("mask_verified", False)):
                risk.append({"ref": ref,
                             "issue": "声明免涂但未做掩膜验证——涂层渗入触点将产生间歇性接触故障"})
        if not keepouts and any(r for r in modules if r != "__meta__"):
            # No explicit contact parts: witness notes still enforce testpoint rule.
            for ref in modules:
                if ref != "__meta__" and ref.upper().startswith(("TP_", "FID")):
                    keepouts.append({"ref": ref, "kind": "TESTPOINT" if ref.startswith("TP_") else "FIDUCIAL",
                                     "package": "", "action": "mask_before_coating"})

    rework_conflict = requires_field_rework and spec["rework"] in ("hard", "very_hard", "impossible")

    parts = []
    if not thickness_ok:
        side = "低于下限" if measured_thickness_um < spec["min_um"] else "超过上限"
        parts.append(
            f"膜厚 {measured_thickness_um:.0f}μm {side} {spec['name']} 窗口 "
            f"({spec['min_um']:.0f}~{spec['max_um']:.0f}μm, IPC-A-610 §10.3)"
        )
    if rework_conflict:
        parts.append(
            f"{spec['name']} 返修等级为 {spec['rework']}，与现场返修需求冲突——改选 Type AR 或局部可剥掩膜方案"
        )
    if risk:
        parts.append(f"{len(risk)} 处触点器件免涂未验证，存在涂层渗入接触失效风险")
    if not parts:
        parts.append(
            f"{spec['name']} 膜厚合规，需掩膜 {len(keepouts)} 处触点器件"
            + ("" if keepouts else "（BOM 未检出连接器/测试点，请人工复核）")
        )
    summary = "；".join(parts) + "。"

    cited = [
        "IPC-CC-830C Qualification and Performance of Electrical Insulating Compound (Conformal Coating)",
        "IPC-A-610G §10.3-§10.4 Coating Thickness & Keep-out Requirements",
        "IPC-WP-825 Conformal Coating Selection Guidelines",
    ]

    return CoatingPlanResult(
        coating_type=key,
        coating_type_name=spec["name"],
        measured_thickness_um=measured_thickness_um,
        min_um=spec["min_um"],
        max_um=spec["max_um"],
        is_thickness_compliant=thickness_ok,
        rework_level=spec["rework"],
        reworkability_conflict=rework_conflict,
        mask_keepouts=keepouts,
        unmasked_contact_risk=risk,
        summary=summary,
        standards_cited=cited,
    )
