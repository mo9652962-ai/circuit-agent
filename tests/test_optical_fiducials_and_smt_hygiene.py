"""Tests for Optical Fiducials (IPC-7351) and SMT BOM/CPL Hygiene.

Engineering requirements:
1. Fiducial marks (FID1, FID2, FID3) must be placed in an asymmetric L-configuration
   near board corners to allow automated pick-and-place optical cameras to identify
   board orientation and stretch without ambiguity.
2. BOM hygiene: Fiducials, testpoints, and mounting holes are bare copper features or
   mechanical drills, NOT physical SMT packages. They must NEVER appear in the JLCPCB BOM
   (which would request a nonexistent LCSC reel) or CPL (which commands the nozzle to place).
3. Gerber fidelity:
   - F_Cu (.gtl): 1.0 mm round copper lands.
   - F_Mask (.gts): 2.0 mm round mask clearance (IPC-7351 0.5 mm bare perimeter ring).
   - F_Paste (.gtp): ZERO aperture / NO solder paste (solder paste wicks and blinds cameras).
"""

from client.export_engine import export_jlcpcb_bom, export_jlcpcb_cpl
from client.gerber_exporter import (
    _format_gerber_coord,
    generate_top_copper_gerber,
    generate_top_paste_gerber,
    generate_top_solder_mask_gerber,
)
from client.placement_engine import heuristic_place_components
from client.synthesizer import synthesize_from_prompt


def test_fiducial_asymmetric_corner_placement():
    """Fiducials must form an asymmetric L-configuration near board corners."""
    modules = {
        "FID1": {"package": "Fiducial_1mm_Mask2mm", "kind": "FIDUCIAL"},
        "FID2": {"package": "Fiducial_1mm_Mask2mm", "kind": "FIDUCIAL"},
        "FID3": {"package": "Fiducial_1mm_Mask2mm", "kind": "FIDUCIAL"},
        "U_MCU": {"package": "ESP32-C3-WROOM-02", "kind": "MCU"},
    }
    bw, bh = 70.0, 50.0
    pl = heuristic_place_components(modules, bw, bh)

    assert "FID1" in pl and "FID2" in pl and "FID3" in pl
    p1, p2, p3 = pl["FID1"], pl["FID2"], pl["FID3"]

    # Bottom-left, Bottom-right, Top-left perimeter zones (within 12mm of corners)
    assert p1.x_mm <= 5.0 and p1.y_mm <= 12.0
    assert p2.x_mm >= bw - 12.0 and p2.y_mm <= 5.0
    assert p3.x_mm <= 5.0 and p3.y_mm >= bh - 12.0

    # Top-right corner must be kept empty to preserve asymmetry for vision cameras
    for p in (p1, p2, p3):
        assert not (p.x_mm >= bw - 12.0 and p.y_mm >= bh - 12.0)


def test_fiducials_do_not_collide_with_mounting_holes():
    """Fiducials must maintain at least 5.0mm clearance from any drilled mounting hole."""
    import math
    import re

    from client.excellon_exporter import export_excellon_drill

    spec = synthesize_from_prompt("带有 Mark 点的 ESP32-C3 节点")
    bw, bh = 70.0, 50.0
    pl = heuristic_place_components(spec["modules"], bw, bh)
    drl = export_excellon_drill(
        spec["modules"],
        spec["netlist"]["connections"],
        "TEST",
        bw,
        bh,
        placements=pl,
    )

    fid_coords = [(pl[r].x_mm, pl[r].y_mm) for r in pl if "FID" in r]
    hits = [
        (round(int(m.group(1)) / 1000.0, 3), round(int(m.group(2)) / 1000.0, 3))
        for m in re.finditer(r"X(\d{6})Y(\d{6})", drl)
    ]
    assert hits, "No drill hits found in drill file"

    for fx, fy in fid_coords:
        for hx, hy in hits:
            dist = math.hypot(fx - hx, fy - hy)
            assert dist >= 5.0, (
                f"FATAL: Fiducial at ({fx}, {fy}) collides with drill hole at ({hx}, {hy}) (dist={dist:.2f}mm < 5mm)!"
            )


