"""IPC-2141A High-Speed Differential Pair Serpentine Delay Tuning Geometry Solver.

Industrial benchmark & standards:
- IPC-2141A & High-Speed Digital System Design (Howard Johnson / Eric Bogatin):
  To eliminate common-mode noise and timing skew on high-speed differential pairs
  (USB 2.0 HS skew <= 10ps, Ethernet <= 25ps, PCIe Gen3/4 <= 5ps), the shorter trace
  must be lengthened with serpentine / accordion meanders.
- Electrical & Geometry Rules:
  * Self-coupling suppression: Meander pitch S >= 3W (where W is trace width).
    If S < 3W, electromagnetic field fringe coupling occurs, causing signal to jump across the loops
    (velocity speed-up), defeating delay tuning and destroying eye-diagram margin.
  * Amplitude height: H >= 3W to achieve efficient delay without excessive impedance discontinuities.
  * 45° mitered or rounded corners to minimize parasitic capacitance at bends.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SerpentineVertex:
    x_mm: float
    y_mm: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SerpentineTuningReport:
    target_added_length_mm: float
    actual_added_length_mm: float
    meander_count: int
    meander_amplitude_h_mm: float
    meander_pitch_s_mm: float
    trace_width_w_mm: float
    self_coupling_ratio_s_over_w: float
    is_ipc_compliant: bool
    vertices: list[SerpentineVertex] = field(default_factory=list)
    ipc_standard: str = "IPC-2141A Section 5.3 / High-Speed Transmission Line Meanders"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["vertices"] = [v.to_dict() if hasattr(v, "to_dict") else v for v in self.vertices]
        return d


def calculate_serpentine_tuning_geometry(
    delta_length_mm: float = 3.50,
    trace_width_mm: float = 0.15,
    start_x_mm: float = 10.0,
    start_y_mm: float = 20.0,
    end_x_mm: float = 30.0,
    end_y_mm: float = 20.0,
    min_s_over_w: float = 3.0,
    min_h_over_w: float = 4.0,
) -> SerpentineTuningReport:
    """Calculate serpentine meander geometry to add target delta length while avoiding self-coupling."""
    delta_l = max(0.1, float(delta_length_mm))
    w = max(0.08, float(trace_width_mm))

    # Standard pitch S >= 3W and height H >= 4W
    pitch_s = round(max(0.40, w * min_s_over_w), 3)
    amp_h = round(max(0.60, w * min_h_over_w), 3)

    # Each full meander cycle (jog up, traverse, jog down) adds ~ 2 * H of extra path
    added_per_cycle = 2.0 * amp_h
    meander_cycles = max(1, math.ceil(delta_l / added_per_cycle))

    # Recalculate exact amplitude to match target delta_l
    amp_h = round(delta_l / (2.0 * meander_cycles), 3)
    if amp_h < w * 3.0:
        amp_h = round(w * 3.0, 3)

    # Path direction unit vector
    dx = end_x_mm - start_x_mm
    dy = end_y_mm - start_y_mm
    dist = math.hypot(dx, dy)
    if dist <= 0:
        dist = 1.0
        dx = 1.0
        dy = 0.0

    ux = dx / dist
    uy = dy / dist
    nx = -uy
    ny = ux

    vertices: list[SerpentineVertex] = [SerpentineVertex(round(start_x_mm, 3), round(start_y_mm, 3))]

    step_forward = dist / max(1, meander_cycles * 2 + 1)
    cur_dist = step_forward

    sign = 1.0
    for _ in range(meander_cycles):
        # Base point 1
        bx1 = start_x_mm + cur_dist * ux
        by1 = start_y_mm + cur_dist * uy
        vertices.append(SerpentineVertex(round(bx1, 3), round(by1, 3)))

        # Crest point 1
        cx1 = bx1 + sign * amp_h * nx
        cy1 = by1 + sign * amp_h * ny
        vertices.append(SerpentineVertex(round(cx1, 3), round(cy1, 3)))

        # Traverse along crest
        cur_dist += pitch_s / 2.0
        cx2 = start_x_mm + cur_dist * ux + sign * amp_h * nx
        cy2 = start_y_mm + cur_dist * uy + sign * amp_h * ny
        vertices.append(SerpentineVertex(round(cx2, 3), round(cy2, 3)))

        # Return to base
        bx2 = start_x_mm + cur_dist * ux
        by2 = start_y_mm + cur_dist * uy
        vertices.append(SerpentineVertex(round(bx2, 3), round(by2, 3)))

        cur_dist += step_forward
        sign = -sign  # Alternate jog direction

    vertices.append(SerpentineVertex(round(end_x_mm, 3), round(end_y_mm, 3)))

    actual_added = round(2.0 * amp_h * meander_cycles, 3)
    ratio = round(pitch_s / w, 2)
    compliant = ratio >= 3.0

    return SerpentineTuningReport(
        target_added_length_mm=delta_l,
        actual_added_length_mm=actual_added,
        meander_count=meander_cycles,
        meander_amplitude_h_mm=amp_h,
        meander_pitch_s_mm=pitch_s,
        trace_width_w_mm=w,
        self_coupling_ratio_s_over_w=ratio,
        is_ipc_compliant=compliant,
        vertices=vertices,
    )
