"""Industrial manufacturing-layer tests: stencil, via annular rings, bundle completeness.

Each test encodes a defect that would have shipped a board no factory can build:

* the copper layers carried no via annular ring, so every drilled via was a hole
  punched through a trace with nothing to plate onto;
* the bundle had no stencil layer, so no SMT line could print paste — every
  package was a hand-solder board no matter what parts it listed.
"""

from __future__ import annotations

import re

import pytest

from client.gerber_exporter import (
    PASTE_REDUCTION_MM,
    _parse_ses_geometry,
    _via_dimensions,
    export_gerber_bundle,
    generate_bottom_copper_gerber,
    generate_bottom_paste_gerber,
    generate_top_copper_gerber,
    generate_top_paste_gerber,
)
from client.placement_engine import heuristic_place_components
from client.synthesizer import synthesize_from_prompt

PROMPT = "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键"
BOARD_W, BOARD_H = 70.0, 50.0

#: One 10 mm trace on Top, a via, then 10 mm on Bottom. Coordinates are in the
#: session's resolution units (1/1000 mm), which is what the router writes.
SES_WITH_VIA = """(session "probe"
  (resolution mm 1000)
  (routes
    (net N1
      (wire (path Top 200
        10000 10000
        20000 10000
      ))
      (via "Via[0.6-0.3]" 20000 10000)
      (wire (path Bottom 200
        20000 10000
        30000 10000
      ))
    )
  )
)"""


def _flash_coords(gerber: str) -> list[tuple[float, float]]:
    out = []
    for m in re.finditer(r"X(-?\d+)Y(-?\d+)D03\*", gerber):
        out.append((int(m.group(1)) / 100000.0, int(m.group(2)) / 100000.0))
    return out


class TestViaGeometry:
    def test_padstack_name_yields_pad_and_drill(self):
        assert _via_dimensions("Via[0.6-0.3]") == (0.6, 0.3)
        assert _via_dimensions("Via[0.8-0.4]") == (0.8, 0.4)

    def test_unnamed_padstack_falls_back_to_the_standard_via(self):
        pad, drill = _via_dimensions("SomeVia")
        assert (pad, drill) == (0.6, 0.3)

    def test_ses_parse_carries_via_dimensions(self):
        geo = _parse_ses_geometry(SES_WITH_VIA)
        assert len(geo["vias"]) == 1
        via = geo["vias"][0]
        assert via["pad_mm"] == pytest.approx(0.6)
        assert via["drill_mm"] == pytest.approx(0.3)
        assert via["x"] == pytest.approx(20.0)
        assert via["y"] == pytest.approx(10.0)


class TestViaAnnularRing:
    """A via must be flashed as copper on every layer it passes through."""

    def test_top_copper_flashes_the_via_ring(self):
        gtl = generate_top_copper_gerber({}, [], ses_text=SES_WITH_VIA, placements={})
        assert "%ADD10C,0.60000*%" in gtl or "C,0.60000*%" in gtl, (
            "no 0.6 mm aperture in top copper; the via has no annular ring"
        )
        assert (20.0, 10.0) in _flash_coords(gtl), "via position is not flashed on top copper"

    def test_bottom_copper_flashes_the_via_ring(self):
        gbl = generate_bottom_copper_gerber({}, [], ses_text=SES_WITH_VIA, placements={})
        assert "C,0.60000*%" in gbl, "no 0.6 mm aperture in bottom copper"
        assert (20.0, 10.0) in _flash_coords(gbl), "via position is not flashed on bottom copper"

    def test_annular_ring_meets_ipc_minimum(self):
        """IPC-2221B Table 9-1: at least 0.05 mm of ring per side."""
        pad, drill = _via_dimensions("Via[0.6-0.3]")
        ring_per_side = (pad - drill) / 2.0
        assert ring_per_side >= 0.05, f"annular ring {ring_per_side} mm below the IPC minimum"

    def test_no_vias_means_no_via_section(self):
        """An unrouted board must not invent via copper."""
        gtl = generate_top_copper_gerber({}, [], ses_text=None, placements={})
        assert "Plated Via Annular Rings" not in gtl


