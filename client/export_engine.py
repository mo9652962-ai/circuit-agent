"""Production Manufacturing & EDA Export Engine (Community & Enterprise Edition).

Provides seamless bridges to:
  1. KiCad 6/7/8/9/10 S-Expression Netlist (.net): Direct import into Pcbnew without schematic entry.
  2. JLCPCB Production BOM (CSV): Grouped by value/package/LCSC, with Basic/Extended classification.
  3. JLCPCB Production CPL / Centroid (CSV): Tape-and-reel rotation corrections (QFN +270°, SOT-23 +180°).
  4. ASCII System Topology Diagram: Visual architecture overview of power rails, buses, and peripherals.

Zero external runtime dependencies: 100% Python standard library.
"""

from __future__ import annotations

import csv
import io
import re
import time
from typing import Any

# Standard rotation correction table for JLCPCB tape-and-reel SMT feeders
# Reference: specs/cpl_standard.md & JLCKicadTools
DEFAULT_ROTATION_RULES: list[tuple[str, float]] = [
    (r"(^|[_:])QFN[-_]", 270.0),
    (r"(^|[_:])DFN[-_]", 270.0),
    (r"RP2040[-_]", 270.0),
    (r"ESP32[-_]", 270.0),
    (r"(^|[_:])L?TQFP[-_]", 270.0),
    (r"(^|[_:])LQFP[-_]", 270.0),
    (r"(^|[_:])HTSSOP[-_]", 270.0),
    (r"(^|[_:])TSSOP[-_]", 270.0),
    (r"(^|[_:])MSOP[-_]", 270.0),
    (r"(^|[_:])SSOP[-_]", 270.0),
    (r"(^|[_:])SOIC[-_]", 270.0),
    (r"(^|[_:])SOP[-_]", 270.0),
    (r"(^|[_:])SOT[-_]23($|[-_])", 180.0),
    (r"(^|[_:])SOT[-_]223($|[-_])", 180.0),
    (r"(^|[_:])SOT[-_]89($|[-_])", 180.0),
    (r"D_SOT[-_]23", 180.0),
    (r"TSOT[-_]23", 180.0),
    (r"D_SOD[-_]123", 180.0),
    (r"D_SOD[-_]323", 180.0),
    (r"D_SMA", 180.0),
    (r"D_SMB", 180.0),
    (r"D_SMC", 180.0),
    (r"SW_SPST_B3", 90.0),
    (r"SW_PUSH", 90.0),
    (r"USB_C_Receptacle", 180.0),
    (r"Type[-_]?C", 180.0),
    (r"CP_Elec", 180.0),
    (r"CP_EIA", 180.0),
]


