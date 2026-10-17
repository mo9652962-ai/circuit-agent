"""Tests for wave solder component orientation, press-fit hole compliance, and ERC rules 38-39."""

from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.press_fit_analyzer import calculate_press_fit_hole_compliance
from client.wave_solder_orientation import calculate_wave_solder_orientation_audit


def test_wave_solder_orientation_passive_tombstone():
    """Verify 0805 parallel to X+ flow triggers tombstoning risk; 90° perpendicular passes."""
    modules_bad = {
        "C1": {"kind": "CAPACITOR", "package": "0805", "rotation_deg": 0.0},  # parallel to X+
    }
    rep_bad = calculate_wave_solder_orientation_audit(modules_bad, flow_direction="X+")
    assert rep_bad.misoriented_count == 1
    assert rep_bad.issues[0].issue_type == "PARALLEL_PASSIVE_TOMBSTONE"

    modules_ok = {
        "C1": {"kind": "CAPACITOR", "package": "0805", "rotation_deg": 90.0},  # perpendicular
    }
    rep_ok = calculate_wave_solder_orientation_audit(modules_ok, flow_direction="X+")
    assert rep_ok.misoriented_count == 0
    assert rep_ok.is_fully_compliant is True


def test_wave_solder_orientation_soic_bridging():
    """Verify SOIC perpendicular to X+ flow triggers bridging risk; 0° parallel passes."""
    modules_bad = {
        "U1": {"kind": "IC", "package": "SOIC-8", "rotation_deg": 90.0},  # perpendicular to X+
    }
    rep_bad = calculate_wave_solder_orientation_audit(modules_bad, flow_direction="X+")
    assert rep_bad.misoriented_count == 1
    assert rep_bad.issues[0].issue_type == "PERPENDICULAR_SOIC_BRIDGING"

    modules_ok = {
        "U1": {"kind": "IC", "package": "SOIC-8", "rotation_deg": 0.0},
    }
    rep_ok = calculate_wave_solder_orientation_audit(modules_ok, flow_direction="X+")
    assert rep_ok.misoriented_count == 0


def test_wave_solder_shadowing():
    """Verify component in shadow zone behind tall component (H=4mm -> shadow=12mm) is flagged."""
    modules = {
        "T1": {"kind": "TRANSFORMER", "height_mm": 4.0, "position": [10.0, 20.0]},
        "C1": {"kind": "CAPACITOR", "package": "0603", "rotation_deg": 90.0, "position": [18.0, 20.0]},  # 8mm downwind <= 12mm
    }
    rep = calculate_wave_solder_orientation_audit(modules, flow_direction="X+")
    assert rep.shadowed_count == 1
    assert rep.issues[0].issue_type == "WAVE_SHADOW_DEFICIT"


def test_press_fit_hole_compliance_checks():
    """Verify finished hole tolerance 0.94~1.09mm and 25μm copper thickness."""
    # Compliant: drill 1.15, copper 25um -> finished = 1.10? Wait: 1.15 - 2*0.025 = 1.10 (max is 1.09)
    # Drill 1.10, copper 25um -> finished = 1.05mm (pass)
    pins = [
        {"pin_id": "P_OK", "connector_ref": "J1", "drill_dia_mm": 1.10, "copper_thickness_um": 25.0},
        {"pin_id": "P_TIGHT", "connector_ref": "J1", "finished_dia_mm": 0.90},  # < 0.94 (too small)
        {"pin_id": "P_LOOSE", "connector_ref": "J1", "finished_dia_mm": 1.15},  # > 1.09 (too large)
        {"pin_id": "P_THIN_CU", "connector_ref": "J1", "drill_dia_mm": 1.05, "copper_thickness_um": 15.0},  # < 25um
    ]
    rep = calculate_press_fit_hole_compliance(pins)
    assert rep.total_pins_audited == 4
    assert rep.compliant_pins_count == 1
    assert rep.violating_pins_count == 3
    assert rep.checks[0].is_compliant is True
    assert "过大" in rep.checks[1].violation_reason
    assert "不足" in rep.checks[2].violation_reason
    assert "孔壁铜厚" in rep.checks[3].violation_reason


def test_erc_rules_38_and_39():
    """Verify ERC rules 38 (wave orientation) and 39 (press fit hole tolerance)."""
    # Rule 38: bottom SMD 0603 parallel to X+ flow
    modules_38 = {
        "__meta__": {"wave_flow_direction": "X+"},
        "C_BOT": {"kind": "CAPACITOR", "package": "0603", "bottom_side": True, "rotation_deg": 0.0},
    }
    issues_38 = run_erc(modules_38, [{"net": "/GND", "points": ["C_BOT.1"]}])
    codes_38 = [i["code"] for i in issues_38]
    assert "BOTTOM_SMD_WAVE_ORIENTATION_MISALIGNED" in codes_38

    # Rule 39: press fit hole violation
    connections_39 = [
        {
            "net": "/PRESS_PIN1",
            "points": ["J1.1"],
            "properties": {"is_press_fit": True, "finished_dia_mm": 0.88},  # < 0.94mm
        }
    ]
    issues_39 = run_erc({}, connections_39)
    codes_39 = [i["code"] for i in issues_39]
    assert "PRESS_FIT_PTH_TOLERANCE_VIOLATION" in codes_39


def test_mcp_server_orientation_and_pressfit_tools():
    """Verify MCP server handles calculate_wave_solder_orientation_audit and calculate_press_fit_hole_compliance."""
    res_ori = handle_tool_call(
        "calculate_wave_solder_orientation_audit",
        {
            "modules": {
                "C1": {"kind": "CAPACITOR", "package": "0805", "rotation_deg": 90.0},
            },
            "flow_direction": "X+",
        },
    )
    assert not res_ori.get("isError")
    assert '"is_fully_compliant": true' in res_ori["content"][0]["text"]

    res_pf = handle_tool_call(
        "calculate_press_fit_hole_compliance",
        {
            "pins": [{"pin_id": "PIN_1", "finished_dia_mm": 1.02}],
        },
    )
    assert not res_pf.get("isError")
    assert '"is_all_compliant": true' in res_pf["content"][0]["text"]