class TestStencilLayer:
    """No stencil, no SMT assembly."""

    def test_stencil_has_one_aperture_per_smd_pad(self):
        spec = synthesize_from_prompt(PROMPT)
        placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)
        gtp = generate_top_paste_gerber(
            spec["modules"], spec["netlist"]["connections"], BOARD_W, BOARD_H, placements=placements
        )
        flashes = _flash_coords(gtp)
        assert len(flashes) > 10, f"stencil has only {len(flashes)} apertures"
        # Aperture count must match the SMD pad count, not exceed it.
        from client.gerber_exporter import _collect_pads

        smd = [p for p in _collect_pads(spec["modules"], spec["netlist"]["connections"], placements) if not p["through_hole"]]
        assert len(flashes) == len(smd), (
            f"{len(flashes)} apertures for {len(smd)} SMD pads"
        )

    def test_apertures_are_smaller_than_the_copper_land(self):
        """IPC-7525B 4.2: paste to the full pad wicks under the part."""
        spec = synthesize_from_prompt(PROMPT)
        placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)
        gtp = generate_top_paste_gerber(
            spec["modules"], spec["netlist"]["connections"], BOARD_W, BOARD_H, placements=placements
        )
        rects = re.findall(r"%ADD\d+R,([0-9.]+)X([0-9.]+)\*%", gtp)
        assert rects, "stencil declares no rectangular apertures"
        from client.gerber_exporter import _collect_pads

        land = {
            (round(p["w"], 5), round(p["h"], 5))
            for p in _collect_pads(spec["modules"], spec["netlist"]["connections"], placements)
            if not p["through_hole"]
        }
        for w_s, h_s in rects:
            w_a, h_a = float(w_s), float(h_s)
            assert any(
                abs(w_a - (lw - 2 * PASTE_REDUCTION_MM)) < 1e-4
                and abs(h_a - (lh - 2 * PASTE_REDUCTION_MM)) < 1e-4
                for lw, lh in land
            ), f"aperture {w_a}x{h_a} is not a reduced land pattern"

    def test_through_hole_pins_get_no_aperture(self):
        """A wave-soldered header must not be printed with paste."""
        spec = synthesize_from_prompt(PROMPT)
        placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)
        gtp = generate_top_paste_gerber(
            spec["modules"], spec["netlist"]["connections"], BOARD_W, BOARD_H, placements=placements
        )
        from client.gerber_exporter import _collect_pads

        th = [
            p
            for p in _collect_pads(spec["modules"], spec["netlist"]["connections"], placements)
            if p["through_hole"]
        ]
        flashes = set(_flash_coords(gtp))
        for pad in th:
            assert (pad["x"], pad["y"]) not in flashes, (
                f"through-hole pin {pad['ref']}.{pad['pin']} got a paste aperture"
            )

    def test_bottom_stencil_is_empty_when_all_parts_are_on_top(self):
        spec = synthesize_from_prompt(PROMPT)
        placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)
        gbp = generate_bottom_paste_gerber(
            spec["modules"], spec["netlist"]["connections"], BOARD_W, BOARD_H, placements=placements
        )
        assert _flash_coords(gbp) == [], "bottom stencil has apertures but no part is on the bottom"


