"""IPC-7093A / IPC-7525A QFN & BTC Thermal Slug Window-Pane Stencil Aperture Solver.

Industrial & Authoritative Standards:
- IPC-7093A (Design and Assembly Process Implementation for Bottom Termination SMT
  Components - BTCs / QFN / DFN / PowerStage):
  Section 4.5.3 governs stencil design for exposed central thermal pads (slugs).
  Unlike leaded packages, BTCs have no mechanical compliancy. Solder paste deposited
  as a solid 100% sheet over large thermal pads (> 3.0mm × 3.0mm) creates catastrophic
  manufacturing defects:
    1. Trapped flux volatiles during reflow cannot escape from the large surface,
       causing huge voiding (> 35% ~ 50%), die tilt / floating, and poor thermal conduction.
    2. Molten solder squeeze-out bridges directly to adjacent peripheral I/O signal pads.
    3. Component "skating" or rotation floating on excessive molten solder volume.
- Window-Pane (Matrix Array) Design Rules (IPC-7525A §3.4.3 & Texas Instruments SLUA271):
  * Target solder paste coverage: 50% ~ 70% of total copper pad area (nominal 60%).
  * Divide solid aperture into an N × M grid of smaller rectangular windows
    (individual window size 1.0mm ~ 1.5mm).
  * Web gap lanes between windows: 0.15mm ~ 0.25mm bare copper channels. These lanes
    act as outgassing chimneys, allowing volatilized flux vapors to escape prior to
    solder solidification, guaranteeing voiding <= 15% (Class 3 / Automotive standard).
  * Thermal Via Isolation: Stencil apertures must not cross open thermal vias unless
    vias are filled-and-capped (IPC-4761 Type VII) to prevent solder wicking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

TARGET_PASTE_COVERAGE_NOMINAL = 0.60  # 60% nominal target coverage
MIN_PASTE_COVERAGE = 0.50             # 50% minimum
MAX_PASTE_COVERAGE = 0.70             # 70% maximum
DEFAULT_WEB_WIDTH_MM = 0.20           # 0.20mm web outgassing channel
MIN_WEB_WIDTH_MM = 0.15               # 0.15mm minimum web
MAX_WINDOW_SIZE_MM = 1.50             # Max individual window size


@dataclass
class StencilWindow:
    """An individual window pane aperture."""

    index: int
    center_x_mm: float
    center_y_mm: float
    width_mm: float
    height_mm: float
    area_mm2: float


@dataclass
class QFNThermalPadStencilResult:
    """Complete window-pane stencil aperture calculation and voiding risk assessment."""

    pad_width_mm: float
    pad_height_mm: float
    total_pad_area_mm2: float
    grid_cols: int
    grid_rows: int
    total_windows_count: int
    window_width_mm: float
    window_height_mm: float
    web_channel_width_mm: float
    total_paste_area_mm2: float
    paste_coverage_pct: float
    is_coverage_compliant: bool
    estimated_voiding_pct: float
    paste_volume_reduction_pct: float
    windows: list[StencilWindow] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pad_width_mm": round(self.pad_width_mm, 2),
            "pad_height_mm": round(self.pad_height_mm, 2),
            "total_pad_area_mm2": round(self.total_pad_area_mm2, 2),
            "grid_layout": f"{self.grid_cols}x{self.grid_rows}",
            "total_windows_count": self.total_windows_count,
            "window_size_mm": [round(self.window_width_mm, 2), round(self.window_height_mm, 2)],
            "web_channel_width_mm": round(self.web_channel_width_mm, 2),
            "total_paste_area_mm2": round(self.total_paste_area_mm2, 2),
            "paste_coverage_pct": round(self.paste_coverage_pct, 1),
            "is_coverage_compliant": self.is_coverage_compliant,
            "estimated_voiding_pct": round(self.estimated_voiding_pct, 1),
            "paste_volume_reduction_pct": round(self.paste_volume_reduction_pct, 1),
            "windows": [
                {
                    "index": w.index,
                    "center": [round(w.center_x_mm, 3), round(w.center_y_mm, 3)],
                    "size": [round(w.width_mm, 3), round(w.height_mm, 3)],
                }
                for w in self.windows
            ],
            "recommendations": self.recommendations,
            "standards_cited": self.standards_cited,
        }


def calculate_qfn_thermal_pad_stencil(
    pad_width_mm: float = 4.5,
    pad_height_mm: float = 4.5,
    target_coverage_pct: float = 60.0,
    web_width_mm: float = DEFAULT_WEB_WIDTH_MM,
    has_unfilled_thermal_vias: bool = False,
    is_automotive_class3: bool = False,
) -> QFNThermalPadStencilResult:
    """Calculate window-pane matrix stencil apertures for QFN/BTC thermal pads per IPC-7093A.

    Args:
        pad_width_mm: Copper thermal slug width in mm (default: 4.5mm).
        pad_height_mm: Copper thermal slug height in mm (default: 4.5mm).
        target_coverage_pct: Target solder paste coverage percentage (50%~70%, default: 60%).
        web_width_mm: Outgassing channel width between panes (default: 0.20mm).
        has_unfilled_thermal_vias: Whether open vias exist in the thermal pad.
        is_automotive_class3: Whether strict Class 3 / automotive voiding limit (<=15%) applies.

    Returns:
        QFNThermalPadStencilResult: Window matrix dimensions, individual apertures, and voiding estimation.
    """
    total_area = pad_width_mm * pad_height_mm
    target_cov = max(MIN_PASTE_COVERAGE, min(MAX_PASTE_COVERAGE, target_coverage_pct / 100.0))
    web = max(MIN_WEB_WIDTH_MM, web_width_mm)

    recs: list[str] = []
    cited = [
        "IPC-7093A Design and Assembly Process Implementation for Bottom Termination SMT Components (BTC) §4.5",
        "IPC-7525A Stencil Design Guidelines §3.4.3 Thermal Pad Windows",
        "Texas Instruments Application Report SLUA271: QFN/SON Stencil Design & Void Mitigation",
    ]

    # Small pads (<= 2.0mm) can use a single aperture with perimeter reduction
    if pad_width_mm <= 2.0 or pad_height_mm <= 2.0:
        cols = 1
        rows = 1
    elif pad_width_mm <= 3.5 and pad_height_mm <= 3.5:
        cols = 2
        rows = 2
    elif pad_width_mm <= 5.5 and pad_height_mm <= 5.5:
        cols = 3
        rows = 3
    else:
        cols = max(3, math.ceil(pad_width_mm / MAX_WINDOW_SIZE_MM))
        rows = max(3, math.ceil(pad_height_mm / MAX_WINDOW_SIZE_MM))

    # Net available width and height excluding web lanes
    net_width = pad_width_mm - (cols - 1) * web
    net_height = pad_height_mm - (rows - 1) * web

    # Scale window size to achieve target coverage
    raw_win_w = net_width / cols
    raw_win_h = net_height / rows
    raw_area = (raw_win_w * cols) * (raw_win_h * rows)

    # Area scaling factor
    scale_factor = math.sqrt((total_area * target_cov) / max(1e-4, raw_area))
    scale_factor = min(1.0, scale_factor)

    win_w = raw_win_w * scale_factor
    win_h = raw_win_h * scale_factor

    actual_paste_area = (win_w * win_h) * (cols * rows)
    actual_coverage_pct = (actual_paste_area / total_area) * 100.0
    vol_reduction_pct = 100.0 - actual_coverage_pct

    # Estimate reflow voiding percentage:
    # Solid 100% paste typically yields 35~45% voiding. Window pane reduces it to 8~14%.
    base_voiding = 10.0 + (actual_coverage_pct - 50.0) * 0.25
    if has_unfilled_thermal_vias:
        base_voiding += 15.0  # Open vias trap gas and cause solder wicking!
        recs.append("Unfilled thermal vias detected inside thermal pad: open holes cause solder wicking to bottom side and severe outgassing voids. Specify IPC-4761 Type VII via-in-pad (VIPPO).")

    if is_automotive_class3 and base_voiding > 15.0:
        recs.append(f"Estimated solder voiding ({base_voiding:.1f}%) exceeds Class 3 / Automotive limit (<= 15.0%). Tighten stencil coverage toward 55% and increase reflow peak soak time.")

    is_compliant = (MIN_PASTE_COVERAGE * 100.0 <= actual_coverage_pct <= MAX_PASTE_COVERAGE * 100.0) and (not has_unfilled_thermal_vias)

    # Generate individual window coordinates centered on (0, 0) of the slug
    windows: list[StencilWindow] = []
    x_pitch = (pad_width_mm - (cols * win_w)) / (cols + 1) + win_w
    y_pitch = (pad_height_mm - (rows * win_h)) / (rows + 1) + win_h

    start_x = -((cols - 1) * x_pitch) / 2.0
    start_y = -((rows - 1) * y_pitch) / 2.0

    w_idx = 1
    for r in range(rows):
        wy = start_y + r * y_pitch
        for c in range(cols):
            wx = start_x + c * x_pitch
            windows.append(
                StencilWindow(
                    index=w_idx,
                    center_x_mm=wx,
                    center_y_mm=wy,
                    width_mm=win_w,
                    height_mm=win_h,
                    area_mm2=win_w * win_h,
                )
            )
            w_idx += 1

    recs.append(f"Planned {cols}x{rows} window-pane array: {cols * rows} apertures of size {win_w:.2f}x{win_h:.2f}mm separated by {web:.2f}mm gas exhaust channels.")

    return QFNThermalPadStencilResult(
        pad_width_mm=pad_width_mm,
        pad_height_mm=pad_height_mm,
        total_pad_area_mm2=total_area,
        grid_cols=cols,
        grid_rows=rows,
        total_windows_count=len(windows),
        window_width_mm=win_w,
        window_height_mm=win_h,
        web_channel_width_mm=web,
        total_paste_area_mm2=actual_paste_area,
        paste_coverage_pct=actual_coverage_pct,
        is_coverage_compliant=is_compliant,
        estimated_voiding_pct=base_voiding,
        paste_volume_reduction_pct=vol_reduction_pct,
        windows=windows,
        recommendations=recs,
        standards_cited=cited,
    )
