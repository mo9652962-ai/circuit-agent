"""Tests for native Gerber RS-274X exporter, PCB stackup engine, and ERC rules 9 & 10."""

import json

import pytest

from client.erc import erc_allowed, run_erc
from client.gerber_exporter import export_gerber_bundle
from client.stackup_engine import (
    get_stackup_profile,
    solve_target_trace_width,
)
from client.synthesizer import synthesize_from_prompt


def test_export_gerber_bundle_layers():
    """Verify generated Gerber bundle contains 4 manufacturing layers with RS-274X syntax."""
    res = synthesize_from_prompt("STM32F103 USB-C LDO CAN")
    bundle = export_gerber_bundle(
        res["modules"],
        res["netlist"]["connections"],
        board_width_mm=80.0,
        board_height_mm=60.0,
    )
    expected_layers = {
        "board-Edge_Cuts.gm1",
        "board-F_Cu.gtl",
        "board-F_Mask.gts",
        "board-F_SilkS.gto",
    }
    assert set(bundle.keys()) == expected_layers

    # Check RS-274X syntax on edge cuts
    gm1 = bundle["board-Edge_Cuts.gm1"]
    assert "%FSLAX45Y45*%" in gm1
    assert "%MOMM*%" in gm1
    assert "M02*" in gm1

    # Check top copper has pad flashes (D11* and D03*)
    gtl = bundle["board-F_Cu.gtl"]
    assert "%ADD11R" in gtl
    assert "D03*" in gtl


def test_stackup_engine_jlc04161h():
    """Verify JLC04161H 4-layer stackup matrix and IPC-2141 trace width solver."""
    prof = get_stackup_profile("JLC04161H")
    assert prof.layer_count == 4
    assert prof.total_thickness_mm == pytest.approx(1.60)
    assert len(prof.impedance_matrix) == 4

    # 50 Ohm microstrip on 0.21mm prepreg -> W should be ~0.38mm
    w_50 = solve_target_trace_width(50.0, h_mm=0.21, er=4.4)
    assert w_50 == pytest.approx(0.38, abs=0.04)


def test_erc_rules_stackup_and_return_path():
    """Verify ERC rule 9 (impedance mismatch) and rule 10 (missing return path)."""
    # 1. Test STACKUP_IMPEDANCE_MISMATCH
    conns_bad_width = [
        {"net": "/GND", "points": ["U1.1", "J1.1"]},
        {
            "net": "/RF_ANT",
            "points": ["U1.2", "J1.2"],
            "properties": {"target_impedance_ohms": 50.0, "trace_width_mm": 0.10},  # 0.10mm << 0.38mm -> Mismatch
        },
    ]
    issues = run_erc({"U1": {"kind": "IC"}, "J1": {"kind": "CONNECTOR"}}, conns_bad_width)
    codes = {i["code"] for i in issues}
    assert "STACKUP_IMPEDANCE_MISMATCH" in codes
    assert erc_allowed(issues) is True

    # 2. Test MISSING_LAYER_RETURN_PATH
    modules_no_gnd = {
        "J_USB": {"kind": "CONNECTOR", "value": "USB-C-16P"},
        "R1": {"kind": "RESISTOR", "value": "10k"},
    }
    conns_no_gnd = [
        {"net": "/VBUS", "points": ["J_USB.VBUS", "R1.1"]},
        {"net": "/SIG", "points": ["J_USB.A5", "R1.2"]},
        # Missing any GND pin on J_USB
    ]
    issues2 = run_erc(modules_no_gnd, conns_no_gnd)
    codes2 = {i["code"] for i in issues2}
    assert "MISSING_LAYER_RETURN_PATH" in codes2


def test_mcp_tools_gerber_and_stackup():
    """Verify MCP tools export_gerber_bundle and calculate_pcb_stackup_impedance."""
    from client.mcp_server import handle_tool_call

    res = synthesize_from_prompt("ESP32-C3 USB-C LDO")

    # 1. export_gerber_bundle
    out_g = handle_tool_call("export_gerber_bundle", {
        "modules": res["modules"],
        "netlist": res["netlist"],
        "board_width_mm": 75.0,
        "board_height_mm": 55.0,
    })
    assert "isError" not in out_g
    g_data = json.loads(out_g["content"][0]["text"])
    assert "board-F_Cu.gtl" in g_data

    # 2. calculate_pcb_stackup_impedance
    out_s = handle_tool_call("calculate_pcb_stackup_impedance", {
        "stackup_id": "JLC04161H",
        "solve_custom_z_ohms": 50.0,
    })
    assert "isError" not in out_s
    s_data = json.loads(out_s["content"][0]["text"])
    assert s_data["layer_count"] == 4
    assert s_data["solved_custom_width_mm"] > 0
