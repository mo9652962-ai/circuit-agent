"""BGA Dogbone Via Fanout & Escape Routing Solver (IPC-7095 Standard).

Industrial benchmark & standards:
- IPC-7095: Design and Assembly Process Implementation for BGAs.
  Section 5.2 defines the geometry and routing channels for Ball Grid Array escape fanouts:
  * Diagonal Dogbone Fanout (45° offset): Via placed at the center of 4 adjacent BGA solder balls.
  * Channel clearance: Space between adjacent balls = Pitch (P) - Pad Diameter (D).
  * Layer demand: Concentric ball rings dictate the minimum number of PCB signal routing layers.
    - Outer Ring 1: Direct surface escape on Top layer without vias.
    - Ring 2: Escapes on Inner Layer 1 (In1.Cu) via dogbone thru-hole vias.
    - Ring 3: Escapes on Inner Layer 2 (In2.Cu) or Bottom layer.
    - Pitch < 0.65mm: Conventional mechanical CNC drill cannot fit between pads, requiring
      HDI micro-via-in-pad (VIPPO / IPC-4761 Type VII).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DogboneVia:
    pin_name: str
    ball_x_mm: float
    ball_y_mm: float
    via_x_mm: float
    via_y_mm: float
    via_drill_mm: float
    via_pad_mm: float
    escape_layer: str  # "Top", "In1.Cu", "In2.Cu", "Bottom"
    trace_width_mm: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BGAEscapeReport:
    ball_count: int
    matrix_size: tuple[int, int]  # rows, cols
    ball_pitch_mm: float
    ball_pad_dia_mm: float
    channel_width_mm: float
    escape_clearance_mm: float
    min_layers_required: int
    hdi_microvia_required: bool
    dogbone_vias: list[DogboneVia] = field(default_factory=list)
    ipc_standard: str = "IPC-7095 Section 5.2"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["dogbone_vias"] = [v.to_dict() if hasattr(v, "to_dict") else v for v in self.dogbone_vias]
        return d


def calculate_bga_escape_routing(
    ball_count: int = 64,
    ball_pitch_mm: float = 0.8,
    ball_pad_dia_mm: float = 0.4,
    via_drill_mm: float = 0.2,
    via_pad_dia_mm: float = 0.45,
    trace_width_mm: float = 0.10,
) -> BGAEscapeReport:
    """Calculate BGA diagonal dogbone via fanout geometry, escape channels, and layer requirements."""
    pitch = max(0.4, float(ball_pitch_mm))
    pad_dia = max(0.2, float(ball_pad_dia_mm))
    via_drill = max(0.1, float(via_drill_mm))
    via_pad = max(via_drill + 0.15, float(via_pad_dia_mm))
    trace_w = max(0.075, float(trace_width_mm))

    # Grid dimension N x N
    grid_dim = math.ceil(math.sqrt(ball_count))
    rows = grid_dim
    cols = grid_dim

    # Channel width between adjacent balls
    channel_w = round(pitch - pad_dia, 3)

    # Clearance on each side of an escape trace routed between two balls
    escape_clearance = round((channel_w - trace_w) / 2.0, 3)

    # Diagonal distance between diagonal ball centers: sqrt(2) * P
    diag_pitch = math.sqrt(2.0) * pitch

    # Check if HDI micro-via-in-pad is required (conventional dogbone via doesn't fit if pitch < 0.65mm)
    hdi_needed = (pitch < 0.65) or (diag_pitch - pad_dia - via_pad < 0.15)

    # Number of concentric rings
    num_rings = math.ceil(grid_dim / 2.0)

    # Minimum layers required: 1 surface ring + 1 ring per internal/bottom layer
    min_layers = 2 if num_rings <= 1 else (4 if num_rings <= 2 else 6)

    # Generate 45° diagonal dogbone vias
    # Distance from ball center to via center along 45° diagonal: D_offset = pitch / 2
    diag_offset = round((pitch / 2.0) * math.sqrt(2.0), 3)

    vias: list[DogboneVia] = []
    center_offset_x = ((cols - 1) * pitch) / 2.0
    center_offset_y = ((rows - 1) * pitch) / 2.0

    count = 0
    for r in range(rows):
        for c in range(cols):
            if count >= ball_count:
                break
            bx = round(c * pitch - center_offset_x, 3)
            by = round(r * pitch - center_offset_y, 3)

            # Determine ring depth from perimeter
            ring_depth = min(r, c, rows - 1 - r, cols - 1 - c)

            # Determine escape layer
            if ring_depth == 0:
                esc_layer = "Top"
                # Outer ring escapes on surface without via
                vx = bx
                vy = by
            elif ring_depth == 1:
                esc_layer = "In1.Cu"
                # Dogbone 45° offset towards center or corner
                vx = round(bx + (diag_offset if bx >= 0 else -diag_offset), 3)
                vy = round(by + (diag_offset if by >= 0 else -diag_offset), 3)
            elif ring_depth == 2:
                esc_layer = "In2.Cu"
                vx = round(bx + (diag_offset if bx >= 0 else -diag_offset), 3)
                vy = round(by + (diag_offset if by >= 0 else -diag_offset), 3)
            else:
                esc_layer = "Bottom"
                vx = round(bx + (diag_offset if bx >= 0 else -diag_offset), 3)
                vy = round(by + (diag_offset if by >= 0 else -diag_offset), 3)

            row_letter = chr(ord("A") + r)
            col_num = c + 1
            pin_name = f"{row_letter}{col_num}"

            vias.append(
                DogboneVia(
                    pin_name=pin_name,
                    ball_x_mm=bx,
                    ball_y_mm=by,
                    via_x_mm=vx,
                    via_y_mm=vy,
                    via_drill_mm=via_drill,
                    via_pad_mm=via_pad,
                    escape_layer=esc_layer,
                    trace_width_mm=trace_w,
                )
            )
            count += 1

    return BGAEscapeReport(
        ball_count=ball_count,
        matrix_size=(rows, cols),
        ball_pitch_mm=pitch,
        ball_pad_dia_mm=pad_dia,
        channel_width_mm=channel_w,
        escape_clearance_mm=escape_clearance,
        min_layers_required=min_layers,
        hdi_microvia_required=hdi_needed,
        dogbone_vias=vias,
    )
