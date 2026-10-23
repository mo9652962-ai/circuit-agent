"""IPC-4552A / IPC-4556 ENIG & ENEPIG Plating Thickness and Black-Pad Risk Analyzer.

Industrial & Authoritative Standards:
- IPC-4552A (Performance Specification for Electroless Nickel / Immersion Gold (ENIG) Plating):
  Qualification requirements for the workhorse chemical finish:
    * Immersion gold: 0.05 ~ 0.20 μm (2 ~ 8 μin) — thin enough to be fully soluble in solder,
      thick enough to protect the nickel during shelf storage.
    * Electroless nickel (phosphorus content 7 ~ 10 wt% P): 3.0 ~ 6.0 μm (120 ~ 240 μin).
  Gold above ~0.25 μm embrittles solder joints (AuSn₄ intermetallics) and wastes cost;
  nickel below 3 μm cannot reliably barrier copper diffusion and fails nickel-corrosion margin.
- IPC-4556 (Specification for Electroless Nickel / Electroless Palladium / Immersion Gold (ENEPIG)):
  Adds a palladium barrier layer 0.10 ~ 0.30 μm between nickel and gold, which eliminates the
  classic "black pad" galvanic hyper-corrosion mechanism of bare ENIG.
- Black Pad (Interfacial Nickel Corrosion) Failure Mechanism:
  During the immersion-gold bath, the galvanic exchange reaction attacks the high-phosphorus grain
  boundaries of the nickel, leaving a non-wettable, cracked Ni(Ox) rich mud-crack surface. Solder
  joints then fail at the pad interface with characteristic brittle fracture and dark appearance
  (IPC-A-610 / IPC-9701 refers to it as a classic intermittent field-failure root cause). Process
  indicators: phosphorus > 11 wt%, gold deposition rate anomalies, bath over-activity, and
  multiple rework cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FINISH_SPECS: dict[str, dict[str, Any]] = {
    "enig": {
        "name": "ENIG (Electroless Nickel / Immersion Gold)",
        "gold_min_um": 0.05,
        "gold_max_um": 0.20,
        "gold_embrittlement_um": 0.25,
        "nickel_min_um": 3.0,
        "nickel_max_um": 6.0,
        "phosphorus_min_pct": 7.0,
        "phosphorus_max_pct": 10.0,
        "palladium_supported": False,
    },
    "enepig": {
        "name": "ENEPIG (Electroless Nickel / Electroless Palladium / Immersion Gold)",
        "gold_min_um": 0.05,
        "gold_max_um": 0.20,
        "gold_embrittlement_um": 0.25,
        "nickel_min_um": 3.0,
        "nickel_max_um": 6.0,
        "phosphorus_min_pct": 7.0,
        "phosphorus_max_pct": 10.0,
        "palladium_supported": True,
        "palladium_min_um": 0.10,
        "palladium_max_um": 0.30,
    },
}


@dataclass
class PlatingViolation:
    """One out-of-spec layer measurement."""

    layer: str
    measured: float
    limit_min: float | None
    limit_max: float | None
    failure_mode: str


@dataclass
class EnigPlatingResult:
    """Layer-stack plating compliance and black-pad susceptibility verdict."""

    finish_type: str
    gold_thickness_um: float
    nickel_thickness_um: float
    phosphorus_wt_pct: float
    gold_embrittlement_risk: bool
    black_pad_risk: str  # 'low' | 'elevated' | 'high'
    wire_bondable: bool
    summary: str
    palladium_thickness_um: float | None = None
    violations: list[PlatingViolation] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finish_type": self.finish_type,
            "gold_thickness_um": round(self.gold_thickness_um, 3),
            "nickel_thickness_um": round(self.nickel_thickness_um, 3),
            "phosphorus_wt_pct": round(self.phosphorus_wt_pct, 2),
            "palladium_thickness_um": (
                round(self.palladium_thickness_um, 3) if self.palladium_thickness_um is not None else None
            ),
            "violations": [
                {
                    "layer": v.layer,
                    "measured": round(v.measured, 3),
                    "limit_min_um": v.limit_min,
                    "limit_max_um": v.limit_max,
                    "failure_mode": v.failure_mode,
                }
                for v in self.violations
            ],
            "gold_embrittlement_risk": self.gold_embrittlement_risk,
            "black_pad_risk": self.black_pad_risk,
            "wire_bondable": self.wire_bondable,
            "summary": self.summary,
            "standards_cited": self.standards_cited,
        }


def analyze_enig_plating(
    finish_type: str = "enig",
    gold_thickness_um: float = 0.08,
    nickel_thickness_um: float = 4.0,
    phosphorus_wt_pct: float = 8.5,
    palladium_thickness_um: float | None = None,
    rework_cycles: int = 0,
    soldering_process: str = "reflow",
) -> EnigPlatingResult:
    """Audit ENIG/ENEPIG layer thicknesses and phosphorus content for black-pad and gold-embrittlement risk.

    Args:
        finish_type: 'enig' (default) or 'enepig'.
        gold_thickness_um: Measured immersion-gold thickness in μm (XRF).
        nickel_thickness_um: Measured electroless-nickel thickness in μm (XRF, cumulative for ENEPIG).
        phosphorus_wt_pct: Nickel deposit phosphorus content in wt% (bath analysis).
        palladium_thickness_um: Measured palladium barrier thickness in μm (ENEPIG only).
        rework_cycles: Number of prior soldering/rework thermal excursions the pad has seen.
        soldering_process: 'reflow', 'wave', or 'hand' — hand soldering exaggerates interface damage.

    Returns:
        EnigPlatingResult: Layer violations, embrittlement flag, black-pad risk, and advice.
    """
    f_key = "enepig" if "epig" in finish_type.lower() or "palladium" in finish_type.lower() else "enig"
    spec = FINISH_SPECS[f_key]

    violations: list[PlatingViolation] = []

    if gold_thickness_um < spec["gold_min_um"]:
        violations.append(
            PlatingViolation("gold", gold_thickness_um, spec["gold_min_um"], None,
                             "Nickel oxidizes during shelf storage; porosity and poor wetting risk.")
        )
    elif gold_thickness_um > spec["gold_max_um"]:
        violations.append(
            PlatingViolation("gold", gold_thickness_um, None, spec["gold_max_um"],
                             "Excess immersion gold indicates an over-active bath and galvanic over-attack on nickel.")
        )

    if nickel_thickness_um < spec["nickel_min_um"]:
        violations.append(
            PlatingViolation("nickel", nickel_thickness_um, spec["nickel_min_um"], None,
                             "Sub-3μm nickel cannot barrier copper diffusion; Cu₃Sn growth weakens joints.")
        )
    elif nickel_thickness_um > spec["nickel_max_um"]:
        violations.append(
            PlatingViolation("nickel", nickel_thickness_um, None, spec["nickel_max_um"],
                             "Thick nickel adds planarity stress and cost without reliability benefit.")
        )

    if phosphorus_wt_pct > spec["phosphorus_max_pct"]:
        violations.append(
            PlatingViolation("phosphorus", phosphorus_wt_pct, None, spec["phosphorus_max_pct"],
                             "High-P (>10-11 wt%) deposits are hard, brittle, and slow to wet; correlated with black pad.")
        )
    elif phosphorus_wt_pct < spec["phosphorus_min_pct"]:
        violations.append(
            PlatingViolation("phosphorus", phosphorus_wt_pct, spec["phosphorus_min_pct"], None,
                             "Low-P nickel is corrosion-prone in the immersion-gold bath (galvanic attack).")
        )

    if spec["palladium_supported"]:
        p_min = spec["palladium_min_um"]
        p_max = spec["palladium_max_um"]
        if palladium_thickness_um is None:
            violations.append(
                PlatingViolation("palladium", 0.0, p_min, p_max,
                                 "ENEPIG declared but no palladium layer measured — finish is effectively bare ENIG.")
            )
        elif palladium_thickness_um < p_min:
            violations.append(
                PlatingViolation("palladium", palladium_thickness_um, p_min, None,
                                 "Palladium below 0.10 μm cannot fully isolate nickel from the gold bath.")
            )
        elif palladium_thickness_um > p_max:
            violations.append(
                PlatingViolation("palladium", palladium_thickness_um, None, p_max,
                                 "Excess palladium wastes cost and can slow wetting spread.")
            )

    gold_embrittlement = gold_thickness_um > spec["gold_embrittlement_um"]

    # Black-pad scoring: bare ENIG + high P + thick gold + rework/aggressive process escalates.
    score = 0.0
    if f_key == "enig":
        score += 1.0  # ENIG inherently carries the galvanic mechanism
    if phosphorus_wt_pct >= 11.0:
        score += 1.0
    if gold_thickness_um > spec["gold_max_um"]:
        score += 0.8
    if rework_cycles >= 2:
        score += 0.6
    if soldering_process in ("wave", "hand"):
        score += 0.3

    if f_key == "enepig" and palladium_thickness_um is not None and palladium_thickness_um >= 0.10:
        score = max(0.0, score - 0.9)  # Pd barrier suppresses the mechanism

    if score >= 2.2:
        risk = "high"
    elif score >= 1.5:
        risk = "elevated"
    else:
        risk = "low"

    if risk == "high":
        summary = (
            "High black-pad susceptibility: brittle interfacial fracture is a credible field-failure mode. "
            "X-ray the pad fracture surface, audit the gold-bath activity, and qualify ENEPIG or OSP+silver alternatives."
        )
    elif risk == "elevated":
        summary = (
            "Elevated nickel-corrosion indicators present; add wetting-balance (IPC-TM-650 2.4.14) sampling "
            "and solder-grid-dip acceptance on incoming lots before release."
        )
    elif violations:
        summary = "Plating stack is out of IPC-4552A/4556 window; corrective action at the plating line required."
    else:
        summary = "Plating layers within specification; black-pad mechanism well controlled."

    cited = [
        "IPC-4552A Performance Specification for Electroless Nickel/Immersion Gold (ENIG) Plating",
        "IPC-4556 Specification for Electroless Nickel/Electroless Palladium/Immersion Gold (ENEPIG)",
        "IPC-A-610G Acceptability of Electronic Assemblies (surface finish conditions)",
    ]

    return EnigPlatingResult(
        finish_type=spec["name"],
        gold_thickness_um=gold_thickness_um,
        nickel_thickness_um=nickel_thickness_um,
        phosphorus_wt_pct=phosphorus_wt_pct,
        gold_embrittlement_risk=gold_embrittlement,
        black_pad_risk=risk,
        wire_bondable=(f_key == "enepig" and palladium_thickness_um is not None),
        summary=summary,
        palladium_thickness_um=palladium_thickness_um if f_key == "enepig" else None,
        violations=violations,
        standards_cited=cited,
    )
