"""Standard PCB Layer Stackup Architecture & Controlled Impedance Matrix (IPC-2141A).

Industrial benchmark & standard:
- IPC-2141A: Design Guide for High-Speed Controlled Impedance Circuit Boards.
- JLCPCB / Standard PCB Fab standard 4-layer (JLC04161H) and 6-layer (JLC06161H) stackup matrices.
- Pre-computes target track geometries for standard controlled impedance nets:
  * 50Ω Single-Ended RF / High-Speed Clock (Microstrip)
  * 90Ω Differential USB 2.0 (D+/D-)
  * 100Ω Differential 100Base-TX / PCIe / LVDS
  * 120Ω Differential CAN-FD / RS-485
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Any

log = logging.getLogger("circuit-stackup")


@dataclass
class LayerSpec:
    name: str
    kind: str           # "signal" | "plane" | "dielectric" | "core"
    thickness_mm: float
    copper_weight_oz: float = 0.0
    er: float = 4.2
    loss_tangent: float = 0.02


@dataclass
class TargetImpedanceSpec:
    bus_type: str
    target_z_ohms: float
    mode: str           # "single_ended" | "differential"
    trace_width_mm: float
    trace_gap_mm: float = 0.0
    tolerance_pct: float = 10.0
    standard_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StackupProfile:
    stackup_id: str
    name_cn: str
    layer_count: int
    total_thickness_mm: float
    layers: list[LayerSpec]
    impedance_matrix: list[TargetImpedanceSpec]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["impedance_matrix"] = [im.to_dict() if hasattr(im, "to_dict") else im for im in self.impedance_matrix]
        return d


STACKUP_DATABASE: dict[str, StackupProfile] = {
    "JLC04161H": StackupProfile(
        stackup_id="JLC04161H",
        name_cn="嘉立创标准四层板 1.6mm (JLC04161H-7628)",
        layer_count=4,
        total_thickness_mm=1.60,
        layers=[
            LayerSpec(name="L1_Top", kind="signal", thickness_mm=0.035, copper_weight_oz=1.0),
            LayerSpec(name="Prepreg_7628", kind="dielectric", thickness_mm=0.210, er=4.4),
            LayerSpec(name="L2_GND", kind="plane", thickness_mm=0.035, copper_weight_oz=1.0),
            LayerSpec(name="Core_FR4", kind="core", thickness_mm=1.065, er=4.5),
            LayerSpec(name="L3_PWR", kind="plane", thickness_mm=0.035, copper_weight_oz=1.0),
            LayerSpec(name="Prepreg_7628", kind="dielectric", thickness_mm=0.210, er=4.4),
            LayerSpec(name="L4_Bottom", kind="signal", thickness_mm=0.035, copper_weight_oz=1.0),
        ],
        impedance_matrix=[
            TargetImpedanceSpec(
                bus_type="RF_50R", target_z_ohms=50.0, mode="single_ended",
                trace_width_mm=0.380, standard_ref="IPC-2141A Surface Microstrip 50Ω",
            ),
            TargetImpedanceSpec(
                bus_type="USB_90R", target_z_ohms=90.0, mode="differential",
                trace_width_mm=0.200, trace_gap_mm=0.150, standard_ref="USB 2.0 High-Speed 90Ω Diff Pair",
            ),
            TargetImpedanceSpec(
                bus_type="ETH_100R", target_z_ohms=100.0, mode="differential",
                trace_width_mm=0.180, trace_gap_mm=0.200, standard_ref="100Base-TX / PCIe 100Ω Diff Pair",
            ),
            TargetImpedanceSpec(
                bus_type="CAN_RS485_120R", target_z_ohms=120.0, mode="differential",
                trace_width_mm=0.150, trace_gap_mm=0.250, standard_ref="ISO 11898-2 CAN / TIA-485-A 120Ω Diff Bus",
            ),
        ],
    ),
    "JLC06161H": StackupProfile(
        stackup_id="JLC06161H",
        name_cn="嘉立创标准六层板 1.6mm (JLC06161H-3313)",
        layer_count=6,
        total_thickness_mm=1.60,
        layers=[
            LayerSpec(name="L1_Top_Signal", kind="signal", thickness_mm=0.035, copper_weight_oz=1.0),
            LayerSpec(name="Prepreg_3313", kind="dielectric", thickness_mm=0.100, er=4.1),
            LayerSpec(name="L2_GND_Plane", kind="plane", thickness_mm=0.035, copper_weight_oz=1.0),
            LayerSpec(name="Core_1", kind="core", thickness_mm=0.450, er=4.5),
            LayerSpec(name="L3_Inner_Signal", kind="signal", thickness_mm=0.035, copper_weight_oz=1.0),
            LayerSpec(name="Prepreg_7628", kind="dielectric", thickness_mm=0.200, er=4.4),
            LayerSpec(name="L4_PWR_Plane", kind="plane", thickness_mm=0.035, copper_weight_oz=1.0),
            LayerSpec(name="Core_2", kind="core", thickness_mm=0.450, er=4.5),
            LayerSpec(name="L5_GND_Plane", kind="plane", thickness_mm=0.035, copper_weight_oz=1.0),
            LayerSpec(name="Prepreg_3313", kind="dielectric", thickness_mm=0.100, er=4.1),
            LayerSpec(name="L6_Bottom_Signal", kind="signal", thickness_mm=0.035, copper_weight_oz=1.0),
        ],
        impedance_matrix=[
            TargetImpedanceSpec(
                bus_type="RF_50R", target_z_ohms=50.0, mode="single_ended",
                trace_width_mm=0.180, standard_ref="Thin Prepreg L1-L2 50Ω Microstrip",
            ),
            TargetImpedanceSpec(
                bus_type="USB_90R", target_z_ohms=90.0, mode="differential",
                trace_width_mm=0.120, trace_gap_mm=0.150, standard_ref="USB 2.0 90Ω Diff Pair",
            ),
            TargetImpedanceSpec(
                bus_type="ETH_100R", target_z_ohms=100.0, mode="differential",
                trace_width_mm=0.110, trace_gap_mm=0.180, standard_ref="Ethernet 100Ω Diff Pair",
            ),
            TargetImpedanceSpec(
                bus_type="CAN_RS485_120R", target_z_ohms=120.0, mode="differential",
                trace_width_mm=0.090, trace_gap_mm=0.220, standard_ref="CAN / RS-485 120Ω Diff Pair",
            ),
        ],
    ),
}

DEFAULT_STACKUP = "JLC04161H"


def get_stackup_profile(stackup_id: str | None = None) -> StackupProfile:
    """Retrieve standard PCB stackup and controlled impedance recommendations."""
    if not stackup_id:
        return STACKUP_DATABASE[DEFAULT_STACKUP]
    u_id = stackup_id.upper().strip()
    return STACKUP_DATABASE.get(u_id, STACKUP_DATABASE[DEFAULT_STACKUP])


def solve_target_trace_width(
    target_z_ohms: float,
    h_mm: float = 0.21,
    er: float = 4.4,
    t_mm: float = 0.035,
) -> float:
    """Invert IPC-2141 microstrip equation to solve recommended trace width W for target Z0."""
    # Bisection solver between 0.05mm and 3.0mm
    low_w = 0.05
    high_w = 3.0

    def calc_z(w: float) -> float:
        w_eff = w + (t_mm / math.pi) * (1.0 + math.log(2.0 * h_mm / t_mm if t_mm > 0 else 1.0))
        u = w_eff / h_mm
        e_eff = (er + 1.0) / 2.0 + ((er - 1.0) / 2.0) * (1.0 / math.sqrt(1.0 + 12.0 / u))
        return (87.0 / math.sqrt(e_eff + 1.41)) * math.log(5.98 * h_mm / (0.8 * w_eff + t_mm))

    for _ in range(40):
        mid_w = (low_w + high_w) / 2.0
        z_mid = calc_z(mid_w)
        if z_mid > target_z_ohms:
            low_w = mid_w
        else:
            high_w = mid_w

    return round(mid_w, 3)
