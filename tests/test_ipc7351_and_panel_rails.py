"""Tests for IPC-7351B land pattern calculator, SMT breakaway panel frame, and ERC rules 15-16."""

import json

from client.erc import counts, erc_allowed, erc_gate, run_erc
from client.ipc7351_calculator import calculate_ipc7351_land_pattern
from client.mcp_server import handle_tool_call
from client.panel_frame import calculate_pcb_panel_rails


def test_ipc7351_chip_calculator_density_levels():
    """Verify IPC-7351B calculation for 0805 across Density Levels A, B, and C."""
    res_a = calculate_ipc7351_land_pattern("0805", density="A")
    res_b = calculate_ipc7351_land_pattern("0805", density="B")
    res_c = calculate_ipc7351_land_pattern("0805", density="C")

    # Level A (Most) must have larger pad dimensions & courtyard than Level B and C
    assert res_a.pad_outer_z_mm > res_b.pad_outer_z_mm > res_c.pad_outer_z_mm
    assert res_a.courtyard_excess_mm == 0.50
    assert res_b.courtyard_excess_mm == 0.25
    assert res_c.courtyard_excess_mm == 0.12

    assert "M" in res_a.land_pattern_name
    assert "N" in res_b.land_pattern_name
    assert "L" in res_c.land_pattern_name

    # Check pad grid rounding (multiples of 0.05)
    assert round(res_b.pad_width_x_mm % 0.05, 4) in (0.0, 0.05)
    assert round(res_b.pad_length_y_mm % 0.05, 4) in (0.0, 0.05)


def test_ipc7351_gullwing_and_qfn_presets():
    """Verify IPC-7351B calculation for Gullwing (SOIC-8) and QFN-32."""
    soic = calculate_ipc7351_land_pattern("SOIC-8", density="B")
    assert soic.toe_goal_mm == 0.35
    assert soic.heel_goal_mm == 0.35
    assert soic.courtyard_excess_mm == 0.25
    assert "SOIC" in soic.land_pattern_name

    qfn = calculate_ipc7351_land_pattern("QFN-32", density="B")
    assert qfn.toe_goal_mm == 0.30
    assert qfn.heel_goal_mm == 0.00
    assert "QFN" in qfn.land_pattern_name


def test_panel_frame_vcut_layout():
    """Verify SMT panel frame calculation with V-cut de-paneling."""
    panel = calculate_pcb_panel_rails(
        board_width_mm=50.0,
        board_height_mm=40.0,
        grid_x=2,
        grid_y=2,
        depaneling_method="v_cut",
        rail_width_mm=5.0,
        rail_sides="left_right",
    )

    # Active boards 2x50 = 100mm, with left/right 5mm rails = 110mm width
    assert panel.panel_width_mm == 110.0
    # Height without top/bottom rails = 2x40 = 80mm
    assert panel.panel_height_mm == 80.0
    assert panel.board_count == 4
    assert panel.material_utilization_pct > 80.0

    # SMEMA tooling holes (3 NPTH holes, 1 corner omitted for orientation keying)
    assert len(panel.tooling_holes) == 3
    assert panel.tooling_holes[0].diameter_mm == 3.2
    assert not panel.tooling_holes[0].is_plated

    # Optical fiducials (3 fiducials in asymmetric L-pattern)
    assert len(panel.fiducials) == 3
    assert panel.fiducials[0].pad_diameter_mm == 1.0

    # V-cut lines
    assert len(panel.v_cut_lines) > 0
    assert panel.v_cut_lines[0]["angle_deg"] == 30


def test_panel_frame_mouse_bites_layout():
    """Verify SMT panel frame calculation with mouse-bites de-paneling."""
    panel = calculate_pcb_panel_rails(
        board_width_mm=45.0,
        board_height_mm=30.0,
        grid_x=2,
        grid_y=1,
        depaneling_method="mouse_bites",
        rail_width_mm=5.0,
        board_spacing_mm=2.5,
        rail_sides="all_four",
    )

    # With all_four rails: width = 2*45 + 2.5 + 2*5 = 102.5mm, height = 30 + 2*5 = 40mm
    assert panel.panel_width_mm == 102.5
    assert panel.panel_height_mm == 40.0
    assert panel.depaneling_method == "mouse_bites"

    # Breakaway tabs with 5x Φ0.6mm holes and 0.25mm edge recess
    assert len(panel.breakaway_tabs) > 0
    t0 = panel.breakaway_tabs[0]
    assert t0.hole_count == 5
    assert t0.hole_diameter_mm == 0.6
    assert t0.edge_recess_mm == 0.25


