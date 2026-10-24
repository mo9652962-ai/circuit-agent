"""Tests for IPC-9701 thermal fatigue estimator, IPC-CC-830 coating planner, and ERC rules 50-51."""

from client.conformal_coating import plan_conformal_coating
from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.thermal_fatigue import estimate_solder_joint_thermal_fatigue


def test_thermal_fatigue_healthy_bga():
    """Verify a BT-BGA with small CTE mismatch survives TC3 comfortably."""
    res = estimate_solder_joint_thermal_fatigue(
        component="U1_BGA256",
        dnp_mm=15.0,
        joint_height_mm=0.10,
        condition="TC3",
        package_cte_ppm=14.0,
        required_cycles=3000.0,
    )
    assert res.delta_t_c == 165.0  # -40 to +125
    assert res.strain_range > 0
    assert res.cycles_to_failure_ntf > 3000.0
    assert res.meets_requirement is True
    assert res.cycle_exponent_c < 0  # negative exponent per Engelmaier


def test_thermal_fatigue_ceramic_package_fails():
    """Verify a ceramic CLCC with large DNP fails the service requirement."""
    res = estimate_solder_joint_thermal_fatigue(
        component="U5_CLCC44",
        dnp_mm=20.0,
        joint_height_mm=0.05,
        package_cte_ppm=6.5,  # ceramic vs FR-4 15 → Δα = 8.5
        condition="TC4",
        required_cycles=3000.0,
    )
    assert res.meets_requirement is False
    assert "underfill" in res.derating_note or "欠填充" in res.derating_note


def test_thermal_fatigue_dwell_creep_aggravation():
    """Verify longer hot dwell shortens life (creep exponent)."""
    short = estimate_solder_joint_thermal_fatigue(hot_dwell_min=5.0, required_cycles=1.0)
    long = estimate_solder_joint_thermal_fatigue(hot_dwell_min=60.0, required_cycles=1.0)
    assert long.cycles_to_failure_ntf < short.cycles_to_failure_ntf


def test_coating_thickness_and_rework_conflict():
    """Verify under-thickness SR flags non-compliance and ER blocks field rework."""
    thin = plan_conformal_coating(coating_type="SR", measured_thickness_um=30.0)  # SR needs ≥50
    assert thin.is_thickness_compliant is False
    assert "下限" in thin.summary

    conflict = plan_conformal_coating(
        coating_type="ER", measured_thickness_um=75.0, requires_field_rework=True
    )
    assert conflict.reworkability_conflict is True


def test_coating_mask_keepouts_from_bom():
    """Verify connectors and test points become masking keepouts."""
    modules = {
        "J1": {"kind": "CONNECTOR", "package": "PinHeader_1x04"},
        "SW1": {"kind": "SWITCH", "package": "SW_SPST"},
        "R1": {"kind": "RESISTOR", "package": "R0603"},
        "TP_GND": {"kind": "TESTPOINT", "package": "TP_1mm"},
    }
    res = plan_conformal_coating(coating_type="AR", measured_thickness_um=75.0, modules=modules)
    keepout_refs = {k["ref"] for k in res.mask_keepouts}
    assert {"J1", "SW1", "TP_GND"} <= keepout_refs
    assert "R1" not in keepout_refs  # resistors get coated
    assert res.is_thickness_compliant is True


def test_erc_rule_50_thermal_fatigue():
    """Verify ERC rule 50 fires on a fatigue-deficient component."""
    connections = [
        {
            "net": "/U5_CLCC_CRITICAL",
            "points": ["U5.1"],
            "properties": {
                "thermal_dnp_mm": 20.0,
                "joint_height_mm": 0.05,
                "package_cte_ppm": 6.5,
                "thermal_cycling_condition": "TC4",
                "required_cycles": 3000.0,
            },
        }
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "THERMAL_CYCLING_FATIGUE_RISK" in codes


def test_erc_rule_51_conformal_coating_contact_risk():
    """Verify ERC rule 51 fires on unverified coating-exempt contact parts."""
    modules = {
        "__meta__": {
            "conformal_coating": "UR",
            "coating_thickness_um": 60.0,
            "requires_field_rework": True,
        },
        "J1": {"kind": "CONNECTOR", "package": "USB_C", "coating_exempt": True},
        "R1": {"kind": "RESISTOR", "package": "R0603"},
    }
    issues = run_erc(modules, [{"net": "/GND", "points": ["R1.1"]}])
    codes = [i["code"] for i in issues]
    assert "CONFORMAL_COATING_CONTACT_RISK" in codes
    # Both the contact risk and the rework conflict should appear
    hits = [i for i in issues if i["code"] == "CONFORMAL_COATING_CONTACT_RISK"]
    assert len(hits) >= 2


def test_mcp_server_fatigue_and_coating_tools():
    """Verify MCP server dispatches both new tools."""
    res_fat = handle_tool_call(
        "estimate_solder_joint_thermal_fatigue",
        {"dnp_mm": 15.0, "condition": "TC3"},
    )
    assert not res_fat.get("isError")
    assert '"meets_requirement": true' in res_fat["content"][0]["text"]

    res_cc = handle_tool_call(
        "plan_conformal_coating",
        {"coating_type": "AR", "measured_thickness_um": 75.0},
    )
    assert not res_cc.get("isError")
    assert '"is_thickness_compliant": true' in res_cc["content"][0]["text"]
