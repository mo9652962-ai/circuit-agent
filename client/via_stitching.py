"""IPC-7093 & IPC-2141A Thermal Via Stitching & High-Frequency Ground Fence Solver.

Industrial benchmark & standards:
- IPC-7093 Section 7.2: Design and Assembly Process Implementation for Bottom Termination SMT (QFN / DFN).
  Exposed power/ground pads (EPAD) require a matrix array of through-hole thermal vias:
  * Standard hole diameter: 0.30mm (12 mil) drill to prevent capillary solder wicking during reflow.
  * Grid pitch: 1.0mm ~ 1.2mm center-to-center pitch.
  * Thermal via plating: >= 25μm (1 mil) copper barrel thickness.
  * Thermal resistance reduction: Each filled/tented via shunts ~30°C/W in parallel, reducing R_theta_JA by 40%~75%.
- IPC-2141A & IEEE High-Frequency Microwave Standards:
  Ground plane stitching vias (Shielding Via Fence):
  * Via-to-via pitch <= lambda / 10 (or standard 2.0mm ~ 2.5mm for sub-6GHz RF / high-speed digital).
  * Fence distance to signal trace: >= 3x dielectric height (3H) to prevent unwanted impedance loading.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StitchingVia:
    x_mm: float
    y_mm: float
    drill_dia_mm: float = 0.30
    pad_dia_mm: float = 0.60
    net: str = "/GND"
    via_type: str = "thermal"  # "thermal" or "shielding_fence"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ViaStitchingReport:
    total_vias_generated: int
    thermal_vias_count: int
    shielding_vias_count: int
    thermal_resistance_reduction_pct: float
    grid_pitch_mm: float
    vias: list[StitchingVia] = field(default_factory=list)
    ipc_standard: str = "IPC-7093 Section 7.2 / IPC-2141A"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["vias"] = [v.to_dict() if hasattr(v, "to_dict") else v for v in self.vias]
        return d


def calculate_via_stitching_array(
    pad_width_mm: float = 5.0,
    pad_height_mm: float = 5.0,
    center_x_mm: float = 0.0,
    center_y_mm: float = 0.0,
    drill_dia_mm: float = 0.30,
    grid_pitch_mm: float = 1.20,
    edge_margin_mm: float = 0.60,
    is_rf_shielding_fence: bool = False,
    trace_path_points: list[tuple[float, float]] | None = None,
    fence_offset_mm: float = 1.5,
) -> ViaStitchingReport:
    """Calculate thermal via array under exposed pad or RF shielding ground fence vias."""
    vias: list[StitchingVia] = []
    drill = max(0.15, float(drill_dia_mm))
    pad_d = round(drill + 0.30, 2)
    pitch = max(0.8, float(grid_pitch_mm))

    if not is_rf_shielding_fence:
        # 1. IPC-7093 QFN/Power Exposed Pad Thermal Via Array
        half_w = pad_width_mm / 2.0 - edge_margin_mm
        half_h = pad_height_mm / 2.0 - edge_margin_mm
        if half_w > 0 and half_h > 0:
            cols = max(1, math.floor((2 * half_w) / pitch) + 1)
            rows = max(1, math.floor((2 * half_h) / pitch) + 1)

            x_start = center_x_mm - ((cols - 1) * pitch) / 2.0
            y_start = center_y_mm - ((rows - 1) * pitch) / 2.0

            for c in range(cols):
                for r in range(rows):
                    vx = round(x_start + c * pitch, 3)
                    vy = round(y_start + r * pitch, 3)
                    vias.append(StitchingVia(x_mm=vx, y_mm=vy, drill_dia_mm=drill, pad_dia_mm=pad_d, net="/GND", via_type="thermal"))

        # Thermal resistance reduction model (each via parallel shunts heat to internal ground plane)
        num_vias = len(vias)
        r_red = round(min(75.0, 15.0 + num_vias * 6.5), 1) if num_vias > 0 else 0.0

        return ViaStitchingReport(
            total_vias_generated=num_vias,
            thermal_vias_count=num_vias,
            shielding_vias_count=0,
            thermal_resistance_reduction_pct=r_red,
            grid_pitch_mm=pitch,
            vias=vias,
        )

    # 2. RF Ground Shielding Fence alongside high frequency trace
    path = trace_path_points or [(center_x_mm, center_y_mm - 10.0), (center_x_mm, center_y_mm + 10.0)]
    for i in range(len(path) - 1):
        x1, y1 = path[i]
        x2, y2 = path[i + 1]
        seg_len = math.hypot(x2 - x1, y2 - y1)
        if seg_len <= 0:
            continue
        ux = (x2 - x1) / seg_len
        uy = (y2 - y1) / seg_len
        # Normal vectors
        nx = -uy
        ny = ux

        steps = max(1, round(seg_len / pitch))
        for s in range(steps + 1):
            px = x1 + s * (seg_len / steps) * ux
            py = y1 + s * (seg_len / steps) * uy
            # Left side via
            vias.append(StitchingVia(x_mm=round(px + fence_offset_mm * nx, 3),
                                     y_mm=round(py + fence_offset_mm * ny, 3),
                                     drill_dia_mm=drill, pad_dia_mm=pad_d, net="/GND", via_type="shielding_fence"))
            # Right side via
            vias.append(StitchingVia(x_mm=round(px - fence_offset_mm * nx, 3),
                                     y_mm=round(py - fence_offset_mm * ny, 3),
                                     drill_dia_mm=drill, pad_dia_mm=pad_d, net="/GND", via_type="shielding_fence"))

    return ViaStitchingReport(
        total_vias_generated=len(vias),
        thermal_vias_count=0,
        shielding_vias_count=len(vias),
        thermal_resistance_reduction_pct=0.0,
        grid_pitch_mm=pitch,
        vias=vias,
    )
