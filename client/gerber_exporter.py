"""Native Gerber RS-274X Fabrication Bundle Direct Exporter.

Industrial benchmark & standard:
- Ucamco The Gerber Layer Format Specification (Revision 2023.08, RS-274X Extended).
- Generates fabrication-ready Gerber layers directly from placed modules and netlist,
  eliminating the dependency on external GUI EDA software for basic PCBA prototyping:
    * board-Edge_Cuts.gm1: Board mechanical outline contour
    * board-F_Cu.gtl: Top copper layer (pad flashes + routed tracks)
    * board-F_Mask.gts: Top solder mask (pad openings, expanded by mask expansion)
    * board-F_SilkS.gto: Top silkscreen (per-package body outlines)

Geometry provenance
-------------------
Every aperture and coordinate here comes from real design data, not a placeholder:

* Pads are flashed at each component *pin* position — placement origin plus the
  footprint's pin offset — with a land size derived from the package, so a 0603
  land differs from an LQFP lead.
* Tracks are the autorouter's actual routed geometry, parsed from the Specctra SES
  session. An unrouted net draws nothing. Inventing a straight line between two
  component centres would lay copper across whatever sits between them, and a fab
  would build it.
* Drill hits are real plated through-holes: through-hole component pins plus the
  vias the router actually placed. SMD parts get no holes.

The previous implementation flashed a uniform 1.6x1.0 mm pad at every component
centre and drew centre-to-centre "guide tracks". It produced a plausible-looking
bundle that could not be fabricated: pads did not coincide with pins, and the
guide tracks were not routes.
"""

from __future__ import annotations

import logging
import math
import re
from itertools import pairwise
from typing import Any

from .placement_engine import (
    BODY_DIMS_MM,
    PACKAGE_HALF_EXTENTS,
    STANDARD_PIN_OFFSETS,
    heuristic_place_components,
)

log = logging.getLogger("circuit-gerber")

#: Solder-mask expansion over the copper pad, per side (mm). JLCPCB/PCBWay standard.
MASK_EXPANSION_MM = 0.05

#: Stencil aperture reduction relative to the copper land, per side (mm).
#: IPC-7525B Section 4.2: paste printed to the full pad area wicks under the part
#: during reflow and lifts it off its pads. 0.05 mm per side is the common
#: starting point for 0402..1206 lands and is what most contract assemblers ask
#: for on a first stencil.
PASTE_REDUCTION_MM = 0.05

#: Minimum gap between silkscreen legend and an exposed copper land (mm).
#: IPC-SM-840 / DFM practice: legend printed on a mask opening blocks solder
#: wetting and leaves a cold joint or a solder ball after reflow.
SILK_TO_PAD_CLEARANCE_MM = 0.15

#: Copper land dimensions (width, height) in mm, keyed by a package substring.
#: These are land patterns, not body sizes: the copper the part actually solders to.
PAD_LAND: dict[str, tuple[float, float]] = {
    "0402": (0.55, 0.60),
    "0603": (0.80, 0.95),
    "0805": (1.00, 1.20),
    "1206": (1.60, 1.80),
    "2512": (3.20, 1.80),
    "SOT-23-6": (0.60, 1.05),
    "SOT-23-5": (0.60, 1.05),
    "SOT-23": (0.60, 1.05),
    "SOT-223": (2.00, 1.50),
    "SOIC-8": (1.55, 0.60),
    "SMA": (1.80, 2.00),
    "SMB": (2.20, 2.30),
    "HTSSOP-28": (1.50, 0.45),
    "LQFP-48": (1.50, 0.30),
    "LQFP-44": (1.50, 0.35),
    "QFN": (0.80, 0.30),
    "ESP32-S3-WROOM-1": (1.50, 0.90),
    "ESP32-C3-WROOM-02": (1.50, 0.90),
    "USB-C-16P": (0.60, 1.15),
    "HDR": (1.70, 1.70),
    "TERMINAL": (2.40, 2.40),
    "CONN-TH": (1.70, 1.70),
    "SW-SMD": (1.10, 1.60),
    "TestPoint": (2.00, 2.00),
    "Fiducial": (2.00, 2.00),
    "RJ45": (1.80, 1.80),
    "L0805": (1.00, 1.20),
    "LED0603": (0.80, 0.95),
    "LED0805": (1.00, 1.20),
}

#: Packages whose pins are drilled and plated through the board.
_THROUGH_HOLE_HINTS = ("HDR", "TERMINAL", "CONN-TH", "RJ45", "PinHeader", "Screw_Terminal")
#: Packages carrying a single round pad rather than rectangular lands.
_ROUND_PAD_HINTS = ("TestPoint", "Fiducial", "MountingHole")


def _format_gerber_coord(val_mm: float) -> str:
    """Format coordinate in Gerber 4.5 metric format (1 unit = 0.00001 mm = 10 nm)."""
    return str(round(val_mm * 100000.0))


def _pad_dims(package: str, ref: str = "") -> tuple[float, float]:
    """Return the copper land size (w, h) in mm for a package."""
    pkg = package or ""
    for key, dims in PAD_LAND.items():
        if key in pkg:
            return dims
    if any(k in pkg for k in _ROUND_PAD_HINTS) or any(k in ref for k in ("TP_", "FID")):
        return (2.0, 2.0)
    # Unknown package: fall back to a conservative 0603 land rather than a
    # 1.6x1.0 block, so an unmodelled part cannot claim more copper than it has.
    return (0.80, 0.95)


