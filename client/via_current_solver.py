"""IPC-2152 / IPC-2221 Via Barrel Current Capacity & Stitching Array Solver.

Industrial & Authoritative Standards:
- IPC-2152 (Standard for Determining Current-carrying Capacity in Printed Board Design):
  Governs via (plated through-hole) current capacity using the barrel cross-section.
  The via barrel is treated as a cylindrical conductor of wall thickness
  t = (finished_plating_um / 1000) mm:
      A_barrel = π/4 × (D_outer² - D_drill²)   [using annular barrel model]
  With the IPC-2221 legacy thermal formula for external conductors
  (constant k = 0.048 for visible external layers, 0.024 internal):
      I = k × ΔT^0.44 × A^0.725    [A, ΔT in °C, A in mil²]
  Because the barrel is buried in the board (resin + copper plane heat sinking on
  both ends), industry practice applies a solid-connection derating credit:
  pours/pads at both ends cut effective temperature rise by 20~50% (NextPCB /
  iconnect007 thermal modeling studies).
- High-reliability practice (QueenEms / pcbeditor / Sierra Circuits):
  * Never route a power rail through a single via: use a stitched array sharing current.
  * Current per via must be derated to 30~50% of single-via capacity (current
    crowding at the entry pad makes the first via carry more than its share).
  * Filled-and-capped vias (IPC-4761 Type VII) carry ~1.5× an open barrel because
    the epoxy fill plus cap adds conduction paths and removes resin-trap voids.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# IPC-2221 thermal constants: external (visible) vs internal (buried) conductors
K_EXTERNAL = 0.048
K_INTERNAL = 0.024

# Current-sharing derating for stitched arrays (entry-pad crowding)
ARRAY_SHARING_DERATE = 0.40  # each via in an array carries ≤40% of its solo capacity
FILLED_VIA_CREDIT = 1.5      # IPC-4761 Type VII fill+cap conduction credit


@dataclass
class ViaCurrentResult:
    """Via barrel current capacity and stitching array recommendation."""

    via_drill_mm: float
    plating_um: float
    barrel_area_mil2: float
    is_filled: bool
    internal_layer: bool
    single_via_capacity_a: float
    array_size: int
    array_capacity_a: float
    per_via_share_a: float
    meets_requirement: bool
    delta_t_c: float
    barrel_current_density_a_per_mm2: float
    recommendation: str
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "via_drill_mm": self.via_drill_mm,
            "plating_um": self.plating_um,
            "barrel_area_mil2": round(self.barrel_area_mil2, 1),
            "is_filled": self.is_filled,
            "internal_layer": self.internal_layer,
            "single_via_capacity_a": round(self.single_via_capacity_a, 2),
            "array_size": self.array_size,
            "array_capacity_a": round(self.array_capacity_a, 2),
            "per_via_share_a": round(self.per_via_share_a, 2),
            "meets_requirement": self.meets_requirement,
            "delta_t_c": self.delta_t_c,
            "barrel_current_density_a_per_mm2": round(self.barrel_current_density_a_per_mm2, 1),
            "recommendation": self.recommendation,
            "standards_cited": self.standards_cited,
        }


def solve_via_current_array(
    current_a: float = 3.0,
    via_drill_mm: float = 0.30,
    plating_um: float = 25.0,
    is_filled: bool = False,
    internal_layer: bool = False,
    max_delta_t_c: float = 20.0,
    max_array_size: int = 8,
) -> ViaCurrentResult:
    """Solve via barrel capacity and required stitching array size for a rail current.

    Args:
        current_a: Rail current to carry (A).
        via_drill_mm: Finished drill diameter (mm).
        plating_um: Copper plating thickness in the barrel (μm); 1oz-class 25, Class 3 ≥25.
        is_filled: True for IPC-4761 Type VII fill+cap vias (adds conduction credit).
        internal_layer: True when the transition is between internal layers (k=0.024).
        max_delta_t_c: Allowable barrel temperature rise (°C), default 20.
        max_array_size: Stitching ceiling before recommending wider traces/pours.

    Returns:
        ViaCurrentResult: capacity, array size, per-via share, and compliance verdict.
    """
    d_out = max(0.05, via_drill_mm)
    d_in = max(0.01, d_out - 2.0 * (plating_um / 1000.0))
    if d_in <= 0:
        d_in = d_out * 0.2

    # Barrel annular cross-section in mm² → mil²
    area_mm2 = math.pi / 4.0 * (d_out**2 - d_in**2)
    area_mil2 = area_mm2 * 1550.0031

    k = K_INTERNAL if internal_layer else K_EXTERNAL
    i_solo = k * (max_delta_t_c**0.44) * (area_mil2**0.725)
    if is_filled:
        i_solo *= FILLED_VIA_CREDIT

    # Derate per-via share in an array, then size the array.
    per_via_share = i_solo * ARRAY_SHARING_DERATE
    n = 1
    if current_a > per_via_share:
        n = math.ceil(current_a / per_via_share)
    n = max(1, min(n, max_array_size))
    array_cap = per_via_share * n

    meets = array_cap >= current_a
    j_density = current_a / max(1e-6, area_mm2 * n)

    if not meets:
        rec = (
            f"即使 {n} 个过孔并联仍差 {current_a - array_cap:.1f}A：加宽走线/在焊盘两端扩大铜泊散热，"
            "或改用 ≥0.4mm 填铜电镀过孔 (IPC-4761 Type VII)。"
        )
    elif n == 1:
        rec = "单过孔足够（含 40% 阵列降额）；大电流路径仍建议双过孔冗余。"
    elif n >= max_array_size:
        rec = f"已顶到 {max_array_size} 阵列上限：优先加宽走线并扩大端部铜泊，而不是继续加过孔。"
    else:
        rec = f"{n} 过孔阵列合规（每孔分摊 {per_via_share:.1f}A，含 40% 降额）。"

    cited = [
        "IPC-2152 Standard for Determining Current-carrying Capacity in Printed Board Design",
        "IPC-2221 Generic Standard on Printed Board Design (legacy thermal formula)",
        "IPC-4761 Protection of Printed Board Via Structures (Type VII fill+cap)",
    ]

    return ViaCurrentResult(
        via_drill_mm=via_drill_mm,
        plating_um=plating_um,
        barrel_area_mil2=area_mil2,
        is_filled=is_filled,
        internal_layer=internal_layer,
        single_via_capacity_a=i_solo,
        array_size=n,
        array_capacity_a=array_cap,
        per_via_share_a=per_via_share,
        meets_requirement=meets,
        delta_t_c=max_delta_t_c,
        barrel_current_density_a_per_mm2=j_density,
        recommendation=rec,
        standards_cited=cited,
    )
