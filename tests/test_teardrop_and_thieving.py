"""Tests for teardrop fillet reinforcement, copper thieving balance, and ERC rules 19-20."""

import json

from client.copper_thieving import calculate_copper_thieving_balance
from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.teardrop_engine import calculate_teardrop_reinforcement


def test_teardrop_fillet_geometry():
    """Verify teardrop fillet math and tangent points."""
    vias = [
        {
            "id": "V1",
            "x_mm": 10.0,
            "y_mm": 20.0,
            "pad_dia_mm": 0.50,
            "drill_dia_mm": 0.25,
            "trace_angle_deg": 45.0,
            "trace_width_mm": 0.20,
        }
    ]
    rep = calculate_teardrop_reinforcement(vias)
    assert rep.total_vias_analyzed == 1
    assert rep.reinforced_vias_count == 1
    td = rep.teardrops[0]
    assert td.annular_ring_margin_mm == 0.125  # (0.50 - 0.25)/2
    assert td.ipc_class3_compliant is True
    assert len(td.tangent_points) == 4


def test_teardrop_class3_narrow_annular():
    """Verify annular ring < 0.050mm fails Class 3 compliance."""
    vias = [
        {
            "id": "V_TIGHT",
            "x_mm": 5.0,
            "y_mm": 5.0,
            "pad_dia_mm": 0.36,
            "drill_dia_mm": 0.30,  # Annular ring = 0.030mm < 0.050mm
        }
    ]
    rep = calculate_teardrop_reinforcement(vias)
    assert rep.teardrops[0].ipc_class3_compliant is False


def test_copper_thieving_balance_high_risk():
    """Verify density imbalance > 35% triggers HIGH warpage risk."""
    rep = calculate_copper_thieving_balance(
        board_width_mm=100.0,
        board_height_mm=80.0,
        top_copper_area_mm2=800.0,  # 10%
        bot_copper_area_mm2=5600.0,  # 70% -> diff = 60%
    )
    assert rep.density_imbalance_pct == 60.0
    assert rep.warpage_risk == "HIGH"
    assert rep.thieving_features_count > 0


def test_copper_thieving_grid_generation():
    """Verify dummy thieving dot pattern grid coordinates."""
    rep = calculate_copper_thieving_balance(
        board_width_mm=50.0,
        board_height_mm=30.0,
        pattern_pitch_mm=5.0,
        dot_diameter_mm=1.2,
    )
    assert rep.thieving_features_count >= 15
    f0 = rep.features[0]
    assert f0.feature_type == "dot"
    assert f0.diameter_mm == 1.2


def test_erc_rule_19_copper_thieving_imbalance():
    """Verify ERC rule 19 triggers on copper density imbalance > 35%."""
    connections = [
        {
            "net": "/GND",
            "points": ["U1.GND"],
            "properties": {"top_copper_density_pct": 15.0, "bot_copper_density_pct": 65.0},
        }
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "LAYER_COPPER_THIEVING_IMBALANCE" in codes


def test_erc_rule_20_unreinforced_via():
    """Verify ERC rule 20 triggers on fine trace <= 0.15mm with unreinforced via."""
    connections = [
        {
            "net": "/NET_FINE",
            "points": ["U1.IO1"],
            "properties": {"trace_width_mm": 0.12, "has_vias": True, "teardrop_reinforced": False},
        }
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "UNREINFORCED_VIA_ANNULAR_BREAKOUT" in codes


def test_mcp_server_teardrop_and_thieving_tools():
    """Verify MCP server handles calculate_teardrop_reinforcement and calculate_copper_thieving_balance."""
    # 1. Teardrop tool
    res_td = handle_tool_call(
        "calculate_teardrop_reinforcement",
        {
            "vias": [{"x_mm": 12.0, "y_mm": 14.0, "pad_dia_mm": 0.45, "drill_dia_mm": 0.20}],
        },
    )
    assert not res_td.get("isError")
    data_td = json.loads(res_td["content"][0]["text"])
    assert data_td["total_vias_analyzed"] == 1

    # 2. Thieving tool
    res_cu = handle_tool_call(
        "calculate_copper_thieving_balance",
        {"board_width_mm": 60.0, "board_height_mm": 40.0},
    )
    assert not res_cu.get("isError")
    data_cu = json.loads(res_cu["content"][0]["text"])
    assert data_cu["board_width_mm"] == 60.0
    assert "thieving_features_count" in data_cu
