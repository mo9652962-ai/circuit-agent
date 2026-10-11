"""IPC-7525A Solder Paste Volume Transfer Efficiency Calculator.

Industrial benchmark & standards:
- IPC-7525A: Stencil Design Guidelines (revision A extends the original with paste volume
  transfer analysis).
  * Deposited paste volume per aperture: V_paste = Opening_area × Foil_thickness × η,
    where η (transfer efficiency) is typically 0.75 ~ 0.95 for laser-cut stencils with
    nano-coated foils, lower (~0.6) for worn or uncoated stencils.
  * Target paste volume: the printed deposit must deliver at least the reference joint
    volume — approximated by aperture area × target standoff height (default 0.10mm for
    standard SMD; Type II/III 0402/0603 often 0.08 ~ 0.12mm).
  * Volume ratio R = V_paste / V_target: R < 1.0 indicates starved joints (opens, tombstone,
    BGA HiP); R > 2.5 indicates excessive paste (bridging, mid-chip beads).
- Accepted window: 1.0 <= R <= 2.5 (per-aperture assessment aligned to IPC-A-610G joint
  acceptance criteria).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PasteVolumeCheck:
    ref: str
    shape: str
    opening_area_mm2: float
    paste_volume_mm3: float
    target_volume_mm3: float
    volume_ratio: float
    is_compliant: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PasteVolumeReport:
    foil_thickness_um: float
    transfer_efficiency: float
    target_standoff_mm: float
    total_paste_mm3: float
    deficient_count: int
    excessive_count: int
    checks: list[PasteVolumeCheck] = field(default_factory=list)
    ipc_standard: str = "IPC-7525A Stencil Design Guidelines (Paste Transfer Analysis)"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _opening_area(shape: str, width_mm: float, length_mm: float) -> float:
    if shape == "circle":
        return math.pi * (width_mm / 2.0) ** 2
    return width_mm * length_mm


def calculate_solder_paste_volume(
    apertures: list[dict],
    foil_thickness_um: float = 100.0,
    transfer_efficiency: float = 0.90,
    target_standoff_mm: float = 0.10,
    min_ratio: float = 1.0,
    max_ratio: float = 2.5,
) -> PasteVolumeReport:
    """Assess per-aperture deposited paste volume against target joint volume (IPC-7525A).

    apertures: [{ref, shape ('rect'|'circle'), width_mm, length_mm}]
    """
    t_mm = max(0.05, float(foil_thickness_um)) / 1000.0
    eta = min(1.0, max(0.3, float(transfer_efficiency)))
    standoff = max(0.02, float(target_standoff_mm))

    checks: list[PasteVolumeCheck] = []
    deficient = 0
    excessive = 0
    total = 0.0

    for ap in apertures:
        ref = str(ap.get("ref", "AP"))
        shape = str(ap.get("shape", "rect")).lower()
        w = max(0.05, float(ap.get("width_mm", 0.3)))
        l = max(0.05, float(ap.get("length_mm", w)))

        area = _opening_area(shape, w, l)
        paste_vol = area * t_mm * eta
        target_vol = area * standoff
        ratio = round(paste_vol / target_vol, 2) if target_vol > 0 else 0.0

        compliant = min_ratio <= ratio <= max_ratio
        if ratio < min_ratio:
            deficient += 1
        elif ratio > max_ratio:
            excessive += 1
        total += paste_vol

        checks.append(
            PasteVolumeCheck(
                ref=ref,
                shape=shape,
                opening_area_mm2=round(area, 4),
                paste_volume_mm3=round(paste_vol, 4),
                target_volume_mm3=round(target_vol, 4),
                volume_ratio=ratio,
                is_compliant=compliant,
            )
        )

    return PasteVolumeReport(
        foil_thickness_um=float(foil_thickness_um),
        transfer_efficiency=eta,
        target_standoff_mm=standoff,
        total_paste_mm3=round(total, 3),
        deficient_count=deficient,
        excessive_count=excessive,
        checks=checks,
    )
