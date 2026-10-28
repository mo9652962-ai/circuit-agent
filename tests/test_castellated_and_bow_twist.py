"""Tests for IPC-A-600J castellated pads solver, IPC-TM-650 bow & twist analyzer, and ERC rules 58-59."""

from client.bow_and_twist import calculate_pcb_bow_and_twist
from client.castellated_pads import calculate_castellated_pad_geometry
from client.erc import run_erc
from client.mcp_server import handle_tool_call


def test_castellated_pad_geometry_compliant():
    """Verify standard 1.0mm castellated hole with 0.8mm pad extension is manufacturable."""
    res = calculate_castellated_pad_geometry(
        hole_drill_diameter_mm=1.00,
        center_to_edge_offset_mm=0.00,
        pad_inward_length_mm=0.80,
        pad_pitch_mm=2.00,
        copper_plating_thickness_um=25.0,
    )
    assert res.is_manufacturable is True
    assert res.is_pitch_compliant is True
    assert res.is_plating_compliant is True
    assert res.tearout_risk_level == "low"
    assert res.burr_risk_level == "low"
    assert res.estimated_solder_joint_shear_strength_n > 50.0
    assert len(res.violations) == 0


def test_castellated_pad_small_drill_and_offcenter():
    """Verify small drill (<0.8mm) and severe cutter offset flag high tearout & burr risks."""
    res = calculate_castellated_pad_geometry(
        hole_drill_diameter_mm=0.60,  # below 0.80mm minimum
        center_to_edge_offset_mm=0.08,  # > 0.05mm max offset
        pad_inward_length_mm=0.35,  # < 0.50mm minimum
        pad_pitch_mm=1.00,  # < 1.27mm minimum
        copper_plating_thickness_um=15.0,  # < 20μm minimum
    )
    assert res.is_manufacturable is False
    assert res.tearout_risk_level == "high"
    assert res.burr_risk_level == "high"
    assert len(res.violations) >= 4
    assert any("router bit deflection" in v.lower() for v in res.violations)


def test_bow_and_twist_balanced_smt_passes():
    """Verify symmetric stackup and balanced copper meets IPC-6012E 0.75% SMT limit."""
    res = calculate_pcb_bow_and_twist(
        board_length_mm=100.0,
        board_width_mm=80.0,
        board_thickness_mm=1.60,
        has_smt_components=True,
        copper_balance_ratio_top_bottom=1.0,
        dielectric_asymmetry_pct=0.0,
    )
    assert res.is_compliant is True
    assert res.calculated_bow_pct <= 0.75
    assert res.calculated_twist_pct <= 0.75
    assert res.bga_head_in_pillow_risk is False
    assert len(res.recommendations) >= 1


def test_bow_and_twist_severe_imbalance_flags_hip():
    """Verify heavy copper imbalance on 0.8mm thin PCB flags BGA Head-in-Pillow risk."""
    res = calculate_pcb_bow_and_twist(
        board_length_mm=120.0,
        board_width_mm=80.0,
        board_thickness_mm=0.80,  # thin board
        has_smt_components=True,
        copper_balance_ratio_top_bottom=2.2,  # 120% copper volume imbalance
        dielectric_asymmetry_pct=30.0,
    )
    assert res.is_compliant is False
    assert res.calculated_bow_pct > 0.75
    assert res.bga_head_in_pillow_risk is True
    assert any("Head-in-Pillow" in r or "thieving" in r for r in res.recommendations)


def test_erc_rule_58_castellated_violation():
    """Verify ERC rule 58 fires when a castellated net has small drill or insufficient pad."""
    connections = [
        {
            "net": "/MOD_GPIO0",
            "points": ["U1.1"],
            "properties": {
                "is_castellated": True,
                "castellated_drill_mm": 0.65,
                "pad_inward_length_mm": 0.30,
            },
        }
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "CASTELLATED_HOLE_FAB_VIOLATION" in codes


def test_erc_rule_59_warpage_risk():
    """Verify ERC rule 59 fires when metadata stackup imbalance triggers warpage >0.75%."""
    modules = {
        "__meta__": {
            "has_smt_components": True,
            "board_thickness_mm": 0.8,
            "copper_balance_ratio": 2.5,
            "dielectric_asymmetry_pct": 35.0,
        },
        "U1": {"package": "BGA-256"},
    }
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.1"]}])
    codes = [i["code"] for i in issues]
    assert "STACKUP_ASYMMETRY_WARPAGE_RISK" in codes


def test_mcp_server_castellated_and_bow_twist_tools():
    """Verify MCP server dispatches calculate_castellated_pad_geometry and calculate_pcb_bow_and_twist."""
    res_cas = handle_tool_call(
        "calculate_castellated_pad_geometry",
        {"hole_drill_diameter_mm": 1.0, "pad_inward_length_mm": 0.8},
    )
    assert not res_cas.get("isError")
    assert '"is_manufacturable": true' in res_cas["content"][0]["text"]

    res_warp = handle_tool_call(
        "calculate_pcb_bow_and_twist",
        {"board_thickness_mm": 1.6, "copper_balance_ratio_top_bottom": 1.0},
    )
    assert not res_warp.get("isError")
    assert '"is_compliant": true' in res_warp["content"][0]["text"]
