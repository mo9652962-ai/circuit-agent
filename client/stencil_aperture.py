"""IPC-7525 SMT Stencil Aperture Area Ratio & Aspect Ratio Compliance Calculator.

Industrial benchmark & standards:
- IPC-7525: Stencil Design Guidelines.
  Governs solder paste release efficiency from laser-cut / electroformed stencils:
  * Area Ratio (AR) = Area of aperture opening / (Perimeter of aperture walls × Foil thickness)
    - Laser-cut stainless stencil: AR >= 0.66 (66%) for reliable paste release.
    - Electroformed / nano-coated stencil: AR >= 0.60 acceptable.
  * Aspect Ratio = Aperture width / Foil thickness >= 1.5.
  * Deficient apertures cause insufficient solder paste deposition (skip/void), leading to
    tombstoning, open joints, and BGA head-in-pillow (HiP) defects (IPC-A-610G).
- Standard foil thicknesses: 100μm (4mil), 120μm (5mil), 130μm (5.1mil), 150μm (6mil).
  Fine-pitch QFN/BGA (0.4mm pitch) typically requires 100μm foil with step-down regions.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ApertureCheck:
    ref: str
    shape: str  # "rect" / "circle"
    width_mm: float
    length_mm: float
    opening_area_mm2: float
    wall_area_mm2: float
    area_ratio: float
    aspect_ratio: float
    is_compliant: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StencilApertureReport:
    foil_thickness_um: float
    min_required_area_ratio: float
    min_required_aspect_ratio: float
    total_apertures: int
    deficient_count: int
    deficient_refs: list[str] = field(default_factory=list)
    checks: list[ApertureCheck] = field(default_factory=list)
    ipc_standard: str = "IPC-7525 Stencil Design Guidelines"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["checks"] = [asdict(c) for c in self.checks]
        return d


def _aperture_geometry(shape: str, width_mm: float, length_mm: float) -> tuple[float, float]:
    """Return (opening_area_mm2, wall_perimeter_mm) for rect / circle apertures."""
    if shape == "circle":
        area = math.pi * (width_mm / 2.0) ** 2
        perimeter = math.pi * width_mm
        return area, perimeter
    # rect (incl. rounded / home-plate shapes approximated by bounding rect)
    area = width_mm * length_mm
    perimeter = 2.0 * (width_mm + length_mm)
    return area, perimeter


def calculate_stencil_aperture_ratios(
    apertures: list[dict],
    foil_thickness_um: float = 100.0,
    min_area_ratio: float = 0.66,
    min_aspect_ratio: float = 1.5,
) -> StencilApertureReport:
    """Evaluate IPC-7525 area/aspect ratios for every stencil aperture.

    apertures: list of dicts {ref, shape ('rect'|'circle'), width_mm, length_mm}.
      For circles, width_mm is the diameter and length_mm is ignored.
    """
    t_mm = max(0.05, float(foil_thickness_um)) / 1000.0
    checks: list[ApertureCheck] = []

    for ap in apertures:
        ref = str(ap.get("ref", "AP"))
        shape = str(ap.get("shape", "rect")).lower()
        w = max(0.05, float(ap.get("width_mm", 0.3)))
        l = max(0.05, float(ap.get("length_mm", w)))

        area, perimeter = _aperture_geometry(shape, w, l)
        wall_area = perimeter * t_mm
        ar = round(area / wall_area, 3) if wall_area > 0 else 0.0
        aspect = round(min(w, l) / t_mm, 2)

        compliant = (ar >= min_area_ratio) and (aspect >= min_aspect_ratio)
        checks.append(
            ApertureCheck(
                ref=ref,
                shape=shape,
                width_mm=w,
                length_mm=l,
                opening_area_mm2=round(area, 4),
                wall_area_mm2=round(wall_area, 4),
                area_ratio=ar,
                aspect_ratio=aspect,
                is_compliant=compliant,
            )
        )

    deficient = [c.ref for c in checks if not c.is_compliant]
    return StencilApertureReport(
        foil_thickness_um=float(foil_thickness_um),
        min_required_area_ratio=min_area_ratio,
        min_required_aspect_ratio=min_aspect_ratio,
        total_apertures=len(checks),
        deficient_count=len(deficient),
        deficient_refs=deficient,
        checks=checks,
    )
