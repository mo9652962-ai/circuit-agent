"""Fabrication-output fidelity tests.

These tests assert that the Gerber/Excellon bundle describes the *design*, not a
plausible-looking approximation. Each one fails against the previous exporter,
which flashed a uniform 1.6x1.0 mm pad at every component centre, drew
centre-to-centre "guide tracks", and drilled a hole beside every SMD part.

A fab builds whatever is in these files. An output that cannot be traced back to
a netlist pin or a routed path is not a simplification, it is a defect.
"""

from __future__ import annotations

import re

import pytest

from client.gerber_exporter import (
    MASK_EXPANSION_MM,
    export_gerber_bundle,
)
from client.placement_engine import (
    STANDARD_PIN_OFFSETS,
    heuristic_place_components,
)
from client.router_engine import autoroute_circuit
from client.synthesizer import synthesize_from_prompt

PROMPT = "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键"
BOARD_W, BOARD_H = 70.0, 50.0


def _flash_coords(gerber: str) -> list[tuple[float, float]]:
    """Every D03 flash position, in mm."""
    out = []
    for m in re.finditer(r"X(-?\d+)Y(-?\d+)D03\*", gerber):
        out.append((int(m.group(1)) / 100000.0, int(m.group(2)) / 100000.0))
    return out


def _draw_points(gerber: str) -> list[tuple[float, float]]:
    """Every D01/D02 coordinate, in mm."""
    out = []
    for m in re.finditer(r"X(-?\d+)Y(-?\d+)D0[12]\*", gerber):
        out.append((int(m.group(1)) / 100000.0, int(m.group(2)) / 100000.0))
    return out


@pytest.fixture(scope="module")
def routed_bundle():
    spec = synthesize_from_prompt(PROMPT)
    routed = autoroute_circuit(
        spec["modules"],
        spec["netlist"]["connections"],
        board_width_mm=BOARD_W,
        board_height_mm=BOARD_H,
    )
    assert routed["success"], routed.get("error")
    bundle = export_gerber_bundle(
        spec["modules"],
        spec["netlist"]["connections"],
        board_width_mm=BOARD_W,
        board_height_mm=BOARD_H,
        ses_text=routed["ses_text"],
    )
    return spec, routed, bundle


def test_pads_sit_on_real_footprint_pins(routed_bundle):
    """Every flashed pad must coincide with a netlist pin's physical position.

    The old exporter flashed one pad per *component*, at its centroid. A real
    footprint has 2..40 pins, none of them at the centroid, so no pad lined up
    with anything the part could solder to.
    """
    spec, _routed, bundle = routed_bundle
    placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)
    flashes = set(_flash_coords(bundle["board-F_Cu.gtl"]))
    assert flashes, "top copper has no pads at all"

    expected: set[tuple[float, float]] = set()
    for conn in spec["netlist"]["connections"]:
        for pt in conn.get("points") or []:
            ref, pin = pt.split(".", 1)
            if ref not in placements:
                continue
            p = placements[ref]
            off = STANDARD_PIN_OFFSETS.get(p.package or "", {}).get(pin)
            if off is None:
                continue
            expected.add((round(p.x_mm + off[0], 4), round(p.y_mm + off[1], 4)))

    assert expected, "test fixture produced no expected pads"
    missing = {p for p in expected if (round(p[0], 4), round(p[1], 4)) not in flashes}
    assert not missing, f"pads missing from top copper at netlist pin positions: {sorted(missing)[:5]}"

    # And no pad may sit at a bare component centroid unless a pin is there.
    centroids = {(round(p.x_mm, 4), round(p.y_mm, 4)) for p in placements.values()}
    pin_positions = expected
    stray = (flashes & centroids) - pin_positions
    assert not stray, f"pads flashed at component centroids with no pin: {sorted(stray)[:5]}"


def test_tracks_are_router_output_not_centroid_lines(routed_bundle):
    """Top copper tracks must come from the SES, not from joining centroids.

    The old exporter drew one straight segment between the two components of each
    net. A routed trace is a multi-segment path that starts and ends on pads.
    """
    spec, routed, bundle = routed_bundle
    placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)

    assert "(path" in routed["ses_text"], "router produced no geometry"
    seg_count = len(_draw_points(bundle["board-F_Cu.gtl"]))
    assert seg_count > 100, f"top copper has only {seg_count} draw points; expected a routed path"

    # No track endpoint may be a component centroid (the old guide-line signature).
    centroids = {(round(p.x_mm, 2), round(p.y_mm, 2)) for p in placements.values()}
    endpoints = {
        (round(x, 2), round(y, 2)) for x, y in _draw_points(bundle["board-F_Cu.gtl"])
    }
    centroid_hits = endpoints & centroids
    assert len(centroid_hits) <= 1, (
        f"{len(centroid_hits)} track endpoints land on component centroids, "
        f"which is the signature of centroid-to-centroid guide lines: {sorted(centroid_hits)[:5]}"
    )