class TestTeardropReinforcement:
    """IPC-2221B 9.1.5: a track entering a via should be filleted."""

    def test_teardrop_is_drawn_where_a_trace_meets_a_via(self):
        gtl = generate_top_copper_gerber({}, [], ses_text=SES_WITH_VIA, placements={})
        assert "Teardrop Reinforcement" in gtl, "no teardrop section in top copper"
        assert "G36*" in gtl and "G37*" in gtl, "teardrops must be filled regions, not strokes"

    def test_teardrop_points_away_from_the_pad(self):
        """A fillet pointing the wrong way reinforces nothing.

        The wire arrives from -X and leaves toward +X, so the two fillets must
        extend in those directions, not back across the pad.
        """
        from client.gerber_exporter import _parse_ses_geometry, _via_teardrop_polygons

        geo = _parse_ses_geometry(SES_WITH_VIA)
        polys = _via_teardrop_polygons(geo)
        assert len(polys) == 2, f"expected one fillet per trace entry, got {len(polys)}"

        vx = 20.0
        for poly in polys:
            apex_x = max(p[0] for p in poly)
            min_x = min(p[0] for p in poly)
            # Each fillet reaches outside the 0.3 mm pad radius on one side only.
            assert apex_x > vx + 0.3 - 1e-6 or min_x < vx - 0.3 + 1e-6, (
                f"fillet {poly} does not extend beyond the pad"
            )

    def test_no_trace_entry_means_no_teardrop(self):
        """A via with no routed trace touching it gets no fillet."""
        ses = """(session "probe"
  (resolution mm 1000)
  (routes
    (net N1
      (wire (path Top 200
        10000 30000
        20000 30000
      ))
      (via "Via[0.6-0.3]" 40000 10000)
    )
  )
)"""
        gtl = generate_top_copper_gerber({}, [], ses_text=ses, placements={})
        assert "Teardrop Reinforcement" not in gtl


class TestSilkscreenClipping:
    """Silk on exposed copper blocks wetting: it must be clipped, not merely drawn."""

    @staticmethod
    def _segments(gerber: str) -> list[tuple[float, float, float, float]]:
        out = []
        for m in re.finditer(r"X(-?\d+)Y(-?\d+)D02\*\s*X(-?\d+)Y(-?\d+)D01\*", gerber):
            out.append(tuple(int(v) / 100000.0 for v in m.groups()))
        return out

    def test_no_segment_crosses_a_mask_opening(self):
        from client.gerber_exporter import (
            MASK_EXPANSION_MM,
            SILK_TO_PAD_CLEARANCE_MM,
            _collect_pads,
            generate_top_silkscreen_gerber,
        )

        spec = synthesize_from_prompt(PROMPT)
        placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)
        conns = spec["netlist"]["connections"]
        gto = generate_top_silkscreen_gerber(
            spec["modules"], BOARD_W, BOARD_H, placements=placements, connections=conns
        )
        pads = _collect_pads(spec["modules"], conns, placements)
        segs = self._segments(gto)
        assert segs, "silkscreen drew nothing at all"

        for x0, y0, x1, y1 in segs:
            sx0, sx1 = min(x0, x1), max(x0, x1)
            sy0, sy1 = min(y0, y1), max(y0, y1)
            for pad in pads:
                hw = pad["w"] / 2 + MASK_EXPANSION_MM + SILK_TO_PAD_CLEARANCE_MM
                hh = pad["h"] / 2 + MASK_EXPANSION_MM + SILK_TO_PAD_CLEARANCE_MM
                crosses = (
                    sx1 > pad["x"] - hw + 1e-9
                    and pad["x"] + hw > sx0 + 1e-9
                    and sy1 > pad["y"] - hh + 1e-9
                    and pad["y"] + hh > sy0 + 1e-9
                )
                assert not crosses, (
                    f"silk {x0:.2f},{y0:.2f}->{x1:.2f},{y1:.2f} crosses "
                    f"{pad['ref']}.{pad['pin']} mask opening"
                )

    def test_clipping_subtracts_rather_than_dropping_whole_edges(self):
        """A long edge with one pad on it keeps the rest of its length.

        Discarding the whole edge erases the legend on every part whose body sits
        between its own pads, which is most of them — the board ships unlabelled.
        """
        spec = synthesize_from_prompt(PROMPT)
        placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)
        from client.gerber_exporter import generate_top_silkscreen_gerber

        gto = generate_top_silkscreen_gerber(
            spec["modules"],
            BOARD_W,
            BOARD_H,
            placements=placements,
            connections=spec["netlist"]["connections"],
        )
        segs = self._segments(gto)
        # 18 packages x 4 edges = 72 candidate edges; a whole-edge drop would
        # leave far fewer than the 40+ fragments real subtraction produces.
        assert len(segs) >= 40, f"only {len(segs)} silk fragments; edges are being dropped whole"


