"""IPC-9252B Bare-Board Electrical Test (Continuity & Isolation) Planner & Safety Auditor.

Industrial & Authoritative Standards:
- IPC-9252B (Requirements for Electrical Testing of Unpopulated Printed Boards):
  Governs continuity and isolation testing of bare PCBs across Flying Probe (FPT) and Bed-of-Nails (ICT) fixtures:
    * Continuity Testing: Verifies integrity of conductor paths. Standard threshold is 5 to 50 Ohms
      (typically <= 10 Ohms for signal nets, <= 2 Ohms for high-current power planes), with test current
      limited between 10 mA and 100 mA to prevent fuse melting of narrow 3 mil traces.
    * Isolation (Insulation Resistance) Testing: Detects micro-shorts, dendrites, and etching slivers.
      Mandated test voltages:
        - Class 1: 40V ~ 50V DC (threshold >= 2 MOhms)
        - Class 2: 100V DC (threshold >= 10 MOhms)
        - Class 3: 250V DC (threshold >= 100 MOhms)
    * Dielectric Breakdown Overstress Protection:
      For fine-pitch designs (spacing < 0.100 mm / 3.94 mil) or nets terminating at sensitive micro-vias,
      250V DC air breakdown potential can spark localized arc-over ionization in uncleaned cavities,
      damaging adjacent thin copper features. Test voltage must be derated to 50V~100V with extended dwell time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NetTestParameter:
    """Electrical test parameters planned for a specific net or net-pair."""

    net_name: str
    net_type: str  # 'power' | 'ground' | 'high_speed' | 'fine_pitch' | 'standard'
    continuity_test_voltage_v: float
    continuity_max_current_ma: float
    continuity_threshold_ohms: float
    isolation_test_voltage_v: float
    isolation_threshold_mohms: float
    min_dwell_time_ms: float
    is_voltage_derated: bool
    derating_reason: str


@dataclass
class BareBoardTestPlan:
    """Comprehensive bare board electrical test plan and electrical overstress risk audit."""

    target_class: str
    tester_type: str  # 'flying_probe' | 'universal_grid'
    total_nets_evaluated: int
    derated_nets_count: int
    has_overstress_risk: bool
    continuity_summary: dict[str, Any]
    isolation_summary: dict[str, Any]
    net_parameters: list[NetTestParameter] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_class": self.target_class,
            "tester_type": self.tester_type,
            "total_nets_evaluated": self.total_nets_evaluated,
            "derated_nets_count": self.derated_nets_count,
            "has_overstress_risk": self.has_overstress_risk,
            "continuity_summary": self.continuity_summary,
            "isolation_summary": self.isolation_summary,
            "net_parameters": [
                {
                    "net_name": np.net_name,
                    "net_type": np.net_type,
                    "continuity_voltage_v": np.continuity_test_voltage_v,
                    "continuity_max_ma": np.continuity_max_current_ma,
                    "continuity_threshold_ohms": np.continuity_threshold_ohms,
                    "isolation_voltage_v": np.isolation_test_voltage_v,
                    "isolation_threshold_mohms": np.isolation_threshold_mohms,
                    "dwell_ms": np.min_dwell_time_ms,
                    "is_derated": np.is_voltage_derated,
                    "derating_reason": np.derating_reason,
                }
                for np in self.net_parameters
            ],
            "standards_cited": self.standards_cited,
        }


def plan_bare_board_test_parameters(
    nets: list[dict[str, Any]] | None = None,
    target_class: str = "Class 2",
    tester_type: str = "flying_probe",
    min_trace_clearance_mm: float = 0.127,
    has_sensitive_rf_nets: bool = False,
) -> BareBoardTestPlan:
    """Plan IPC-9252B compliant continuity and isolation electrical test recipes and guard against voltage overstress.

    Args:
        nets: Optional list of net definitions ({name, min_clearance_mm, is_power, is_sensitive, ...})
        target_class: IPC reliability class ('Class 1', 'Class 2', 'Class 3')
        tester_type: 'flying_probe' (FPT) or 'universal_grid' (Bed-of-Nails)
        min_trace_clearance_mm: Board-level minimum conductor gap in mm (default: 0.127mm / 5 mil)
        has_sensitive_rf_nets: True if board contains ultra-sensitive RF/microwave structures

    Returns:
        BareBoardTestPlan: Full test voltage, current threshold, and safety derating plan
    """
    cls_key = "Class 3" if "3" in str(target_class) else ("Class 1" if "1" in str(target_class) else "Class 2")

    # Baseline limits per IPC-9252B Table 4-1
    if cls_key == "Class 3":
        base_cont_thresh = 5.0  # <= 5 Ohms
        base_iso_volt = 250.0  # 250V DC
        base_iso_thresh = 100.0  # >= 100 MOhms
    elif cls_key == "Class 1":
        base_cont_thresh = 20.0  # <= 20 Ohms
        base_iso_volt = 50.0  # 50V DC
        base_iso_thresh = 2.0  # >= 2 MOhms
    else:  # Class 2
        base_cont_thresh = 10.0  # <= 10 Ohms
        base_iso_volt = 100.0  # 100V DC
        base_iso_thresh = 10.0  # >= 10 MOhms

    # Default dummy nets if unstated
    if not nets:
        nets = [
            {"name": "GND", "is_power": True, "min_clearance_mm": 0.200},
            {"name": "VCC_3V3", "is_power": True, "min_clearance_mm": 0.200},
            {"name": "SIGNAL_IO", "min_clearance_mm": min_trace_clearance_mm},
            {"name": "USB_DP", "is_sensitive": True, "min_clearance_mm": min_trace_clearance_mm},
        ]

    planned_params: list[NetTestParameter] = []
    derated_count = 0
    has_overstress = False

    for n in nets:
        net_name = str(n.get("name", "NET"))
        is_pwr = bool(n.get("is_power", False)) or net_name in ("GND", "VCC", "3V3", "5V", "+3.3V")
        is_sens = bool(n.get("is_sensitive", False)) or has_sensitive_rf_nets
        clr = float(n.get("min_clearance_mm", min_trace_clearance_mm))

        cont_v = 10.0 if not is_pwr else 5.0
        cont_ma = 50.0 if not is_pwr else 100.0
        cont_ohm = 2.0 if is_pwr else base_cont_thresh

        iso_v = base_iso_volt
        iso_mohm = base_iso_thresh
        dwell_ms = 10.0 if tester_type == "flying_probe" else 25.0
        is_derated = False
        reason = "Normal IPC baseline"

        # Check for dielectric overstress on fine-pitch conductor gaps:
        # Air dielectric strength ≈ 3 kV/mm. For 0.075mm gap, breakdown voltage is ~225V.
        # A 250V Class 3 isolation test can cause micro-arc breakdown!
        if clr < 0.100 and iso_v >= 200.0:
            iso_v = 100.0  # Derate to 100V
            dwell_ms = 40.0  # Extend dwell time to verify leakage at lower voltage
            is_derated = True
            derated_count += 1
            has_overstress = True
            reason = f"Conductor gap {clr:.3f}mm < 0.100mm: derated from 250V to 100V to prevent air breakdown arc-over."
        elif is_sens and iso_v > 100.0:
            iso_v = 100.0
            is_derated = True
            derated_count += 1
            reason = "Sensitive high-speed/RF net: isolation voltage clamped to 100V to avoid dielectric overstress."

        net_type = "power" if is_pwr else ("fine_pitch" if clr < 0.100 else ("sensitive" if is_sens else "standard"))

        planned_params.append(
            NetTestParameter(
                net_name=net_name,
                net_type=net_type,
                continuity_test_voltage_v=cont_v,
                continuity_max_current_ma=cont_ma,
                continuity_threshold_ohms=cont_ohm,
                isolation_test_voltage_v=iso_v,
                isolation_threshold_mohms=iso_mohm,
                min_dwell_time_ms=dwell_ms,
                is_voltage_derated=is_derated,
                derating_reason=reason,
            )
        )

    cited = [
        "IPC-9252B Requirements for Electrical Testing of Unpopulated Printed Boards §4.2-§4.4 Table 4-1",
        "IPC-A-600J Acceptability of Printed Boards §2.10 Electrical Continuity",
    ]

    return BareBoardTestPlan(
        target_class=cls_key,
        tester_type=tester_type,
        total_nets_evaluated=len(planned_params),
        derated_nets_count=derated_count,
        has_overstress_risk=has_overstress,
        continuity_summary={
            "default_test_voltage_v": 10.0,
            "max_current_ma": 50.0,
            "signal_threshold_ohms": base_cont_thresh,
            "power_threshold_ohms": 2.0,
        },
        isolation_summary={
            "default_test_voltage_v": base_iso_volt,
            "threshold_mohms": base_iso_thresh,
            "fine_pitch_derated_voltage_v": min(base_iso_volt, 100.0),
        },
        net_parameters=planned_params,
        standards_cited=cited,
    )
