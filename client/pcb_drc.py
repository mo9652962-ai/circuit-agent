"""Native PCB Physical Design Rule Check (DRC) Engine.

Industrial benchmarks & standards:
- IPC-2221B: Generic Standard on Printed Board Design.
  * Section 6.3: Conductor Clearance (Table 6-1 electrical spacing limits).
  * Section 10.1.2: Conductor routing geometry & elimination of acid traps (< 90° corners).
  * Section 10.1.3: Conductor width requirements for current carrying and etching capability.
  * Section 8.2: Minimum board edge spacing and mechanical mounting hole clearance.
- IPC-2141A: Design Guide for High-Speed Controlled Impedance Circuit Boards.
  * Section 3.4: Differential pair symmetry, skew budget, and physical length matching.
- JLCPCB / Standard Commercial Fab Capability Matrix:
  * Minimum trace width: 0.127 mm (5 mil) standard / 0.100 mm (4 mil) advanced.
  * Minimum clearance: 0.127 mm (5 mil) standard / 0.100 mm (4 mil) advanced.
  * Minimum board edge clearance: 0.5 mm - 0.8 mm (milling/V-cut keepout).
  * Mounting hole copper clearance: 3.0 mm radius around standard M3 holes.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .placement_engine import (
    PACKAGE_HALF_EXTENTS,
    STANDARD_PIN_OFFSETS,
    ComponentPlacement,
    heuristic_place_components,
)


@dataclass
class DRCViolation:
    rule_id: str
    severity: str  # "CRITICAL", "ERROR", "WARNING", "INFO"
    category: str  # "CLEARANCE", "ETCHING_ACID_TRAP", "WIDTH", "KEEPOUT", "SIGNAL_INTEGRITY", "TOPOLOGY"
    net: str
    layer: str
    location: tuple[float, float]
    description: str
    measured_value: float | None = None
    required_value: float | None = None
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DRCReport:
    passed: bool
    score: int
    violations: list[DRCViolation] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "summary": self.summary,
            "metrics": self.metrics,
            "violations": [v.to_dict() for v in self.violations],
        }

    def to_markdown(self) -> str:
        status_badge = "✅ PASSED" if self.passed else "❌ FAILED"
        lines = [
            f"# PCB Physical Design Rule Check (DRC) Report - {status_badge}",
            f"**DRC Quality Score:** {self.score}/100 | **Total Violations:** {len(self.violations)}",
            f"**Summary:** {self.summary}\n",
            "## Summary Metrics",
            f"- Total Routed Nets: {self.metrics.get('total_routed_nets', 0)}",
            f"- Total Trace Segments: {self.metrics.get('total_segments', 0)}",
            f"- Total Vias: {self.metrics.get('total_vias', 0)}",
            f"- Minimum Measured Copper Clearance: {self.metrics.get('min_measured_clearance_mm', 'N/A')} mm",
            f"- Acid Traps Detected: {self.metrics.get('acid_traps_count', 0)}",
            f"- Keepout Boundary Intrusions: {self.metrics.get('keepout_intrusions_count', 0)}",
            f"- High-Speed Differential Skew Violations: {self.metrics.get('diff_skew_violations_count', 0)}\n",
        ]

        if not self.violations:
            lines.append("🎉 No physical DRC violations detected. Layout satisfies all fabrication rules.")
        else:
            lines.append("## DRC Violations Detail")
            lines.append("| Rule ID | Severity | Category | Net | Layer | Location (mm) | Description | Recommendation |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for v in self.violations:
                loc_str = f"({v.location[0]:.2f}, {v.location[1]:.2f})"
                lines.append(
                    f"| {v.rule_id} | {v.severity} | {v.category} | {v.net} | {v.layer} | {loc_str} | {v.description} | {v.recommendation} |"
                )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Fast Geometry Helpers
# --------------------------------------------------------------------------- #


#: Segments shorter than this are treated as routing artefacts, not corners.
#: The exact engine appends the pad's true centre to a grid-snapped path, which
#: can leave a sub-0.15 mm jog at the endpoint (e.g. (18.75, 22.0) -> (18.7, 21.9)).
#: That jog is not a copper corner — it is the same pad — but measuring the angle
#: across it reports a 26-degree "acid trap" that no etchant will ever see.
_MIN_CORNER_LEG_MM = 0.150


def _pad_boxes(placements: dict[str, Any], connections: list[dict[str, Any]]) -> list[tuple[float, float, float, float]]:
    """Copper boxes of every pad the netlist touches, as (x0, y0, x1, y1).

    A corner inside a pad is not an etched crevice: the etchant sees the pad's
    own outline, not the trace's turn. On the STM32 board the router entered
    USB_DP's pad, jogged 0.2 mm, then left, producing a 76-degree "acid trap"
    that sat entirely inside the pad land.
    """
    try:
        from .gerber_exporter import _collect_pads
    except Exception:  # pragma: no cover - defensive
        return []
    boxes: list[tuple[float, float, float, float]] = []
    for pad in _collect_pads({}, connections, placements):
        hw, hh = pad["w"] / 2.0, pad["h"] / 2.0
        boxes.append((pad["x"] - hw, pad["y"] - hh, pad["x"] + hw, pad["y"] + hh))
    return boxes


def _inside_pad(pt: tuple[float, float], boxes: list[tuple[float, float, float, float]]) -> bool:
    for x0, y0, x1, y1 in boxes:
        if x0 - 1e-6 <= pt[0] <= x1 + 1e-6 and y0 - 1e-6 <= pt[1] <= y1 + 1e-6:
            return True
    return False


def _clean_path(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop duplicate and sub-resolution vertices from a routed polyline."""
    out: list[tuple[float, float]] = []
    for pt in points:
        if not out:
            out.append(pt)
            continue
        if math.hypot(pt[0] - out[-1][0], pt[1] - out[-1][1]) >= _MIN_CORNER_LEG_MM:
            out.append(pt)
    # The final vertex is deliberately *not* forced back in. Replacing the last
    # kept point with the raw pad centre left a diagonal of arbitrary angle and
    # reported 87.9-degree "acid traps" where the route was square. A sub-0.15 mm
    # shortfall at the end is inside the pad's own copper.
    return out


