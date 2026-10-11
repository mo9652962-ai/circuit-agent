"""Tests for impedance tolerance analysis, material CTI creepage evaluation, and ERC rules 36-37."""

from client.erc import run_erc
from client.impedance_tolerance_analyzer import analyze_impedance_tolerance
from client.material_cti_evaluator import evaluate_material_cti_creepage, get_material_group
from client.mcp_server import handle_tool_call


def test_impedance_tolerance_50ohm():
    """Verify microstrip tolerance analysis, sensitivities, and yield estimate."""
    rep = analyze_impedance_tolerance(
        target_z0_ohms=50.0,
        trace_width_mm=0.38,
        dielectric_height_mm=0.20,
        copper_thickness_mm=0.035,
        dielectric_er=4.2,
    )
    assert 45.0 <= rep.nominal_z0_ohms <= 55.0
    assert rep.min_z0_ohms < rep.nominal_z0_ohms < rep.max_z0_ohms
    assert rep.sensitivity_dZ_dW < 0.0  # wider trace reduces impedance
    assert rep.sensitivity_dZ_dH > 0.0  # thicker dielectric increases impedance
    assert rep.yield_estimate_pct >= 60.0


def test_material_cti_evaluation_group_and_creepage():
    """Verify CTI group classification and creepage comparison."""
    assert get_material_group(600.0) == "Group I"
    assert get_material_group(450.0) == "Group II"
    assert get_material_group(175.0) == "Group IIIa"
    assert get_material_group(120.0) == "Group IIIb"

    # At 220V, Group I requires 1.25mm while Group IIIa requires 2.50mm
    rep_std = evaluate_material_cti_creepage(working_voltage_v=220.0, actual_clearance_mm=1.8, substrate_cti_v=175.0)
    assert rep_std.material_group == "Group IIIa"
    assert rep_std.required_creepage_mm == 2.50
    assert rep_std.is_compliant is False
    assert rep_std.recommend_high_cti_laminate is True

    rep_high = evaluate_material_cti_creepage(working_voltage_v=220.0, actual_clearance_mm=1.8, substrate_cti_v=600.0)
    assert rep_high.material_group == "Group I"
    assert rep_high.required_creepage_mm == 1.25
    assert rep_high.is_compliant is True


def test_erc_rules_36_and_37():
    """Verify ERC rules 36 (impedance tolerance) and 37 (CTI creepage deficit)."""
    # Rule 36: mismatched geometry that causes Z to deviate from 50R
    connections = [
        {
            "net": "/RF_50R",
            "points": ["U1.1"],
            "properties": {
                "target_impedance_ohms": 50.0,
                "trace_width_mm": 0.10,  # too narrow -> Z ~ 90R -> exceeds 10%
                "dielectric_height_mm": 0.30,
            },
        }
    ]
    issues_36 = run_erc({}, connections)
    codes_36 = [i["code"] for i in issues_36]
    assert "IMPEDANCE_TOLERANCE_WINDOW_EXCEEDED" in codes_36

    # Rule 37: 220V with 1.8mm clearance on standard FR-4 (requires 2.5mm)
    conns_37 = [
        {
            "net": "/AC_MAINS",
            "points": ["J1.1"],
            "properties": {
                "voltage_v": 220.0,
                "clearance_mm": 1.8,
                "substrate_cti_v": 175.0,
                "pollution_degree": 2,
            },
        }
    ]
    issues_37 = run_erc({}, conns_37)
    codes_37 = [i["code"] for i in issues_37]
    assert "POLLUTION_DEGREE_CREEPAGE_DEFICIT" in codes_37


def test_mcp_server_impedance_and_cti_tools():
    """Verify MCP server handles analyze_impedance_tolerance and evaluate_material_cti_creepage."""
    # 1. Impedance tolerance
    res_z = handle_tool_call(
        "analyze_impedance_tolerance",
        {"target_z0_ohms": 50.0, "trace_width_mm": 0.38, "dielectric_height_mm": 0.20},
    )
    assert not res_z.get("isError")
    assert '"yield_estimate_pct"' in res_z["content"][0]["text"]

    # 2. Material CTI
    res_cti = handle_tool_call(
        "evaluate_material_cti_creepage",
        {"working_voltage_v": 220.0, "actual_clearance_mm": 2.2, "substrate_cti_v": 600.0},
    )
    assert not res_cti.get("isError")
    assert '"material_group": "Group I"' in res_cti["content"][0]["text"]
