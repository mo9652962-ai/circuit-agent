"""IPC-4562B / IPC-2221B High-Frequency Copper Foil Roughness & Skin Effect Loss Analyzer.

Industrial & Authoritative Standards:
- IPC-4562B (Metal Foil for Printed Wiring Applications):
  Standardizes electrodeposited (ED) and rolled-annealed (RA) copper foil profile roughness:
    * Standard Profile (STD / ED): Rz = 5.0 ~ 8.0 μm, Rq ≈ 1.8 ~ 2.5 μm
    * Very Low Profile (VLP): Rz = 2.5 ~ 4.0 μm, Rq ≈ 0.8 ~ 1.2 μm
    * Hyper Very Low Profile / Reverse Treated Foil (HVLP / RTF): Rz = 1.0 ~ 1.8 μm, Rq ≈ 0.3 ~ 0.6 μm
- IPC-2141A / IEEE 802.3ck (100 Gb/s per Lane Transmission):
  At high frequencies (1 GHz to 50 GHz, such as PCIe 5.0/6.0, USB4, 5G NR, 112G PAM4), alternating
  current concentrates within the skin depth (delta = sqrt(rho / (pi * f * mu))).
  When skin depth is comparable to or smaller than copper surface roughness tooth height (delta <= Rq),
  current must follow the convoluted microscopic peaks and valleys of the copper tooth profile, dramatically
  increasing effective path length, AC resistance, and insertion loss (Hammerstad-Jensen & Huray models).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# Physical Constants
MU_0 = 4.0 * math.pi * 1e-7  # Permeability of free space (H/m)
COPPER_RESISTIVITY_BULK = 1.724e-8  # Bulk copper resistivity at 20°C (Ohm * m)

# Standard Copper Foil Profile Presets (IPC-4562B)
COPPER_FOIL_PRESETS: dict[str, dict[str, Any]] = {
    "standard_ed": {
        "name": "Standard Profile Electrodeposited (STD / ED)",
        "rz_um": 6.5,
        "rq_um": 2.0,
        "description": "Standard profile, high tooth adhesion, high loss > 3 GHz.",
    },
    "vlp": {
        "name": "Very Low Profile (VLP)",
        "rz_um": 3.0,
        "rq_um": 1.0,
        "description": "Optimized tooth profile for PCIe 4.0 / 10G signals.",
    },
    "hvlp": {
        "name": "Hyper Very Low Profile (HVLP / RTF)",
        "rz_um": 1.2,
        "rq_um": 0.4,
        "description": "Ultra-smooth profile for PCIe 5.0/6.0, 112G SerDes, and 77GHz mmWave.",
    },
}


@dataclass
class SkinEffectLossResult:
    """Calculated skin effect depth, surface roughness correction, and attenuation loss."""

    frequency_ghz: float
    copper_foil_type: str
    skin_depth_um: float
    copper_rq_um: float
    roughness_correction_factor_ksr: float
    conductor_loss_smooth_db_per_inch: float
    conductor_loss_rough_db_per_inch: float
    total_attenuation_db_per_meter: float
    roughness_loss_percentage: float
    is_roughness_acceptable: bool
    recommendation: str
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frequency_ghz": round(self.frequency_ghz, 2),
            "copper_foil_type": self.copper_foil_type,
            "skin_depth_um": round(self.skin_depth_um, 3),
            "copper_rq_um": round(self.copper_rq_um, 2),
            "roughness_correction_factor_ksr": round(self.roughness_correction_factor_ksr, 3),
            "conductor_loss_smooth_db_per_inch": round(self.conductor_loss_smooth_db_per_inch, 3),
            "conductor_loss_rough_db_per_inch": round(self.conductor_loss_rough_db_per_inch, 3),
            "total_attenuation_db_per_meter": round(self.total_attenuation_db_per_meter, 2),
            "roughness_loss_percentage": round(self.roughness_loss_percentage, 1),
            "is_roughness_acceptable": self.is_roughness_acceptable,
            "recommendation": self.recommendation,
            "standards_cited": self.standards_cited,
        }


def calculate_high_speed_skin_depth_loss(
    frequency_ghz: float = 10.0,
    trace_width_mm: float = 0.150,
    trace_thickness_mm: float = 0.035,
    dielectric_er: float = 4.2,
    foil_type: str = "vlp",
    custom_rq_um: float | None = None,
    max_acceptable_ksr: float = 1.85,
) -> SkinEffectLossResult:
    """Calculate skin depth, Hammerstad surface roughness correction factor, and insertion loss.

    Args:
        frequency_ghz: Signal Nyquist or operating frequency in GHz
        trace_width_mm: Conductor trace width in mm (default: 0.150)
        trace_thickness_mm: Conductor copper thickness in mm (default: 0.035, 1oz)
        dielectric_er: Substrate relative permittivity (default: 4.2 for FR-4)
        foil_type: Copper profile ('standard_ed', 'vlp', 'hvlp')
        custom_rq_um: Optional override for RMS surface roughness Rq in μm
        max_acceptable_ksr: Maximum allowable roughness correction penalty factor (standard 1.60)

    Returns:
        SkinEffectLossResult: Depth, Ksr, attenuation, and foil selection advice
    """
    freq_hz = max(1e6, frequency_ghz * 1e9)
    w_m = max(1e-5, trace_width_mm * 1e-3)
    t_m = max(1e-5, trace_thickness_mm * 1e-3)

    # 1. Skin depth: delta = sqrt(rho / (pi * f * mu0 * mu_r))
    # Copper relative permeability mu_r = 0.999994 ≈ 1.0
    skin_depth_m = math.sqrt(COPPER_RESISTIVITY_BULK / (math.pi * freq_hz * MU_0))
    skin_depth_um = skin_depth_m * 1e6

    # 2. Extract or override surface roughness Rq (RMS)
    f_key = foil_type.lower()
    preset = COPPER_FOIL_PRESETS.get(f_key, COPPER_FOIL_PRESETS["vlp"])
    rq_um = custom_rq_um if (custom_rq_um is not None and custom_rq_um > 0) else preset["rq_um"]

    # 3. Hammerstad-Jensen roughness correction factor:
    # K_sr = 1 + (2 / pi) * arctan(1.4 * (Rq / delta)^2)
    rq_to_delta = rq_um / max(1e-4, skin_depth_um)
    ksr = 1.0 + (2.0 / math.pi) * math.atan(1.4 * (rq_to_delta**2))

    # 4. Smooth conductor attenuation (approximate microstrip model)
    # AC surface resistance: R_ac = rho / (2 * (w + t) * delta)
    perimeter_m = 2.0 * (w_m + t_m)
    r_ac_smooth_per_m = COPPER_RESISTIVITY_BULK / (perimeter_m * skin_depth_m)

    # Characteristic impedance approximation (for microstrip)
    z0 = 50.0  # Standard reference 50 Ohm
    # Alpha_c (Np/m) = R_ac / (2 * Z0)
    # Convert Np/m to dB/m (1 Np = 8.686 dB)
    alpha_smooth_db_m = (r_ac_smooth_per_m / (2.0 * z0)) * 8.685889
    alpha_rough_db_m = alpha_smooth_db_m * ksr

    # Convert to dB / inch (1 meter ≈ 39.37 inches)
    alpha_smooth_db_in = alpha_smooth_db_m / 39.3701
    alpha_rough_db_in = alpha_rough_db_m / 39.3701

    roughness_overhead_pct = ((ksr - 1.0) / 1.0) * 100.0
    is_acceptable = ksr <= max_acceptable_ksr

    if not is_acceptable:
        rec = f"Surface roughness penalty Ksr={ksr:.2f} exceeds limit {max_acceptable_ksr:.2f}. Upgrade copper foil from {f_key} to HVLP (Rq <= 0.4μm) to recover signal margin."
    elif ksr > 1.35:
        rec = f"Moderate roughness loss (Ksr={ksr:.2f}, +{roughness_overhead_pct:.1f}% loss). Consider VLP/HVLP copper for trace lengths > 4 inches."
    else:
        rec = f"Skin depth delta={skin_depth_um:.2f}μm is adequate relative to Rq={rq_um:.2f}μm (Ksr={ksr:.2f}). Insertion loss is well managed."

    cited = [
        "IPC-4562B Metal Foil for Printed Wiring Applications §3.2 Table 3-1",
        "IPC-2141A Design Guide for High-Speed Multilayer Printed Boards §5.4 Skin Effect",
        "E. Hammerstad and O. Jensen, Accurate Models for Microstrip Computer-Aided Design, IEEE MTT-S",
    ]

    return SkinEffectLossResult(
        frequency_ghz=frequency_ghz,
        copper_foil_type=preset["name"],
        skin_depth_um=skin_depth_um,
        copper_rq_um=rq_um,
        roughness_correction_factor_ksr=ksr,
        conductor_loss_smooth_db_per_inch=alpha_smooth_db_in,
        conductor_loss_rough_db_per_inch=alpha_rough_db_in,
        total_attenuation_db_per_meter=alpha_rough_db_m,
        roughness_loss_percentage=roughness_overhead_pct,
        is_roughness_acceptable=is_acceptable,
        recommendation=rec,
        standards_cited=cited,
    )
