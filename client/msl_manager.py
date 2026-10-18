"""JEDEC J-STD-033D & IPC-M-109 SMD Moisture Sensitivity Level (MSL) & Floor Life Manager.

Industrial & Authoritative Standards:
- JEDEC J-STD-033D (Handling, Packing, Shipping and Use of Moisture, Reflow, and Process Sensitive Devices):
  SMD plastic packages (BGAs, QFNs, TQFPs, and CSPs) absorb ambient atmospheric moisture through plastic
  molding compounds. When subjected to the high temperature profile of lead-free convection reflow (255°C~265°C),
  trapped moisture instantly vaporizes, generating explosive steam pressures (>3.0 MPa) causing package cracking,
  internal delamination, and bonding wire lift-off ("popcorn" effect).
- Standard JEDEC MSL Classification Table:
    * Level 1: Unlimited floor life (at <= 30°C / 85% RH)
    * Level 2: 1 Year (at <= 30°C / 60% RH)
    * Level 2a: 4 Weeks (at <= 30°C / 60% RH)
    * Level 3: 168 Hours / 7 Days (at <= 30°C / 60% RH)
    * Level 4: 72 Hours / 3 Days (at <= 30°C / 60% RH)
    * Level 5: 48 Hours / 2 Days (at <= 30°C / 60% RH)
    * Level 5a: 24 Hours / 1 Day (at <= 30°C / 60% RH)
    * Level 6: Mandatory bake before use (mandatory reflow within strict time window)
- Standard Bake Options (J-STD-033D Table 4-1):
    * High-temp bake: 125°C for 24~48 hours (high-temperature carrier tape or metal trays)
    * Intermediate bake: 90°C (<= 5% RH) for 48~96 hours
    * Low-temp bake: 40°C (<= 5% RH desiccant chamber) for 192~288 hours (prevents tape melting)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Standard Floor Life Hours at <= 30°C / 60% RH
MSL_FLOOR_LIFE_HOURS: dict[str, float] = {
    "Level 1": float("inf"),
    "Level 2": 8760.0,  # 1 year = 365 * 24
    "Level 2a": 672.0,  # 4 weeks = 28 * 24
    "Level 3": 168.0,  # 7 days
    "Level 4": 72.0,  # 3 days
    "Level 5": 48.0,  # 2 days
    "Level 5a": 24.0,  # 1 day
    "Level 6": 6.0,  # Must be baked, reflow within 6 hours
}

# Standard Packages Default MSL Mapping if unstated
PACKAGE_DEFAULT_MSL: dict[str, str] = {
    "BGA": "Level 3",
    "FBGA": "Level 3",
    "QFN": "Level 3",
    "WQFN": "Level 3",
    "TQFP": "Level 3",
    "LQFP": "Level 3",
    "CSP": "Level 4",
    "WLCSP": "Level 4",
    "SOP": "Level 2",
    "SOIC": "Level 2",
    "SOT": "Level 1",
    "0402": "Level 1",
    "0603": "Level 1",
    "0805": "Level 1",
}


@dataclass
class ComponentMSLStatus:
    """MSL evaluation status for a single BOM component."""

    ref_des: str
    part_number: str
    package: str
    msl_level: str
    max_floor_life_hours: float
    exposed_hours: float
    remaining_floor_life_hours: float
    is_expired: bool
    baking_required: bool
    recommended_baking_regime: str


@dataclass
class MSLAuditReport:
    """Comprehensive MSL floor life and moisture risk audit report."""

    total_components_checked: int
    moisture_sensitive_count: int
    expired_components_count: int
    is_assembly_safe: bool
    ambient_temp_c: float
    ambient_rh_pct: float
    components: list[ComponentMSLStatus] = field(default_factory=list)
    baking_action_items: list[dict[str, Any]] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_components_checked": self.total_components_checked,
            "moisture_sensitive_count": self.moisture_sensitive_count,
            "expired_components_count": self.expired_components_count,
            "is_assembly_safe": self.is_assembly_safe,
            "ambient_temp_c": round(self.ambient_temp_c, 1),
            "ambient_rh_pct": round(self.ambient_rh_pct, 1),
            "components": [asdict(c) for c in self.components],
            "baking_action_items": self.baking_action_items,
            "standards_cited": self.standards_cited,
        }


def audit_component_msl_floor_life(
    modules: dict[str, dict[str, Any]],
    exposed_hours_default: float = 48.0,
    ambient_temp_c: float = 25.0,
    ambient_rh_pct: float = 55.0,
) -> MSLAuditReport:
    """Audit SMD components for moisture sensitivity level (MSL) and remaining floor life per J-STD-033D.

    Args:
        modules: Component modules dict from synthesis or netlist ({refDes: {package, part_number, msl_level, exposed_hours}})
        exposed_hours_default: Default open-bag exposure time on shop floor if unstated (hours)
        ambient_temp_c: Factory ambient temperature in °C (standard <= 30°C)
        ambient_rh_pct: Factory relative humidity in % (standard <= 60% RH)

    Returns:
        MSLAuditReport: Status of all moisture sensitive components and required baking schedules
    """
    comp_statuses: list[ComponentMSLStatus] = []
    baking_items: list[dict[str, Any]] = []
    ms_count = 0
    expired_count = 0

    # Ambient humidity derating: If RH > 60%, floor life reduces significantly
    derating_factor = 1.0
    if ambient_rh_pct > 60.0:
        derating_factor = max(0.2, 1.0 - (ambient_rh_pct - 60.0) * 0.03)

    for ref, comp in modules.items():
        if ref == "__meta__":
            continue
        pkg = str(comp.get("package", comp.get("pkg", "0603"))).upper()
        pn = str(comp.get("part_number", comp.get("lcsc_part", ref)))

        # Determine MSL level
        msl = str(comp.get("msl_level", comp.get("msl", "")))
        if not msl:
            msl = _infer_msl_from_package(pkg)

        max_life = MSL_FLOOR_LIFE_HOURS.get(msl, float("inf")) * derating_factor
        exp_h = float(comp.get("exposed_hours", exposed_hours_default))

        if msl != "Level 1":
            ms_count += 1

        rem_h = max(0.0, max_life - exp_h) if max_life != float("inf") else float("inf")
        is_exp = (exp_h > max_life) or (msl == "Level 6")

        if is_exp:
            expired_count += 1
            bake_plan = _recommend_baking(msl, pkg)
            baking_items.append({
                "ref_des": ref,
                "part_number": pn,
                "package": pkg,
                "msl_level": msl,
                "exposed_hours": exp_h,
                "allowed_hours": round(max_life, 1),
                "baking_plan": bake_plan,
            })
        else:
            bake_plan = "None (Within safe floor life)"

        comp_statuses.append(
            ComponentMSLStatus(
                ref_des=ref,
                part_number=pn,
                package=pkg,
                msl_level=msl,
                max_floor_life_hours=round(max_life, 1) if max_life != float("inf") else 999999.0,
                exposed_hours=round(exp_h, 1),
                remaining_floor_life_hours=round(rem_h, 1) if rem_h != float("inf") else 999999.0,
                is_expired=is_exp,
                baking_required=is_exp,
                recommended_baking_regime=bake_plan,
            )
        )

    cited = [
        "JEDEC J-STD-033D Handling, Packing, Shipping and Use of Moisture Sensitive Devices",
        "IPC-M-109 Moisture-Sensitive Component Standards and Guideline Manual",
    ]

    return MSLAuditReport(
        total_components_checked=len(comp_statuses),
        moisture_sensitive_count=ms_count,
        expired_components_count=expired_count,
        is_assembly_safe=expired_count == 0,
        ambient_temp_c=ambient_temp_c,
        ambient_rh_pct=ambient_rh_pct,
        components=comp_statuses,
        baking_action_items=baking_items,
        standards_cited=cited,
    )


def _infer_msl_from_package(package: str) -> str:
    for k, lvl in PACKAGE_DEFAULT_MSL.items():
        if k in package:
            return lvl
    return "Level 1"


def _recommend_baking(msl: str, package: str) -> str:
    if "BGA" in package or "CSP" in package:
        return "125°C bake for 48 hours (high-temperature tray) or 40°C <= 5% RH for 192 hours"
    if msl in ("Level 4", "Level 5", "Level 5a", "Level 6"):
        return "125°C bake for 24 hours or 40°C <= 5% RH for 168 hours"
    return "125°C bake for 12 hours or 40°C <= 5% RH for 96 hours"