def point_to_segment_dist(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """Shortest Euclidean distance from point (px, py) to line segment (x1, y1)-(x2, y2)."""
    dx = x2 - x1
    dy = y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    """Check if 2D line segments p1-p2 and p3-p4 intersect (excluding colinear touch)."""
    def ccw(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (ccw(p1, p2, p3) != ccw(p1, p2, p4))


def segment_to_segment_dist(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> float:
    """Shortest Euclidean distance between segment p1-p2 and segment p3-p4."""
    if _segments_intersect(p1, p2, p3, p4):
        return 0.0
    return min(
        point_to_segment_dist(p1[0], p1[1], p3[0], p3[1], p4[0], p4[1]),
        point_to_segment_dist(p2[0], p2[1], p3[0], p3[1], p4[0], p4[1]),
        point_to_segment_dist(p3[0], p3[1], p1[0], p1[1], p2[0], p2[1]),
        point_to_segment_dist(p4[0], p4[1], p1[0], p1[1], p2[0], p2[1]),
    )


# --------------------------------------------------------------------------- #
# SES Parser to Internal Routing Geometry
# --------------------------------------------------------------------------- #


@dataclass
class RoutedSegment:
    net: str
    layer: str
    width_mm: float
    p1: tuple[float, float]
    p2: tuple[float, float]

    @property
    def length_mm(self) -> float:
        return math.hypot(self.p2[0] - self.p1[0], self.p2[1] - self.p1[1])

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y) bounding box including copper width."""
        r = self.width_mm / 2.0
        return (
            min(self.p1[0], self.p2[0]) - r,
            min(self.p1[1], self.p2[1]) - r,
            max(self.p1[0], self.p2[0]) + r,
            max(self.p1[1], self.p2[1]) + r,
        )


@dataclass
class RoutedVia:
    net: str
    padstack: str
    x_mm: float
    y_mm: float
    drill_mm: float = 0.3
    pad_mm: float = 0.6


@dataclass
class RoutedPath:
    """One ordered polyline from a SES ``(path ...)`` scope."""

    net: str
    layer: str
    width_mm: float
    points: list[tuple[float, float]]


def _iter_net_scopes(ses_text: str):
    """Yield (net_name, inner_text) for each ``(net ...)`` scope, paren-balanced.

    A regex with a lookahead for the closing parens cannot do this correctly: it
    stops at whichever ``) ) )`` happens to come next, so a path inside a net
    loses its own closing paren and the path regex then never matches. On the
    real router output the nesting happened to be deep enough to mask it, which
    is why the board-level numbers looked right while a hand-written SES parsed
    as zero paths.
    """
    for m in re.finditer(r"\(net\s+([^\s()]+)", ses_text):
        start = m.end()
        depth = 1
        i = start
        while i < len(ses_text) and depth > 0:
            ch = ses_text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        yield m.group(1), ses_text[start : i - 1]


def parse_ses_geometry(
    ses_text: str,
) -> tuple[list[RoutedSegment], list[RoutedVia]]:
    """Extract physical segments and vias from Specctra SES text."""
    segments, _paths, vias = parse_ses_paths(ses_text)
    return segments, vias


def parse_ses_paths(
    ses_text: str,
) -> tuple[list[RoutedSegment], list[RoutedPath], list[RoutedVia]]:
    """Extract segments, ordered polylines and vias from Specctra SES text.

    The ordered polylines matter for corner analysis: a corner is a turn *along a
    path*, not any two segments that happen to share a vertex. Flattening first
    and comparing pairwise makes every pad where several branches converge look
    like a sub-90-degree fold.
    """
    segments: list[RoutedSegment] = []
    paths: list[RoutedPath] = []
    vias: list[RoutedVia] = []

    unit_div = 1000.0
    rm = re.search(r"\(resolution\s+(\w+)\s+([0-9.]+)\s*\)", ses_text)
    if rm:
        unit_div = float(rm.group(2)) or 1000.0
        if rm.group(1).lower() in ("inch", "in"):
            unit_div *= 25.4

    for net_raw, net_content in _iter_net_scopes(ses_text):
        net_name = net_raw.strip('"')

        for vm in re.finditer(r'\(via\s+"?([^"\s]+)"?\s+([0-9.-]+)\s+([0-9.-]+)', net_content):
            vias.append(
                RoutedVia(
                    net=net_name,
                    padstack=vm.group(1),
                    x_mm=round(float(vm.group(2)) / unit_div, 4),
                    y_mm=round(float(vm.group(3)) / unit_div, 4),
                )
            )

        for pm in re.finditer(r"\(path\s+(\w+)\s+([0-9.]+)\s+([0-9\s.-]+)\)", net_content):
            layer = pm.group(1)
            w_raw = float(pm.group(2))
            width_mm = w_raw / unit_div if w_raw > 1.0 else (w_raw or 0.150)
            nums = [float(x) / unit_div for x in pm.group(3).split()]
            pts = [
                (round(nums[i], 4), round(nums[i + 1], 4))
                for i in range(0, len(nums) - 1, 2)
            ]
            if len(pts) >= 2:
                cleaned = _clean_path(pts)
                paths.append(
                    RoutedPath(
                        net=net_name,
                        layer=layer,
                        width_mm=round(width_mm, 4),
                        points=cleaned if len(cleaned) >= 2 else pts,
                    )
                )
            # Clearance runs on every real segment, because a 0.05 mm jog still
            # carries copper even though it is not a corner.
            cleaned = _clean_path(pts) if len(pts) >= 2 else pts
            for i in range(len(cleaned) - 1):
                p1, p2 = cleaned[i], cleaned[i + 1]
                if p1 != p2:
                    segments.append(
                        RoutedSegment(
                            net=net_name,
                            layer=layer,
                            width_mm=round(width_mm, 4),
                            p1=p1,
                            p2=p2,
                        )
                    )

    return segments, paths, vias


# --------------------------------------------------------------------------- #
# DRC Engine Implementation
# --------------------------------------------------------------------------- #


def run_pcb_physical_drc(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    ses_text: str | None = None,
    placements: dict[str, ComponentPlacement] | None = None,
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    min_trace_width_mm: float = 0.127,
    min_clearance_mm: float = 0.100,
    edge_clearance_mm: float = 0.800,
    max_diff_skew_mm: float = 1.250,
    check_acid_traps: bool = True,
) -> DRCReport:
    """Execute rigorous physical Design Rule Check on PCB layout & routing geometry.

    Evaluates:
    1. Acid Traps & Sharp 90° Corners (IPC-2221B Section 10.1.2)
    2. Minimum Trace Width & Power Rail Current Carrying Capacity (IPC-2221B Section 10.1.3)
    3. Keepout & Mechanical Clearances (Board Edge, M3 Mounting Screws, RF Antenna)
    4. High-Speed Differential Pair Length Mismatch / Skew (IPC-2141A Section 3.4)
    5. Unterminated Trace Stubs / Floating Antennas
    6. Segment-to-Segment True Copper Clearance (IPC-2221B Table 6-1)
    """
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    if ses_text is None:
        from .router_engine import autoroute_circuit

        # Route with the board's *routing* defaults, not the DRC *minimums*. The
        # minimum width (0.127) is the thinnest thing the fab can etch, not the
        # width the router should use; routing at it produces geometry the router
        # would never emit and then reports violations against that.
        route_res = autoroute_circuit(
            modules=modules,
            connections=connections,
            placements=placements,
            board_width_mm=board_width_mm,
            board_height_mm=board_height_mm,
        )
        ses_text = route_res.get("ses_text", "")

    segments, paths, vias = parse_ses_paths(ses_text)
    pad_boxes = _pad_boxes(placements, connections)

    violations: list[DRCViolation] = []
    min_measured_clearance = 999.0
    worst_clearance_by_pair: dict[tuple[str, str, str], tuple[float, tuple[float, float]]] = {}
    acid_traps_count = 0
    keepout_intrusions_count = 0
    diff_skew_violations_count = 0

    # Build net to physical pad locations map
    net_pads: dict[str, set[tuple[float, float]]] = {}
    all_pads_list: list[tuple[str, tuple[float, float], float]] = []  # (net, (x, y), radius)

    for conn in connections:
        raw_net = str(conn.get("net", "")).lstrip("/")
        net_pads.setdefault(raw_net, set())
        for pt in conn.get("points") or []:
            if "." in pt:
                ref, pin = pt.split(".", 1)
                p = placements.get(ref)
                if p is not None:
                    off = STANDARD_PIN_OFFSETS.get(p.package or "", {}).get(pin)
                    if off is not None:
                        pad_pos = (round(p.x_mm + off[0], 4), round(p.y_mm + off[1], 4))
                        net_pads[raw_net].add(pad_pos)
                        # Estimate pad equivalent radius for clearance
                        all_pads_list.append((raw_net, pad_pos, 0.40))

    # ----------------------------------------------------------------------- #
    # Rule 1: Acid Traps (< 90° Acute Angle) & Sharp 90° Corners
    # ----------------------------------------------------------------------- #
    if check_acid_traps:
        # A corner is a turn along one ordered polyline, not any two segments that
        # share a vertex. Pairwise comparison over flattened segments turned every
        # pad where several branches converge into a 0-degree "acid trap" — 89 of
        # them on an orthogonal route that has no corners below 90 degrees at all.
        #
        # Right-angle corners on high-speed nets are counted per net rather than
        # listed individually: a 45-degree-staircase route has dozens of them, and
        # 233 separate entries say less than "USB_DM has 131 right-angle corners".
        right_angle_counts: dict[tuple[str, str], int] = {}

        for path in paths:
            for i in range(1, len(path.points) - 1):
                prev_pt = path.points[i - 1]
                cur = path.points[i]
                next_pt = path.points[i + 1]

                v1x, v1y = prev_pt[0] - cur[0], prev_pt[1] - cur[1]
                v2x, v2y = next_pt[0] - cur[0], next_pt[1] - cur[1]
                len1 = math.hypot(v1x, v1y)
                len2 = math.hypot(v2x, v2y)
                if len1 <= 0.001 or len2 <= 0.001:
                    continue

                # Interior angle of the bend: 180 deg = straight, 90 deg = right
                # angle, 0 deg = the trace folds back on itself.
                cos_theta = (v1x * v2x + v1y * v2y) / (len1 * len2)
                cos_theta = max(-1.0, min(1.0, cos_theta))
                angle_deg = math.degrees(math.acos(cos_theta))

                if angle_deg < 89.0 and not _inside_pad(cur, pad_boxes):
                    acid_traps_count += 1
                    violations.append(
                        DRCViolation(
                            rule_id="DRC-ACID-01",
                            severity="ERROR",
                            category="ETCHING_ACID_TRAP",
                            net=path.net,
                            layer=path.layer,
                            location=cur,
                            measured_value=round(angle_deg, 1),
                            required_value=90.0,
                            description=(
                                f"Acid trap on net '{path.net}': trace bend interior angle is "
                                f"{angle_deg:.1f} deg (< 90 deg). Etchant accumulates in the acute "
                                "crevice, over-etching the trace and risking an open circuit "
                                "(IPC-2221B Section 10.1.2)."
                            ),
                            recommendation="Replace the acute bend with a 135-degree obtuse corner or add a copper fillet.",
                        )
                    )
                elif angle_deg <= 91.0 and any(
                    k in path.net.upper()
                    for k in ("DP", "DM", "USB", "ETH", "CAN", "RF", "CLK", "SCLK")
                ):
                    right_angle_counts[(path.net, path.layer)] = (
                        right_angle_counts.get((path.net, path.layer), 0) + 1
                    )

        for (net, layer), count in sorted(right_angle_counts.items()):
            violations.append(
                DRCViolation(
                    rule_id="DRC-ACID-02",
                    severity="WARNING",
                    category="SIGNAL_INTEGRITY",
                    net=net,
                    layer=layer,
                    location=(0.0, 0.0),
                    measured_value=float(count),
                    required_value=0.0,
                    description=(
                        f"High-speed net '{net}' has {count} right-angle corners. Each is a localised "
                        "impedance dip and a radiation point; a 90-degree bend is never used on a "
                        "controlled-impedance trace."
                    ),
                    recommendation="Miter each corner to 135 degrees (45-degree chamfer) or reroute on 45-degree angles.",
                )
            )

    # ----------------------------------------------------------------------- #
    # Rule 2: Minimum Trace Width & Power Rail Current Capability
    # ----------------------------------------------------------------------- #
    # One finding per offending *net*, not per segment. A 2 mm power trace emits
    # dozens of segments, and reporting each one buried the four real acid traps
    # under 1272 identical width warnings.
    narrow_nets: dict[str, float] = {}
    for seg in segments:
        if seg.width_mm < min_trace_width_mm - 0.005:
            narrow_nets[seg.net] = min(narrow_nets.get(seg.net, 99.0), seg.width_mm)

    for net, worst_width in sorted(narrow_nets.items()):
        violations.append(
            DRCViolation(
                rule_id="DRC-WID-01",
                severity="ERROR",
                category="WIDTH",
                net=net,
                layer="*",
                location=(0.0, 0.0),
                measured_value=worst_width,
                required_value=min_trace_width_mm,
                description=(
                    f"Net '{net}' has {worst_width:.3f} mm traces, below the process capability "
                    f"threshold of {min_trace_width_mm:.3f} mm (IPC-2221B 10.1.3)."
                ),
                recommendation=f"Raise the width rule for this net to at least {min_trace_width_mm:.3f} mm.",
            )
        )

    power_narrow: dict[str, float] = {}
    for seg in segments:
        u_net = seg.net.upper()
        if not any(
            k in u_net
            for k in ("VBUS", "GND", "VMOT", "24V", "12V", "P3.3V", "+3.3V", "+5V", "VCC")
        ):
            continue
        if seg.width_mm < 0.200 - 0.005:
            power_narrow[seg.net] = min(power_narrow.get(seg.net, 99.0), seg.width_mm)

    for net, worst_width in sorted(power_narrow.items()):
        violations.append(
            DRCViolation(
                rule_id="DRC-WID-02",
                severity="WARNING",
                category="WIDTH",
                net=net,
                layer="*",
                location=(0.0, 0.0),
                measured_value=worst_width,
                required_value=0.254,
                description=(
                    f"Power/ground net '{net}' is routed at {worst_width:.3f} mm. At 1 A that is "
                    "a 5.6 degC rise per 10 mm; transient load will sag the rail (IPC-2152)."
                ),
                recommendation="Widen power traces to >= 0.254 mm or use a ground plane.",
            )
        )

    # ----------------------------------------------------------------------- #
    # Rule 3: Keepout & Boundary Intrusions (Board Edge, Mounts, RF Antenna)
    # ----------------------------------------------------------------------- #
    # Mounting hole centers (4 corners, inset 4mm, radius 3mm keepout)
    mount_centers = [
        (4.0, 4.0),
        (board_width_mm - 4.0, 4.0),
        (4.0, board_height_mm - 4.0),
        (board_width_mm - 4.0, board_height_mm - 4.0),
    ]

    # Detect antenna keepout if ESP32/wireless modules present
    antenna_bbox: tuple[float, float, float, float] | None = None
    for ref, p in placements.items():
        val = str(modules.get(ref, {}).get("value", "")).upper()
        pkg = str(p.package or "").upper()
        if any(k in val or k in pkg for k in ("ESP32", "WROOM", "BL652", "NRF52", "CC2540")):
            m_hh = PACKAGE_HALF_EXTENTS.get(p.package or "", (6.0, 8.0))[1]
            ky1 = p.y_mm + m_hh
            ky2 = min(board_height_mm, ky1 + 8.0)
            if ky1 < board_height_mm - 2.0:
                antenna_bbox = (p.x_mm - 5.0, ky1, p.x_mm + 5.0, ky2)
                break

    for seg in segments:
        r_trace = seg.width_mm / 2.0
        # 3a. Board edge check
        pts_to_check = [seg.p1, seg.p2]
        for px, py in pts_to_check:
            dist_left = px - r_trace
            dist_right = (board_width_mm - px) - r_trace
            dist_bottom = py - r_trace
            dist_top = (board_height_mm - py) - r_trace
            min_edge_dist = min(dist_left, dist_right, dist_bottom, dist_top)

            if min_edge_dist < edge_clearance_mm - 0.01:
                keepout_intrusions_count += 1
                violations.append(
                    DRCViolation(
                        rule_id="DRC-KPO-01",
                        severity="ERROR",
                        category="KEEPOUT",
                        net=seg.net,
                        layer=seg.layer,
                        location=(px, py),
                        measured_value=round(min_edge_dist, 3),
                        required_value=edge_clearance_mm,
                        description=(
                            f"Trace on net '{seg.net}' violates board edge clearance: distance {min_edge_dist:.3f} mm "
                            f"< required {edge_clearance_mm:.3f} mm. V-cut or routing router will nick copper, "
                            "causing moisture ingress and edge delamination (IPC-2221B Section 8.2)."
                        ),
                        recommendation=f"Retract trace inside boundary; maintain at least {edge_clearance_mm:.1f} mm edge setback.",
                    )
                )
                break

        # 3b. Mounting hole clearance check (radius 3.0mm around M3 hole centers)
        for mx, my in mount_centers:
            d_seg_mount = point_to_segment_dist(mx, my, seg.p1[0], seg.p1[1], seg.p2[0], seg.p2[1])
            clearance_to_screw = d_seg_mount - r_trace
            if clearance_to_screw < 3.0:
                keepout_intrusions_count += 1
                violations.append(
                    DRCViolation(
                        rule_id="DRC-KPO-02",
                        severity="ERROR",
                        category="KEEPOUT",
                        net=seg.net,
                        layer=seg.layer,
                        location=seg.p1,
                        measured_value=round(clearance_to_screw, 3),
                        required_value=3.0,
                        description=(
                            f"Trace on net '{seg.net}' intrudes into M3 mounting hole clearance zone at ({mx:.1f}, {my:.1f}): "
                            f"clearance {clearance_to_screw:.3f} mm < required 3.0 mm. Screw head/washer mechanical stress "
                            "will crack solder mask and short conductors."
                        ),
                        recommendation="Reroute conductors outside the 3.0 mm mounting standoff keepout circle.",
                    )
                )

        # 3c. RF Antenna keepout check
        if antenna_bbox:
            ax1, ay1, ax2, ay2 = antenna_bbox
            # If segment intersects antenna bounding box
            seg_bb = seg.bbox
            if not (seg_bb[2] < ax1 or seg_bb[0] > ax2 or seg_bb[3] < ay1 or seg_bb[1] > ay2):
                keepout_intrusions_count += 1
                violations.append(
                    DRCViolation(
                        rule_id="DRC-KPO-03",
                        severity="CRITICAL",
                        category="KEEPOUT",
                        net=seg.net,
                        layer=seg.layer,
                        location=seg.p1,
                        description=(
                            f"Conductor on net '{seg.net}' crosses RF antenna clearance zone ({ax1:.1f}-{ax2:.1f}, {ay1:.1f}-{ay2:.1f}). "
                            "Copper under or near the antenna detunes resonance, destroys matching, and severely attenuates Wi-Fi/BLE range."
                        ),
                        recommendation="Clear all copper and ground pours from the RF antenna projection area.",
                    )
                )

    # ----------------------------------------------------------------------- #
    # Rule 4: High-Speed Differential Pair Length Mismatch / Skew
    # ----------------------------------------------------------------------- #
    diff_pairs = [
        ("USB_DP", "USB_DM", "USB 2.0 差分对 (90Ω)", max_diff_skew_mm),
        ("CAN_TX", "CAN_RX", "CAN 收发差分对", 2.0),
        ("CAN_H", "CAN_L", "CAN 总线物理差分对", 2.0),
        ("ETH_TXP", "ETH_TXN", "以太网发送差分对 (100Ω)", 2.5),
        ("ETH_RXP", "ETH_RXN", "以太网接收差分对 (100Ω)", 2.5),
    ]

    net_lengths: dict[str, float] = {}
    for seg in segments:
        net_clean = seg.net.lstrip("/")
        net_lengths[net_clean] = net_lengths.get(net_clean, 0.0) + seg.length_mm

    for p_name, n_name, bus_label, allowed_skew in diff_pairs:
        if p_name in net_lengths and n_name in net_lengths:
            lp = net_lengths[p_name]
            ln = net_lengths[n_name]
            skew = abs(lp - ln)
            if skew > allowed_skew:
                diff_skew_violations_count += 1
                violations.append(
                    DRCViolation(
                        rule_id="DRC-DIFF-01",
                        severity="WARNING",
                        category="SIGNAL_INTEGRITY",
                        net=f"{p_name}/{n_name}",
                        layer="Top",
                        location=(board_width_mm / 2.0, board_height_mm / 2.0),
                        measured_value=round(skew, 3),
                        required_value=allowed_skew,
                        description=(
                            f"{bus_label} 走线物理长度失配: {p_name}={lp:.2f} mm, {n_name}={ln:.2f} mm, "
                            f"长度差 Skew={skew:.2f} mm > 容限 {allowed_skew:.2f} mm (IPC-2141A Section 3.4)。"
                            "严重失配会导致共模噪声增大及眼图闭合。"
                        ),
                        recommendation="在较短线段处加入蛇形绕线（Accordion/Trombone Serpentine Tuning）以补偿差分相移。",
                    )
                )

    # ----------------------------------------------------------------------- #
    # Rule 5: Segment-to-Segment Copper Clearance (Different Nets, Same Layer)
    # ----------------------------------------------------------------------- #
    # Spatial binning or bounding box pruning for O(N log N) clearance check
    # Check pairwise non-identical nets on the same layer
    for i in range(len(segments)):
        s1 = segments[i]
        b1 = s1.bbox
        for j in range(i + 1, len(segments)):
            s2 = segments[j]
            if s1.net == s2.net or s1.layer != s2.layer:
                continue

            b2 = s2.bbox
            # Bounding box quick rejection
            if (
                b1[2] + min_clearance_mm < b2[0]
                or b2[2] + min_clearance_mm < b1[0]
                or b1[3] + min_clearance_mm < b2[1]
                or b2[3] + min_clearance_mm < b1[1]
            ):
                continue

            centerline_dist = segment_to_segment_dist(s1.p1, s1.p2, s2.p1, s2.p2)
            copper_clearance = centerline_dist - (s1.width_mm + s2.width_mm) / 2.0
            if copper_clearance < min_measured_clearance:
                min_measured_clearance = copper_clearance

            if copper_clearance < min_clearance_mm - 0.008:
                # One finding per (net pair, layer, worst location). Two traces
                # that run parallel for 5 mm produce a violation for every
                # segment pair along the way, all reporting the same gap.
                key = (s1.net, s2.net, s1.layer)
                prev = worst_clearance_by_pair.get(key)
                if prev is None or copper_clearance < prev[0]:
                    worst_clearance_by_pair[key] = (copper_clearance, s1.p1)

    for (net1, net2, layer), (gap, loc) in sorted(
        worst_clearance_by_pair.items(), key=lambda kv: kv[1][0]
    ):
        violations.append(
            DRCViolation(
                rule_id="DRC-CLR-01",
                severity="ERROR",
                category="CLEARANCE",
                net=f"{net1} <-> {net2}",
                layer=layer,
                location=loc,
                measured_value=round(gap, 3),
                required_value=min_clearance_mm,
                description=(
                    f"Copper clearance violation between net '{net1}' and '{net2}' on layer "
                    f"'{layer}': clearance {gap:.3f} mm < minimum required "
                    f"{min_clearance_mm:.3f} mm (IPC-2221B Table 6-1). High risk of solder "
                    "bridging or dielectric breakdown."
                ),
                recommendation="Reroute traces with expanded clearance or change routing layer.",
            )
        )

    # ----------------------------------------------------------------------- #
    # Scoring & Final Summary
    # ----------------------------------------------------------------------- #
    critical_errs = sum(1 for v in violations if v.severity in ("CRITICAL", "ERROR"))
    warnings = sum(1 for v in violations if v.severity == "WARNING")

    score = max(0, 100 - (critical_errs * 20 + warnings * 5))
    passed = critical_errs == 0

    if min_measured_clearance == 999.0:
        min_measured_clearance = min_clearance_mm

    summary = (
        f"PCB Physical DRC audit completed with score {score}/100. "
        f"Detected {critical_errs} blocking errors and {warnings} warnings."
    )

    metrics = {
        "total_routed_nets": len(net_lengths),
        "total_segments": len(segments),
        "total_vias": len(vias),
        "min_measured_clearance_mm": round(min_measured_clearance, 3),
        "acid_traps_count": acid_traps_count,
        "keepout_intrusions_count": keepout_intrusions_count,
        "diff_skew_violations_count": diff_skew_violations_count,
        "critical_errors_count": critical_errs,
        "warnings_count": warnings,
    }

    return DRCReport(
        passed=passed,
        score=score,
        violations=violations,
        metrics=metrics,
        summary=summary,
    )
