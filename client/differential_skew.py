"""High-Speed Differential Pair Skew, Phase Tolerance & Serpentine Tuning Engine.

Industrial standards & protocol specifications:
- USB 2.0 High-Speed Specification §7.1.4: Intra-pair skew ≤ 10ps (trace length delta ≤ 1.5mm on FR4).
- 100Base-TX IEEE 802.3u / MII specification: Pair delay skew ≤ 25ps.
- CAN / CAN-FD ISO 11898-2: Intra-pair propagation delay mismatch ≤ 50ps.
- Propagation velocity on microstrip:
  v = c / sqrt(epsilon_eff), where epsilon_eff ≈ 0.64 * er + 0.36 for surface microstrip.
  Typical FR4 propagation delay: t_pd ≈ 6.5 ~ 6.8 ps/mm.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Any

log = logging.getLogger("circuit-diff-skew")

C_LIGHT_MM_PER_PS = 0.299792458  # speed of light in mm/ps


@dataclass
class DifferentialSkewResult:
    """Differential pair skew analysis & length matching target."""

    protocol: str
    trace_length_delta_mm: float
    effective_dielectric_er: float
    propagation_velocity_mm_per_ps: float
    delay_skew_ps: float
    max_allowed_skew_ps: float
    is_compliant: bool
    required_tuning_length_mm: float
    serpentine_bumps_count: int
    serpentine_step_mm: float
    serpentine_height_mm: float
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PROTOCOL_SKEW_LIMITS = {
    "USB2_HS": (10.0, "USB 2.0 High-Speed 480Mbps (Intra-pair Skew ≤ 10ps / ~1.5mm)"),
    "USB2_FS": (100.0, "USB 2.0 Full-Speed 12Mbps (Intra-pair Skew ≤ 100ps)"),
    "ETH_100M": (25.0, "100Base-TX Ethernet MII/RMII (Intra-pair Delay Skew ≤ 25ps)"),
    "CAN_FD": (50.0, "CAN-FD / ISO 11898-2 (Intra-pair Propagation Delay ≤ 50ps)"),
    "RS485": (200.0, "TIA/EIA-485-A Differential Serial (Relaxed Skew ≤ 200ps)"),
}


def solve_differential_pair_skew(
    trace_length_delta_mm: float,
    protocol: str = "USB2_HS",
    dielectric_er: float = 4.2,
    trace_width_mm: float = 0.254,
    height_mm: float = 0.100,
) -> DifferentialSkewResult:
    """Calculate intra-pair signal skew and solve required serpentine length matching tuning."""
    dl = abs(float(trace_length_delta_mm))
    er = float(dielectric_er)
    u_proto = protocol.upper().replace("-", "_").replace(" ", "_")

    limit_ps, proto_desc = PROTOCOL_SKEW_LIMITS.get(u_proto, PROTOCOL_SKEW_LIMITS["USB2_HS"])

    # Effective dielectric constant for microstrip (Schneider formula)
    u = trace_width_mm / height_mm if height_mm > 0 else 2.5
    eeff = (er + 1.0) / 2.0 + ((er - 1.0) / 2.0) * (1.0 / math.sqrt(1.0 + 12.0 / u))
    # Propagation speed in mm/ps
    v_prop = C_LIGHT_MM_PER_PS / math.sqrt(eeff)

    # Signal propagation delay skew in picoseconds
    skew_ps = dl / v_prop if v_prop > 0 else 0.0

    is_compliant = skew_ps <= limit_ps
    needed_len_mm = max(dl - (limit_ps * v_prop), 0.0) if not is_compliant else 0.0

    # Serpentine tuning geometry: bumps with 3x trace width amplitude and spacing
    bump_pitch = max(trace_width_mm * 4.0, 1.0)
    bump_height = max(trace_width_mm * 3.0, 0.8)
    # Each rectangular bump adds 2 * bump_height of track length
    added_per_bump = 2.0 * bump_height
    bumps_count = math.ceil(needed_len_mm / added_per_bump) if needed_len_mm > 0 else 0

    notes = [
        f"Protocol: {proto_desc}.",
        f"Microstrip delay: ~{1.0 / v_prop:.2f} ps/mm (eeff={eeff:.2f}).",
    ]
    if is_compliant:
        notes.append("✅ Skew meets specification; no serpentine tuning required.")
    else:
        notes.append(
            f"⚠️ Skew exceeds {limit_ps:.0f}ps limit; requires ~{needed_len_mm:.2f}mm ({bumps_count} bumps) serpentine compensation."
        )

    return DifferentialSkewResult(
        protocol=u_proto,
        trace_length_delta_mm=round(dl, 3),
        effective_dielectric_er=round(eeff, 3),
        propagation_velocity_mm_per_ps=round(v_prop, 4),
        delay_skew_ps=round(skew_ps, 2),
        max_allowed_skew_ps=limit_ps,
        is_compliant=is_compliant,
        required_tuning_length_mm=round(needed_len_mm, 3),
        serpentine_bumps_count=bumps_count,
        serpentine_step_mm=round(bump_pitch, 3),
        serpentine_height_mm=round(bump_height, 3),
        notes=" ".join(notes),
    )
