"""Every exporter must produce *usable* content, not merely non-empty content.

The 600-odd tests before this file checked that exports existed and had the right
number of rows. None of them looked at what the numbers said, so a CPL where
every part sat at (0.000mm, 0.000mm) — a file that tells the assembly machine to
stack the whole board on one point — passed the entire suite.

That is the failure mode this file exists for: syntactically valid, semantically
worthless. Each test asserts a property a human would check before sending the
files to a fab.
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from client.mcp_server import handle_tool_call
from client.synthesizer import synthesize_from_prompt

BOARD_W, BOARD_H = 70.0, 50.0

PROMPTS = [
    "ESP32-S3 带以太网口的工业网关",
    "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键",
    "RP2040 带电流采样和看门狗的开发板",
    "STM32F103 带电机驱动的控制器",
    "51单片机带 RS485 的工业板",
    "ESP32-S3 工业 CAN 与 RS485 网关，带 Type-C 供电、指示灯、按键和 I2C 传感器插座",
]


def _spec(prompt):
    return synthesize_from_prompt(prompt)


def _cpl_rows(prompt):
    spec = _spec(prompt)
    text = handle_tool_call("export_manufacturing_cpl", spec)["content"][0]["text"]
    return [ln.split(",") for ln in text.splitlines()[1:] if ln.strip()]


# --------------------------------------------------------------------------- #
# CPL: the file that places parts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p[:24])
def test_cpl_coordinates_are_not_all_zero(prompt):
    """The defect that motivated this file: every part at the origin."""
    rows = _cpl_rows(prompt)
    assert rows, "CPL has no rows"
    coords = {(r[1], r[2]) for r in rows}
    assert len(coords) > 1, f"all {len(rows)} parts share one coordinate: {coords}"
    assert coords != {("0.000mm", "0.000mm")}, "every part placed at the origin"


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p[:24])
def test_cpl_coordinates_land_inside_the_board(prompt):
    """A part placed off the outline cannot be assembled."""
    for r in _cpl_rows(prompt):
        x = float(r[1].removesuffix("mm"))
        y = float(r[2].removesuffix("mm"))
        assert 0.0 <= x <= BOARD_W, f"{r[0]} at X={x} is outside the 0-{BOARD_W}mm board"
        assert 0.0 <= y <= BOARD_H, f"{r[0]} at Y={y} is outside the 0-{BOARD_H}mm board"


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p[:24])
def test_no_two_parts_occupy_the_same_point(prompt):
    """Overlapping placements collide on the machine and short on the board."""
    rows = _cpl_rows(prompt)
    coords = [(r[1], r[2]) for r in rows]
    dupes = {c for c in coords if coords.count(c) > 1}
    assert not dupes, f"parts share coordinates {dupes}"


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p[:24])
def test_cpl_covers_every_component(prompt):
    """One placement row per part, no more and no fewer."""
    spec = _spec(prompt)
    refs = {r for r in spec["modules"] if r != "__meta__"}
    placed = {r[0] for r in _cpl_rows(prompt)}
    assert placed == refs, f"missing {refs - placed}, unexpected {placed - refs}"


def test_rotation_correction_applies_to_packages_that_need_it():
    """JLCPCB reels are rotated relative to KiCad for several package families.

    The rules previously matched only KiCad library names (`D_SMA`), so a part
    whose package field said `SMA` shipped at 0 degrees — reversed on the reel.
    """
    from client.export_engine import get_cpl_rotation_offset

    assert get_cpl_rotation_offset("LQFP-48_7x7mm_P0.5mm") == 270.0
    assert get_cpl_rotation_offset("SOT-223") == 180.0
    assert get_cpl_rotation_offset("SMA") == 180.0
    assert get_cpl_rotation_offset("SOD-123") == 180.0
    assert get_cpl_rotation_offset("USB-C-16P-SMD") == 180.0
    # Passives are not rotated.
    assert get_cpl_rotation_offset("C0603") == 0.0
    assert get_cpl_rotation_offset("R0603") == 0.0


# --------------------------------------------------------------------------- #
# Gerber / drill / netlist
# --------------------------------------------------------------------------- #


def test_gerber_layers_contain_real_geometry():
    """Every required layer must have draw commands, not just a header."""
    spec = _spec("ESP32-S3 带以太网口的工业网关")
    bundle = json.loads(handle_tool_call("export_gerber_bundle", spec)["content"][0]["text"])
    assert bundle, "empty Gerber bundle"
    for name, content in bundle.items():
        if not name.endswith((".gm1", ".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".gko")):
            continue  # the bundle also carries the Excellon drill file
        assert "M02*" in content, f"{name} has no end-of-file marker"
        # A layer with only a header and M02 draws nothing.
        draws = re.findall(r"D0[123]\*", content)
        assert len(draws) >= 2, f"{name} contains no draw commands"


def test_drill_file_has_holes_at_distinct_positions():
    """A drill file whose holes all sit at one point cannot be drilled."""
    spec = _spec("ESP32-S3 带以太网口的工业网关")
    drill = handle_tool_call("export_excellon_drill", spec)["content"][0]["text"]
    coords = re.findall(r"X(-?\d+)Y(-?\d+)", drill)
    assert coords, "no hole coordinates"
    assert len(set(coords)) > 1, "every hole at the same coordinate"
    assert "M48" in drill and "METRIC" in drill, "missing header"


def test_assembly_drawing_places_parts_inside_its_own_outline():
    """The drawing is a visual check; parts outside the frame mean it lies."""
    spec = _spec("ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键")
    svg = handle_tool_call("export_assembly_drawing_svg", spec)["content"][0]["text"]
    outline = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', svg)
    assert outline, "no board outline in the drawing"
    ox, oy, ow, oh = (float(g) for g in outline.groups())
    for x, y in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', svg):
        assert ox <= float(x) <= ox + ow, f"marker at X={x} outside the outline"
        assert oy <= float(y) <= oy + oh, f"marker at Y={y} outside the outline"


# --------------------------------------------------------------------------- #
# BOM
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("prompt", PROMPTS[:3], ids=lambda p: p[:24])
def test_bom_part_numbers_are_well_formed(prompt):
    """An LCSC number that is not `C` + digits cannot be ordered."""
    import csv
    import io

    spec = _spec(prompt)
    bom = handle_tool_call("export_manufacturing_bom", spec)["content"][0]["text"]
    rows = list(csv.reader(io.StringIO(bom)))
    header = rows[0]
    lcsc_idx = header.index("LCSC Part Number")
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        lcsc = row[lcsc_idx] if lcsc_idx < len(row) else ""
        assert re.match(r"^C\d+$", lcsc), f"{row[1]} has bad LCSC '{lcsc}'"


def test_bom_quantities_match_designator_counts():
    """A row claiming 2 parts must list 2 designators."""
    spec = _spec("ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键")
    bom = handle_tool_call("export_manufacturing_bom", spec)["content"][0]["text"]
    import csv
    import io

    for row in list(csv.reader(io.StringIO(bom)))[1:]:
        if not row or not row[0]:
            continue
        des = [d for d in row[1].split(",") if d]
        assert int(row[5]) == len(des), f"{row[0]}: quantity {row[5]} but {len(des)} designators"
