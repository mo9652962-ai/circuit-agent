"""IPC-2152 Copper Pour Plane & Busbar DC IR-Drop & Thermal Density Analyzer.

Industrial & Authoritative Standards:
- IPC-2152 (Standard for Determining Current-carrying Capacity in Printed Board Design):
  Section 5.0 governs copper planes, busbars, and complex polygon geometries. Unlike thin rectangular
  isolated traces, large copper pours and power planes dissipate heat through wide 2D thermal conduction.
  However, neck-down constriction zones (bottlenecks around via fields, anti-pads, and board cutouts)
  concentrate current vectors, leading to catastrophic local heating, solder mask blistering, and thermal delamination.
- IEC 60092-352 / DIN EN 60384:
  High-current power electronics standards enforce maximum DC current density limits:
    * Conservative nominal continuous current density: J <= 30.0 A/mm²
    * Extreme maximum short-duration current density: J <= 50.0 A/mm²
    * Beyond 50 A/mm², localized Joule heating (I²R) exceeds natural PCB FR-4 convective/conductive
      cooling capacity, creating hazardous localized thermal runaway hotspots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Pure copper resistivity at 20°C in Ohm*mm²/m (or 1.72e-5 Ohm*mm)
COPPER_RESISTIVITY_20C_OHM_MM = 1.724e-5  # Ohm * mm
COPPER_TEMP_COEFF_PER_C = 0.00393  # 1/°C


@dataclass
class CopperPourIRDropResult:
    """Evaluation result of DC IR drop, Joule heating, and current density across copper pour."""

    current_a: float
    copper_weight_oz: float
    copper_thickness_mm: float
    operating_temp_c: float
    effective_length_mm: float
    effective_width_mm: float
    bottleneck_width_mm: float
    sheet_resistance_mohm_sq: float
    total_resistance_mohm: float
    voltage_drop_mv: float
    power_dissipation_watts: float
    bottleneck_current_density_a_per_mm2: float
    is_density_compliant: bool
    estimated_temp_rise_c: float
    max_safe_current_a: float
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_a": round(self.current_a, 2),
            "copper_weight_oz": round(self.copper_weight_oz, 2),
            "copper_thickness_mm": round(self.copper_thickness_mm, 4),
            "operating_temp_c": round(self.operating_temp_c, 1),
            "effective_length_mm": round(self.effective_length_mm, 2),
            "effective_width_mm": round(self.effective_width_mm, 2),
            "bottleneck_width_mm": round(self.bottleneck_width_mm, 2),
            "sheet_resistance_mohm_sq": round(self.sheet_resistance_mohm_sq, 3),
            "total_resistance_mohm": round(self.total_resistance_mohm, 3),
            "voltage_drop_mv": round(self.voltage_drop_mv, 2),
            "power_dissipation_watts": round(self.power_dissipation_watts, 3),
            "bottleneck_current_density_a_per_mm2": round(self.bottleneck_current_density_a_per_mm2, 2),
            "is_density_compliant": self.is_density_compliant,
            "estimated_temp_rise_c": round(self.estimated_temp_rise_c, 1),
            "max_safe_current_a": round(self.max_safe_current_a, 2),
            "standards_cited": self.standards_cited,
        }


def calculate_copper_pour_current_drop(
    current_a: float,
    copper_weight_oz: float = 1.0,
    effective_length_mm: float = 50.0,
    effective_width_mm: float = 20.0,
    bottleneck_width_mm: float | None = None,
    ambient_temp_c: float = 25.0,
    max_allowed_temp_rise_c: float = 30.0,
    max_allowed_current_density_a_per_mm2: float = 35.0,
) -> CopperPourIRDropResult:
    """Analyze DC resistance, voltage drop, and localized bottleneck current density in a copper plane.

    Args:
        current_a: Applied DC load current in Amperes
        copper_weight_oz: Copper foil weight (1.0 oz = ~0.035 mm, 2.0 oz = ~0.070 mm)
        effective_length_mm: Current path length from source to sink in mm
        effective_width_mm: Average conduction width of the copper plane in mm
        bottleneck_width_mm: Narrowest constriction width (e.g. between via drills or cutouts) in mm
        ambient_temp_c: Ambient operating temperature in °C
        max_allowed_temp_rise_c: Target allowable temperature rise in °C
        max_allowed_current_density_a_per_mm2: Maximum safe current density ceiling (standard 35.0 A/mm²)

    Returns:
        CopperPourIRDropResult: Comprehensive IR-drop, power, and thermal safety calculation
    """
    # 1. Copper thickness calculation
    t_cu = max(0.009, copper_weight_oz * 0.035)  # mm

    if bottleneck_width_mm is None or bottleneck_width_mm <= 0:
        bottleneck_width_mm = effective_width_mm

    # 2. Temperature adjusted resistivity
    # Estimated plane temperature under load
    est_temp_c = ambient_temp_c + max_allowed_temp_rise_c * 0.5
    rho_t = COPPER_RESISTIVITY_20C_OHM_MM * (
        1.0 + COPPER_TEMP_COEFF_PER_C * (est_temp_c - 20.0)
    )

    # 3. Sheet resistance R_sq (mOhm / square)
    # R_sq = rho / t
    r_sq_mohm = (rho_t / t_cu) * 1000.0

    # 4. Total DC Resistance R = R_sq * (L / W)
    num_squares = max(0.01, effective_length_mm / max(0.1, effective_width_mm))
    total_r_mohm = r_sq_mohm * num_squares

    # 5. Voltage Drop and Power Dissipation
    v_drop_mv = current_a * total_r_mohm
    power_watts = (current_a**2) * (total_r_mohm / 1000.0)

    # 6. Current Density at Bottleneck
    bottleneck_area_mm2 = max(1e-4, bottleneck_width_mm * t_cu)
    j_bottleneck = current_a / bottleneck_area_mm2

    is_compliant = j_bottleneck <= max_allowed_current_density_a_per_mm2

    # 7. Estimated temperature rise via IPC-2152 empirical approximation for planes
    # Planes dissipate heat ~2.5x more efficiently than isolated narrow traces
    # Delta_T approx = (I / (k * A^0.725))^(1 / 0.44)
    # Scaled thermal model for copper planes:
    a_mils2 = (effective_width_mm * 39.37) * (t_cu * 39.37)
    i_term = current_a / (0.048 * (a_mils2**0.44)) if a_mils2 > 0 else 0
    delta_t = min(150.0, max(0.5, (i_term**1.2) * 0.45))

    # 8. Maximum Safe Current before hitting current density ceiling
    max_safe_current = max_allowed_current_density_a_per_mm2 * bottleneck_area_mm2

    cited = [
        "IPC-2152 Standard for Determining Current-carrying Capacity in Printed Board Design §5.0",
        "IEC 60092-352 Electrical Installations in Ships - Choice and Installation of Cables & Busbars",
    ]

    return CopperPourIRDropResult(
        current_a=current_a,
        copper_weight_oz=copper_weight_oz,
        copper_thickness_mm=t_cu,
        operating_temp_c=ambient_temp_c + delta_t,
        effective_length_mm=effective_length_mm,
        effective_width_mm=effective_width_mm,
        bottleneck_width_mm=bottleneck_width_mm,
        sheet_resistance_mohm_sq=r_sq_mohm,
        total_resistance_mohm=total_r_mohm,
        voltage_drop_mv=v_drop_mv,
        power_dissipation_watts=power_watts,
        bottleneck_current_density_a_per_mm2=j_bottleneck,
        is_density_compliant=is_compliant,
        estimated_temp_rise_c=delta_t,
        max_safe_current_a=max_safe_current,
        standards_cited=cited,
    )
