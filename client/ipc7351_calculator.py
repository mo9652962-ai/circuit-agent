"""IPC-7351B SMT Land Pattern & Courtyard Calculator.

Industrial benchmark & standards:
- IPC-7351B: Generic Requirements for Surface Mount Design and Land Pattern Standard.
  Defines mathematical solder joint goals (Toe, Heel, Side) and statistical RMS tolerances
  across three standard Density Levels:
  * Density Level A (Most / Maximum): Robust solder fillets, high-reliability/military,
    wave soldering compatibility or manual rework (Code 'M').
  * Density Level B (Nominal / Median): Standard commercial equipment, consumer electronics (Code 'N').
  * Density Level C (Least / Minimum): Ultra-compact mobile, dense handheld packaging (Code 'L').
- Courtyard Excess:
  * Level A: 0.50 mm perimeter clearance.
  * Level B: 0.25 mm perimeter clearance.
  * Level C: 0.12 mm perimeter clearance.
- IPC Standard Naming Conventions:
  Generates standardized land pattern identifiers, e.g. RESC2012X60N, CAPC1608X90N, SOIC127P600X175-8N.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

# IPC-7351B Table 3-x Solder Joint Goals (in millimeters)
# Lead Type -> Density -> (Toe JT, Heel JH, Side JS, Courtyard CY)
IPC_SOLDER_GOALS: dict[str, dict[str, tuple[float, float, float, float]]] = {
    "chip": {
        "A": (0.55, 0.10, 0.05, 0.50),  # Most
        "B": (0.35, 0.00, -0.05, 0.25),  # Nominal
        "C": (0.15, -0.05, -0.10, 0.12),  # Least
    },
    "gullwing": {
        "A": (0.55, 0.45, 0.05, 0.50),
        "B": (0.35, 0.35, 0.03, 0.25),
        "C": (0.15, 0.25, 0.01, 0.12),
    },
    "no_lead": {  # QFN / DFN
        "A": (0.40, 0.00, -0.04, 0.50),
        "B": (0.30, 0.00, -0.05, 0.25),
        "C": (0.20, 0.00, -0.05, 0.12),
    },
    "j_lead": {  # PLCC / SOJ
        "A": (0.55, 0.45, 0.10, 0.50),
        "B": (0.35, 0.35, 0.05, 0.25),
        "C": (0.15, 0.25, 0.03, 0.12),
    },
}

# Standard Component Package Presets (Dimensions in mm: overall L, lead width W, contact band T, lead pitch, lead_type)
PACKAGE_PRESETS: dict[str, dict[str, Any]] = {
    "0201": {"type": "chip", "L": 0.60, "W": 0.30, "T": 0.15, "pitch": 0.0, "tol": 0.03},
    "0402": {"type": "chip", "L": 1.00, "W": 0.50, "T": 0.25, "pitch": 0.0, "tol": 0.05},
    "0603": {"type": "chip", "L": 1.60, "W": 0.80, "T": 0.35, "pitch": 0.0, "tol": 0.10},
    "0805": {"type": "chip", "L": 2.00, "W": 1.25, "T": 0.45, "pitch": 0.0, "tol": 0.15},
    "1206": {"type": "chip", "L": 3.20, "W": 1.60, "T": 0.50, "pitch": 0.0, "tol": 0.20},
    "1210": {"type": "chip", "L": 3.20, "W": 2.50, "T": 0.50, "pitch": 0.0, "tol": 0.20},
    "SOT-23": {"type": "gullwing", "L": 2.90, "W": 0.40, "T": 0.45, "pitch": 0.95, "tol": 0.10},
    "SOT-223": {"type": "gullwing", "L": 6.50, "W": 0.70, "T": 0.85, "pitch": 2.30, "tol": 0.15},
    "SOIC-8": {"type": "gullwing", "L": 6.00, "W": 0.42, "T": 0.70, "pitch": 1.27, "tol": 0.15},
    "TSSOP-14": {"type": "gullwing", "L": 6.40, "W": 0.25, "T": 0.60, "pitch": 0.65, "tol": 0.10},
    "QFN-32": {"type": "no_lead", "L": 5.00, "W": 0.25, "T": 0.40, "pitch": 0.50, "tol": 0.05},
    "LQFP-48": {"type": "gullwing", "L": 9.00, "W": 0.22, "T": 0.60, "pitch": 0.50, "tol": 0.10},
}


@dataclass
class IPC7351LandPatternResult:
    land_pattern_name: str
    package: str
    density_level: str  # A, B, C
    density_name: str  # Most, Nominal, Least
    pad_width_x_mm: float  # Pad X
    pad_length_y_mm: float  # Pad Y
    pad_center_c_mm: float  # Center distance C
    pad_outer_z_mm: float  # Outer pad boundary Zmax
    pad_inner_g_mm: float  # Inner pad boundary Gmin
    courtyard_width_mm: float
    courtyard_height_mm: float
    courtyard_bounds: tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
    courtyard_excess_mm: float
    toe_goal_mm: float
    heel_goal_mm: float
    side_goal_mm: float
    ipc_standard: str = "IPC-7351B Section 3.1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_ipc7351_land_pattern(
    package: str,
    density: str = "B",  # A (Most), B (Nominal), C (Least)
    lead_type: str | None = None,
    overall_length_l: float | None = None,
    lead_width_w: float | None = None,
    lead_contact_t: float | None = None,
    lead_pitch: float | None = None,
    fab_tolerance: float = 0.05,
    placement_tolerance: float = 0.05,
) -> IPC7351LandPatternResult:
    """Calculate mathematically compliant IPC-7351B surface mount land pattern geometry.

    Parameters:
    - package: Standard package name (e.g. '0805', '0603', 'SOIC-8', 'QFN-32') or custom name.
    - density: 'A' (Most/M), 'B' (Nominal/N), 'C' (Least/L). Default is 'B'.
    - lead_type: 'chip', 'gullwing', 'no_lead', or 'j_lead'.
    - overall_length_l: Component overall tip-to-tip span (mm).
    - lead_width_w: Component lead width (mm).
    - lead_contact_t: Component lead contact length/band (mm).
    - lead_pitch: Pin center-to-center pitch (mm) for multi-lead packages.
    - fab_tolerance: PCB fabrication tolerance (standard 0.05mm).
    - placement_tolerance: Pick-and-place accuracy tolerance (standard 0.05mm).
    """
    pkg_key = package.strip().upper()
    density_norm = density.strip().upper()
    if density_norm in ("MOST", "M", "A"):
        density_code = "A"
        density_suffix = "M"
        density_label = "Most (Maximum Protrusion)"
    elif density_norm in ("LEAST", "L", "C"):
        density_code = "C"
        density_suffix = "L"
        density_label = "Least (Minimum Protrusion)"
    else:
        density_code = "B"
        density_suffix = "N"
        density_label = "Nominal (Median Protrusion)"

    preset = PACKAGE_PRESETS.get(pkg_key, {})
    l_type = (lead_type or preset.get("type", "chip")).lower()
    if l_type not in IPC_SOLDER_GOALS:
        l_type = "chip"

    l_dim = overall_length_l if overall_length_l is not None else preset.get("L", 2.00)
    w_dim = lead_width_w if lead_width_w is not None else preset.get("W", 1.25)
    t_dim = lead_contact_t if lead_contact_t is not None else preset.get("T", 0.45)
    tol = preset.get("tol", 0.10)

    # Component body distance between opposing leads: S = L - 2*T
    s_dim = max(0.10, l_dim - 2.0 * t_dim)

    # Solder Joint Goals from IPC-7351B
    jt, jh, js, cy = IPC_SOLDER_GOALS[l_type][density_code]

    # Statistical RMS tolerance accumulation
    rms_l = math.sqrt(tol**2 + fab_tolerance**2 + placement_tolerance**2)
    rms_s = math.sqrt(tol**2 + fab_tolerance**2 + placement_tolerance**2)
    rms_w = math.sqrt(tol**2 + fab_tolerance**2 + placement_tolerance**2)

    # IPC-7351B Equations:
    # Zmax = Lmin + 2*JT + sqrt(C_L^2 + F^2 + P^2)
    # Gmin = Smax - 2*JH - sqrt(C_S^2 + F^2 + P^2)
    # Xmax = Wmin + 2*JS + sqrt(C_W^2 + F^2 + P^2)
    z_max = round(l_dim + 2.0 * jt + rms_l, 2)
    g_min = round(max(0.10, s_dim - 2.0 * jh - rms_s), 2)
    x_val = round(max(0.15, w_dim + 2.0 * js + rms_w), 2)

    # Pad length Y and pad center-to-center C
    y_val = round((z_max - g_min) / 2.0, 2)
    c_val = round((z_max + g_min) / 2.0, 2)

    # Round to IPC standard 0.05 mm grid
    x_val = round(round(x_val / 0.05) * 0.05, 2)
    y_val = round(round(y_val / 0.05) * 0.05, 2)
    c_val = round(round(c_val / 0.05) * 0.05, 2)
    z_max = round(c_val + y_val, 2)
    g_min = round(max(0.05, c_val - y_val), 2)

    # Courtyard Boundary Calculation (Pad bounds + CY buffer)
    total_pad_span_x = z_max
    total_pad_span_y = x_val
    cy_w = round(total_pad_span_x + 2.0 * cy, 2)
    cy_h = round(total_pad_span_y + 2.0 * cy, 2)
    cy_bounds = (-round(cy_w / 2.0, 2), -round(cy_h / 2.0, 2), round(cy_w / 2.0, 2), round(cy_h / 2.0, 2))

    # Standard IPC Land Pattern Name
    metric_code = f"{round(l_dim * 10):02d}{round(w_dim * 10):02d}"
    if l_type == "chip":
        prefix = "RESC" if "R" in pkg_key or "RES" in pkg_key else "CAPC"
        pat_name = f"{prefix}{metric_code}X{round(t_dim * 100):02d}{density_suffix}"
    elif l_type == "gullwing":
        p_val = lead_pitch or preset.get("pitch", 1.27)
        pat_name = f"SOIC{round(p_val * 100)}P{round(l_dim * 100)}X{round(t_dim * 100)}-{density_suffix}"
    else:
        pat_name = f"QFN{round(l_dim * 10)}P{round(t_dim * 100)}_{density_suffix}"

    return IPC7351LandPatternResult(
        land_pattern_name=pat_name,
        package=pkg_key,
        density_level=density_code,
        density_name=density_label,
        pad_width_x_mm=x_val,
        pad_length_y_mm=y_val,
        pad_center_c_mm=c_val,
        pad_outer_z_mm=z_max,
        pad_inner_g_mm=g_min,
        courtyard_width_mm=cy_w,
        courtyard_height_mm=cy_h,
        courtyard_bounds=cy_bounds,
        courtyard_excess_mm=cy,
        toe_goal_mm=jt,
        heel_goal_mm=jh,
        side_goal_mm=js,
    )