def test_ground_pour_avoids_mounting_holes():
    """Bottom copper ground pour must not run copper tracks through mounting holes."""
    from client.gerber_exporter import _pour_hatch_segments

    segs = _pour_hatch_segments(70.0, 50.0, [], [], [], set())
    for mx, my in ((3.5, 3.5), (66.5, 3.5), (3.5, 46.5), (66.5, 46.5)):
        crossing = [
            s for s in segs
            if abs(s[1] - my) < 1.6 and s[0] <= mx <= s[2]
        ]
        assert not crossing, (
            f"Ground pour has copper segments running straight through mount at ({mx}, {my}): {crossing}"
        )


def test_synthesizer_mounting_holes_block():
    """Synthesizer must recognize mounting hole prompt tokens and generate mechanical blocks."""
    spec = synthesize_from_prompt("ESP32-C3 环境监测节点，带有 4个固定孔 和 2个按键")
    mount_modules = [
        ref for ref in spec["modules"]
        if ref.upper().startswith(("H", "MH", "MOUNT"))
    ]
    assert len(mount_modules) == 4, f"Expected 4 mounting holes, got: {mount_modules}"


def test_bom_and_cpl_smt_hygiene():
    """Fiducials, testpoints, and mounting holes must be excluded from BOM & CPL."""
    spec = synthesize_from_prompt("带有 Mark 点和测试点的工业网关，具备4个安装孔")
    bom = export_jlcpcb_bom(spec)
    cpl = export_jlcpcb_cpl(spec)

    for line in bom.splitlines():
        # Check Designator column
        parts = line.split(",")
        if len(parts) >= 2:
            desig = parts[1].strip('"')
            assert not any(desig.startswith(pfx) for pfx in ("FID", "TP", "H", "MH", "MOUNT")), f"Illegal part in BOM: {line}"

    for line in cpl.splitlines():
        parts = line.split(",")
        if parts:
            desig = parts[0]
            assert not any(desig.startswith(pfx) for pfx in ("FID", "TP", "H", "MH", "MOUNT")), f"Illegal part in CPL: {line}"


def test_gerber_fiducial_layer_physics():
    """Fiducials must have copper and mask openings, but strictly zero stencil paste."""
    modules = {
        "FID1": {"package": "Fiducial_1mm_Mask2mm", "kind": "FIDUCIAL"},
        "U_MCU": {"package": "ESP32-C3-WROOM-02", "kind": "MCU"},
    }
    connections = [{"net": "/GND", "points": ["U_MCU.1"]}]
    bw, bh = 70.0, 50.0
    pl = heuristic_place_components(modules, bw, bh)

    gtl = generate_top_copper_gerber(modules, connections, bw, bh, placements=pl)
    gts = generate_top_solder_mask_gerber(modules, bw, bh, connections=connections, placements=pl)
    gtp = generate_top_paste_gerber(modules, connections, bw, bh, placements=pl)

    fid_x = _format_gerber_coord(pl["FID1"].x_mm)
    fid_y = _format_gerber_coord(pl["FID1"].y_mm)
    flash_cmd = f"X{fid_x}Y{fid_y}"

    # Copper target present
    assert flash_cmd in gtl, "Fiducial copper pad missing from F_Cu (.gtl)"
    # Mask clearance present
    assert flash_cmd in gts, "Fiducial mask opening missing from F_Mask (.gts)"
    # IPC-7351 2.0mm aperture present in mask layer
    assert any("C,2.00000" in l for l in gts.splitlines()), "2.0mm circular aperture missing in F_Mask"
    # Solder paste stencil MUST NOT have fiducial flash
    assert flash_cmd not in gtp, "FATAL: Solder paste stencil contains fiducial aperture!"
