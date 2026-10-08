"""SMT Breakaway Rails & Panelization Calculator (IPC-2221B & IPC-SMEMA-9851).

Industrial benchmark & standards:
- IPC-2221B Section 8.4: Breakaway Tabs and Panelization Guidelines.
- IPC-SMEMA-9851: Mechanical Interface Specification for SMT Conveyors.
  Defines standard 3.0mm to 5.0mm conveyor edge clearance, tooling hole placement,
  and optical fiducial alignment patterns.
- SMTA De-paneling Guidelines:
  * V-Scoring (V-Cut): 0mm board spacing, 30° / 45° scoring angle, residual web 1/3 board thickness.
  * Tab-Routing with Mouse-Bites: 2.0mm milling channel, 5.0mm tab width, 5x Φ0.6mm drill holes
    spaced at 1.0mm pitch with 0.25mm inward edge recess (prevents protruding burrs after snapping).
- Material Utilization Rate (η):
  Calculates active board copper area vs total panel laminate utilization percentage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolingHole:
    x_mm: float
    y_mm: float
    diameter_mm: float = 3.2
    is_plated: bool = False


@dataclass
class OpticalFiducial:
    x_mm: float
    y_mm: float
    pad_diameter_mm: float = 1.0
    mask_clearance_mm: float = 3.0


@dataclass
class BreakawayTab:
    center_x_mm: float
    center_y_mm: float
    orientation: str  # "horizontal" or "vertical"
    tab_width_mm: float = 5.0
    hole_count: int = 5
    hole_diameter_mm: float = 0.6
    hole_pitch_mm: float = 1.0
    edge_recess_mm: float = 0.25


@dataclass
class PanelFrameResult:
    panel_width_mm: float
    panel_height_mm: float
    board_count: int
    grid_x: int
    grid_y: int
    rail_width_mm: float
    depaneling_method: str  # "v_cut" or "mouse_bites"
    board_spacing_mm: float
    material_utilization_pct: float
    tooling_holes: list[ToolingHole] = field(default_factory=list)
    fiducials: list[OpticalFiducial] = field(default_factory=list)
    breakaway_tabs: list[BreakawayTab] = field(default_factory=list)
    v_cut_lines: list[dict[str, Any]] = field(default_factory=list)
    ipc_standard: str = "IPC-2221B Section 8.4 / IPC-SMEMA-9851"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tooling_holes"] = [asdict(h) for h in self.tooling_holes]
        d["fiducials"] = [asdict(f) for f in self.fiducials]
        d["breakaway_tabs"] = [asdict(t) for t in self.breakaway_tabs]
        return d


def calculate_pcb_panel_rails(
    board_width_mm: float,
    board_height_mm: float,
    grid_x: int = 2,
    grid_y: int = 2,
    depaneling_method: str = "v_cut",  # "v_cut" or "mouse_bites"
    rail_width_mm: float = 5.0,
    board_spacing_mm: float | None = None,
    rail_sides: str = "left_right",  # "left_right", "top_bottom", or "all_four"
    board_thickness_mm: float = 1.6,
) -> PanelFrameResult:
    """Calculate SMT panel frame with breakaway process rails, fiducials, and tooling holes.

    Parameters:
    - board_width_mm: Single PCB outline width (mm).
    - board_height_mm: Single PCB outline height (mm).
    - grid_x: Number of boards in X direction (default 2).
    - grid_y: Number of boards in Y direction (default 2).
    - depaneling_method: "v_cut" or "mouse_bites".
    - rail_width_mm: Conveyor clamping rail width (standard 5.0mm, min 3.0mm per SMEMA).
    - board_spacing_mm: Spacing between boards (default 0mm for V-cut, 2.0mm for mouse-bites).
    - rail_sides: "left_right" (standard 2 rails), "top_bottom", or "all_four".
    - board_thickness_mm: Nominal board thickness (standard 1.6mm).
    """
    grid_x = max(1, int(grid_x))
    grid_y = max(1, int(grid_y))
    rail_w = max(3.0, float(rail_width_mm))
    method = depaneling_method.lower().strip()
    if method not in ("v_cut", "mouse_bites", "tab_route"):
        method = "v_cut"

    # Default board spacing
    if board_spacing_mm is None:
        spacing = 0.0 if method == "v_cut" else 2.0
    else:
        spacing = max(0.0, float(board_spacing_mm))

    # Calculate active board area and panel dimensions
    boards_w = grid_x * board_width_mm + (grid_x - 1) * spacing
    boards_h = grid_y * board_height_mm + (grid_y - 1) * spacing

    has_x_rails = rail_sides in ("left_right", "all_four")
    has_y_rails = rail_sides in ("top_bottom", "all_four")

    panel_w = round(boards_w + (2.0 * rail_w if has_x_rails else 0.0), 2)
    panel_h = round(boards_h + (2.0 * rail_w if has_y_rails else 0.0), 2)

    total_board_area = grid_x * grid_y * board_width_mm * board_height_mm
    total_panel_area = panel_w * panel_h
    utilization_pct = round((total_board_area / total_panel_area) * 100.0, 1) if total_panel_area > 0 else 0.0

    # Origin offset for active board area
    offset_x = rail_w if has_x_rails else 0.0
    offset_y = rail_w if has_y_rails else 0.0

    # 1. SMEMA Standard Tooling Holes (NPTH Φ3.2mm on 3 corners to prevent reverse orientation)
    tooling_holes: list[ToolingHole] = []
    margin = min(rail_w / 2.0, 3.5) if (has_x_rails or has_y_rails) else 2.5
    tooling_holes.append(ToolingHole(x_mm=round(margin, 2), y_mm=round(margin, 2)))
    tooling_holes.append(ToolingHole(x_mm=round(panel_w - margin, 2), y_mm=round(margin, 2)))
    tooling_holes.append(ToolingHole(x_mm=round(margin, 2), y_mm=round(panel_h - margin, 2)))

    # 2. Optical Fiducials (Φ1.0mm pad + Φ3.0mm mask opening in asymmetric L-pattern)
    fiducials: list[OpticalFiducial] = []
    fid_off_x = round(rail_w / 2.0, 2) if has_x_rails else round(board_width_mm / 4.0, 2)
    fid_off_y = round(rail_w / 2.0, 2) if has_y_rails else round(board_height_mm / 4.0, 2)

    # 3 fiducials forming an unambiguous L-shape
    fiducials.append(OpticalFiducial(x_mm=round(fid_off_x, 2), y_mm=round(fid_off_y + 10.0, 2)))
    fiducials.append(OpticalFiducial(x_mm=round(panel_w - fid_off_x, 2), y_mm=round(fid_off_y + 10.0, 2)))
    fiducials.append(OpticalFiducial(x_mm=round(fid_off_x, 2), y_mm=round(panel_h - (fid_off_y + 10.0), 2)))

    # 3. De-paneling features: V-Cut lines or Mouse-bite tabs
    v_cuts: list[dict[str, Any]] = []
    tabs: list[BreakawayTab] = []

    if method == "v_cut":
        # Horizontal score lines
        for j in range(grid_y + 1):
            y_pos = round(offset_y + j * (board_height_mm + spacing), 2)
            v_cuts.append(
                {
                    "start": (0.0, y_pos),
                    "end": (panel_w, y_pos),
                    "angle_deg": 30,
                    "residual_web_mm": round(board_thickness_mm / 3.0, 2),
                }
            )
        # Vertical score lines
        for i in range(grid_x + 1):
            x_pos = round(offset_x + i * (board_width_mm + spacing), 2)
            v_cuts.append(
                {
                    "start": (x_pos, 0.0),
                    "end": (x_pos, panel_h),
                    "angle_deg": 30,
                    "residual_web_mm": round(board_thickness_mm / 3.0, 2),
                }
            )
    else:
        # Mouse-bites on tabs connecting boards to rails and board to board
        # Place tabs at the center of board edges
        for i in range(grid_x):
            for j in range(grid_y):
                bx = offset_x + i * (board_width_mm + spacing)
                by = offset_y + j * (board_height_mm + spacing)
                # Bottom tab
                tabs.append(BreakawayTab(center_x_mm=round(bx + board_width_mm / 2.0, 2), center_y_mm=round(by, 2), orientation="horizontal"))
                # Left tab
                tabs.append(BreakawayTab(center_x_mm=round(bx, 2), center_y_mm=round(by + board_height_mm / 2.0, 2), orientation="vertical"))
                # Top tab (if at top edge)
                if j == grid_y - 1:
                    tabs.append(BreakawayTab(center_x_mm=round(bx + board_width_mm / 2.0, 2), center_y_mm=round(by + board_height_mm, 2), orientation="horizontal"))
                # Right tab (if at right edge)
                if i == grid_x - 1:
                    tabs.append(BreakawayTab(center_x_mm=round(bx + board_width_mm, 2), center_y_mm=round(by + board_height_mm / 2.0, 2), orientation="vertical"))

    return PanelFrameResult(
        panel_width_mm=panel_w,
        panel_height_mm=panel_h,
        board_count=grid_x * grid_y,
        grid_x=grid_x,
        grid_y=grid_y,
        rail_width_mm=rail_w,
        depaneling_method=method,
        board_spacing_mm=spacing,
        material_utilization_pct=utilization_pct,
        tooling_holes=tooling_holes,
        fiducials=fiducials,
        breakaway_tabs=tabs,
        v_cut_lines=v_cuts,
    )
