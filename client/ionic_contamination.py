"""IPC-CH-65 / IPC-TM-650 Ionic Contamination (ROSE Test) & Cleanliness Compliance Analyzer.

Industrial & Authoritative Standards:
- IPC-CH-65 (Guidelines for Cleaning of Printed Boards and Assemblies):
  Defines cleanliness categories and ionic contamination acceptance for electronic assemblies.
  Residual flux activators (halides, organic acids), plating chemistry residues, and handling salts
  dissolve in ambient humidity forming localized galvanic cells that grow conductive anodic filaments (CAF)
  and dendrites between biased conductors, causing field leakage failures months after assembly.
- IPC-TM-650 2.3.25 (Solvent Extract Resistivity / ROSE Test):
  The classic Resistivity of Solvent Extract test measures bulk ionic contamination as NaCl-equivalent
  loading per unit area. Historically the industry acceptance limit is 1.56 μg/cm² (10.06 μg/in²)
  NaCl equivalence for assemblies; tighter internal limits (0.8~1.2 μg/cm²) are common for Class 3
  high-reliability and high-voltage products.
- IPC-TM-650 2.3.28 (Ion Chromatography):
  Separates and quantifies individual ionic species (Cl⁻, Br⁻, F⁻, NO₃⁻, SO₄²⁻, WOA - weak organic acids).
  Per J-STD-001 / IPC: chloride limit 0.70 μg/cm², bromide 0.54 μg/cm² (as indicators of activated
  flux residue carryover). ROSE gives only a single bulk number; IC identifies the actual culprit species.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# NaCl-equivalent bulk limits (μg/cm²) by reliability class
CLASS_ROSE_LIMITS: dict[str, float] = {
    "Class 1": 1.56,   # historical industry standard limit
    "Class 2": 1.56,   # standard assembly workmanship
    "Class 3": 1.20,   # tightened internal limit common for high-rel / HV boards
}

# Individual species limits from ion chromatography (IPC-TM-650 2.3.28), μg/cm²
SPECIES_LIMITS: dict[str, float] = {
    "chloride": 0.70,
    "bromide": 0.54,
    "fluoride": 0.50,
    "nitrate": 0.50,
    "sulfate": 0.50,
    "weak_organic_acid": 5.00,
}


@dataclass
class IonicContaminationResult:
    """ROSE test / ion chromatography evaluation for one board or process lot."""

    target_class: str
    board_area_cm2: float
    rose_measured_ug_cm2: float
    rose_limit_ug_cm2: float
    is_rose_compliant: bool
    dendrite_risk_level: str  # 'low' | 'moderate' | 'high'
    cleaning_recommendation: str
    species_ug_cm2: dict[str, float] = field(default_factory=dict)
    species_violations: list[tuple[str, float]] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_class": self.target_class,
            "board_area_cm2": round(self.board_area_cm2, 2),
            "rose_measured_ug_cm2": round(self.rose_measured_ug_cm2, 3),
            "rose_limit_ug_cm2": self.rose_limit_ug_cm2,
            "is_rose_compliant": self.is_rose_compliant,
            "species_ug_cm2": {k: round(v, 3) for k, v in self.species_ug_cm2.items()},
            "species_violations": [
                {"species": k, "measured": round(v, 3), "limit": SPECIES_LIMITS[k]}
                for k, v in self.species_violations
            ],
            "dendrite_risk_level": self.dendrite_risk_level,
            "cleaning_recommendation": self.cleaning_recommendation,
            "standards_cited": self.standards_cited,
        }


def analyze_ionic_contamination(
    board_area_cm2: float = 100.0,
    rose_measured_ug_cm2: float = 0.80,
    target_class: str = "Class 2",
    species_ug_cm2: dict[str, float] | None = None,
    bias_voltage_v: float = 5.0,
    min_conductor_gap_mm: float = 0.20,
) -> IonicContaminationResult:
    """Evaluate ROSE bulk ionic contamination and per-species ion chromatography results.

    Args:
        board_area_cm2: Total board surface area processed through the extraction (cm²).
        rose_measured_ug_cm2: Measured NaCl-equivalent loading from the ROSE tester (μg/cm²).
        target_class: IPC reliability class ('Class 1', 'Class 2', or 'Class 3').
        species_ug_cm2: Optional per-species ion chromatography results in μg/cm²
            (keys: chloride, bromide, fluoride, nitrate, sulfate, weak_organic_acid).
        bias_voltage_v: Largest sustained DC bias between adjacent conductors (drives dendrite risk).
        min_conductor_gap_mm: Smallest biased conductor spacing (mm) — tighter gaps lower the
            contamination level at which dendrite growth becomes credible.

    Returns:
        IonicContaminationResult: ROSE compliance, species violations, and dendrite risk verdict.
    """
    cls_key = "Class 3" if "3" in str(target_class) else ("Class 1" if "1" in str(target_class) else "Class 2")
    rose_limit = CLASS_ROSE_LIMITS[cls_key]
    is_compliant = rose_measured_ug_cm2 <= rose_limit

    species = {k: float(v) for k, v in (species_ug_cm2 or {}).items() if k in SPECIES_LIMITS}
    violations: list[tuple[str, float]] = []
    for name, val in species.items():
        if val > SPECIES_LIMITS[name]:
            violations.append((name, val))

    # Dendrite/CAF risk scoring: contamination ratio x electrochemical aggressiveness.
    # High bias and fine gaps multiply the harm of a given residue level.
    ratio = rose_measured_ug_cm2 / rose_limit
    electro = 1.0
    if bias_voltage_v >= 48.0:
        electro *= 1.6
    elif bias_voltage_v >= 12.0:
        electro *= 1.3
    if min_conductor_gap_mm <= 0.10:
        electro *= 1.5
    elif min_conductor_gap_mm <= 0.20:
        electro *= 1.2

    score = ratio * electro
    if score >= 1.0 or violations:
        risk = "high"
    elif score >= 0.75:
        risk = "moderate"
    else:
        risk = "low"

    if not is_compliant:
        rec = (
            f"ROSE result {rose_measured_ug_cm2:.2f} μg/cm² exceeds the {cls_key} limit {rose_limit:.2f} μg/cm². "
            "Re-clean in an aqueous/saponifier wash, verify no-clean flux is fully heat-activated, and re-test; "
            "run ion chromatography (IPC-TM-650 2.3.28) to identify the culprit species."
        )
    elif violations:
        worst = max(violations, key=lambda kv: kv[1] / SPECIES_LIMITS[kv[0]])
        rec = (
            f"Bulk ROSE passes but ion chromatography flags {worst[0]} at {worst[1]:.2f} μg/cm² "
            f"(limit {SPECIES_LIMITS[worst[0]]:.2f}). Target the specific residue source: unactivated flux "
            "for halides, plating drag-out for sulfate/fluoride."
        )
    elif risk != "low":
        rec = (
            "Bulk cleanliness passes, but high bias combined with fine conductor pitch keeps dendrite "
            "risk non-negligible; verify conformal coat coverage or tighten the internal process limit."
        )
    else:
        rec = "Cleanliness compliant for bulk ROSE and species limits; maintain current cleaning process."

    cited = [
        "IPC-CH-65 Guidelines for Cleaning of Printed Boards and Assemblies",
        "IPC-TM-650 2.3.25 Resistivity of Solvent Extract (ROSE) Test",
        "IPC-TM-650 2.3.28 Ionic Analysis of Circuit Boards, Ion Chromatography Method",
    ]

    return IonicContaminationResult(
        target_class=cls_key,
        board_area_cm2=max(1.0, board_area_cm2),
        rose_measured_ug_cm2=rose_measured_ug_cm2,
        rose_limit_ug_cm2=rose_limit,
        is_rose_compliant=is_compliant,
        dendrite_risk_level=risk,
        cleaning_recommendation=rec,
        species_ug_cm2=species,
        species_violations=violations,
        standards_cited=cited,
    )
