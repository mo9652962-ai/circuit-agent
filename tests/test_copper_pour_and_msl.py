"""Tests for IPC-2152 copper pour IR-drop analyzer, JEDEC MSL floor life manager, and ERC rules 44-45."""

from client.copper_pour_analyzer import calculate_copper_pour_current_drop
from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.msl_manager import audit_component_msl_floor_life


def test_calculate_copper_pour_safe_current():
    """Verify standard 10A current on 20mm wide 1oz copper pour is well within safe limits."""
    res = calculate_copper_pour_current_drop(
        current_a=10.0,
        copper_weight_oz=1.0,
        effective_length_mm=40.0,
        effective_width_mm=20.0,
        bottleneck_width_mm=15.0,
    )
    assert res.is_density_compliant is True
    assert res.bottleneck_current_density_a_per_mm2 < 35.0
    assert res.voltage_drop_mv > 0.0
    assert res.power_dissipation_watts > 0.0
    assert res.estimated_temp_rise_c < 30.0


def test_calculate_copper_pour_bottleneck_exceeded():
    """Verify narrow 0.5mm neck under 25A current triggers current density violation."""
    res = calculate_copper_pour_current_drop(
        current_a=25.0,
        copper_weight_oz=1.0,  # t = 0.035mm
        effective_length_mm=50.0,
        effective_width_mm=20.0,
        bottleneck_width_mm=0.5,  # area = 0.0175 mm² -> J = 1428 A/mm²
    )
    assert res.is_density_compliant is False
    assert res.bottleneck_current_density_a_per_mm2 > 50.0
    assert res.max_safe_current_a < 25.0


def test_audit_component_msl_safe_exposure():
    """Verify component within JEDEC floor life is marked safe."""
    modules = {
        "U1": {"package": "QFN-32", "part_number": "MCU", "msl_level": "Level 3", "exposed_hours": 24.0},
        "C1": {"package": "0402", "part_number": "CAP", "msl_level": "Level 1", "exposed_hours": 100.0},
    }
    rep = audit_component_msl_floor_life(modules)
    assert rep.is_assembly_safe is True
    assert rep.expired_components_count == 0
    assert len(rep.baking_action_items) == 0


def test_audit_component_msl_expired_triggers_bake_plan():
    """Verify BGA component exposed beyond Level 3 (168h) triggers mandatory bake plan."""
    modules = {
        "U1": {"package": "BGA-256", "part_number": "SOC", "msl_level": "Level 3", "exposed_hours": 200.0},
    }
    rep = audit_component_msl_floor_life(modules)
    assert rep.is_assembly_safe is False
    assert rep.expired_components_count == 1
    assert len(rep.baking_action_items) == 1
    item = rep.baking_action_items[0]
    assert item["ref_des"] == "U1"
    assert "125°C bake" in item["baking_plan"]


def test_erc_rule_44_copper_pour_current_density():
    """Verify ERC rule 44 triggers warning when bottleneck density exceeds 35 A/mm²."""
    connections = [
        {
            "net": "/PWR_VCC",
            "points": ["U1.VCC"],
            "properties": {
                "pour_current_a": 30.0,
                "pour_effective_width_mm": 25.0,
                "pour_bottleneck_width_mm": 0.8,  # t=0.035, area=0.028 mm² -> J > 1000 A/mm²
            },
        }
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "COPPER_POUR_CURRENT_DENSITY_EXCEEDED" in codes


def test_erc_rule_45_msl_expired():
    """Verify ERC rule 45 triggers warning when shop floor exposure exceeds MSL life."""
    modules = {
        "U1": {"package": "QFN", "msl_level": "Level 4"},  # Level 4 = 72 hours
        "__meta__": {"shop_floor_exposed_hours": 100.0},  # 100h > 72h!
    }
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.1"]}])
    codes = [i["code"] for i in issues]
    assert "MSL_FLOOR_LIFE_EXPIRED_WITHOUT_BAKE" in codes


def test_mcp_server_pour_and_msl_tools():
    """Verify MCP server handles calculate_copper_pour_current_drop and audit_component_msl_floor_life."""
    res_pour = handle_tool_call(
        "calculate_copper_pour_current_drop",
        {"current_a": 10.0, "effective_length_mm": 30.0, "effective_width_mm": 15.0},
    )
    assert not res_pour.get("isError")
    assert '"is_density_compliant": true' in res_pour["content"][0]["text"]

    res_msl = handle_tool_call(
        "audit_component_msl_floor_life",
        {"modules": {"U1": {"package": "QFN-32", "exposed_hours": 20.0}}},
    )
    assert not res_msl.get("isError")
    assert '"is_assembly_safe": true' in res_msl["content"][0]["text"]
