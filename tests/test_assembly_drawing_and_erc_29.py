"""Tests for ASME Y14.5 assembly drawing SVG, ERC rule 29, and MCP tool 42."""

from client.assembly_drawing import export_assembly_drawing_svg
from client.erc import run_erc
from client.mcp_server import handle_tool_call


def _modules():
    return {
        "U1": {"kind": "MCU", "value": "ESP32-C3", "package": "Module-ESP32-C3", "position": [30.0, 20.0]},
        "D1": {"kind": "LED", "value": "GREEN", "package": "0603", "position": [40.0, 20.0]},
        "C1": {"kind": "CAPACITOR", "value": "100nF", "package": "0402", "position": [20.0, 20.0]},
    }


def test_assembly_drawing_svg_structure():
    """Verify SVG root, board outline, refDes labels, and title block."""
    drawing = export_assembly_drawing_svg(modules=_modules(), board_width_mm=60.0, board_height_mm=40.0)
    svg = drawing.svg
    assert svg.startswith("<svg") and "</svg>" in svg
    assert 'id="board-outline"' in svg
    assert 'id="titleblock"' in svg
    assert "PCBA ASSEMBLY DRAWING" in svg
    assert "REV A" in svg
    assert ">U1<" in svg
    assert ">D1<" in svg
    assert drawing.component_count == 3


def test_assembly_drawing_polarity_marks():
    """Verify pin-1 dot for ICs and cathode bar for diodes (IPC-A-610G §5.2)."""
    drawing = export_assembly_drawing_svg(modules=_modules())
    kinds = {m.ref: m.kind for m in drawing.polarity_marks}
    assert kinds["U1"] == "pin1_dot"
    assert kinds["D1"] == "cathode_bar"
    assert "C1" not in kinds  # non-polarized MLCC has no mark


def test_assembly_drawing_bottom_view_mirrored():
    """Verify bottom view mirrors X coordinates."""
    drawing = export_assembly_drawing_svg(
        modules={"U1": {"kind": "MCU", "value": "X", "package": "SOIC-8", "position": [10.0, 10.0]}},
        board_width_mm=60.0,
        board_height_mm=40.0,
        mirrored_bottom=True,
    )
    # mirrored x in svg text of rect: 60 - 10 = 50 -> rect centered near 8+50=58
    assert drawing.mirrored_bottom is True
    assert "(MIRRORED)" in drawing.svg

    drawing_top = export_assembly_drawing_svg(
        modules={"U1": {"kind": "MCU", "value": "X", "package": "SOIC-8", "position": [10.0, 10.0]}},
        board_width_mm=60.0,
        board_height_mm=40.0,
        mirrored_bottom=False,
    )
    assert "(MIRRORED)" not in drawing_top.svg


def test_erc_rule_29_fine_pitch_mask_dam():
    """Verify ERC rule 29 (FINE_PITCH_MASK_DAM_UNDEFINED)."""
    modules = {"U1": {"kind": "IC", "package": "QFN-32_EPAD", "mask_dam_defined": False}}
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.GND"]}])
    codes = [i["code"] for i in issues]
    assert "FINE_PITCH_MASK_DAM_UNDEFINED" in codes

    modules_ok = {"U1": {"kind": "IC", "package": "QFN-32_EPAD", "mask_dam_defined": True}}
    issues_ok = run_erc(modules_ok, [{"net": "/GND", "points": ["U1.GND"]}])
    assert "FINE_PITCH_MASK_DAM_UNDEFINED" not in [i["code"] for i in issues_ok]


def test_mcp_server_assembly_drawing_tool():
    """Verify MCP server dispatches export_assembly_drawing_svg (tool 42)."""
    res = handle_tool_call(
        "export_assembly_drawing_svg",
        {"modules": _modules(), "board_width_mm": 60.0, "board_height_mm": 40.0, "revision": "B"},
    )
    assert not res.get("isError")
    svg = res["content"][0]["text"]
    assert svg.startswith("<svg")
    assert "REV B" in svg
