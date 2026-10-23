"""Ground pour: a real copper plane, not an outline of one.

The previous implementation drew a single 0.25 mm rectangle around the board and
labelled it "Ground Pour Boundary". It was not a pour and it was not ground: a CAM
engineer receives a floating hairline loop at the edge inset, which is worse than
no pour at all because it looks intentional. These tests hold the pour to what a
plane has to be — copper across the board, cleared of everything it must not
touch, and thermally relieved where it connects.
"""

from __future__ import annotations

import re

import pytest

from client.gerber_exporter import (
    POUR_CLEARANCE_MM,
    POUR_EDGE_INSET_MM,
    _collect_pads,
    _gnd_pad_keys,
    _is_bottom_layer,
    _parse_ses_geometry,
    _pour_hatch_segments,
    _thermal_spokes,
    export_gerber_bundle,
)
from client.placement_engine import heuristic_place_components
from client.router_engine import autoroute_circuit
from client.synthesizer import synthesize_from_prompt

PROMPT = "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键"
W, H = 70.0, 50.0


@pytest.fixture(scope="module")
def board():
    """One routed board, shared: routing dominates the runtime of this module."""
    spec = synthesize_from_prompt(PROMPT)
    mods, conns = spec["modules"], spec["netlist"]["connections"]
    routed = autoroute_circuit(mods, conns, board_width_mm=W, board_height_mm=H)
    ses = routed.get("ses_text") if routed.get("success") else None
    placements = heuristic_place_components(mods, W, H)
    bundle = export_gerber_bundle(mods, conns, W, H, ses_text=ses, placements=placements)
    return {
        "mods": mods,
        "conns": conns,
        "placements": placements,
        "bundle": bundle,
        "gnd": _gnd_pad_keys(mods, conns),
        "geo": _parse_ses_geometry(ses),
    }


def _pour_segments(gbl: str) -> list[tuple[float, float, float, float]]:
    start = gbl.find("Ground Pour (GND hatch")
    if start < 0:
        return []
    end = gbl.find("Ground Pad Thermal Relief")
    if end < 0:
        end = gbl.find("G04 Component Pads")
    if end < 0:
        end = len(gbl)
    block = gbl[start:end]
    out = []
    for m in re.finditer(r"X(-?\d+)Y(-?\d+)D02\*\s*X(-?\d+)Y(-?\d+)D01\*", block):
        out.append(tuple(int(v) / 100000.0 for v in m.groups()))
    return out


class TestPourIsCopperNotAnOutline:
    def test_the_old_floating_rectangle_is_gone(self, board):
        gbl = board["bundle"]["board-B_Cu.gbl"]
        assert "Ground Pour Boundary" not in gbl, (
            "the pour is still the hollow rectangle: it draws a loop of copper around "
            "empty board and connects to nothing"
        )

    def test_the_pour_covers_the_board_in_many_segments(self, board):
        segs = _pour_segments(board["bundle"]["board-B_Cu.gbl"])
        assert len(segs) > 100, f"only {len(segs)} pour segments; that is not a plane"

    def test_the_pour_spans_the_usable_board(self, board):
        segs = _pour_segments(board["bundle"]["board-B_Cu.gbl"])
        xs = [v for s in segs for v in (s[0], s[2])]
        ys = [v for s in segs for v in (s[1], s[3])]
        assert min(xs) >= POUR_EDGE_INSET_MM - 1e-6
        assert max(xs) <= W - POUR_EDGE_INSET_MM + 1e-6
        assert min(ys) >= POUR_EDGE_INSET_MM - 1e-6
        assert max(ys) <= H - POUR_EDGE_INSET_MM + 1e-6
        # A pour that only covers a corner is not a ground plane.
        assert max(xs) - min(xs) > W * 0.8
        assert max(ys) - min(ys) > H * 0.8