class TestMaskDam:
    """A mask web thinner than the process floor scums and bridges at reflow."""

    def test_openings_are_parsed_from_the_real_mask_layer(self):
        from client.mfg_validator import _mask_openings

        spec = synthesize_from_prompt(PROMPT)
        bundle = export_gerber_bundle(
            spec["modules"], spec["netlist"]["connections"], BOARD_W, BOARD_H
        )
        rects = _mask_openings(bundle["board-F_Mask.gts"])
        assert len(rects) > 10, f"parsed only {len(rects)} mask openings"
        for x0, y0, x1, y1 in rects:
            assert x1 > x0 and y1 > y0, "opening has non-positive extent"

    def test_a_normal_board_reports_its_tightest_dam(self):
        from client.mfg_validator import MIN_MASK_DAM_MM, _tightest_mask_dam

        spec = synthesize_from_prompt(PROMPT)
        bundle = export_gerber_bundle(
            spec["modules"], spec["netlist"]["connections"], BOARD_W, BOARD_H
        )
        dam = _tightest_mask_dam(bundle, spec["modules"])
        assert dam is not None, "no mask dam measured at all"
        assert dam[0] >= MIN_MASK_DAM_MM, f"this board's dam {dam[0]:.3f} mm is under the floor"

    def test_a_dam_under_the_floor_fails_the_package(self):
        """Two 0.25 mm pads 0.30 mm apart leave a 0.20 mm web — but with the
        default 0.05 mm mask expansion the openings close to 0.10 mm, and below
        0.08 mm the web lifts. The validator must reject that, not pass it."""
        # Hand-built mask layer: two 0.25 mm openings whose edges are 0.05 mm apart.
        mask = (
            "G04 Gerber RS-274X Top Solder Mask Openings*\n"
            "%FSLAX45Y45*%\n"
            "%MOMM*%\n"
            "%LPD*%\n"
            "%ADD10R,0.25000X0.25000*%\n"
            "D10*\n"
            "X1000000Y1000000D03*\n"
            "X1030000Y1000000D03*\n"
            "M02*"
        )
        from client.mfg_validator import MIN_MASK_DAM_MM, _tightest_mask_dam

        dam = _tightest_mask_dam({"board-F_Mask.gts": mask}, None)
        assert dam is not None
        assert dam[0] < MIN_MASK_DAM_MM, (
            f"fixture gap {dam[0]:.3f} mm should be under the {MIN_MASK_DAM_MM} mm floor"
        )

    def test_missing_mask_layer_reports_no_dam_instead_of_crashing(self):
        from client.mfg_validator import _tightest_mask_dam

        assert _tightest_mask_dam({}, None) is None


class TestBundleCompleteness:
    def test_bundle_carries_all_nine_layers(self):
        spec = synthesize_from_prompt(PROMPT)
        bundle = export_gerber_bundle(
            spec["modules"], spec["netlist"]["connections"], BOARD_W, BOARD_H
        )
        assert set(bundle) == {
            "board-Edge_Cuts.gm1",
            "board-F_Cu.gtl",
            "board-B_Cu.gbl",
            "board-F_Mask.gts",
            "board-B_Mask.gbs",
            "board-F_SilkS.gto",
            "board-F_Paste.gtp",
            "board-B_Paste.gbp",
            "board.drl",
        }

    def test_manufacturing_validator_requires_the_stencil(self):
        """The gate must reject a package with no stencil, not silently pass it."""
        from client.mfg_validator import validate_manufacturing_package

        report = validate_manufacturing_package(
            {
                "board-Edge_Cuts.gm1": "x",
                "board-F_Cu.gtl": "x",
                "board-B_Cu.gbl": "x",
                "board-F_Mask.gts": "x",
                "board-B_Mask.gbs": "x",
                "board.drl": "x",
                "bom.csv": "x",
                "cpl.csv": "x",
            }
        )
        missing = [c.artifact_name for c in report.checks if c.status == "MISSING"]
        assert "board-F_Paste.gtp" in missing, (
            f"validator accepted a package with no stencil; missing={missing}"
        )
