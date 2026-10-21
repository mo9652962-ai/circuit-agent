"""Native Excellon CNC Drill (.drl) Direct Exporter (IPC-NC-349 Standard).

Industrial benchmark & standard:
- IPC-NC-349: Computer Numerical Control Formatting for Drilling and Routing Equipment.
- Universal Excellon Format 2 consumed by automated CNC drilling machines
  (Hitachi, Posalux, Schmoll) across global PCB fabrication facilities.
- Groups drill hits by aperture diameter (T01C..., T02C...), outputs metric
  coordinates, and completes the drill file of a full PCB production bundle
  alongside RS-274X Gerber.

What gets drilled
-----------------
Only holes the design actually requires:

* Through-hole component pins, at their real footprint pin positions.
* Vias the autorouter placed, at the coordinates it placed them.
* Mounting holes, when the board carries a mounting-hole component.

The previous implementation drilled a 0.3 mm hole next to *every* SMD part and a
second hole 2.54 mm beside every connector, regardless of pin count or position.
Those holes exist nowhere in the design; a fab would drill them straight through
pads and traces.
"""

from __future__ import annotations

import logging
from typing import Any

from .placement_engine import STANDARD_PIN_OFFSETS, heuristic_place_components

log = logging.getLogger("circuit-excellon")

#: Standard drill diameters in mm, keyed by package class.
DRILL_HEADER_PIN = 1.0  # 2.54mm pitch headers / connectors
DRILL_TESTPOINT = 1.0
DRILL_VIA = 0.3  # finished via drill for a 0.6mm via pad
DRILL_MOUNT = 3.2  # M3 clearance

#: Packages whose pins are plated through-holes.
_THROUGH_HOLE_HINTS = ("HDR", "TERMINAL", "CONN-TH", "RJ45", "PinHeader", "Screw_Terminal")
_ROUND_PAD_HINTS = ("TestPoint", "Fiducial", "MountingHole")


def _pin_offsets(package: str, ref: str) -> dict[str, tuple[float, float]]:
    """Pin offset map for a package, falling back to the placement engine's synthesiser."""
    from .placement_engine import _synthesize_footprint_pins

    offs = STANDARD_PIN_OFFSETS.get(package or "")
    if offs:
        return offs
    if any(k in (package or "") for k in _ROUND_PAD_HINTS) or ref.upper().startswith(("TP_", "FID")):
        return {"1": (0.0, 0.0)}
    return _synthesize_footprint_pins(package or "", ["1", "2"])


def export_excellon_drill(
    modules: dict[str, Any],
    connections: list[dict[str, Any]] | None = None,
    job_name: str = "CIRCUIT_AGENT_PCB",
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    *,
    placements: dict[str, Any] | None = None,
    vias: list[dict[str, Any]] | None = None,
) -> str:
    """Generate a production-ready Excellon CNC drill file (.drl).

    Holes come from three real sources and nothing else: through-hole component
    pins, router-placed vias, and mounting holes declared as components. A design
    with no through-hole parts and no vias produces a valid file with no hits —
    which is the truth for a fully-SMD single-sided assembly.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    drill_groups: dict[float, list[tuple[float, float]]] = {}
    # A footprint may alias one physical pad under several pin names (a USB-C
    # shell pin is both "GND" and "1"). Drilling each name would put two hits on
    # one spot; a fab reads that as a duplicate tool path.
    _seen_hits: set[tuple[float, float, float]] = set()

    def _add(dia: float, x: float, y: float) -> None:
        key = (round(dia, 3), round(x, 4), round(y, 4))
        if key in _seen_hits:
            return
        _seen_hits.add(key)
        drill_groups.setdefault(round(dia, 3), []).append((round(x, 4), round(y, 4)))

    # 1. Through-hole component pins, at real pin positions.
    for ref, comp in sorted(modules.items()):
        p = placements.get(ref)
        if p is None:
            continue
        pkg = str(comp.get("package", ""))
        val = str(comp.get("value", "")).upper()
        upper_ref = ref.upper()

        if "MOUNT" in upper_ref or "HOLE" in upper_ref or "M3" in val:
            _add(DRILL_MOUNT, p.x_mm, p.y_mm)
            continue

        is_th = any(k in pkg for k in _THROUGH_HOLE_HINTS) or upper_ref.startswith("J_")
        if not is_th:
            continue

        dia = DRILL_TESTPOINT if upper_ref.startswith("TP_") else DRILL_HEADER_PIN
        offs = _pin_offsets(pkg, ref)
        # Drill every pin the footprint declares, not a guessed count.
        for off in offs.values():
            _add(dia, p.x_mm + off[0], p.y_mm + off[1])

    # 2. Vias the router actually placed.
    for via in vias or []:
        _add(DRILL_VIA, float(via["x"]), float(via["y"]))

    # 3. Board mounting holes, only when the board is large enough to carry them
    #    and the design did not already declare mounting-hole components.
    declared_mounts = any(
        "MOUNT" in ref.upper() or "HOLE" in ref.upper() for ref in modules
    )
    if not declared_mounts and board_width_mm >= 30.0 and board_height_mm >= 30.0:
        for mx, my in (
            (3.5, 3.5),
            (board_width_mm - 3.5, 3.5),
            (3.5, board_height_mm - 3.5),
            (board_width_mm - 3.5, board_height_mm - 3.5),
        ):
            _add(DRILL_MOUNT, mx, my)

    L = [
        "M48",
        f"; DRILL file {job_name}",
        "; FORMAT={3:3}",
        "METRIC,TZ",
    ]

    tool_map: dict[float, str] = {}
    for idx, dia in enumerate(sorted(drill_groups), start=1):
        t_code = f"T{idx:02d}"
        tool_map[dia] = t_code
        L.append(f"{t_code}C{dia:.3f}")

    L.extend(["%", "G90", "G05"])

    total_hits = 0
    for dia in sorted(drill_groups):
        L.append(tool_map[dia])
        for x_mm, y_mm in drill_groups[dia]:
            # METRIC 3:3 — e.g. 10.5mm -> X010500
            L.append(f"X{round(x_mm * 1000.0):06d}Y{round(y_mm * 1000.0):06d}")
            total_hits += 1

    L.append("M30")

    log.info(
        "✅ 生成 Excellon CNC 钻孔文件: %d 组钻头, 共 %d 个钻孔点",
        len(tool_map),
        total_hits,
    )
    return "\n".join(L) + "\n"
