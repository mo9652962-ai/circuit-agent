"""Tests for IPC-4562B skin effect roughness loss analyzer, IPC-9252B bare board test planner, and ERC rules 46-47."""

from client.bare_board_test_planner import plan_bare_board_test_parameters
from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.skin_effect_analyzer import calculate_high_speed_skin_depth_loss


def test_calculate_high_speed_skin_depth_loss_vlp():
    """Verify 10 GHz on VLP copper foil gives reasonable skin depth and Ksr."""
    res = calculate_high_speed_skin_depth_loss(
        frequency_ghz=10.0,
        trace_width_mm=0.150,
        foil_type="vlp",
    )
    assert res.skin_depth_um < 1.0  # Skin depth at 10GHz is ~0.66μm
    assert res.roughness_correction_factor_ksr > 1.0
    assert res.is_roughness_acceptable is True
    assert res.conductor_loss_rough_db_per_inch > res.conductor_loss_smooth_db_per_inch

    # Test HVLP for ultra-smooth high-frequency
    res_hvlp = calculate_high_speed_skin_depth_loss(
        frequency_ghz=28.0,
        trace_width_mm=0.100,
        foil_type="hvlp",
    )
    assert res_hvlp.is_roughness_acceptable is True
    assert res_hvlp.roughness_correction_factor_ksr < 1.70


def test_calculate_high_speed_skin_depth_loss_rough_fails():
    """Verify standard ED rough foil at 25 GHz triggers excessive Ksr penalty."""
    res = calculate_high_speed_skin_depth_loss(
        frequency_ghz=25.0,
        trace_width_mm=0.100,
        foil_type="standard_ed",  # Rq ≈ 2.0μm
        max_acceptable_ksr=1.50,
    )
    assert res.is_roughness_acceptable is False
    assert res.roughness_correction_factor_ksr > 1.50
    assert "Upgrade copper foil" in res.recommendation


def test_plan_bare_board_test_parameters_class2():
    """Verify Class 2 bare board test establishes 100V isolation and 10 ohm continuity."""
    plan = plan_bare_board_test_parameters(target_class="Class 2", min_trace_clearance_mm=0.150)
    assert plan.target_class == "Class 2"
    assert plan.continuity_summary["signal_threshold_ohms"] == 10.0
    assert plan.isolation_summary["default_test_voltage_v"] == 100.0
    assert plan.derated_nets_count == 0
    assert plan.has_overstress_risk is False


def test_plan_bare_board_test_parameters_class3_fine_pitch_derating():
    """Verify Class 3 fine-pitch (<0.100mm) nets are derated to 100V to avoid dielectric breakdown."""
    nets = [
        {"name": "GND", "is_power": True, "min_clearance_mm": 0.200},
        {"name": "BGA_ESCAPE_NET", "min_clearance_mm": 0.075},  # fine-pitch!
    ]
    plan = plan_bare_board_test_parameters(nets=nets, target_class="Class 3")
    assert plan.target_class == "Class 3"
    assert plan.derated_nets_count == 1
    assert plan.has_overstress_risk is True
    derated_net = next(n for n in plan.net_parameters if n.net_name == "BGA_ESCAPE_NET")
    assert derated_net.isolation_test_voltage_v == 100.0
    assert derated_net.is_voltage_derated is True


def test_erc_rule_46_roughness_loss_excessive():
    """Verify ERC rule 46 triggers warning on high frequency >= 5GHz with standard ED foil."""
    connections = [
        {
            "net": "/PCIE_TX_P",
            "points": ["U1.1"],
            "properties": {
                "operating_freq_ghz": 16.0,
                "copper_foil_type": "standard_ed",
                "trace_width_mm": 0.120,
            },
        }
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "HIGH_SPEED_ROUGHNESS_LOSS_EXCESSIVE" in codes


def test_erc_rule_47_bare_board_test_overstress():
    """Verify ERC rule 47 triggers warning for Class 3 boards with fine pitch clearance."""
    modules = {"__meta__": {"ipc_class": "Class 3"}}
    connections = [
        {
            "net": "/DENSE_BUS_0",
            "points": ["U1.2"],
            "properties": {"trace_clearance_mm": 0.080},
        }
    ]
    issues = run_erc(modules, connections)
    codes = [i["code"] for i in issues]
    assert "BARE_BOARD_TEST_VOLTAGE_OVERSTRESS_RISK" in codes


def test_mcp_server_skin_effect_and_bare_board_tools():
    """Verify MCP server handles calculate_high_speed_skin_depth_loss and calculate_bare_board_test_parameters."""
    res_skin = handle_tool_call(
        "calculate_high_speed_skin_depth_loss",
        {"frequency_ghz": 10.0, "foil_type": "vlp"},
    )
    assert not res_skin.get("isError")
    assert '"is_roughness_acceptable": true' in res_skin["content"][0]["text"]

    res_test = handle_tool_call(
        "calculate_bare_board_test_parameters",
        {"target_class": "Class 2"},
    )
    assert not res_test.get("isError")
    assert '"target_class": "Class 2"' in res_test["content"][0]["text"]
