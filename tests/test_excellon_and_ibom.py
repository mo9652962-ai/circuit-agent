"""Tests for native Excellon CNC drill exporter (.drl) and Interactive HTML BOM generator (iBOM)."""

from client.excellon_exporter import export_excellon_drill
from client.gerber_exporter import export_gerber_bundle
from client.interactive_bom_generator import generate_interactive_bom_html
from client.synthesizer import synthesize_from_prompt


def test_export_excellon_drill_syntax():
    """Verify generated Excellon drill file conforms to IPC-NC-349 standard."""
    res = synthesize_from_prompt("STM32F103 USB-C LDO CAN")
    drl_txt = export_excellon_drill(
        res["modules"],
        res["netlist"]["connections"],
        job_name="TEST_DRILL_JOB",
        board_width_mm=80.0,
        board_height_mm=60.0,
    )
    lines = drl_txt.splitlines()
    assert lines[0] == "M48"
    assert any("; DRILL file TEST_DRILL_JOB" in l for l in lines)
    assert any("METRIC,TZ" in l for l in lines)
    assert any(l.startswith("T01C") for l in lines)
    assert "%" in lines
    assert "G90" in lines
    assert "M30" in lines
    # Check metric coordinate format
    coord_lines = [l for l in lines if l.startswith("X") and "Y" in l]
    assert len(coord_lines) >= 4  # Includes 4 mounting holes and component vias


def test_gerber_bundle_includes_drill_file():
    """Verify export_gerber_bundle now produces complete 5-layer fab bundle including board.drl."""
    res = synthesize_from_prompt("ESP32-C3 USB-C LDO")
    bundle = export_gerber_bundle(
        res["modules"],
        res["netlist"]["connections"],
        board_width_mm=70.0,
        board_height_mm=50.0,
    )
    assert "board.drl" in bundle
    assert bundle["board.drl"].startswith("M48")
    assert len(bundle) == 5  # .gm1, .gtl, .gts, .gto, .drl


def test_generate_interactive_bom_html():
    """Verify generated iBOM is a self-contained HTML page with SVG map and component data."""
    res = synthesize_from_prompt("STM32F103 USB-C LDO CAN 步进电机")
    html_doc = generate_interactive_bom_html(
        res["modules"],
        title="Production Inspection Batch A",
        board_width_mm=80.0,
        board_height_mm=60.0,
    )
    assert "<!DOCTYPE html>" in html_doc
    assert "Production Inspection Batch A · iBOM" in html_doc
    assert "<svg" in html_doc and "</svg>" in html_doc
    assert ".comp-box" in html_doc
    assert "bomData =" in html_doc
    assert "compData =" in html_doc
    assert "function highlightRefs" in html_doc


def test_mcp_tools_drill_and_ibom():
    """Verify MCP tools export_excellon_drill and generate_interactive_bom execute cleanly."""
    from client.mcp_server import handle_tool_call

    res = synthesize_from_prompt("STM32F103 RS485")

    # 1. export_excellon_drill
    out_drl = handle_tool_call("export_excellon_drill", {
        "modules": res["modules"],
        "connections": res["netlist"]["connections"],
        "job_name": "MCP_DRILL_TEST",
    })
    assert "isError" not in out_drl
    drl_content = out_drl["content"][0]["text"]
    assert "M48" in drl_content
    assert "M30" in drl_content

    # 2. generate_interactive_bom
    out_ibom = handle_tool_call("generate_interactive_bom", {
        "modules": res["modules"],
        "title": "MCP FAI Test",
    })
    assert "isError" not in out_ibom
    ibom_content = out_ibom["content"][0]["text"]
    assert "<!DOCTYPE html>" in ibom_content
    assert "MCP FAI Test" in ibom_content