def test_erc_courtyard_collision_risk():
    """Verify ERC rule 15 triggers when components are placed with overlapping courtyards."""
    modules = {
        "U1": {"kind": "IC", "position": [10.0, 10.0], "package": "QFN-32"},
        "C1": {"kind": "CAPACITOR", "value": "100nF", "position": [10.1, 10.1], "package": "0402"},
    }
    connections = [
        {"net": "/GND", "points": ["U1.GND", "C1.2"]},
        {"net": "/3V3", "points": ["U1.VCC", "C1.1"]},
    ]
    issues = run_erc(modules, connections)
    codes = [i["code"] for i in issues]
    assert "COURTYARD_COLLISION_RISK" in codes

    # When spaced safely apart, COURTYARD_COLLISION_RISK should not trigger
    modules["C1"]["position"] = [15.0, 10.0]
    issues_ok = run_erc(modules, connections)
    assert "COURTYARD_COLLISION_RISK" not in [i["code"] for i in issues_ok]


def test_erc_thermal_relief_missing_on_high_current():
    """Verify ERC rule 16 triggers on high current nets without thermal relief."""
    modules = {
        "U1": {"kind": "REGULATOR", "value": "LM2596"},
        "C1": {"kind": "CAPACITOR", "value": "100nF"},
    }
    connections = [
        {
            "net": "/VIN_PWR",
            "points": ["U1.VIN", "C1.1"],
            "properties": {"zone_connection": "solid", "current_rating_a": 3.0},
        },
        {"net": "/GND", "points": ["U1.GND", "C1.2"]},
    ]
    issues = run_erc(modules, connections)
    codes = [i["code"] for i in issues]
    assert "THERMAL_RELIEF_MISSING_ON_HIGH_CURRENT" in codes


def test_erc_gate_all_clean():
    """Verify ERC gate passes on compliant netlist."""
    modules = {
        "U1": {"kind": "MCU", "value": "ESP32", "position": [20.0, 20.0]},
        "C1": {"kind": "CAPACITOR", "value": "100nF", "position": [30.0, 20.0]},
    }
    connections = [
        {"net": "/GND", "points": ["U1.GND", "C1.2"]},
        {"net": "/3V3", "points": ["U1.VCC", "C1.1"]},
    ]
    issues = run_erc(modules, connections)
    gate = erc_gate(issues)
    assert erc_allowed(issues)
    assert gate["allowed"] is True
    assert counts(issues)["blocking"] == 0
    assert counts(issues)["error"] == 0


def test_mcp_server_new_tools():
    """Verify MCP server dispatches calculate_ipc7351_land_pattern and calculate_pcb_panel_rails."""
    # 1. Land pattern tool
    res_lp = handle_tool_call(
        "calculate_ipc7351_land_pattern",
        {"package": "0805", "density": "B"},
    )
    assert not res_lp.get("isError")
    data_lp = json.loads(res_lp["content"][0]["text"])
    assert data_lp["package"] == "0805"
    assert "pad_width_x_mm" in data_lp
    assert "courtyard_bounds" in data_lp

    # 2. Panel frame tool
    res_pf = handle_tool_call(
        "calculate_pcb_panel_rails",
        {
            "board_width_mm": 60.0,
            "board_height_mm": 40.0,
            "grid_x": 2,
            "grid_y": 2,
            "depaneling_method": "v_cut",
        },
    )
    assert not res_pf.get("isError")
    data_pf = json.loads(res_pf["content"][0]["text"])
    assert data_pf["panel_width_mm"] == 130.0  # 2*60 + 2*5 = 130
    assert len(data_pf["tooling_holes"]) == 3
    assert len(data_pf["fiducials"]) == 3
