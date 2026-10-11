"""Tests for PCB fab cost estimator, ERC rule 33, and MCP tool 46."""

from client.erc import run_erc
from client.fab_cost import calculate_fab_cost
from client.mcp_server import handle_tool_call


def test_fab_cost_tier_and_layers():
    """Verify base price tiers by layers and quantity."""
    r2l = calculate_fab_cost(layers=2, quantity=5)
    r4l = calculate_fab_cost(layers=4, quantity=5)
    r6l = calculate_fab_cost(layers=6, quantity=5)
    assert r2l.base_price_cny < r4l.base_price_cny < r6l.base_price_cny

    q5 = calculate_fab_cost(layers=4, quantity=5).total_cost_cny
    q10 = calculate_fab_cost(layers=4, quantity=10).total_cost_cny
    assert q10 > q5

    # Unit cost drops with quantity (tier pricing)
    u5 = calculate_fab_cost(layers=4, quantity=5).unit_cost_cny
    u100 = calculate_fab_cost(layers=4, quantity=100).unit_cost_cny
    assert u100 < u5


def test_fab_cost_surcharges():
    """Verify area/color/surface/thickness/lead-time surcharges."""
    base = calculate_fab_cost(layers=4, quantity=5, board_width_mm=100.0, board_height_mm=100.0)
    assert base.area_surcharge_cny == 0.0

    big = calculate_fab_cost(layers=4, quantity=5, board_width_mm=200.0, board_height_mm=100.0)
    assert big.area_surcharge_cny > 0.0  # 2 dm² → 1 extra dm²
    assert big.area_dm2 == 2.0

    black = calculate_fab_cost(layers=4, quantity=5, solder_mask_color="black")
    assert black.color_surcharge_cny == 40.0

    enig = calculate_fab_cost(layers=4, quantity=5, surface_finish="enig")
    assert enig.surface_surcharge_cny == 80.0

    urgent = calculate_fab_cost(layers=4, quantity=5, lead_time="urgent_24h")
    assert urgent.lead_time_factor == 2.5
    normal = calculate_fab_cost(layers=4, quantity=5, lead_time="normal")
    assert urgent.total_cost_cny > normal.total_cost_cny


def test_erc_rule_33_panel_features_missing():
    """Verify ERC rule 33 (PANEL_PROCESS_FEATURES_MISSING)."""
    connections = [
        {
            "net": "/PANEL_NET",
            "points": ["U1.1"],
            "properties": {"panelized": True, "has_process_rails": True, "has_fiducials": False, "has_tooling_holes": False},
        }
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "PANEL_PROCESS_FEATURES_MISSING" in codes

    ok = [
        {
            "net": "/PANEL_NET",
            "points": ["U1.1"],
            "properties": {"panelized": True, "has_process_rails": True, "has_fiducials": True, "has_tooling_holes": True},
        }
    ]
    issues_ok = run_erc({}, ok)
    assert "PANEL_PROCESS_FEATURES_MISSING" not in [i["code"] for i in issues_ok]

    # Non-panelized exempt
    single = [{"net": "/N", "points": ["U1.1"], "properties": {}}]
    issues_single = run_erc({}, single)
    assert "PANEL_PROCESS_FEATURES_MISSING" not in [i["code"] for i in issues_single]


def test_mcp_server_fab_cost_tool():
    """Verify MCP server dispatches calculate_fab_cost (tool 46)."""
    res = handle_tool_call(
        "calculate_fab_cost",
        {"layers": 4, "quantity": 10, "board_width_mm": 80.0, "board_height_mm": 60.0, "surface_finish": "enig"},
    )
    assert not res.get("isError")
    text = res["content"][0]["text"]
    assert '"total_cost_cny"' in text
    assert '"unit_cost_cny"' in text