def _extract_components_and_connections(raw_netlist: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract normalized components and connections from raw dictionary or wrapped netlist."""
    nl = raw_netlist.get("netlist") if "netlist" in raw_netlist and isinstance(raw_netlist["netlist"], dict) else raw_netlist
    components = nl.get("components", [])
    if not components:
        src_modules = raw_netlist.get("modules") or nl.get("modules")
        if isinstance(src_modules, dict):
            components = [{"ref": ref, **info} for ref, info in src_modules.items() if isinstance(info, dict)]

    connections = nl.get("connections", [])
    if not connections and "connections" in raw_netlist:
        connections = raw_netlist.get("connections", [])
    return components, connections


def get_cpl_rotation_offset(package: str) -> float:
    """Determine SMT pick-and-place rotation correction angle for a package."""
    for pattern, angle in DEFAULT_ROTATION_RULES:
        if re.search(pattern, package, re.IGNORECASE):
            return angle
    return 0.0


# --------------------------------------------------------------------------- #
# 1. KiCad S-Expression Netlist Exporter
# --------------------------------------------------------------------------- #

def export_kicad_netlist(netlist_data: dict[str, Any], title: str = "CircuitAgent_Design") -> str:
    """Export standard KiCad S-Expression Netlist format (version E) compatible with KiCad 6/7/8/9/10.

    Can be imported directly into KiCad Pcbnew via File -> Import -> Netlist.
    """
    components, connections = _extract_components_and_connections(netlist_data)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        '(export (version "E")',
        '  (design',
        f'    (source "{title}.kicad_sch")',
        f'    (date "{timestamp}")',
        '    (tool "CircuitAgent Industrial Compiler")',
        '  )',
        '  (components',
    ]

    for comp in sorted(components, key=lambda c: c.get("ref", "")):
        ref = comp.get("ref", "U?")
        val = comp.get("value", "")
        pkg = comp.get("package", "")
        lcsc = comp.get("lcsc", "")
        lines.append(f'    (comp (ref "{ref}")')
        lines.append(f'      (value "{val}")')
        lines.append(f'      (footprint "{pkg}")')
        lines.append('      (fields')
        if lcsc:
            lines.append(f'        (field (name "LCSC") "{lcsc}")')
        lines.append('        (field (name "Source") "CircuitAgent")')
        lines.append('      )')
        lines.append('    )')
    lines.append('  )')

    lines.append('  (nets')
    for code, conn in enumerate(connections, start=1):
        net_name = conn.get("net", f"Net-(N{code})")
        points = conn.get("points", [])
        lines.append(f'    (net (code "{code}") (name "{net_name}")')
        for pt in points:
            if "." in pt:
                ref, pin = pt.split(".", 1)
                lines.append(f'      (node (ref "{ref}") (pin "{pin}"))')
        lines.append('    )')
    lines.append('  )')
    lines.append(')')

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# 2. JLCPCB Production BOM Exporter (CSV)
# --------------------------------------------------------------------------- #

def export_jlcpcb_bom(netlist_data: dict[str, Any]) -> str:
    """Generate JLCPCB-compliant production BOM CSV.

    Columns: Comment, Designator, Footprint, LCSC Part Number, JLCPCB Part Class, Quantity
    Groups identical parts into single rows and flags Basic vs Extended parts.
    """
    components, _ = _extract_components_and_connections(netlist_data)

    # Grouping key: (value, package, lcsc)
    groups: dict[tuple[str, str, str], list[str]] = {}
    for comp in components:
        ref = comp.get("ref", "")
        val = comp.get("value", "")
        pkg = comp.get("package", "")
        lcsc = comp.get("lcsc", "")
        key = (val, pkg, lcsc)
        groups.setdefault(key, []).append(ref)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part Number", "JLCPCB Part Class", "Quantity"])

    for (val, pkg, lcsc), refs in sorted(groups.items(), key=lambda x: x[0][0]):
        # Sort designators with natural numeric order: R1, R2, R10
        sorted_refs = sorted(refs, key=lambda r: (re.sub(r"\d+", "", r), int(re.search(r"\d+", r).group(0)) if re.search(r"\d+", r) else 0))
        des_str = ",".join(sorted_refs)
        part_class = "Basic Part" if pkg in ("0603", "0805", "SOT-23", "SOT-223") and lcsc.startswith("C") else "Extended Part"
        writer.writerow([val, des_str, pkg, lcsc, part_class, len(refs)])

    return output.getvalue()


# --------------------------------------------------------------------------- #
# 3. JLCPCB Production CPL / Centroid Exporter (CSV)
# --------------------------------------------------------------------------- #

def export_jlcpcb_cpl(netlist_data: dict[str, Any], default_layer: str = "Top") -> str:
    """Generate JLCPCB SMT Component Placement List (CPL) centroid file with tape-and-reel rotation corrections."""
    components, _ = _extract_components_and_connections(netlist_data)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation", "Val", "Package"])

    for comp in sorted(components, key=lambda c: c.get("ref", "")):
        ref = comp.get("ref", "")
        val = comp.get("value", "")
        pkg = comp.get("package", "")
        pos_x = float(comp.get("x", 0.0))
        pos_y = float(comp.get("y", 0.0))
        raw_rot = float(comp.get("rotation", 0.0))
        corr_angle = (raw_rot + get_cpl_rotation_offset(pkg)) % 360.0
        writer.writerow([ref, f"{pos_x:.3f}mm", f"{pos_y:.3f}mm", default_layer, f"{corr_angle:.1f}", val, pkg])

    return output.getvalue()


# --------------------------------------------------------------------------- #
# 4. ASCII System Topology Diagram Generator
# --------------------------------------------------------------------------- #

def render_ascii_topology(netlist_data: dict[str, Any]) -> str:
    """Render a clean, structured ASCII architectural diagram of the hardware system."""
    components, connections = _extract_components_and_connections(netlist_data)
    chip_id = netlist_data.get("chip_id", "Main MCU")

    power_rails = sorted({c.get("net") for c in connections if any(p in c.get("net", "").upper() for p in ("VBUS", "VCC", "3.3V", "5V", "VBAT"))})
    busses = sorted({c.get("net") for c in connections if any(b in c.get("net", "").upper() for b in ("SCL", "SDA", "TX", "RX", "CAN", "RS485"))})

    sensor_blocks = [c.get("ref") for c in components if any(s in c.get("ref", "").upper() for s in ("U_AHT", "U_MPU", "SENSOR"))]
    comm_blocks = [c.get("ref") for c in components if any(s in c.get("ref", "").upper() for s in ("U_485", "U_CAN", "CH340", "USB"))]
    prot_blocks = [c.get("ref") for c in components if any(s in c.get("ref", "").upper() for s in ("D_TVS", "D_REV", "FB_", "TP_"))]

    lines = [
        "=======================================================================",
        f"               SYSTEM ARCHITECTURE TOPOLOGY: {chip_id}",
        "=======================================================================",
        " Power Domain Rails:",
    ]
    for p in power_rails:
        lines.append(f"   [== {p} ==]")
    lines.append("")
    lines.append("                  +-----------------------------------+")
    lines.append(f"                  |       {chip_id.center(27)} |")
    lines.append("                  |   (Core Controller & Pin Mappings)|")
    lines.append("                  +-----------------+-----------------+")
    lines.append("                                    |")

    if busses:
        lines.append("   ----------------- Communication & Sensor Busses -----------------")
        for b in busses:
            lines.append(f"   <---> Net: {b:<20}")
        lines.append("   -----------------------------------------------------------------")

    lines.append(" Subsystems & Functional Modules:")
    lines.append(f"   * Sensors & Actuators: {', '.join(sensor_blocks) if sensor_blocks else 'None'}")
    lines.append(f"   * Transceivers & Comms: {', '.join(comm_blocks) if comm_blocks else 'None'}")
    lines.append(f"   * Protection & Test:  {', '.join(prot_blocks) if prot_blocks else 'None'}")
    lines.append(f" Total Components: {len(components)} | Total Nets: {len(connections)}")
    lines.append("=======================================================================")

    return "\n".join(lines)