def test_track_endpoints_land_on_pads(routed_bundle):
    """A routed trace must terminate on a pad, otherwise the net is not connected.

    This is the check that catches a coordinate-unit mistake: when SES coordinates
    were treated as millimetres instead of 1/1000 mm, every trace shrank by 1000x
    and no endpoint reached its pad.
    """
    _spec, _routed, bundle = routed_bundle
    flashes = {(round(x, 2), round(y, 2)) for x, y in _flash_coords(bundle["board-F_Cu.gtl"])}
    flashes |= {(round(x, 2), round(y, 2)) for x, y in _flash_coords(bundle["board-B_Cu.gbl"])}

    points = _draw_points(bundle["board-F_Cu.gtl"])
    # Draw points include intermediate grid steps, so only require that *some*
    # endpoints coincide with pads and that the geometry stays inside the board.
    on_pad = sum(1 for x, y in points if (round(x, 2), round(y, 2)) in flashes)
    assert on_pad >= 10, f"only {on_pad} track points coincide with pads; geometry is misaligned"

    for x, y in points:
        assert -0.5 <= x <= BOARD_W + 0.5, f"track point x={x} outside board"
        assert -0.5 <= y <= BOARD_H + 0.5, f"track point y={y} outside board"


def test_ses_coordinates_use_declared_resolution():
    """SES coordinates must be in the session's resolution units, not millimetres.

    ``(resolution mm 1000)`` means one coordinate unit is 0.001 mm. Emitting a pad
    at 10.25 mm as ``10 28`` puts the trace up to half a millimetre off — larger
    than a 0603 pad — and every consumer inherits the error.
    """
    spec = synthesize_from_prompt(PROMPT)
    routed = autoroute_circuit(
        spec["modules"],
        spec["netlist"]["connections"],
        board_width_mm=BOARD_W,
        board_height_mm=BOARD_H,
    )
    ses = routed["ses_text"]
    assert "(resolution mm 1000)" in ses

    coords: list[float] = []
    for m in re.finditer(r"\(path\s+\w+\s+\d+\s+([0-9\s.\-]+)\)", ses):
        coords.extend(float(v) for v in m.group(1).split())
    assert coords, "no routed coordinates"

    # A routed point should sit on a 1 um grid, and at least one must be
    # sub-millimetre — a real pad offset is not a whole millimetre.
    assert any(c != int(c) for c in coords) or max(coords) > 1000.0, (
        "SES coordinates look like whole millimetres; resolution scaling is missing"
    )
    assert max(coords) > 1000.0, "coordinates are not in 1/1000 mm units"


def test_drill_hits_are_real_holes_only(routed_bundle):
    """Every drill hit must trace back to a through-hole pin, a router via, or a mount.

    The old exporter drilled a 0.3 mm hole at ``component_centre + (0.8, 0.8)`` for
    every SMD part and a second hole 2.54 mm beside every connector. Those positions
    are derived from nothing — they sit *near* pads rather than on them, so a
    "no hit lands on an SMD pad" check passes while 19 of 27 holes are fabricated.
    This test therefore whitelists real hole origins instead of blacklisting bad ones.
    """
    spec, routed, bundle = routed_bundle
    placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)
    drl = bundle["board.drl"]

    hits = [
        (round(int(m.group(1)) / 1000.0, 3), round(int(m.group(2)) / 1000.0, 3))
        for m in re.finditer(r"X(\d{6})Y(\d{6})", drl)
    ]
    assert hits, "drill file has no hits"

    # Legal origins: through-hole pins, router vias, declared mounting holes,
    # and the four corner mounts the exporter adds for large boards.
    legal: set[tuple[float, float]] = set()
    for ref, comp in spec["modules"].items():
        p = placements.get(ref)
        if p is None:
            continue
        pkg = comp.get("package", "") or ""
        upper = ref.upper()
        if "MOUNT" in upper or "HOLE" in upper or "M3" in str(comp.get("value", "")).upper():
            legal.add((round(p.x_mm, 3), round(p.y_mm, 3)))
            continue
        is_th = any(k in pkg for k in ("HDR", "TERMINAL", "CONN-TH", "RJ45")) or upper.startswith("J_")
        if not is_th:
            continue
        for off in STANDARD_PIN_OFFSETS.get(pkg, {}).values():
            legal.add((round(p.x_mm + off[0], 3), round(p.y_mm + off[1], 3)))

    for m in re.finditer(r'\(via\s+"?[^"\s]+"?\s+(\d+)\s+(\d+)', routed["ses_text"]):
        legal.add((round(int(m.group(1)) / 1000.0, 3), round(int(m.group(2)) / 1000.0, 3)))

    for mx, my in ((3.5, 3.5), (BOARD_W - 3.5, 3.5), (3.5, BOARD_H - 3.5), (BOARD_W - 3.5, BOARD_H - 3.5)):
        legal.add((round(mx, 3), round(my, 3)))

    fabricated = [h for h in hits if h not in legal]
    assert not fabricated, (
        f"{len(fabricated)} of {len(hits)} drill hits trace to no pin, via or mount: {fabricated[:6]}"
    )

    # No duplicate hits: one spot, one hole.
    assert len(hits) == len(set(hits)), "duplicate drill hits at the same coordinate"

    # Router vias must be drilled, or the board cannot route between layers.
    via_coords = {
        (round(int(m.group(1)) / 1000.0, 3), round(int(m.group(2)) / 1000.0, 3))
        for m in re.finditer(r'\(via\s+"?[^"\s]+"?\s+(\d+)\s+(\d+)', routed["ses_text"])
    }
    if via_coords:
        missing = via_coords - set(hits)
        assert not missing, f"router vias with no drill hit: {sorted(missing)[:5]}"


