"""Tests for ICT bed-of-nails testpoint allocator, BGA escape router, and ERC rules 17-18."""

import json

from client.bga_escape_router import calculate_bga_escape_routing
from client.erc import run_erc
from client.ict_testpoints import calculate_ict_testpoints
from client.mcp_server import handle_tool_call


def test_ict_testpoints_allocation():
    """Verify ICT testpoint placement and probe style assignment."""
    connections = [
        {"net": "/GND", "points": ["U1.GND", "C1.2"]},
        {"net": "/3V3", "points": ["U1.VCC", "C1.1"]},
        {"net": "/SWDIO", "points": ["U1.PA13", "J1.2"]},
        {"net": "/SWCLK", "points": ["U1.PA14", "J1.3"]},
        {"net": "/SIG_IN", "points": ["U1.PA0", "R1.1"]},
    ]
    rep = calculate_ict_testpoints(connections, board_width_mm=60.0, board_height_mm=40.0)

    assert rep.total_nets == 5
    assert rep.tested_nets_count == 5
    assert rep.net_coverage_pct == 100.0
    assert rep.power_coverage_pct == 100.0
    assert rep.bed_of_nails_compatible is True

    # Check probe types
    tp_map = {tp.net: tp for tp in rep.testpoints}
    assert tp_map["/GND"].probe_type == "100mil_crown"
    assert tp_map["/3V3"].probe_type == "100mil_crown"
    assert tp_map["/SWDIO"].probe_type == "75mil_spear"
    assert tp_map["/SIG_IN"].probe_type == "50mil_serrated"


def test_erc_rule_17_ict_coverage_deficit():
    """Verify ERC rule 17 triggers when critical power or reset nets lack testpoints."""
    modules = {"U1": {"kind": "MCU"}, "C1": {"kind": "CAPACITOR", "value": "100nF"}}
    connections = [
        {"net": "/GND", "points": ["U1.GND", "C1.2"]},
        {"net": "/VBUS", "points": ["U1.VBUS", "C1.1"], "properties": {"has_testpoint": False}},
    ]
    issues = run_erc(modules, connections)
    codes = [i["code"] for i in issues]
    assert "ICT_TESTPOINT_COVERAGE_DEFICIT" in codes


def test_erc_rule_18_clock_trace_length():
    """Verify ERC rule 18 triggers when crystal clock trace length exceeds 15mm."""
    modules = {"U1": {"kind": "MCU"}, "Y1": {"kind": "CRYSTAL"}}
    connections = [
        {"net": "/GND", "points": ["U1.GND"]},
        {"net": "/3V3", "points": ["U1.VCC"]},
        {"net": "/OSC_IN", "points": ["U1.OSC_IN", "Y1.1"], "properties": {"trace_length_mm": 22.5}},
    ]
    issues = run_erc(modules, connections)
    codes = [i["code"] for i in issues]
    assert "HIGH_FREQUENCY_CLOCK_TRACE_LENGTH" in codes

    # Within 15mm should not trigger
    connections[2]["properties"]["trace_length_mm"] = 8.0
    issues_ok = run_erc(modules, connections)
    assert "HIGH_FREQUENCY_CLOCK_TRACE_LENGTH" not in [i["code"] for i in issues_ok]


def test_bga_escape_routing_dogbone():
    """Verify BGA 0.8mm pitch 64-ball diagonal dogbone via fanout calculation."""
    rep = calculate_bga_escape_routing(
        ball_count=64,
        ball_pitch_mm=0.8,
        ball_pad_dia_mm=0.4,
        via_drill_mm=0.2,
        via_pad_dia_mm=0.45,
        trace_width_mm=0.10,
    )
    assert rep.ball_count == 64
    assert rep.channel_width_mm == 0.40  # 0.8 - 0.4 = 0.4mm
    assert rep.escape_clearance_mm == 0.15  # (0.4 - 0.1) / 2 = 0.15mm
    assert rep.min_layers_required >= 4
    assert rep.hdi_microvia_required is False
    assert len(rep.dogbone_vias) == 64

    # Outer ring has Top escape layer
    assert rep.dogbone_vias[0].escape_layer == "Top"


def test_bga_escape_hdi_needed():
    """Verify fine-pitch BGA (0.5mm) triggers HDI micro-via-in-pad requirement."""
    rep = calculate_bga_escape_routing(
        ball_count=100,
        ball_pitch_mm=0.5,
        ball_pad_dia_mm=0.3,
        via_drill_mm=0.2,
        via_pad_dia_mm=0.45,
    )
    assert rep.hdi_microvia_required is True


def test_mcp_server_ict_and_bga_tools():
    """Verify MCP server handles calculate_ict_testpoints and calculate_bga_escape_routing."""
    # 1. ICT tool call
    res_ict = handle_tool_call(
        "calculate_ict_testpoints",
        {
            "connections": [
                {"net": "/GND", "points": ["U1.1", "C1.1"]},
                {"net": "/3V3", "points": ["U1.2", "C1.2"]},
            ],
            "board_width_mm": 50.0,
            "board_height_mm": 40.0,
        },
    )
    assert not res_ict.get("isError")
    data_ict = json.loads(res_ict["content"][0]["text"])
    assert data_ict["total_nets"] == 2
    assert "testpoints" in data_ict

    # 2. BGA tool call
    res_bga = handle_tool_call(
        "calculate_bga_escape_routing",
        {"ball_count": 64, "ball_pitch_mm": 0.8},
    )
    assert not res_bga.get("isError")
    data_bga = json.loads(res_bga["content"][0]["text"])
    assert data_bga["ball_count"] == 64
    assert len(data_bga["dogbone_vias"]) == 64
