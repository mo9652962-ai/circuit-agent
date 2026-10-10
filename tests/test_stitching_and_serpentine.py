"""Tests for thermal via stitching, RF shielding fence, serpentine tuning, and ERC rules 21-22."""

import json

from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.serpentine_tuning import calculate_serpentine_tuning_geometry
from client.via_stitching import calculate_via_stitching_array


def test_thermal_via_stitching_epad():
    """Verify QFN/DFN exposed pad thermal via array calculation."""
    # 5.0 x 5.0mm EPAD with 1.2mm pitch
    rep = calculate_via_stitching_array(
        pad_width_mm=5.0,
        pad_height_mm=5.0,
        center_x_mm=0.0,
        center_y_mm=0.0,
        drill_dia_mm=0.30,
        grid_pitch_mm=1.20,
    )
    assert rep.thermal_vias_count > 0
    assert rep.shielding_vias_count == 0
    assert rep.thermal_resistance_reduction_pct >= 40.0
    v0 = rep.vias[0]
    assert v0.drill_dia_mm == 0.30
    assert v0.net == "/GND"
    assert v0.via_type == "thermal"


def test_rf_ground_shielding_fence():
    """Verify dual-side ground shielding fence vias along microstrip path."""
    rep = calculate_via_stitching_array(
        is_rf_shielding_fence=True,
        center_x_mm=10.0,
        center_y_mm=20.0,
        grid_pitch_mm=2.0,
    )
    assert rep.shielding_vias_count > 0
    assert rep.thermal_vias_count == 0
    assert rep.vias[0].via_type == "shielding_fence"


def test_serpentine_tuning_geometry():
    """Verify serpentine delay tuning vertices and S >= 3W compliance."""
    rep = calculate_serpentine_tuning_geometry(
        delta_length_mm=4.0,
        trace_width_mm=0.15,
        start_x_mm=0.0,
        start_y_mm=0.0,
        end_x_mm=25.0,
        end_y_mm=0.0,
    )
    assert rep.target_added_length_mm == 4.0
    assert rep.actual_added_length_mm >= 3.8
    assert rep.meander_count >= 1
    assert rep.self_coupling_ratio_s_over_w >= 3.0
    assert rep.is_ipc_compliant is True
    assert len(rep.vertices) >= 4


def test_erc_rule_21_exposed_pad_thermal_via_missing():
    """Verify ERC rule 21 triggers on power IC with exposed pad missing thermal vias."""
    modules = {
        "U1": {"kind": "REGULATOR", "package": "QFN-32_EPAD", "has_thermal_vias": False},
    }
    connections = [{"net": "/GND", "points": ["U1.GND"]}]
    issues = run_erc(modules, connections)
    codes = [i["code"] for i in issues]
    assert "EXPOSED_PAD_THERMAL_VIA_MISSING" in codes


def test_erc_rule_22_rf_ground_shielding_fence_spacing():
    """Verify ERC rule 22 triggers when RF ground shield via spacing exceeds 2.5mm."""
    connections = [
        {
            "net": "/RF_ANT_50R",
            "points": ["U1.ANT", "ANT1.1"],
            "properties": {"shield_via_pitch_mm": 3.5},
        }
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "RF_GROUND_SHIELDING_FENCE_SPACING" in codes


def test_mcp_server_stitching_and_serpentine_tools():
    """Verify MCP server handles calculate_via_stitching_array and calculate_serpentine_tuning_geometry."""
    # 1. Via stitching tool
    res_v = handle_tool_call(
        "calculate_via_stitching_array",
        {"pad_width_mm": 4.0, "pad_height_mm": 4.0, "grid_pitch_mm": 1.0},
    )
    assert not res_v.get("isError")
    data_v = json.loads(res_v["content"][0]["text"])
    assert data_v["thermal_vias_count"] > 0

    # 2. Serpentine tuning tool
    res_s = handle_tool_call(
        "calculate_serpentine_tuning_geometry",
        {"delta_length_mm": 2.5, "trace_width_mm": 0.20},
    )
    assert not res_s.get("isError")
    data_s = json.loads(res_s["content"][0]["text"])
    assert data_s["is_ipc_compliant"] is True
