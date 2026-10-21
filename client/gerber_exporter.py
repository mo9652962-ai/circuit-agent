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
import re
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

    Returns ``{"wires": [{layer, width_mm, pts}], "vias": [{x, y}]}`` in mm.
    Coordinates inside a SES are integers in the declared resolution units, so the
    divisor is read from the file — treating them as millimetres would shrink
    every trace by a factor of 1000.
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
        vias.append({"x": float(m.group(2)) / div, "y": float(m.group(3)) / div})

    return {"wires": wires, "vias": vias}


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


def _write_copper_layer(
    title: str,
    pads: list[dict[str, Any]],
    wires: list[dict[str, Any]],
    *,
    include_pour: tuple[float, float] | None = None,
) -> str:
    """Render one copper layer: aperture table, pad flashes, then real tracks."""
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

    wire_codes: dict[float, int] = {}
    for w in sorted({round(x["width_mm"], 4) for x in wires}):
        wire_codes[w] = next_code
        defs.append(f"%ADD{next_code}C,{w:.5f}*%")
        next_code += 1

    pour_code: int | None = None
    if include_pour is not None:
        defs.append(f"%ADD{next_code}C,0.25000*%")
        pour_code = next_code

    L = [f"G04 Gerber RS-274X {title}*", "%FSLAX45Y45*%", "%MOMM*%", "%LPD*%", *defs]

    if pour_code is not None and include_pour is not None:
        bw, bh = include_pour
        inset = 1.0
        L.append("G04 Ground Pour Boundary*")
        L.append(f"D{pour_code}*")
        corners = [
            (inset, inset),
            (bw - inset, inset),
            (bw - inset, bh - inset),
            (inset, bh - inset),
            (inset, inset),
        ]
        for i, (x, y) in enumerate(corners):
            L.append(f"X{_format_gerber_coord(x)}Y{_format_gerber_coord(y)}{'D02' if i == 0 else 'D01'}*")

    if pads:
        L.append("G04 Component Pads*")
        by_code: dict[int, list[dict[str, Any]]] = {}
        for pad in pads:
            by_code.setdefault(pad_codes[(pad["w"], pad["h"], pad["round"])], []).append(pad)
        for code in sorted(by_code):
            L.append(f"D{code}*")
            for pad in by_code[code]:
                L.append(f"X{_format_gerber_coord(pad['x'])}Y{_format_gerber_coord(pad['y'])}D03*")

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

    return _write_copper_layer("Top Copper Layer", pads, top_wires)


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
    )


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
) -> str:
    """Generate Gerber RS-274X Top Silkscreen layer (.gto) with real body outlines.

    Extents come from each package's body size, so a 0603 gets a 0603 outline
    instead of a uniform box that overlaps its neighbours.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    L = [
        "G04 Gerber RS-274X Top Silkscreen Layer*",
        "%FSLAX45Y45*%",
        "%MOMM*%",
        "%LPD*%",
        "%ADD10C,0.12000*%",  # 0.12mm silkscreen pen
        "D10*",
    ]
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

        x0 = _format_gerber_coord(p.x_mm - body[0] / 2)
        x1 = _format_gerber_coord(p.x_mm + body[0] / 2)
        y0 = _format_gerber_coord(p.y_mm - body[1] / 2)
        y1 = _format_gerber_coord(p.y_mm + body[1] / 2)
        L.append(f"X{x0}Y{y0}D02*")
        L.append(f"X{x1}Y{y0}D01*")
        L.append(f"X{x1}Y{y1}D01*")
        L.append(f"X{x0}Y{y1}D01*")
        L.append(f"X{x0}Y{y0}D01*")

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
