"""IPC-D-356A Bare Board Electrical Test Format Direct Exporter.

Industrial benchmark & standard:
- IPC-D-356A (Standard for Bare Board Electrical Test Information).
- Universal interchange format consumed by flying probe testers (AEMG, ATG,
  MicroCraft, Gardien) and bed-of-nails test fixture generators worldwide.
- Standard 80-column fixed-width card record format:
  * 317: Component pin / SMD pad test point
  * 327: Dedicated test point pad
  * Header records: P  JOB, P  UNITS, C  COMMENTS
"""

from __future__ import annotations

import logging
from typing import Any

from .placement_engine import heuristic_place_components

log = logging.getLogger("circuit-ipc-d356")


def _format_coord(val_mm: float, prefix: str) -> str:
    """Format coordinate in mil tenths (0.0001 in) with leading sign and 6 digits."""
    val_mils = val_mm / 0.0254 * 10.0  # units in 0.1 mil
    sign = "+" if val_mils >= 0 else "-"
    abs_int = min(round(abs(val_mils)), 999999)
    return f"{prefix}{sign}{abs_int:06d}"


def export_ipc_d356(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    job_name: str = "CIRCUIT_AGENT_PCB",
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
) -> str:
    """Generate production IPC-D-356A ASCII electrical bare-board test netlist."""
    placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    lines = [
        "P  JOB " + job_name[:20].upper(),
        "P  UNITS CUST 0",
        "C  IPC-D-356A BARE BOARD ELECTRICAL TEST NETLIST",
        "C  GENERATOR: CircuitAgent Enterprise Netlist Compiler",
        "C  FORMAT: FIXED-WIDTH 80-COLUMN CARD IMAGE",
        "C  ----------------------------------------------------------------",
    ]

    # Map each pin connection: (ref, pin) -> net
    pin_to_net: dict[tuple[str, str], str] = {}
    for conn in connections:
        net = str(conn.get("net", "")).replace("/", "").replace("+", "P").replace("-", "N")
        for pt in conn.get("points") or []:
            if "." in pt:
                ref, pin = pt.split(".", 1)
                pin_to_net[(ref, pin)] = net

    for ref, comp in sorted(modules.items()):
        p = placements.get(ref)
        if not p:
            continue
        kind = str(comp.get("kind", "")).upper()
        is_testpoint = "TESTPOINT" in kind or "TP" in ref

        # Find all declared or connected pins
        connected_pins = [pin for (r, pin) in pin_to_net if r == ref]
        if not connected_pins:
            connected_pins = ["1"]

        for pin in connected_pins:
            net = pin_to_net.get((ref, pin), "UNCONNECTED")[:14].ljust(14)
            ref_field = ref[:8].ljust(8)
            pin_field = pin[:4].ljust(4)

            record_type = "327" if is_testpoint else "317"
            pad_type = "M"  # Surface mount
            access = "A01"  # Top layer access (A01=Top, A02=Bottom)

            coord_str = _format_coord(p.x_mm, "X") + _format_coord(p.y_mm, "Y")
            dim_str = "X0500Y0500"  # 50x50 mil nominal pad size

            line = f"{record_type} {net} {ref_field}{pin_field}{pad_type}{access}{coord_str}{dim_str}"
            lines.append(line.ljust(80)[:80])

    lines.append("C  ----------------------------------------------------------------")
    lines.append("999")  # End of data record

    log.info(f"✅ 生成 IPC-D-356A 飞针测试网表: {len(lines)} 行记录")
    return "\n".join(lines) + "\n"
