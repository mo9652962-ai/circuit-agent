"""Tests for the physical DRC that gates the router's output.

Each test here encodes a defect that was measured on a real board, not a
hypothetical: the exact engine reported 100% completion while leaving a
0.060 mm gap against a 0.100 mm rule, and the acid-trap check first reported
89 traps on an orthogonal route that has no acute corners at all.
"""

import math
import sys

import pytest

sys.path.insert(0, ".")

from client.pcb_drc import (
    _clean_path,
    point_to_segment_dist,
    run_pcb_physical_drc,
    segment_to_segment_dist,
)
from client.placement_engine import ComponentPlacement
from client.synthesizer import synthesize_from_prompt

ENV_NODE = "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键"


@pytest.fixture(scope="module")
def env_node_report():
    """Route the reference board once for the whole module.

    Each full route takes ~20 s, and six tests that each re-route the same board
    turned this file into a 15-minute suite. The routing is deterministic, so one
    shared report is the same evidence as six.
    """
    spec = synthesize_from_prompt(ENV_NODE)
    return run_pcb_physical_drc(spec["modules"], spec["netlist"]["connections"])


@pytest.fixture(scope="module")
def env_node_route():
    from client.router_engine import autoroute_circuit

    spec = synthesize_from_prompt(ENV_NODE)
    return autoroute_circuit(spec["modules"], spec["netlist"]["connections"])


def _ses(paths: list[str]) -> str:
    """Build a minimal SES document shaped like the router's real output.

    Two details matter and both cost a debugging round:
    * coordinates are in resolution units — with ``(resolution mm 1000)`` a 10 mm
      vertex is written as 10000. Writing millimetres made every test path
      collapse to a 0.01 mm speck that produced no corners, so the "no violation"
      assertions passed without exercising anything;
    * ``(path ...)`` lives *inside* a ``(wire ...)`` inside a ``(net ...)`` scope,
      with the coordinates on their own lines.
    """
    body = "\n".join(paths)
    return f"""(session "probe"
  (base_design "probe.dsn")
  (resolution mm 1000)
  (routes
{body}
  )
)
"""


def _path(net: str, layer: str, width: float, coords: list[tuple[float, float]]) -> str:
    """Emit one SES net/wire/path block. ``width`` and ``coords`` are millimetres."""
    pts = "\n".join(f"            {x * 1000:g} {y * 1000:g}" for x, y in coords)
    return f"""    (net {net}
      (wire
        (path {layer} {width * 1000:g}
{pts}
        )
      )
    )"""


