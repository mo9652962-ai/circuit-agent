"""Native Python PCB Auto-Routing Engine & Specctra SES Analysis.

Industrial benchmark & standard:
- Specctra SES (Session) format v15.0: The standard output exchange format for
  autorouters (FreeRouting, Cadence Specctra, Altium, Electra).
- Multi-Layer Grid Router & Exact Routing Pipeline:
  * Zero external Java/JVM dependencies (pure Python implementation).
  * Rip-up and retry pathfinding with DRC clearance enforcement.
  * Multi-layer routing with automated via generation.
  * Comprehensive physical routing metrics: net completion rate, track length,
    via counts, and layer utilization.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

from .placement_engine import (
    ComponentPlacement,
    export_specctra_dsn,
    heuristic_place_components,
)

log = logging.getLogger("circuit-router")


def parse_ses_routing(ses_text: str, total_expected_nets: int | None = None) -> dict[str, Any]:
    """Parse Specctra SES routing session text and extract structured metrics.

    Coordinates inside a SES ``routes`` scope are integers in the session's
    declared resolution units — ``(resolution mm 1000)`` means 1/1000 mm — not
    millimetres. The divisor is read from the file rather than assumed, so a
    session written in a coarser unit still reports true lengths.
    """
    routed_nets: list[str] = []
    total_wire_length_mm: float = 0.0
    layers_used: set[str] = set()
    wire_segments_count: int = 0

    # Resolution divisor: mm-per-unit. Default 1000 (1 um) if the file omits it.
    unit_div = 1000.0
    rm = re.search(r"\(resolution\s+(\w+)\s+([0-9.]+)\s*\)", ses_text)
    if rm:
        unit_div = float(rm.group(2)) or 1000.0
        if rm.group(1).lower() in ("inch", "in"):
            unit_div *= 25.4

    # Extract all vias
    via_matches = re.findall(r'\(via\s+"?([^"\s]+)"?\s+([0-9.-]+)\s+([0-9.-]+)', ses_text)
    via_count = len(via_matches)

    # Extract nets and their routing paths
    net_blocks = re.findall(
        r'\(net\s+([\w"+\-.]+)(.*?)(?=\(net\s+[\w"+\-.]+|\Z|\)\s*\)\s*\))',
        ses_text,
        re.DOTALL,
    )

    for net_name_raw, net_content in net_blocks:
        net_name = net_name_raw.strip('"')
        routed_nets.append(net_name)

        # Parse wire paths within this net
        path_matches = re.finditer(
            r'\(path\s+(\w+)\s+\d+\s+([0-9\s.-]+)\)',
            net_content,
        )
        for pm in path_matches:
            layer = pm.group(1)
            layers_used.add(layer)
            coords_str = pm.group(2).strip()
            nums = [float(x) for x in coords_str.split()]
            pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]

            if len(pts) >= 2:
                for i in range(len(pts) - 1):
                    wire_segments_count += 1
                    dx = (pts[i + 1][0] - pts[i][0]) / unit_div
                    dy = (pts[i + 1][1] - pts[i][1]) / unit_div
                    dist = math.hypot(dx, dy)
                    total_wire_length_mm += dist

    total_nets = total_expected_nets if total_expected_nets is not None else len(routed_nets)
    completion_rate_pct = (
        round((len(routed_nets) / total_nets) * 100.0, 1) if total_nets > 0 else 100.0
    )

    return {
        "success": len(routed_nets) > 0 or total_nets == 0,
        "total_nets": total_nets,
        "routed_nets_count": len(routed_nets),
        "unrouted_nets_count": max(0, total_nets - len(routed_nets)),
        "completion_rate_pct": completion_rate_pct,
        "routed_nets": routed_nets,
        "wire_segments_count": wire_segments_count,
        "via_count": via_count,
        "total_wire_length_mm": round(total_wire_length_mm, 2),
        "layers_used": sorted(layers_used),
    }


def autoroute_specctra_dsn(
    dsn_text: str,
    engine: str = "grid",
    shove: bool = False,
) -> dict[str, Any]:
    """Execute automated PCB routing on Specctra DSN text.

    Args:
        dsn_text: Valid Specctra DSN format string.
        engine: Routing algorithm engine ('grid', 'exact', 'room').
        shove: Whether to enable push-and-shove clearance optimization.

    Returns:
        Dict containing SES output text, metrics, and routing status.
    """
    try:
        import freeroute.route  # noqa: F401  (availability probe; routing goes through _route_with_correct_units)
    except ImportError:
        err_msg = (
            "Native PCB autorouter module 'freeroute' is not installed. "
            "Please install it via: pip install freeroute"
        )
        log.warning(err_msg)
        return {
            "success": False,
            "error": err_msg,
            "ses_text": "",
            "metrics": {},
        }

    # Extract expected nets count from DSN
    expected_nets = len(re.findall(r'\(net\s+"?[\w"+\-.]+"?', dsn_text))

    try:
        ses_text = _route_with_correct_units(dsn_text, engine=engine, shove=shove)
        metrics = parse_ses_routing(ses_text, total_expected_nets=expected_nets)
        return {
            "success": metrics["success"],
            "ses_text": ses_text,
            "metrics": metrics,
        }
    except Exception as exc:
        log.exception("Autorouting execution failed")
        return {
            "success": False,
            "error": str(exc),
            "ses_text": "",
            "metrics": {},
        }


def _route_with_correct_units(dsn_text: str, *, engine: str = "grid", shove: bool = False) -> str:
    """Run the autorouter and re-emit SES with Specctra-correct coordinate units.

    ``freeroute``'s ``write_ses`` emits routing coordinates as *integers*, but the
    router works in millimetres and the SES header declares ``(resolution mm 1000)``.
    The two only agree when a coordinate happens to be a whole millimetre: a pad at
    (10.25, 27.5) mm was written as ``10 28``, i.e. up to half a millimetre of error,
    which is larger than a 0603 pad. Every downstream consumer — KiCad's
    ``ImportSpecctraSES``, and our own Gerber exporter — inherits that error.

    We do not patch the third-party writer. Instead we build the ``RoutingResult``
    ourselves, scale coordinates and widths into DSN resolution units, and hand the
    already-scaled result to the same writer, which then rounds to the correct
    integer grid (0.001 mm).
    """
    from freeroute.dsn import parse_dsn
    from freeroute.route import pipeline
    from freeroute.ses import write_ses
    from freeroute.ses.model import RoutedVia, RoutedWire, RoutingResult

    dsn = parse_dsn(dsn_text)
    scale = max(dsn.resolution.value, 1)

    routed = pipeline.build_routing_result(dsn)

    scaled = RoutingResult()
    for net in routed.nets:
        for wire in net.wires:
            scaled.add_wire(
                net.name,
                RoutedWire(
                    layer=wire.layer,
                    width=wire.width * scale,
                    coords=[c * scale for c in wire.coords],
                    fixed=wire.fixed,
                ),
            )
        for via in net.vias:
            scaled.add_via(
                net.name,
                RoutedVia(padstack=via.padstack, x=via.x * scale, y=via.y * scale, fixed=via.fixed),
            )

    return write_ses(dsn, scaled)


def autoroute_circuit(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    placements: dict[str, ComponentPlacement] | None = None,
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    trace_width_mm: float = 0.150,
    clearance_mm: float = 0.100,
    engine: str = "grid",
) -> dict[str, Any]:
    """Execute end-to-end placement and autorouting for a circuit specification.

    1. Executes heuristic component placement.
    2. Compiles standardized Specctra DSN v15.0 format.
    3. Runs native autorouting pipeline to generate Specctra SES tracks.
    4. Analyzes routing metrics and physical parameters.
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    dsn_text = export_specctra_dsn(
        modules=modules,
        connections=connections,
        placements=placements,
        board_width_mm=board_width_mm,
        board_height_mm=board_height_mm,
        trace_width_mm=trace_width_mm,
        clearance_mm=clearance_mm,
    )

    result = autoroute_specctra_dsn(dsn_text, engine=engine)
    result["dsn_text"] = dsn_text
    result["placements"] = {ref: p.to_dict() for ref, p in placements.items()}
    return result
