"""Tests for Telcordia MTBF predictor, JESD22-B111 drop shock assessor, and ERC rules 52-53."""

from client.drop_shock import assess_drop_shock_reliability
from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.mtbf_predictor import predict_assembly_mtbf


def test_mtbf_part_counts_prediction():
    """Verify a moderate BOM predicts sensible FIT / MTBF / 5yr survival."""
    res = predict_assembly_mtbf(
        part_counts={"MICROCONTROLLER": 1, "RESISTOR_CHIP": 20, "CAPACITOR_CERAMIC": 15,
                     "INDUCTOR_POWER": 3, "CONNECTOR_PIN": 8},
        ambient_temp_c=40.0,
        environment="ground_fixed",
    )
    assert res.parts_counted == 47
    assert res.total_fits > 0
    assert res.mtbf_hours > 100_000
    assert 0.9 < res.reliability_5yr <= 1.0
    assert len(res.dominant_parts) == 5
    assert res.dominant_parts[0]["share_pct"] >= res.dominant_parts[-1]["share_pct"]


def test_mtbf_temperature_and_environment_aggravation():
    """Verify hot airborne conditions degrade MTBF vs benign lab."""
    benign = predict_assembly_mtbf(part_counts={"IC_DIGITAL_CMOS": 10}, ambient_temp_c=25.0, environment="ground_benign")
    harsh = predict_assembly_mtbf(part_counts={"IC_DIGITAL_CMOS": 10}, ambient_temp_c=70.0, environment="airborne")
    assert harsh.mtbf_hours < benign.mtbf_hours
    assert harsh.pi_e == 12.0 and benign.pi_e == 1.0
    assert harsh.pi_t > benign.pi_t


def test_mtbf_from_bom_modules_autoclassified():
    """Verify BOM modules auto-classify into Telcordia part classes."""
    modules = {
        "U1": {"kind": "MICROCONTROLLER", "value": "STM32"},
        "C1": {"kind": "CAPACITOR", "value": "100nF"},
        "C9": {"kind": "CAPACITOR", "value": "470uF ELECTROLYTIC"},
        "R1": {"kind": "RESISTOR", "value": "10k"},
        "J1": {"kind": "CONNECTOR", "value": "USB_C"},
        "TP_1": {"kind": "TESTPOINT", "value": ""},
        "FID1": {"kind": "FIDUCIAL", "value": ""},
    }
    res = predict_assembly_mtbf(modules=modules)
    assert res.parts_counted == 5  # testpoint/fiducial excluded
    shares = {d["part_class"] for d in res.dominant_parts}
    assert "CAPACITOR_ELECTROLYTIC" in shares  # wear-out dominant


def test_drop_shock_heavy_shield_high_risk():
    """Verify a 40g shield on 4 joints overloads into high risk."""
    res = assess_drop_shock_reliability(
        board_width_mm=100.0,
        board_height_mm=60.0,
        components=[
            {"ref": "SHD1", "mass_g": 40.0, "x_mm": 40.0, "y_mm": 24.0, "joint_count": 4},
        ],
    )
    assert res.high_risk_count == 1
    shield = res.components[0]
    # F = 0.04kg × 1500 × 9.81 ≈ 589N / 4 ≈ 147N/joint
    assert shield.per_joint_load_n > 100.0
    assert shield.risk_level == "high"
    assert "欠填充" in shield.mitigation or "螺柱" in shield.mitigation


def test_drop_shock_center_small_parts_pass():
    """Verify small center components are low risk and corner zone stays clear."""
    res = assess_drop_shock_reliability(
        board_width_mm=100.0,
        board_height_mm=60.0,
        components=[
            {"ref": "C1", "mass_g": 0.05, "x_mm": 5.0, "y_mm": 3.0, "joint_count": 2},
            {"ref": "U2", "mass_g": 0.8, "x_mm": 0.0, "y_mm": 0.0, "joint_count": 48},
        ],
    )
    assert res.high_risk_count == 0
    assert all(c.risk_level == "low" for c in res.components)
    assert res.corner_zone_clear is True


def test_drop_shock_stiffener_raises_frequency():
    """Verify a border ring roughly doubles the estimated natural frequency."""
    plain = assess_drop_shock_reliability(board_width_mm=80.0)
    stiff = assess_drop_shock_reliability(board_width_mm=80.0, has_border_ring_stiffener=True)
    assert stiff.est_natural_freq_hz > plain.est_natural_freq_hz * 1.5


def test_erc_rule_52_mtbf_shortfall():
    """Verify ERC rule 52 fires when predicted MTBF falls below the allocation target."""
    modules = {
        "__meta__": {"mtbf_target_hours": 5_000_000, "reliability_environment": "ground_fixed"},
        "C1": {"kind": "CAPACITOR", "value": "470uF ELECTROLYTIC"},
        "U1": {"kind": "MICROCONTROLLER", "value": "STM32"},
    }
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.1"]}])
    codes = [i["code"] for i in issues]
    assert "MTBF_RELIABILITY_BUDGET_SHORTFALL" in codes


def test_erc_rule_53_drop_shock_risk():
    """Verify ERC rule 53 fires for heavy corner components under drop metadata."""
    modules = {
        "__meta__": {
            "board_width_mm": 100.0,
            "board_height_mm": 60.0,
            "drop_test_components": [
                {"ref": "SHD1", "mass_g": 40.0, "x_mm": 40.0, "y_mm": 24.0, "joint_count": 4},
            ],
        },
        "R1": {"kind": "RESISTOR", "value": "10k"},
    }
    issues = run_erc(modules, [{"net": "/GND", "points": ["R1.1"]}])
    codes = [i["code"] for i in issues]
    assert "DROP_SHOCK_HIGH_RISK_PLACEMENT" in codes


def test_mcp_server_mtbf_and_drop_tools():
    """Verify MCP server dispatches both new tools."""
    res_rel = handle_tool_call(
        "predict_assembly_mtbf",
        {"part_counts": {"IC_DIGITAL_CMOS": 10}, "environment": "ground_benign"},
    )
    assert not res_rel.get("isError")
    assert '"mtbf_hours"' in res_rel["content"][0]["text"]

    res_drop = handle_tool_call(
        "assess_drop_shock_reliability",
        {"components": [{"ref": "U1", "mass_g": 0.5, "x_mm": 0, "y_mm": 0, "joint_count": 32}]},
    )
    assert not res_drop.get("isError")
    assert '"high_risk_count": 0' in res_drop["content"][0]["text"]