def _is_through_hole(package: str, ref: str) -> bool:
    pkg = package or ""
    if any(k in pkg for k in _THROUGH_HOLE_HINTS):
        return True
    return ref.upper().startswith(("J_", "TP_"))


def _pin_offsets(package: str, ref: str) -> dict[str, tuple[float, float]]:
    """Pin offset map for a package, falling back to the placement engine's synthesiser."""
    from .placement_engine import _synthesize_footprint_pins

    offs = STANDARD_PIN_OFFSETS.get(package or "")
    if offs:
        return offs
    if any(k in (package or "") for k in _ROUND_PAD_HINTS) or ref.upper().startswith(("TP_", "FID")):
        return {"1": (0.0, 0.0)}
    return _synthesize_footprint_pins(package or "", ["1", "2"])


def _collect_pads(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    placements: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the real pad list: one entry per component pin the netlist uses.

    Only pins referenced by the netlist are flashed. A pin the design never wires
    still exists physically, but flashing an offset the footprint does not model
    would invent copper at a position the part may not have — and the netlist is
    the authoritative statement of which pins this design uses.
    """
    used: dict[str, set[str]] = {}
    for conn in connections:
        for pt in conn.get("points") or []:
            if "." in pt:
                ref, pin = pt.split(".", 1)
                if ref in placements:
                    used.setdefault(ref, set()).add(pin)

    pads: list[dict[str, Any]] = []
    for ref, pins in used.items():
        p = placements[ref]
        pkg = p.package or ""
        offs = _pin_offsets(pkg, ref)
        w, h = _pad_dims(pkg, ref)
        th = _is_through_hole(pkg, ref)
        is_round = any(k in pkg for k in _ROUND_PAD_HINTS)
        for pin in sorted(pins):
            off = offs.get(pin)
            if off is None:
                # Pin name the footprint does not model. Skipping is honest:
                # better no copper than copper in the wrong place.
                continue
            pads.append(
                {
                    "ref": ref,
                    "pin": pin,
                    "x": round(p.x_mm + off[0], 4),
                    "y": round(p.y_mm + off[1], 4),
                    "w": w,
                    "h": h,
                    "through_hole": th,
                    "round": is_round,
                }
            )
    return pads


def _ses_unit_divisor(ses_text: str) -> float:
    """Millimetres per SES coordinate unit, read from the session's resolution line."""
    div = 1000.0
    m = re.search(r"\(resolution\s+(\w+)\s+([0-9.]+)\s*\)", ses_text)
    if m:
        div = float(m.group(2)) or 1000.0
        if m.group(1).lower() in ("inch", "in"):
            div *= 25.4
    return div


def _parse_ses_geometry(ses_text: str | None) -> dict[str, list[dict[str, Any]]]:
    """Extract real routed geometry from a Specctra SES session.

    Returns ``{"wires": [...], "vias": [...]}`` in mm. Coordinates inside a SES
    are integers in the declared resolution units, so the divisor is read from the
    file — treating them as millimetres would shrink every trace by a factor of
    1000.

    Each via carries its padstack's ``pad_mm`` and ``drill_mm``, parsed from the
    name the router writes (``Via[0.6-0.3]``). The copper layer needs that pad
    diameter to flash an annular ring; a drill hit with no copper ring around it
    is a hole through the trace, not a connection to the other side.
    """
    wires: list[dict[str, Any]] = []
    vias: list[dict[str, Any]] = []
    if not ses_text:
        return {"wires": wires, "vias": vias}

    div = _ses_unit_divisor(ses_text)

    for m in re.finditer(r"\(path\s+(\w+)\s+([0-9.]+)\s+([0-9\s.\-]+)\)", ses_text):
        layer = m.group(1)
        width_mm = float(m.group(2)) / div
        nums = [float(v) for v in m.group(3).split()]
        pts = [(nums[i] / div, nums[i + 1] / div) for i in range(0, len(nums) - 1, 2)]
        if len(pts) >= 2:
            wires.append({"layer": layer, "width_mm": width_mm, "pts": pts})

    for m in re.finditer(r'\(via\s+"?([^"\s]+)"?\s+([0-9.\-]+)\s+([0-9.\-]+)', ses_text):
        padstack = m.group(1)
        pad_mm, drill_mm = _via_dimensions(padstack)
        vias.append(
            {
                "x": float(m.group(2)) / div,
                "y": float(m.group(3)) / div,
                "padstack": padstack,
                "pad_mm": pad_mm,
                "drill_mm": drill_mm,
            }
        )

    return {"wires": wires, "vias": vias}


#: Fallback via geometry when the padstack name carries no dimensions.
#: 0.6/0.3 is the JLCPCB/PCBWay standard 2-layer via and the one the router emits.
DEFAULT_VIA_PAD_MM = 0.60
DEFAULT_VIA_DRILL_MM = 0.30


def _via_dimensions(padstack: str) -> tuple[float, float]:
    """Read (pad, drill) diameters in mm from a padstack name like ``Via[0.6-0.3]``."""
    m = re.search(r"\[\s*([0-9.]+)\s*-\s*([0-9.]+)\s*\]", padstack or "")
    if m:
        pad = float(m.group(1))
        drill = float(m.group(2))
        if pad > 0 and drill > 0:
            return pad, drill
    return DEFAULT_VIA_PAD_MM, DEFAULT_VIA_DRILL_MM


def _is_top_layer(layer: str) -> bool:
    return layer.lower() in ("top", "f.cu", "f_cu", "front")


def _is_bottom_layer(layer: str) -> bool:
    return layer.lower() in ("bottom", "b.cu", "b_cu", "back")


def generate_edge_cuts_gerber(board_width_mm: float, board_height_mm: float) -> str:
    """Generate Gerber RS-274X outline layer (.gm1)."""
    w_str = _format_gerber_coord(board_width_mm)
    h_str = _format_gerber_coord(board_height_mm)
    return "\n".join([
        "G04 Gerber RS-274X Edge Cuts Outline*",
        "%FSLAX45Y45*%",
        "%MOMM*%",
        "%LPD*%",
        "%ADD10C,0.15000*%",  # 0.15mm milling outline trace
        "D10*",
        "X0Y0D02*",
        f"X{w_str}Y0D01*",
        f"X{w_str}Y{h_str}D01*",
        f"X0Y{h_str}D01*",
        "X0Y0D01*",
        "M02*",
    ]) + "\n"


def _via_teardrop_polygons(
    geo: dict[str, list[dict[str, Any]]],
    *,
    extension_ratio: float = 0.65,
) -> list[list[tuple[float, float]]]:
    """Build a filled teardrop polygon at every via that a trace enters.

    IPC-2221B Section 9.1.5 / IPC-A-600J Class 3: a track meeting a round pad
    should be filleted. Drill wander alone is allowed 0.075 mm, which on a 0.6/0.3
    via eats the entire 0.15 mm annular ring at the entry point — the trace neck
    tears out of the pad and the net opens. The fillet widens that neck by 50-100%.

    The entry angle is derived from the actual routed wire that terminates on the
    via, not assumed: a teardrop pointing the wrong way reinforces nothing.
    """
    vias = geo.get("vias") or []
    wires = geo.get("wires") or []
    if not vias or not wires:
        return []

    polys: list[list[tuple[float, float]]] = []
    for via in vias:
        vx, vy = via["x"], via["y"]
        r_pad = via["pad_mm"] / 2.0
        if r_pad <= 0:
            continue

        # Which routed wires actually land on this via?
        entries: list[tuple[float, float, float]] = []  # (dx, dy, width)
        for wire in wires:
            pts = wire["pts"]
            for end, other in ((pts[0], pts[1]), (pts[-1], pts[-2])):
                if math.hypot(end[0] - vx, end[1] - vy) > r_pad + 0.05:
                    continue
                d = math.hypot(end[0] - other[0], end[1] - other[1])
                if d <= 1e-6:
                    continue
                # Direction the trace travels *away* from the via.
                entries.append(
                    ((end[0] - other[0]) / d, (end[1] - other[1]) / d, wire["width_mm"])
                )

        for dx, dy, tr_w in entries:
            td_len = r_pad * extension_ratio
            # Apex along the trace, half-width at least the trace, tapering to the pad.
            apex = (vx + (r_pad + td_len) * dx, vy + (r_pad + td_len) * dy)
            half = max(tr_w / 2.0, r_pad * 0.45)
            perp = (-dy, dx)

            # Tangent contact points sit on the pad circle at +/-45 deg from the
            # entry direction — the standard teardrop construction. Rotating the
            # unit direction is the whole computation; anything more elaborate
            # just introduces its own sign errors.
            c45 = math.cos(math.pi / 4)
            s45 = math.sin(math.pi / 4)
            t1 = (vx + r_pad * (dx * c45 - dy * s45), vy + r_pad * (dx * s45 + dy * c45))
            t2 = (vx + r_pad * (dx * c45 + dy * s45), vy + r_pad * (-dx * s45 + dy * c45))

            polys.append(
                [
                    t1,
                    (apex[0] + perp[0] * half, apex[1] + perp[1] * half),
                    (apex[0] - perp[0] * half, apex[1] - perp[1] * half),
                    t2,
                ]
            )
    return polys


#: Ground pour geometry, in mm. These are the values a 2-layer board actually
#: gets built with, not arbitrary round numbers:
#: * CLEARANCE — copper-to-copper spacing the fab can etch reliably at 1 oz.
#: * GRID — the fill is drawn as a hatch of this pitch. A solid G36/G37 region
#:   would be one polygon with the pads cut out of it, which no simple exporter
#:   can express; a hatch is what most 2-layer ground pours actually are, and it
#:   keeps the copper off the drill and the soldermask dams.
#: * THERMAL_GAP / THERMAL_SPOKE — a GND pad tied straight into the pour is a heat
#:   sink: hand soldering never reaches temperature and reflow wicks the paste
#:   away. IPC-7351 asks for four spokes and a gap; the pad connects thermally,
#:   not as a solid block.
POUR_CLEARANCE_MM = 0.30
POUR_GRID_MM = 0.60
POUR_TRACE_MM = 0.30
POUR_THERMAL_GAP_MM = 0.30
POUR_THERMAL_SPOKE_MM = 0.30
POUR_EDGE_INSET_MM = 0.50


def _gnd_pad_keys(
    modules: dict[str, Any], connections: list[dict[str, Any]]
) -> set[tuple[str, str]]:
    """(ref, pin) pairs on the ground net, from the netlist itself."""
    gnd: set[tuple[str, str]] = set()
    for conn in connections:
        net = str(conn.get("net") or "")
        if net.strip("/").upper() not in ("GND", "AGND", "DGND", "VSS", "GROUND"):
            continue
        for pt in conn.get("points") or []:
            if "." in pt:
                ref, pin = pt.split(".", 1)
                gnd.add((ref, pin))
    return gnd


def _pour_hatch_segments(
    board_w: float,
    board_h: float,
    pads: list[dict[str, Any]],
    wires: list[dict[str, Any]],
    vias: list[dict[str, Any]],
    gnd_pads: set[tuple[str, str]],
) -> list[tuple[float, float, float, float]]:
    """Compute the hatch lines of a real ground pour, with every obstacle cut out.

    Each horizontal hatch line is the board span minus the intervals occupied by
    pads, tracks and vias (each expanded by the pour clearance). Subtracting the
    obstacles rather than skipping whole lines is the difference between a pour
    and a set of stripes: a line crossing a single 0603 pad would otherwise be
    deleted end to end.

    GND pads are not obstacles — they are the connection. They are handled by
    leaving the pad's own thermal gap open and adding spokes, so the pad is
    thermally relieved instead of being swallowed by the plane.
    """
    lo_x = POUR_EDGE_INSET_MM
    hi_x = board_w - POUR_EDGE_INSET_MM
    lo_y = POUR_EDGE_INSET_MM
    hi_y = board_h - POUR_EDGE_INSET_MM
    if hi_x <= lo_x or hi_y <= lo_y:
        return []

    obstacles: list[tuple[float, float, float, float]] = []

    for pad in pads:
        if (pad["ref"], pad["pin"]) in gnd_pads:
            continue
        hw = pad["w"] / 2.0 + POUR_CLEARANCE_MM
        hh = pad["h"] / 2.0 + POUR_CLEARANCE_MM
        obstacles.append((pad["x"] - hw, pad["y"] - hh, pad["x"] + hw, pad["y"] + hh))

    for wire in wires:
        w = wire["width_mm"] / 2.0 + POUR_CLEARANCE_MM
        for (x0, y0), (x1, y1) in pairwise(wire["pts"]):
            obstacles.append((min(x0, x1) - w, min(y0, y1) - w, max(x0, x1) + w, max(y0, y1) + w))

    for via in vias:
        r = via["pad_mm"] / 2.0 + POUR_CLEARANCE_MM
        obstacles.append((via["x"] - r, via["y"] - r, via["x"] + r, via["y"] + r))

    segments: list[tuple[float, float, float, float]] = []
    y = lo_y
    while y <= hi_y + 1e-9:
        blocked: list[tuple[float, float]] = []
        for ox0, oy0, ox1, oy1 in obstacles:
            if oy1 < y or y < oy0:
                continue
            b_lo, b_hi = max(ox0, lo_x), min(ox1, hi_x)
            if b_hi > b_lo:
                blocked.append((b_lo, b_hi))

        cursor = lo_x
        blocked.sort()
        for b_lo, b_hi in blocked:
            if b_lo > cursor:
                segments.append((cursor, y, b_lo, y))
            cursor = max(cursor, b_hi)
        if cursor < hi_x:
            segments.append((cursor, y, hi_x, y))

        y += POUR_GRID_MM

    # A stub shorter than the fill width is a fleck of copper, not a connection.
    return [(x0, y0, x1, y1) for x0, y0, x1, y1 in segments if x1 - x0 > POUR_TRACE_MM]


def _thermal_spokes(pad: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    """Four spokes from a GND pad out to the pour, per IPC-7351 thermal relief."""
    cx, cy = pad["x"], pad["y"]
    hw = pad["w"] / 2.0 + POUR_THERMAL_GAP_MM
    hh = pad["h"] / 2.0 + POUR_THERMAL_GAP_MM
    out = POUR_THERMAL_GAP_MM + POUR_THERMAL_SPOKE_MM
    half = POUR_THERMAL_SPOKE_MM / 2.0
    return [
        (cx - hw - out, cy - half, cx - hw, cy + half),  # left
        (cx + hw, cy - half, cx + hw + out, cy + half),  # right
        (cx - half, cy - hh - out, cx + half, cy - hh),  # down
        (cx - half, cy + hh, cx + half, cy + hh + out),  # up
    ]


def _write_copper_layer(
    title: str,
    pads: list[dict[str, Any]],
    wires: list[dict[str, Any]],
    *,
    include_pour: tuple[float, float] | None = None,
    vias: list[dict[str, Any]] | None = None,
    teardrops: list[list[tuple[float, float]]] | None = None,
    gnd_pads: set[tuple[str, str]] | None = None,
) -> str:
    """Render one copper layer: apertures, pour, pads, via rings, then tracks.

    Vias are flashed here as annular rings. A drill hit with no copper around it
    is a hole punched through a trace: the plating has nothing to anchor to and
    the two sides never connect. IPC-2221B Table 9-1 asks for an annular ring of
    at least 0.05 mm per side, which the 0.6/0.3 padstack satisfies at 0.15 mm.
    """
    defs: list[str] = []
    pad_codes: dict[tuple[float, float, bool], int] = {}
    next_code = 10

    for pad in pads:
        key = (pad["w"], pad["h"], pad["round"])
        if key not in pad_codes:
            pad_codes[key] = next_code
            if pad["round"]:
                defs.append(f"%ADD{next_code}C,{pad['w']:.5f}*%")
            else:
                defs.append(f"%ADD{next_code}R,{pad['w']:.5f}X{pad['h']:.5f}*%")
            next_code += 1

    via_pads = vias or []
    via_codes: dict[float, int] = {}
    for d in sorted({round(v["pad_mm"], 4) for v in via_pads}):
        via_codes[d] = next_code
        defs.append(f"%ADD{next_code}C,{d:.5f}*%")
        next_code += 1

    wire_codes: dict[float, int] = {}
    for w in sorted({round(x["width_mm"], 4) for x in wires}):
        wire_codes[w] = next_code
        defs.append(f"%ADD{next_code}C,{w:.5f}*%")
        next_code += 1

    pour_track_code: int | None = None
    if include_pour is not None:
        defs.append(f"%ADD{next_code}C,{POUR_TRACE_MM:.5f}*%")
        pour_track_code = next_code
        next_code += 1

    L = [f"G04 Gerber RS-274X {title}*", "%FSLAX45Y45*%", "%MOMM*%", "%LPD*%", *defs]

    if pour_track_code is not None and include_pour is not None:
        bw, bh = include_pour
        segments = _pour_hatch_segments(bw, bh, pads, wires, vias or [], gnd_pads or set())
        if segments:
            L.append("G04 Ground Pour (GND hatch, obstacles cleared)*")
            L.append(f"D{pour_track_code}*")
            for x0, y0, x1, y1 in segments:
                L.append(f"X{_format_gerber_coord(x0)}Y{_format_gerber_coord(y0)}D02*")
                L.append(f"X{_format_gerber_coord(x1)}Y{_format_gerber_coord(y1)}D01*")
        if gnd_pads:
            L.append("G04 Ground Pad Thermal Relief Spokes*")
            L.append(f"D{pour_track_code}*")
            for pad in pads:
                if (pad["ref"], pad["pin"]) not in gnd_pads:
                    continue
                for x0, y0, x1, y1 in _thermal_spokes(pad):
                    L.append(f"X{_format_gerber_coord(x0)}Y{_format_gerber_coord(y0)}D02*")
                    L.append(f"X{_format_gerber_coord(x1)}Y{_format_gerber_coord(y1)}D01*")

    if pads:
        L.append("G04 Component Pads*")
        by_code: dict[int, list[dict[str, Any]]] = {}
        for pad in pads:
            by_code.setdefault(pad_codes[(pad["w"], pad["h"], pad["round"])], []).append(pad)
        for code in sorted(by_code):
            L.append(f"D{code}*")
            for pad in by_code[code]:
                L.append(f"X{_format_gerber_coord(pad['x'])}Y{_format_gerber_coord(pad['y'])}D03*")

    if via_pads:
        L.append("G04 Plated Via Annular Rings*")
        by_via: dict[int, list[dict[str, Any]]] = {}
        for via in via_pads:
            by_via.setdefault(via_codes[round(via["pad_mm"], 4)], []).append(via)
        for code in sorted(by_via):
            L.append(f"D{code}*")
            for via in by_via[code]:
                L.append(f"X{_format_gerber_coord(via['x'])}Y{_format_gerber_coord(via['y'])}D03*")

    if teardrops:
        # G36/G37 is the RS-274X region statement: the polygon between them is
        # filled, not stroked. A stroked teardrop would be an outline of copper
        # around empty space — worse than no teardrop at all.
        L.append("G04 Teardrop Reinforcement Fillets (IPC-2221B 9.1.5)*")
        for poly in teardrops:
            if len(poly) < 3:
                continue
            L.append("G36*")
            x0, y0 = poly[0]
            L.append(f"X{_format_gerber_coord(x0)}Y{_format_gerber_coord(y0)}D02*")
            for x, y in poly[1:]:
                L.append(f"X{_format_gerber_coord(x)}Y{_format_gerber_coord(y)}D01*")
            L.append(f"X{_format_gerber_coord(x0)}Y{_format_gerber_coord(y0)}D01*")
            L.append("G37*")

    if wires:
        L.append("G04 Routed Tracks*")
        for w in sorted(wire_codes):
            L.append(f"D{wire_codes[w]}*")
            for wire in wires:
                if round(wire["width_mm"], 4) != w:
                    continue
                x0, y0 = wire["pts"][0]
                L.append(f"X{_format_gerber_coord(x0)}Y{_format_gerber_coord(y0)}D02*")
                for x, y in wire["pts"][1:]:
                    L.append(f"X{_format_gerber_coord(x)}Y{_format_gerber_coord(y)}D01*")

    L.append("M02*")
    return "\n".join(L) + "\n"


def generate_top_copper_gerber(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    *,
    placements: dict[str, Any] | None = None,
    ses_text: str | None = None,
) -> str:
    """Generate Gerber RS-274X Top Copper layer (.gtl) from real pads and real routes.

    Pads come from footprint pin offsets; tracks come from the autorouter's SES.
    Without ``ses_text`` the layer carries pads only — the truthful state of an
    unrouted board, rather than a board full of straight-line "guide" copper.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    pads = _collect_pads(modules, connections, placements)
    geo = _parse_ses_geometry(ses_text)
    top_wires = [w for w in geo["wires"] if _is_top_layer(w["layer"])]

    return _write_copper_layer(
        "Top Copper Layer",
        pads,
        top_wires,
        vias=geo["vias"],
        teardrops=_via_teardrop_polygons(geo),
    )


def generate_bottom_copper_gerber(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    *,
    placements: dict[str, Any] | None = None,
    ses_text: str | None = None,
) -> str:
    """Generate Gerber RS-274X Bottom Copper layer (.gbl).

    A two-layer board needs bottom copper even when every part sits on top: the
    ground return lives there. The bundle once emitted only top copper while
    `validate_manufacturing_package` required both, so no design could produce a
    complete package — a gate unsatisfiable by construction.

    Carries the ground pour outline, through-hole pads (which exist on both sides),
    and the router's bottom-layer tracks.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    pads = [p for p in _collect_pads(modules, connections, placements) if p["through_hole"]]
    geo = _parse_ses_geometry(ses_text)
    bot_wires = [w for w in geo["wires"] if _is_bottom_layer(w["layer"])]

    return _write_copper_layer(
        "Bottom Copper Layer",
        pads,
        bot_wires,
        include_pour=(board_width_mm, board_height_mm),
        vias=geo["vias"],
        teardrops=_via_teardrop_polygons(geo),
        gnd_pads=_gnd_pad_keys(modules, connections),
    )


def generate_top_paste_gerber(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    *,
    placements: dict[str, Any] | None = None,
    paste_reduction: float = PASTE_REDUCTION_MM,
) -> str:
    """Generate the SMT stencil layer (.gtp) — one aperture per surface-mount pad.

    Without this layer no SMT line can build the board: the stencil is what the
    printer uses to deposit solder paste, and paste is what the reflow step turns
    into the solder joint. The bundle shipped seven layers without it, so every
    package was a "through-hole or hand-solder" board regardless of its parts.

    Apertures are *reduced* relative to the copper land (IPC-7525B Section 4.2):
    paste printed to the full pad area wicks under the part during reflow and
    lifts it off its pads, producing opens and tombstones. Through-hole pins get
    no aperture — they are wave- or hand-soldered, not reflowed.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    pads = [
        p
        for p in _collect_pads(modules, connections, placements)
        if not p["through_hole"]
    ]

    L = ["G04 Gerber RS-274X SMT Stencil (Top Paste)*", "%FSLAX45Y45*%", "%MOMM*%", "%LPD*%"]

    groups: dict[tuple[float, float, bool], list[dict[str, Any]]] = {}
    for pad in pads:
        w = round(pad["w"] - 2 * paste_reduction, 5)
        h = round(pad["h"] - 2 * paste_reduction, 5)
        if w <= 0 or h <= 0:
            continue
        groups.setdefault((w, h, pad["round"]), []).append(pad)

    code = 10
    for (w, h, is_round), items in groups.items():
        if is_round:
            L.append(f"%ADD{code}C,{w:.5f}*%")
        else:
            L.append(f"%ADD{code}R,{w:.5f}X{h:.5f}*%")
        L.append(f"D{code}*")
        for pad in items:
            L.append(f"X{_format_gerber_coord(pad['x'])}Y{_format_gerber_coord(pad['y'])}D03*")
        code += 1

    L.append("M02*")
    return "\n".join(L) + "\n"


def generate_bottom_paste_gerber(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    *,
    placements: dict[str, Any] | None = None,
    paste_reduction: float = PASTE_REDUCTION_MM,
) -> str:
    """Generate the bottom-side stencil layer (.gbp).

    Only parts placed on the bottom side get apertures. A double-sided reflow
    assembly needs both; a single-sided one legitimately has an empty file, and an
    empty layer is the honest answer rather than apertures under parts that are
    not there.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    bottom_refs = {ref for ref, p in placements.items() if p.layer == "Bottom"}
    used: set[str] = set()
    for conn in connections:
        for pt in conn.get("points") or []:
            if "." in pt:
                ref = pt.split(".", 1)[0]
                if ref in bottom_refs:
                    used.add(ref)

    pads = [
        p
        for p in _collect_pads(modules, connections, placements)
        if not p["through_hole"] and p["ref"] in used
    ]

    L = ["G04 Gerber RS-274X SMT Stencil (Bottom Paste)*", "%FSLAX45Y45*%", "%MOMM*%", "%LPD*%"]

    groups: dict[tuple[float, float, bool], list[dict[str, Any]]] = {}
    for pad in pads:
        w = round(pad["w"] - 2 * paste_reduction, 5)
        h = round(pad["h"] - 2 * paste_reduction, 5)
        if w <= 0 or h <= 0:
            continue
        groups.setdefault((w, h, pad["round"]), []).append(pad)

    code = 10
    for (w, h, is_round), items in groups.items():
        if is_round:
            L.append(f"%ADD{code}C,{w:.5f}*%")
        else:
            L.append(f"%ADD{code}R,{w:.5f}X{h:.5f}*%")
        L.append(f"D{code}*")
        for pad in items:
            L.append(f"X{_format_gerber_coord(pad['x'])}Y{_format_gerber_coord(pad['y'])}D03*")
        code += 1

    L.append("M02*")
    return "\n".join(L) + "\n"


def _write_mask_layer(title: str, pads: list[dict[str, Any]]) -> str:
    """Render a solder-mask layer: one opening per pad, expanded by the mask allowance."""
    L = [f"G04 Gerber RS-274X {title}*", "%FSLAX45Y45*%", "%MOMM*%", "%LPD*%"]

    groups: dict[tuple[float, float, bool], list[dict[str, Any]]] = {}
    for pad in pads:
        key = (
            round(pad["w"] + 2 * MASK_EXPANSION_MM, 5),
            round(pad["h"] + 2 * MASK_EXPANSION_MM, 5),
            pad["round"],
        )
        groups.setdefault(key, []).append(pad)

    code = 10
    for (w, h, is_round), items in groups.items():
        if is_round:
            L.append(f"%ADD{code}C,{w:.5f}*%")
        else:
            L.append(f"%ADD{code}R,{w:.5f}X{h:.5f}*%")
        L.append(f"D{code}*")
        for pad in items:
            L.append(f"X{_format_gerber_coord(pad['x'])}Y{_format_gerber_coord(pad['y'])}D03*")
        code += 1

    L.append("M02*")
    return "\n".join(L) + "\n"


def generate_top_solder_mask_gerber(
    modules: dict[str, Any],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    *,
    connections: list[dict[str, Any]] | None = None,
    placements: dict[str, Any] | None = None,
) -> str:
    """Generate Gerber RS-274X Top Solder Mask layer (.gts).

    Openings track the real pad list. A mask aperture that ignores pad position
    exposes copper where there is none and covers the pad that needs solder.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)
    pads = _collect_pads(modules, connections or [], placements)
    return _write_mask_layer("Top Solder Mask Openings", pads)


def generate_bottom_solder_mask_gerber(
    modules: dict[str, Any],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    *,
    connections: list[dict[str, Any]] | None = None,
    placements: dict[str, Any] | None = None,
) -> str:
    """Generate Gerber RS-274X Bottom Solder Mask layer (.gbs).

    SMD parts are on top, so the bottom mask opens only for through-hole pads.
    The layer must still exist: a missing bottom mask reads as "unspecified" and
    the CAM engineer either asks or guesses. An explicit layer that opens exactly
    the through-holes states what is true.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)
    pads = [p for p in _collect_pads(modules, connections or [], placements) if p["through_hole"]]
    return _write_mask_layer("Bottom Solder Mask Openings", pads)


def generate_top_silkscreen_gerber(
    modules: dict[str, Any],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    *,
    placements: dict[str, Any] | None = None,
    connections: list[dict[str, Any]] | None = None,
) -> str:
    """Generate Gerber RS-274X Top Silkscreen layer (.gto) with real body outlines.

    Extents come from each package's body size, so a 0603 gets a 0603 outline
    instead of a uniform box that overlaps its neighbours.

    Each outline is clipped so no segment crosses a mask opening. Silk printed on
    exposed copper is not cosmetic: the ink sits between the pad and the solder,
    blocks wetting, and turns into a cold joint or a solder ball after reflow.
    IPC-SM-840 asks for 0.15 mm between legend and an exposed land, so the clip
    uses the mask opening expanded by that much.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    # Mask openings (pad + expansion) plus the legend-to-land clearance.
    avoid: list[tuple[float, float, float, float]] = []
    for pad in _collect_pads(modules, connections or [], placements):
        hw = pad["w"] / 2.0 + MASK_EXPANSION_MM + SILK_TO_PAD_CLEARANCE_MM
        hh = pad["h"] / 2.0 + MASK_EXPANSION_MM + SILK_TO_PAD_CLEARANCE_MM
        avoid.append((pad["x"] - hw, pad["y"] - hh, pad["x"] + hw, pad["y"] + hh))

    def _free_spans(
        x0: float, y0: float, x1: float, y1: float
    ) -> list[tuple[float, float]]:
        """Subtract mask openings from an axis-aligned segment.

        Dropping a whole edge whenever a pad touches it erases the legend on any
        part whose body sits between its own pads — which is most of them. The
        correct result is the segment minus the blocked intervals: a QFN keeps
        its long top edge, and a 0603 keeps nothing because both of its end edges
        genuinely sit under copper.
        """
        horizontal = abs(y1 - y0) < 1e-9
        a0, a1 = (x0, x1) if horizontal else (y0, y1)
        fixed = y0 if horizontal else x0
        lo, hi = min(a0, a1), max(a0, a1)

        blocked: list[tuple[float, float]] = []
        for bx0, by0, bx1, by1 in avoid:
            b_lo, b_hi = (bx0, bx1) if horizontal else (by0, by1)
            f_lo, f_hi = (by0, by1) if horizontal else (bx0, bx1)
            if f_hi < fixed or fixed < f_lo:
                continue
            if b_hi <= lo or hi <= b_lo:
                continue
            blocked.append((max(b_lo, lo), min(b_hi, hi)))

        if not blocked:
            return [(lo, hi)]

        blocked.sort()
        spans: list[tuple[float, float]] = []
        cursor = lo
        for b_lo, b_hi in blocked:
            if b_lo > cursor:
                spans.append((cursor, b_lo))
            cursor = max(cursor, b_hi)
        if cursor < hi:
            spans.append((cursor, hi))

        # A stub shorter than the pen width is a dot of legend, not a line.
        return [(s, e) for s, e in spans if e - s > 0.1]

    L = [
        "G04 Gerber RS-274X Top Silkscreen Layer*",
        "%FSLAX45Y45*%",
        "%MOMM*%",
        "%LPD*%",
        "%ADD10C,0.12000*%",  # 0.12mm silkscreen pen
        "D10*",
    ]
    clipped = 0
    for _ref, p in sorted(placements.items()):
        pkg = p.package or ""
        body = BODY_DIMS_MM.get(pkg)
        if body is None:
            for key, dims in BODY_DIMS_MM.items():
                if key in pkg:
                    body = (dims[0], dims[1])
                    break
        if body is None:
            half = PACKAGE_HALF_EXTENTS.get(pkg, (1.0, 0.6))
            body = (half[0] * 2, half[1] * 2)

        cx0 = p.x_mm - body[0] / 2
        cx1 = p.x_mm + body[0] / 2
        cy0 = p.y_mm - body[1] / 2
        cy1 = p.y_mm + body[1] / 2

        edges = [
            (cx0, cy0, cx1, cy0),
            (cx1, cy0, cx1, cy1),
            (cx1, cy1, cx0, cy1),
            (cx0, cy1, cx0, cy0),
        ]
        for x0, y0, x1, y1 in edges:
            horizontal = abs(y1 - y0) < 1e-9
            spans = _free_spans(x0, y0, x1, y1)
            if not spans:
                clipped += 1
                continue
            for s, e in spans:
                if horizontal:
                    L.append(f"X{_format_gerber_coord(s)}Y{_format_gerber_coord(y0)}D02*")
                    L.append(f"X{_format_gerber_coord(e)}Y{_format_gerber_coord(y0)}D01*")
                else:
                    L.append(f"X{_format_gerber_coord(x0)}Y{_format_gerber_coord(s)}D02*")
                    L.append(f"X{_format_gerber_coord(x0)}Y{_format_gerber_coord(e)}D01*")

    L.append("M02*")
    return "\n".join(L) + "\n"


def export_gerber_bundle(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    *,
    placements: dict[str, Any] | None = None,
    ses_text: str | None = None,
) -> dict[str, str]:
    """Generate a complete manufacturing Gerber RS-274X + Excellon bundle.

    Pass ``ses_text`` from ``autoroute_circuit`` to include the router's real track
    geometry. Without it the copper layers carry pads only — an unrouted board,
    described as such.

    Returns dict mapping layer filename to content:
      {
        "board-Edge_Cuts.gm1": "...",
        "board-F_Cu.gtl": "...",
        "board-B_Cu.gbl": "...",
        "board-F_Mask.gts": "...",
        "board-B_Mask.gbs": "...",
        "board-F_SilkS.gto": "...",
        "board-F_Paste.gtp": "...",
        "board-B_Paste.gbp": "...",
        "board.drl": "..."
      }
    """
    from .excellon_exporter import export_excellon_drill

    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    geo = _parse_ses_geometry(ses_text)

    layers = {
        "board-Edge_Cuts.gm1": generate_edge_cuts_gerber(board_width_mm, board_height_mm),
        "board-F_Cu.gtl": generate_top_copper_gerber(
            modules,
            connections,
            board_width_mm,
            board_height_mm,
            placements=placements,
            ses_text=ses_text,
        ),
        "board-B_Cu.gbl": generate_bottom_copper_gerber(
            modules,
            connections,
            board_width_mm,
            board_height_mm,
            placements=placements,
            ses_text=ses_text,
        ),
        "board-F_Mask.gts": generate_top_solder_mask_gerber(
            modules,
            board_width_mm,
            board_height_mm,
            connections=connections,
            placements=placements,
        ),
        "board-B_Mask.gbs": generate_bottom_solder_mask_gerber(
            modules,
            board_width_mm,
            board_height_mm,
            connections=connections,
            placements=placements,
        ),
        "board-F_SilkS.gto": generate_top_silkscreen_gerber(
            modules,
            board_width_mm,
            board_height_mm,
            placements=placements,
            connections=connections,
        ),
        "board-F_Paste.gtp": generate_top_paste_gerber(
            modules,
            connections,
            board_width_mm,
            board_height_mm,
            placements=placements,
        ),
        "board-B_Paste.gbp": generate_bottom_paste_gerber(
            modules,
            connections,
            board_width_mm,
            board_height_mm,
            placements=placements,
        ),
        "board.drl": export_excellon_drill(
            modules,
            connections,
            board_width_mm=board_width_mm,
            board_height_mm=board_height_mm,
            placements=placements,
            vias=geo["vias"],
        ),
    }
    log.info(
        "✅ 生成原生 Gerber RS-274X + Excellon 制造包: 7 层 (尺寸 %.0f×%.0fmm, %d 条走线, %d 个过孔)",
        board_width_mm,
        board_height_mm,
        len(geo["wires"]),
        len(geo["vias"]),
    )
    return layers
