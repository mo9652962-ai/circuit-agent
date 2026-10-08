"""In-Circuit Test (ICT) Bed-of-Nails Testpoint Allocator & Fault Coverage Analyzer.

Industrial benchmark & standards:
- IPC-9252: Requirements for Electrical Testing of Unpopulated Printed Boards.
  Defines universal test grids, probe targets, probe head geometries (crown, spear, serrated, cup),
  and 4-wire Kelvin contact resistance measurement criteria.
- IPC-2221B Section 12: Design for Testability (DFT) Guidelines.
  * Minimum testpad diameter: 1.0mm (standard 100-mil / 75-mil pogo probes; absolute minimum 0.8mm).
  * Minimum testpad center-to-center pitch: 1.27mm (50-mil) or 2.54mm (100-mil) to prevent probe deflection shorts.
  * Minimum clearance to adjacent tall SMT components: >= 2.0mm to clear probe socket guide plates.
  * Testpad side: bottom side (B.Cu) preferred for single-sided lower bed-of-nails fixture cost minimization.
- In-Circuit Test (ICT) fault coverage:
  Tracks critical testability coverage on Power (VBUS/3V3/5V/VBAT), Reference Ground (GND),
  Programming/Debug lines (SWDIO/SWCLK/RESET/BOOT), and communication buses (I2C/UART/CAN/485).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

GND_RE = re.compile(r"(^|/)(GND|AGND|DGND|PGND)$", re.IGNORECASE)
POWER_RE = re.compile(r"(VBUS|VCC|VDD|VIN|VOUT|VBAT|\+?3V3|\+?5V|\+12V|\+?1V8|\+?2V8)", re.IGNORECASE)
DEBUG_BUS_RE = re.compile(r"(SWD|SWCLK|SWDIO|NRST|RESET|BOOT|TX|RX|SCL|SDA|CAN|485|EN)", re.IGNORECASE)


@dataclass
class ICTTestpoint:
    net: str
    x_mm: float
    y_mm: float
    diameter_mm: float = 1.0  # Standard 1.0mm round testpad
    side: str = "Bottom"  # Bottom side preferred for single-stage bed of nails
    probe_type: str = "100mil_crown"  # 100mil_crown (power), 75mil_spear (signal), 50mil_serrated (dense)
    target_role: str = "signal"  # "power", "ground", "debug", "signal"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ICTCoverageReport:
    total_nets: int
    tested_nets_count: int
    net_coverage_pct: float
    power_coverage_pct: float
    uncovered_critical_nets: list[str]
    bed_of_nails_compatible: bool
    testpoints: list[ICTTestpoint] = field(default_factory=list)
    ipc_standard: str = "IPC-9252 / IPC-2221B Section 12"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["testpoints"] = [tp.to_dict() if hasattr(tp, "to_dict") else tp for tp in self.testpoints]
        return d


def calculate_ict_testpoints(
    connections: list[dict],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    min_pad_diameter_mm: float = 1.0,
    min_probe_pitch_mm: float = 2.0,
) -> ICTCoverageReport:
    """Analyze netlist testability, allocate bed-of-nails ICT testpoints, and compute fault coverage."""
    all_nets = [c.get("net", "") for c in connections if c.get("net")]
    unique_nets = sorted(set(all_nets))
    if not unique_nets:
        return ICTCoverageReport(
            total_nets=0,
            tested_nets_count=0,
            net_coverage_pct=0.0,
            power_coverage_pct=0.0,
            uncovered_critical_nets=[],
            bed_of_nails_compatible=False,
        )

    # Classify critical nets that require 100% ICT coverage
    power_nets = [n for n in unique_nets if POWER_RE.search(n)]
    gnd_nets = [n for n in unique_nets if GND_RE.search(n)]
    debug_nets = [n for n in unique_nets if DEBUG_BUS_RE.search(n)]
    critical_nets = set(power_nets + gnd_nets + debug_nets)

    # Place testpoints across the bottom grid with safe clearances (margin 5.0mm from board edge)
    testpoints: list[ICTTestpoint] = []
    curr_x = 8.0
    curr_y = 8.0
    dx = max(min_probe_pitch_mm, 2.54)
    dy = max(min_probe_pitch_mm, 2.54)
    max_x = board_width_mm - 8.0
    max_y = board_height_mm - 8.0

    covered_nets_set: set[str] = set()

    for net in unique_nets:
        # Determine probe style and role
        if GND_RE.search(net):
            p_type = "100mil_crown"
            role = "ground"
        elif POWER_RE.search(net):
            p_type = "100mil_crown"
            role = "power"
        elif DEBUG_BUS_RE.search(net):
            p_type = "75mil_spear"
            role = "debug"
        else:
            p_type = "50mil_serrated"
            role = "signal"

        if curr_x <= max_x and curr_y <= max_y:
            testpoints.append(
                ICTTestpoint(
                    net=net,
                    x_mm=round(curr_x, 2),
                    y_mm=round(curr_y, 2),
                    diameter_mm=min_pad_diameter_mm,
                    side="Bottom",
                    probe_type=p_type,
                    target_role=role,
                )
            )
            covered_nets_set.add(net)

            # Advance raster position on 2.54mm (100-mil) universal test grid
            curr_x += dx
            if curr_x > max_x:
                curr_x = 8.0
                curr_y += dy

    # Ground nets receive an extra Kelvin probe for precision resistance verification
    for gnd in gnd_nets:
        if curr_x <= max_x and curr_y <= max_y:
            testpoints.append(
                ICTTestpoint(
                    net=f"{gnd}_SENSE",
                    x_mm=round(curr_x, 2),
                    y_mm=round(curr_y, 2),
                    diameter_mm=min_pad_diameter_mm,
                    side="Bottom",
                    probe_type="100mil_crown",
                    target_role="ground",
                )
            )
            curr_x += dx
            if curr_x > max_x:
                curr_x = 8.0
                curr_y += dy

    uncovered_crit = sorted(critical_nets - covered_nets_set)
    total_cnt = len(unique_nets)
    tested_cnt = len(covered_nets_set)
    net_cov = round((tested_cnt / total_cnt) * 100.0, 1) if total_cnt > 0 else 0.0

    power_tested = len([n for n in power_nets if n in covered_nets_set])
    pwr_cov = round((power_tested / len(power_nets)) * 100.0, 1) if power_nets else 100.0

    compatible = (pwr_cov >= 100.0) and (net_cov >= 80.0) and (len(uncovered_crit) == 0)

    return ICTCoverageReport(
        total_nets=total_cnt,
        tested_nets_count=tested_cnt,
        net_coverage_pct=net_cov,
        power_coverage_pct=pwr_cov,
        uncovered_critical_nets=uncovered_crit,
        bed_of_nails_compatible=compatible,
        testpoints=testpoints,
    )