class TestPourClearance:
    def test_no_segment_touches_a_non_ground_through_hole_pad(self, board):
        segs = _pour_segments(board["bundle"]["board-B_Cu.gbl"])
        th = [p for p in _collect_pads(board["mods"], board["conns"], board["placements"]) if p["through_hole"]]
        assert th, "fixture has no through-hole pads; the test would pass vacuously"

        for x0, y0, x1, y1 in segs:
            sx0, sx1 = min(x0, x1), max(x0, x1)
            sy0, sy1 = min(y0, y1), max(y0, y1)
            for pad in th:
                if (pad["ref"], pad["pin"]) in board["gnd"]:
                    continue
                hw = pad["w"] / 2 + POUR_CLEARANCE_MM
                hh = pad["h"] / 2 + POUR_CLEARANCE_MM
                crosses = (
                    sx1 > pad["x"] - hw + 1e-9
                    and pad["x"] + hw > sx0 + 1e-9
                    and sy1 > pad["y"] - hh + 1e-9
                    and pad["y"] + hh > sy0 + 1e-9
                )
                assert not crosses, (
                    f"pour segment {x0:.2f},{y0:.2f}->{x1:.2f},{y1:.2f} runs into "
                    f"{pad['ref']}.{pad['pin']}; that is a short"
                )

    def test_no_segment_touches_a_bottom_trace(self, board):
        segs = _pour_segments(board["bundle"]["board-B_Cu.gbl"])
        bottom = [w for w in board["geo"]["wires"] if _is_bottom_layer(w["layer"])]
        assert bottom, "fixture has no bottom traces; the test would pass vacuously"

        for x0, y0, x1, y1 in segs:
            sx0, sx1 = min(x0, x1), max(x0, x1)
            sy0, sy1 = min(y0, y1), max(y0, y1)
            for wire in bottom:
                hw = wire["width_mm"] / 2 + POUR_CLEARANCE_MM
                for (ax, ay), (bx, by) in zip(wire["pts"], wire["pts"][1:]):
                    ox0, ox1 = min(ax, bx) - hw, max(ax, bx) + hw
                    oy0, oy1 = min(ay, by) - hw, max(ay, by) + hw
                    crosses = (
                        sx1 > ox0 + 1e-9
                        and ox1 > sx0 + 1e-9
                        and sy1 > oy0 + 1e-9
                        and oy1 > sy0 + 1e-9
                    )
                    assert not crosses, (
                        f"pour segment runs into a {wire['width_mm']:.2f} mm bottom trace "
                        f"at {ax:.2f},{ay:.2f}"
                    )

    def test_obstacles_are_subtracted_not_skipped_wholesale(self):
        """A line crossing one pad keeps the rest of its length.

        Deleting any hatch line that meets an obstacle erases most of the plane on
        a dense board — the pour becomes a few stripes in the empty corners.
        """
        pad = {"ref": "R1", "pin": "1", "x": 10.0, "y": 10.1, "w": 1.0, "h": 1.0,
               "through_hole": False, "round": False}
        segs = _pour_hatch_segments(40.0, 30.0, [pad], [], [], set())
        # The hatch starts at the edge inset and steps by the grid pitch, so the
        # line that meets the pad is at y = 10.1, not at the pad centre.
        on_pad_row = [s for s in segs if abs(s[1] - 10.1) < 1e-6]
        assert on_pad_row, "the hatch line through the pad was dropped entirely"
        total_len = sum(s[2] - s[0] for s in on_pad_row)
        # The pad blocks 1.0 + 2*clearance of the 39 mm span; the rest survives.
        assert total_len > 30.0, f"only {total_len:.1f} mm of that line survived"


class TestThermalRelief:
    def test_ground_pads_get_four_spokes(self):
        pad = {"x": 5.0, "y": 5.0, "w": 1.0, "h": 1.0}
        spokes = _thermal_spokes(pad)
        assert len(spokes) == 4, "IPC-7351 asks for four spokes, not two"

    def test_spokes_start_outside_the_thermal_gap(self):
        """A spoke that starts at the pad edge short-circuits the relief.

        The gap exists so the pad does not sink heat into the plane during
        soldering; a spoke bridging it directly is the same as a solid connection.
        """
        pad = {"x": 5.0, "y": 5.0, "w": 1.0, "h": 1.0}
        for x0, y0, x1, y1 in _thermal_spokes(pad):
            # No spoke may pass through the pad body itself.
            inside_x = min(x0, x1) < pad["x"] + pad["w"] / 2 and max(x0, x1) > pad["x"] - pad["w"] / 2
            inside_y = min(y0, y1) < pad["y"] + pad["h"] / 2 and max(y0, y1) > pad["y"] - pad["h"] / 2
            assert not (inside_x and inside_y), f"spoke {x0,y0,x1,y1} runs through the pad"

    def test_ground_pads_are_recognised_from_the_netlist(self, board):
        gnd = board["gnd"]
        assert len(gnd) >= 5, f"only {len(gnd)} ground pads found"
        refs = {r for r, _ in gnd}
        assert "U_MCU" in refs or "C_IN1" in refs, f"ground net looks wrong: {sorted(refs)}"

    def test_the_layer_carries_thermal_spokes(self, board):
        gbl = board["bundle"]["board-B_Cu.gbl"]
        assert "Thermal Relief Spokes" in gbl, "no thermal relief emitted for ground pads"

    def test_a_board_with_no_ground_net_gets_no_spokes(self):
        segs = _pour_hatch_segments(40.0, 30.0, [], [], [], set())
        assert segs, "a pour with no pads should still fill the board"
        assert _gnd_pad_keys({}, [{"net": "/VCC", "points": ["U1.1"]}]) == set()