def test_solder_mask_openings_track_pads(routed_bundle):
    """Mask openings must sit on real footprint pins, not merely match the copper.

    Checking "mask == copper" is worthless: the old exporter emitted both layers
    from the same centroid list, so they agreed with each other while both were
    wrong. The opening has to be verified against the netlist's pin geometry.
    """
    spec, _routed, bundle = routed_bundle
    placements = heuristic_place_components(spec["modules"], BOARD_W, BOARD_H)
    mask = {(round(x, 4), round(y, 4)) for x, y in _flash_coords(bundle["board-F_Mask.gts"])}
    assert mask, "top mask has no openings"

    expected: set[tuple[float, float]] = set()
    for conn in spec["netlist"]["connections"]:
        for pt in conn.get("points") or []:
            ref, pin = pt.split(".", 1)
            if ref not in placements:
                continue
            p = placements[ref]
            off = STANDARD_PIN_OFFSETS.get(p.package or "", {}).get(pin)
            if off is not None:
                expected.add((round(p.x_mm + off[0], 4), round(p.y_mm + off[1], 4)))

    orphan = mask - expected
    assert not orphan, (
        f"mask openings that are not on a netlist pin: {sorted(orphan)[:5]} "
        f"({len(orphan)} of {len(mask)} openings)"
    )

    # Expansion is applied to the aperture, not the coordinate.
    mask_apertures = [
        float(m.group(1)) for m in re.finditer(r"%ADD\d+R,([0-9.]+)X", bundle["board-F_Mask.gts"])
    ]
    copper_apertures = [
        float(m.group(1)) for m in re.finditer(r"%ADD\d+R,([0-9.]+)X", bundle["board-F_Cu.gtl"])
    ]
    assert mask_apertures and copper_apertures
    assert min(mask_apertures) > min(copper_apertures), (
        "mask apertures are not expanded over copper "
        f"(mask min {min(mask_apertures)} vs copper min {min(copper_apertures)})"
    )
    assert abs((min(mask_apertures) - min(copper_apertures)) - 2 * MASK_EXPANSION_MM) < 0.01


def test_silkscreen_uses_per_package_bodies(routed_bundle):
    """Silkscreen outlines must differ by package, not be one uniform box.

    The old exporter drew the same 3.6x2.4 mm box for every part, so a 0603 and an
    ESP32 module got identical outlines that overlapped their neighbours.
    """
    spec, _routed, bundle = routed_bundle
    gto = bundle["board-F_SilkS.gto"]
    points = _draw_points(gto)
    assert len(points) >= 4 * len(spec["modules"]), "silk does not outline every part"

    # Collect box widths by scanning consecutive 4-point rectangles.
    widths = set()
    heights = set()
    for i in range(0, len(points) - 4, 5):
        box = points[i : i + 5]
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        widths.add(round(max(xs) - min(xs), 2))
        heights.add(round(max(ys) - min(ys), 2))
    assert len(widths) >= 3, f"all silkscreen outlines share one width: {widths}"
    assert len(heights) >= 3, f"all silkscreen outlines share one height: {heights}"


def test_bundle_without_ses_has_pads_but_no_invented_tracks():
    """Without routing geometry the copper carries pads only — never fake tracks."""
    spec = synthesize_from_prompt(PROMPT)
    bundle = export_gerber_bundle(
        spec["modules"],
        spec["netlist"]["connections"],
        board_width_mm=BOARD_W,
        board_height_mm=BOARD_H,
        ses_text=None,
    )
    gtl = bundle["board-F_Cu.gtl"]
    assert "Routed Tracks" not in gtl, "tracks emitted without any routing geometry"
    assert _flash_coords(gtl), "pads must still be present on an unrouted board"


def test_mcp_gerber_tool_routes_before_exporting():
    """The MCP tool must hand real geometry to the exporter by default."""
    from client.mcp_server import handle_tool_call

    spec = synthesize_from_prompt(PROMPT)
    out = handle_tool_call("export_gerber_bundle", spec)
    assert "isError" not in out
    import json

    bundle = json.loads(out["content"][0]["text"])
    assert "Routed Tracks" in bundle["board-F_Cu.gtl"] or "Routed Tracks" in bundle["board-B_Cu.gbl"], (
        "MCP tool exported a bundle with no routed geometry"
    )