class TestAcidTrapDetection:
    """Corner detection must measure the bend, not the vertex."""

    def test_obtuse_bend_is_not_an_acid_trap(self):
        """A 135-degree bend is the recommended corner, not a defect.

        (0,0) -> (5,0) -> (10,5) turns by 45 degrees, so its *interior* angle is
        135 degrees — exactly what IPC-2221B asks for. An earlier version of this
        file asserted the opposite and would have locked in the wrong rule.
        """
        a, b, c = (0, 0), (5, 0), (10, 5)
        v1 = (a[0] - b[0], a[1] - b[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (math.hypot(*v1) * math.hypot(*v2))
        assert abs(math.degrees(math.acos(cos)) - 135.0) < 0.01

        ses = _ses([_path("N1", "Top", 0.2, [(0, 0), (5, 0), (10, 5)])])
        res = run_pcb_physical_drc(modules={}, connections=[], ses_text=ses)
        assert [v for v in res.violations if v.rule_id == "DRC-ACID-01"] == []

    def test_right_angle_is_not_an_acid_trap(self):
        ses = _ses([_path("N1", "Top", 0.2, [(0, 0), (5, 0), (5, 5)])])
        res = run_pcb_physical_drc(modules={}, connections=[], ses_text=ses)
        acid = [v for v in res.violations if v.rule_id == "DRC-ACID-01"]
        assert acid == [], f"90-degree corner wrongly flagged: {acid}"

    def test_pad_jitter_is_not_a_corner(self):
        """The exact engine appends the pad centre, leaving a sub-0.15 mm jog.

        On the real board this produced (18.75, 21.75) -> (18.75, 22.0) ->
        (18.7, 21.9): a 26.6-degree "acid trap" at a pad that carries no corner.
        The jog is dropped, and the last *meaningful* vertex is kept — forcing
        the raw endpoint back in would recreate a diagonal of arbitrary angle.
        """
        points = [(19.0, 21.5), (19.0, 21.75), (18.75, 21.75), (18.75, 22.0), (18.7, 21.9)]
        cleaned = _clean_path([(float(x), float(y)) for x, y in points])
        assert (18.7, 21.9) not in cleaned
        assert cleaned[-1] == (18.75, 22.0)
        assert len(cleaned) < len(points)

    def test_real_acute_corner_survives_cleaning(self):
        """Cleaning must not erase a genuine 26-degree bend."""
        points = [(0.0, 0.0), (10.0, 0.0), (10.5, 0.25)]
        cleaned = _clean_path(points)
        assert cleaned == points

    def test_acute_corner_inside_a_pad_is_not_reported(self):
        """A jog inside a pad land is not an etched crevice.

        R0603 pad 1 sits at (-0.75, 0) with a 0.8 x 0.95 mm land, so it covers
        x in [-1.15, -0.35] and y in [-0.475, 0.475]. The route comes in from
        below, doubles back toward the pad centre at a 22.6-degree interior
        angle, then leaves — geometrically an acid trap, but the etchant only
        ever sees the pad's rectangular outline.
        """
        placements = {
            "R1": ComponentPlacement(ref="R1", package="R0603", x_mm=0.0, y_mm=0.0),
        }
        connections = [{"net": "N1", "points": ["R1.1", "R1.2"]}]
        # Bend at (-0.75, 0.0) — the centre of pad 1. The route climbs into the
        # pad, then folds back down-right at a 26.6-degree interior angle, which
        # is the crevice shape that traps etchant.
        ses = _ses(
            [
                _path(
                    "N1",
                    "Top",
                    0.2,
                    [(-0.75, -1.5), (-0.75, 0.0), (-0.25, -0.25), (-0.25, -1.5)],
                ),
            ]
        )
        res = run_pcb_physical_drc(
            modules={}, connections=connections, ses_text=ses, placements=placements
        )
        acid = [v for v in res.violations if v.rule_id == "DRC-ACID-01"]
        assert acid == [], f"corner inside a pad wrongly reported: {acid}"

    def test_acute_corner_outside_a_pad_is_reported(self):
        """A genuine fold-back in open copper must still be an error.

        (0,0) -> (10,0) -> (5,-0.5) doubles back, giving a 5.7-degree interior
        angle — the crevice etchant actually collects in.
        """
        ses = _ses([_path("N1", "Top", 0.2, [(0, 0), (10, 0), (5, -0.5)])])
        res = run_pcb_physical_drc(modules={}, connections=[], ses_text=ses)
        acid = [v for v in res.violations if v.rule_id == "DRC-ACID-01"]
        assert len(acid) == 1, f"expected one acid trap, got {len(acid)}"
        assert acid[0].measured_value < 30.0
        assert res.metrics["acid_traps_count"] == 1


class TestClearanceDetection:
    def test_overlapping_segments_are_caught(self):
        d = segment_to_segment_dist((0, 0), (10, 0), (5, -5), (5, 5))
        assert d == pytest.approx(0.0, abs=1e-9)

    def test_parallel_segments_report_gap(self):
        d = segment_to_segment_dist((0, 0), (10, 0), (0, 0.5), (10, 0.5))
        assert d == pytest.approx(0.5, abs=1e-9)

    def test_point_to_segment_distance(self):
        assert point_to_segment_dist(5, 3, 0, 0, 10, 0) == pytest.approx(3.0)
        # Beyond the endpoint the distance is to the endpoint, not the line.
        assert point_to_segment_dist(-4, 0, 0, 0, 10, 0) == pytest.approx(4.0)

    def test_parallel_traces_report_one_finding(self):
        """Two traces running side by side must not emit one finding per segment.

        The real board reported the same 0.060 mm GND/P3.3V gap twice because two
        adjacent segment pairs both violated it. A net pair is one problem.

        The trace here is deliberately a staircase rather than a straight run: a
        straight run is two segments with a single (p1, p2) pair, so a per-segment
        implementation would still emit exactly one finding and the test would
        pass against the defect it exists to catch.
        """
        stair = [(x, 0) for x in range(0, 21, 2)]
        ses = _ses(
            [
                _path("A", "Top", 0.2, stair),
                _path("B", "Top", 0.2, [(x, 0.23) for x, _ in stair]),
            ]
        )
        res = run_pcb_physical_drc(modules={}, connections=[], ses_text=ses)
        clr = [v for v in res.violations if v.rule_id == "DRC-CLR-01"]
        assert len(clr) == 1, f"expected one finding for the net pair, got {len(clr)}"

    def test_real_board_meets_clearance(self, env_node_report):
        """The shipped board must not violate its own clearance rule."""
        clr = [v for v in env_node_report.violations if v.rule_id == "DRC-CLR-01"]
        assert clr == [], f"clearance violations: {[(v.net, v.measured_value) for v in clr]}"


class TestReportUsability:
    """A report with 1723 entries hides the 4 that matter."""

    def test_report_is_not_saturated(self, env_node_report):
        assert len(env_node_report.violations) < 40, (
            f"{len(env_node_report.violations)} violations — findings must be aggregated per net"
        )

    def test_width_findings_are_per_net(self, env_node_report):
        width = [v for v in env_node_report.violations if v.rule_id in ("DRC-WID-01", "DRC-WID-02")]
        nets = [v.net for v in width]
        assert len(nets) == len(set(nets)), f"duplicate width findings per net: {nets}"

    def test_metrics_are_populated(self, env_node_report):
        assert env_node_report.metrics["total_segments"] > 0
        assert env_node_report.metrics["total_routed_nets"] > 0
        assert env_node_report.metrics["min_measured_clearance_mm"] > 0


class TestRouterGating:
    """autoroute_circuit must not hand back a board that fails DRC."""

    def test_router_returns_a_passing_board(self, env_node_route):
        assert env_node_route["drc_passed"] is True, (
            f"router returned a failing board; engines tried: {env_node_route.get('engines_tried')}; "
            f"errors: {[v['rule_id'] for v in env_node_route.get('drc', {}).get('violations', [])]}"
        )

    def test_router_reports_which_engines_it_tried(self, env_node_route):
        assert isinstance(env_node_route.get("engines_tried"), list)
        assert env_node_route["engines_tried"], "engines_tried must record the engine actually used"

    def test_routed_nets_are_complete(self, env_node_route):
        m = env_node_route["metrics"]
        assert m["routed_nets_count"] == m["total_nets"], (
            f"only {m['routed_nets_count']}/{m['total_nets']} nets routed"
        )
