"""Tests for QFN/BTC thermal pad window-pane stencil solver, SMT tombstone risk auditor, and ERC rules 56-57."""

from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.qfn_thermal_pad import calculate_qfn_thermal_pad_stencil
from client.tombstone_analyzer import audit_smt_tombstone_risk


def test_qfn_thermal_pad_stencil_standard():
    """Verify 4.5x4.5mm QFN slug plans a 3x3 window pane grid with 50~70% paste coverage."""
    res = calculate_qfn_thermal_pad_stencil(
        pad_width_mm=4.5,
        pad_height_mm=4.5,
        target_coverage_pct=60.0,
        web_width_mm=0.20,
    )
    assert res.grid_cols == 3 and res.grid_rows == 3
    assert res.total_windows_count == 9
    assert 50.0 <= res.paste_coverage_pct <= 70.0
    assert res.is_coverage_compliant is True
    assert res.estimated_voiding_pct < 20.0
    assert len(res.windows) == 9
    assert len(res.recommendations) >= 1


def test_qfn_thermal_pad_unfilled_vias_flags_violation():
    """Verify open unfilled vias in thermal pad trigger outgassing / wicking warning."""
    res = calculate_qfn_thermal_pad_stencil(
        pad_width_mm=5.0,
        pad_height_mm=5.0,
        has_unfilled_thermal_vias=True,
    )
    assert res.is_coverage_compliant is False
    assert res.estimated_voiding_pct >= 25.0
    assert any("Type VII" in r or "VIPPO" in r for r in res.recommendations)


def test_tombstone_balanced_passives():
    """Verify symmetric trace connections on 0402 passives report low tombstone risk."""
    components = [
        {"ref": "C1", "package": "0402", "pad1_type": "trace", "pad2_type": "trace", "pad1_width_mm": 0.20, "pad2_width_mm": 0.20},
        {"ref": "R1", "package": "0603", "pad1_type": "trace", "pad2_type": "trace", "pad1_width_mm": 0.25, "pad2_width_mm": 0.25},
    ]
    rep = audit_smt_tombstone_risk(components)
    assert rep.is_assembly_safe is True
    assert rep.high_risk_count == 0
    assert rep.moderate_risk_count == 0


def test_tombstone_solid_plane_imbalance_high_risk():
    """Verify 0402 with one pad tied directly to solid plane flags high tombstoning risk."""
    components = [
        {"ref": "C2", "package": "0402", "pad1_type": "trace", "pad2_type": "solid_plane", "pad1_width_mm": 0.20, "pad2_width_mm": 2.50},
    ]
    rep = audit_smt_tombstone_risk(components)
    assert rep.is_assembly_safe is False
    assert rep.high_risk_count == 1
    assert len(rep.at_risk_components) == 1
    c2_risk = rep.at_risk_components[0]
    assert c2_risk.risk_level == "high"
    assert c2_risk.thermal_imbalance_ratio >= 3.5
    assert "thermal relief" in c2_risk.recommendation.lower()


def test_erc_rule_56_qfn_solid_paste_voiding():
    """Verify ERC rule 56 fires when QFN thermal pad uses solid paste or has open vias."""
    modules = {
        "U1": {
            "package": "QFN-32",
            "has_exposed_thermal_slug": True,
            "solid_thermal_paste": True,
        }
    }
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.EP"]}])
    codes = [i["code"] for i in issues]
    assert "QFN_THERMAL_PAD_SOLID_PASTE_VOIDING_RISK" in codes


def test_erc_rule_57_tombstone_risk():
    """Verify ERC rule 57 fires on 0402/0603 passives with one-sided solid plane connections."""
    modules = {
        "C10": {
            "package": "0402",
            "pad1_connection_type": "trace",
            "pad2_connection_type": "solid_plane",
        }
    }
    issues = run_erc(modules, [{"net": "/VBUS", "points": ["C10.1"]}])
    codes = [i["code"] for i in issues]
    assert "SMT_PAD_THERMAL_IMBALANCE_TOMBSTONE_RISK" in codes


def test_mcp_server_qfn_and_tombstone_tools():
    """Verify MCP server dispatches calculate_qfn_thermal_pad_stencil and audit_smt_tombstone_risk."""
    res_qfn = handle_tool_call("calculate_qfn_thermal_pad_stencil", {"pad_width_mm": 4.0, "pad_height_mm": 4.0})
    assert not res_qfn.get("isError")
    assert '"is_coverage_compliant": true' in res_qfn["content"][0]["text"]

    res_tomb = handle_tool_call("audit_smt_tombstone_risk", {"components": [{"ref": "C1", "package": "0603"}]})
    assert not res_tomb.get("isError")
    assert '"is_assembly_safe": true' in res_tomb["content"][0]["text"]
