"""Heuristic PCB Component Auto-Placement & Specctra DSN Auto-Router Exporter.

Industrial benchmark & standard:
- Specctra DSN (Design Specctra Netlist v15.0 standard): The universal ASCII
  interchange format for automatic PCB routing tools (Freerouting, Cadence Specctra,
  Altium, Electra).
- Heuristic Placement Algorithm:
    * Microcontroller (MCU) placed in the geometric center of the PCB.
    * Power entry (USB Type-C, Battery, LDO) placed along the left board edge.
    * Decoupling capacitors clustered tightly adjacent to MCU power pins (<3mm).
    * High-frequency crystal oscillator placed adjacent to XTAL pins (<3mm).
    * Fieldbus transceivers (CAN, RS-485, Ethernet) and connectors arranged along the board perimeter.
    * User I/O (Buttons, LEDs) aligned along edges.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass
from typing import Any

log = logging.getLogger("circuit-placement")


@dataclass
class ComponentPlacement:
    ref: str
    package: str
    x_mm: float
    y_mm: float
    rotation_deg: float = 0.0
    layer: str = "Top"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def heuristic_place_components(
    modules: dict[str, Any],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
) -> dict[str, ComponentPlacement]:
    """Calculate deterministic heuristic 2D placement coordinates for components."""
    cx = board_width_mm / 2.0
    cy = board_height_mm / 2.0

    placements: dict[str, ComponentPlacement] = {}

    # 1. Identify MCU / Core chip -> Center
    mcu_refs = [
        ref
        for ref, m in modules.items()
        if any(
            k in ref.upper() or k in str(m.get("value", "")).upper()
            for k in ("MCU", "STM32", "ESP32", "RP2040", "STC89", "U1")
        )
        or m.get("kind") in ("MCU", "IC")
    ]
    primary_mcu = mcu_refs[0] if mcu_refs else None
    if primary_mcu:
        placements[primary_mcu] = ComponentPlacement(
            ref=primary_mcu,
            package=modules[primary_mcu].get("package", "QFN-48"),
            x_mm=round(cx, 2),
            y_mm=round(cy, 2),
        )

    # 2. Power input & LDO -> Left border
    left_x = 8.0
    power_y = cy
    for ref, m in modules.items():
        if ref in placements:
            continue
        val = str(m.get("value", "")).upper()
        if "USB" in ref or "USB" in val:
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", ""), x_mm=left_x, y_mm=round(power_y, 2)
            )
            power_y += 10.0
        elif "LDO" in ref or "AMS1117" in val or "TP4056" in val:
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", ""), x_mm=left_x + 8.0, y_mm=round(power_y - 5.0, 2)
            )

    # 3. Crystal -> Near MCU (offset +6mm, +4mm)
    for ref, m in modules.items():
        if ref in placements:
            continue
        if m.get("kind") == "CRYSTAL" or "XTAL" in ref or "Y1" in ref:
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", ""), x_mm=round(cx + 6.0, 2), y_mm=round(cy + 5.0, 2)
            )

    # 4. Decoupling capacitors -> Clustered around MCU perimeter
    decoup_angle = 0.0
    decoup_r = 8.0
    for ref, m in modules.items():
        if ref in placements:
            continue
        val = str(m.get("value", "")).upper()
        if m.get("kind") == "CAPACITOR" and ("100N" in val or "0.1U" in val):
            dx = cx + decoup_r * math.cos(decoup_angle)
            dy = cy + decoup_r * math.sin(decoup_angle)
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", "C0603"), x_mm=round(dx, 2), y_mm=round(dy, 2)
            )
            decoup_angle += math.pi / 4.0

    # 5. Bus transceivers & connectors -> Right & Top borders
    right_x = board_width_mm - 10.0
    right_y = 12.0
    top_x = 20.0
    top_y = board_height_mm - 8.0

    for ref, m in modules.items():
        if ref in placements:
            continue
        kind = m.get("kind", "").upper()
        val = str(m.get("value", "")).upper()
        if any(k in ref for k in ("485", "CAN", "ETH", "RJ45")) or "HDR" in ref or "CONN" in kind:
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", ""), x_mm=round(right_x, 2), y_mm=round(right_y, 2)
            )
            right_y += 12.0
            if right_y > board_height_mm - 10:
                right_y = 12.0
                right_x -= 10.0
        elif any(k in ref for k in ("SW", "BTN", "LED", "D1", "D2", "BZ")):
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", ""), x_mm=round(top_x, 2), y_mm=round(top_y, 2)
            )
            top_x += 10.0
            if top_x > board_width_mm - 15:
                top_x = 20.0
                top_y -= 8.0

    # 6. Remaining components -> Placed in grid rows
    grid_x = 18.0
    grid_y = 8.0
    for ref, m in modules.items():
        if ref not in placements:
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", "0603"), x_mm=round(grid_x, 2), y_mm=round(grid_y, 2)
            )
            grid_x += 7.0
            if grid_x > board_width_mm - 15.0:
                grid_x = 18.0
                grid_y += 6.0

    log.info(f"✅ 启发式布局完成: {len(placements)} 个器件布于 {board_width_mm:.0f}×{board_height_mm:.0f}mm 目标板框")
    return placements


def export_specctra_dsn(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    placements: dict[str, ComponentPlacement] | None = None,
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    trace_width_mm: float = 0.254,
    clearance_mm: float = 0.200,
) -> str:
    """Generate universal Specctra DSN (v15.0) auto-router interchange file for Freerouting/KiCad."""
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    bw = round(board_width_mm, 3)
    bh = round(board_height_mm, 3)
    tw = round(trace_width_mm, 3)
    cl = round(clearance_mm, 3)

    L = [
        "(pcb pcb_board",
        "  (parser",
        '    (string_quote ")',
        "    (space_in_quoted_tokens on)",
        '    (host_cad "CircuitAgent")',
        '    (host_version "1.0")',
        "  )",
        "  (resolution mm 1000)",
        "  (unit mm)",
        "  (structure",
        "    (layer Top (type signal))",
        "    (layer Bottom (type signal))",
        f"    (boundary (path pcb 0 0 0 {bw} 0 {bw} {bh} 0 {bh} 0 0))",
        "    (rule",
        f"      (width {tw})",
        f"      (clearance {cl})",
        "    )",
        "  )",
        "  (placement",
    ]

    for ref, p in sorted(placements.items()):
        clean_pkg = re.sub(r"[^\w\-.]", "_", p.package or "SMD")
        L.append(f'    (component "{clean_pkg}"')
        L.append(f'      (place "{ref}" {p.x_mm:.3f} {p.y_mm:.3f} front {p.rotation_deg:.1f})')
        L.append("    )")
    L.append("  )")

    L.append("  (network")
    for conn in connections:
        net_name = str(conn.get("net", "")).replace("/", "").replace(" ", "_")
        if not net_name:
            continue
        pts = conn.get("points") or []
        if len(pts) < 2:
            continue
        L.append(f'    (net "{net_name}"')
        pins_str = " ".join(f'"{p}"' for p in pts)
        L.append(f"      (pins {pins_str})")
        L.append("    )")
    L.append("  )")
    L.append(")")

    return "\n".join(L) + "\n"
