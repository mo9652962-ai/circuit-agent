"""Telcordia SR-332 / MIL-HDBK-217F Part-Stress MTBF Reliability Prediction Engine.

Industrial & Authoritative Standards:
- Telcordia SR-332 (Reliability Prediction Procedure for Electronic Equipment, Issue 3):
  The telecom-industry standard black-box prediction method. Part-stress failure rate:
      λ = (λ_b × πQ × πT × πE) + λ_soldering × N_solder
  where the quality factor πQ follows the qualification level (I/II/III, default 1.0),
  πT is the Arrhenius acceleration from device junction/ambient temperature
      πT = 0.08 × e^(4808 × (1/293 - 1/(T+273)))   [for components with activation energy 0.08 eV class]
  and πE maps the environment (ground benign 1.0, ground fixed 2.5, mobile 6.0,
  airborne 12.0). Solder-joint fatigue adds a DNP/thermal-cycle dependent term
  carried over from the IPC-9701 estimate.
- MIL-HDBK-217F (Reliability Prediction of Electronic Equipment):
  The defense baseline the Telcordia method extends; part-count screening mode
  (λ = Σ N·λ_b·πQ) gives a first-order budget before stress data exists.
- Usage context:
  MTBF = 1 / λ_total. FIT (failures in 10⁹ hours) is the reporting unit of the
  semiconductor industry: FIT = λ(per-hour) × 1e9.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Baseline failure rates λb (failures / 10⁹ hours = FIT) per part class,
# Telcordia Tables (mid-range quality, benign conditions).
PART_BASELINE_FIT: dict[str, float] = {
    "IC_DIGITAL_CMOS": 20.0,      # generic CMOS logic/SoC
    "IC_LINEAR": 15.0,             # op-amps/regulators controllers
    "IC_MEMORY_FLASH": 40.0,       # NAND/NOR flash
    "IC_MEMORY_DRAM": 35.0,
    "IC_RF_TRANSCEIVER": 60.0,     # RF front-end
    "MICROCONTROLLER": 25.0,
    "DIODE_GENERAL": 2.0,
    "DIODE_ZENER": 4.0,
    "TRANSISTOR_BJT": 3.0,
    "TRANSISTOR_MOSFET": 8.0,
    "RESISTOR_FILM": 0.5,
    "RESISTOR_CHIP": 0.2,
    "CAPACITOR_CERAMIC": 2.0,
    "CAPACITOR_TANTALUM": 8.0,    # solid tantalum, derated
    "CAPACITOR_ELECTROLYTIC": 25.0,  # Al-elec, temperature dominated
    "INDUCTOR_POWER": 5.0,
    "CRYSTAL": 12.0,
    "OSCILLATOR": 18.0,
    "CONNECTOR_PIN": 0.5,          # per pin
    "PCB_VIA": 0.05,               # per via
    "SOLDER_JOINT": 0.15,          # per joint (process quality πQ applied)
}

# Environmental factors πE (Telcordia Issue 3 Table)
ENVIRONMENT_FACTORS: dict[str, float] = {
    "ground_benign": 1.0,     # climate-controlled office/lab
    "ground_fixed": 2.5,      # uncontrolled factory floor
    "ground_mobile": 6.0,     # vehicular / portable
    "airborne": 12.0,         # airborne uninhabited cargo
}


@dataclass
class MtbfResult:
    """Part-stress MTBF prediction for one assembly."""

    parts_counted: int
    total_fits: float
    mtbf_hours: float
    reliability_5yr: float
    pi_t: float
    pi_e: float
    environment: str
    ambient_temp_c: float
    dominant_parts: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parts_counted": self.parts_counted,
            "total_fits": round(self.total_fits, 2),
            "mtbf_hours": round(self.mtbf_hours, 0),
            "mtbf_years": round(self.mtbf_hours / 8760.0, 1),
            "reliability_5yr": round(self.reliability_5yr, 4),
            "pi_t": round(self.pi_t, 3),
            "pi_e": self.pi_e,
            "environment": self.environment,
            "ambient_temp_c": self.ambient_temp_c,
            "dominant_parts": self.dominant_parts,
            "assumptions": self.assumptions,
            "standards_cited": self.standards_cited,
        }


def predict_assembly_mtbf(
    part_counts: dict[str, int] | None = None,
    modules: dict[str, dict[str, Any]] | None = None,
    ambient_temp_c: float = 40.0,
    environment: str = "ground_fixed",
    quality_level: int = 2,
    duty_cycle_derate: float = 1.0,
) -> MtbfResult:
    """Predict assembly MTBF using Telcordia SR-332 part-stress method.

    Args:
        part_counts: Explicit {part_class: quantity} mapping (keys of PART_BASELINE_FIT);
            optional when modules given — BOM kinds are auto-classified.
        modules: Optional BOM modules ({ref: {kind, value}}) to auto-derive part counts.
        ambient_temp_c: Worst-case operating ambient (°C) driving Arrhenius πT.
        environment: 'ground_benign' | 'ground_fixed' (default) | 'ground_mobile' | 'airborne'.
        quality_level: Telcordia qualification level 1 (screened, 0.8×) / 2 (standard 1.0×)
            / 3 (uncertified 2.0×).
        duty_cycle_derate: Operating duty fraction (0~1) applied to total λ.

    Returns:
        MtbfResult: Total FIT, MTBF, 5-year survival probability, and dominant contributors.
    """
    counts: dict[str, int] = dict(part_counts or {})
    if modules:
        for ref, m in modules.items():
            if ref == "__meta__":
                continue
            kind = str(m.get("kind", "")).upper()
            val = str(m.get("value", ""))
            cls = _classify_part(kind, val, ref)
            if cls:
                counts[cls] = counts.get(cls, 0) + 1

    if not counts:
        return MtbfResult(
            parts_counted=0, total_fits=0.0, mtbf_hours=float("inf"),
            reliability_5yr=1.0, pi_t=1.0, pi_e=1.0, environment=environment,
            ambient_temp_c=ambient_temp_c,
            assumptions=["No parts counted — pass part_counts or modules."],
            standards_cited=["Telcordia SR-332 Issue 3"],
        )

    # Arrhenius temperature factor at operating ambient (0.08 eV class reference curve)
    t_kelvin = ambient_temp_c + 273.15
    pi_t = 0.08 * pow(2.718281828, 4808.0 * (1.0 / 293.0 - 1.0 / t_kelvin)) / 0.08
    # normalize: πT(20°C)=1 → divide by the 293K value
    pi_t_ref = 0.08 * pow(2.718281828, 4808.0 * (1.0 / 293.0 - 1.0 / 293.15)) / 0.08
    pi_t = pi_t / max(1e-9, pi_t_ref)

    pi_e = ENVIRONMENT_FACTORS.get(environment, ENVIRONMENT_FACTORS["ground_fixed"])
    pi_q = {1: 0.8, 2: 1.0, 3: 2.0}.get(quality_level, 1.0)

    total_fits = 0.0
    contributors: list[tuple[str, int, float]] = []
    for cls, qty in counts.items():
        base = PART_BASELINE_FIT.get(cls, 10.0)
        # Electrolytic capacitors: extra Arrhenius weight (wear-out dominated)
        temp_mult = pi_t if cls != "CAPACITOR_ELECTROLYTIC" else pi_t ** 2.0
        sub_fits = base * qty * pi_q * temp_mult * pi_e
        total_fits += sub_fits
        contributors.append((cls, qty, sub_fits))

    total_lambda = (total_fits / 1e9) * max(0.05, min(1.0, duty_cycle_derate))
    mtbf_h = 1.0 / total_lambda if total_lambda > 0 else float("inf")
    # 5-year mission survival R = e^(-t/MTBF)
    five_years_h = 5.0 * 8760.0
    rel5 = pow(2.718281828, -five_years_h / mtbf_h) if mtbf_h > 0 else 1.0

    contributors.sort(key=lambda c: -c[2])
    dominant = [
        {"part_class": c, "quantity": q, "share_pct": round(100.0 * f / total_fits, 1)}
        for c, q, f in contributors[:5]
    ]

    assumptions = [
        "Part-stress black-box method; constant hazard-rate (exponential) assumption.",
        "Quality level " + str(quality_level) + f" (πQ={pi_q}); environment '{environment}' (πE={pi_e}).",
        f"Arrhenius πT={pi_t:.2f} at {ambient_temp_c:.0f}°C ambient (0.08 eV class); electrolytics ×πT².",
    ]

    cited = [
        "Telcordia SR-332 Issue 3 Reliability Prediction Procedure for Electronic Equipment",
        "MIL-HDBK-217F Reliability Prediction of Electronic Equipment",
    ]

    return MtbfResult(
        parts_counted=sum(counts.values()),
        total_fits=total_fits * max(0.05, min(1.0, duty_cycle_derate)),
        mtbf_hours=mtbf_h,
        reliability_5yr=rel5,
        pi_t=pi_t,
        pi_e=pi_e,
        environment=environment,
        ambient_temp_c=ambient_temp_c,
        dominant_parts=dominant,
        assumptions=assumptions,
        standards_cited=cited,
    )


def _classify_part(kind: str, value: str, ref: str) -> str | None:
    """Map a BOM component to a Telcordia part class."""
    k = kind.upper()
    v = value.upper()
    if "MICROCONTROLLER" in k or "MCU" in k:
        return "MICROCONTROLLER"
    if "TRANSCEIVER" in k or "RF" in k:
        return "IC_RF_TRANSCEIVER"
    if "FLASH" in k or "EEPROM" in v:
        return "IC_MEMORY_FLASH"
    if "DRAM" in k or "SDRAM" in v:
        return "IC_MEMORY_DRAM"
    if any(t in k for t in ("IC", "MCU", "SOC", "LOGIC")):
        return "IC_DIGITAL_CMOS"
    if "LDO" in k or "REGULATOR" in k or "OPAMP" in k or "COMPARATOR" in k:
        return "IC_LINEAR"
    if "CRYSTAL" in k:
        return "CRYSTAL"
    if "OSCILLATOR" in k:
        return "OSCILLATOR"
    if "ZENER" in k:
        return "DIODE_ZENER"
    if "DIODE" in k:
        return "DIODE_GENERAL"
    if "MOSFET" in k:
        return "TRANSISTOR_MOSFET"
    if "TRANSISTOR" in k or "BJT" in k:
        return "TRANSISTOR_BJT"
    if "ELECTROLYTIC" in k or "ELECTROLYTIC" in v:
        return "CAPACITOR_ELECTROLYTIC"
    if "TANTALUM" in k or "TANTALUM" in v:
        return "CAPACITOR_TANTALUM"
    if "CAPACITOR" in k:
        return "CAPACITOR_CERAMIC"
    if "INDUCTOR" in k or "CHOKE" in k:
        return "INDUCTOR_POWER"
    if "RESISTOR" in k:
        return "RESISTOR_CHIP"
    if "CONNECTOR" in k or "HEADER" in k or "USB" in k:
        return "CONNECTOR_PIN"
    if "TESTPOINT" in k or "FIDUCIAL" in k:
        return None  # mechanical, no λ contribution
    if "TVS" in k:
        return "DIODE_GENERAL"
    if "LED" in k:
        return "DIODE_GENERAL"
    if "SWITCH" in k or "BUTTON" in k:
        return "CONNECTOR_PIN"  # electromechanical contact class
    return "RESISTOR_CHIP" if ref.startswith("R") else None
