"""Tests for IPC-CH-65 ionic contamination analyzer, ENIG black-pad auditor, and ERC rules 48-49."""

from client.enig_plating_analyzer import analyze_enig_plating
from client.erc import run_erc
from client.ionic_contamination import analyze_ionic_contamination
from client.mcp_server import handle_tool_call


def test_ionic_contamination_compliant():
    """Verify a clean board at 0.8 μg/cm² passes bulk ROSE with low dendrite risk."""
    res = analyze_ionic_contamination(
        rose_measured_ug_cm2=0.80,
        target_class="Class 2",
        species_ug_cm2={"chloride": 0.20, "bromide": 0.10},
    )
    assert res.is_rose_compliant is True
    assert res.dendrite_risk_level == "low"
    assert res.species_violations == []
    assert "compliant" in res.cleaning_recommendation


def test_ionic_contamination_exceedance_and_species_violation():
    """Verify ROSE exceedance plus chloride carryover flags high risk."""
    res = analyze_ionic_contamination(
        rose_measured_ug_cm2=2.10,  # > 1.56 limit
        target_class="Class 2",
        species_ug_cm2={"chloride": 0.95, "bromide": 0.30},  # Cl over 0.70
        bias_voltage_v=48.0,
        min_conductor_gap_mm=0.10,
    )
    assert res.is_rose_compliant is False
    assert res.dendrite_risk_level == "high"
    assert any(v[0] == "chloride" for v in res.species_violations)
    assert "Re-clean" in res.cleaning_recommendation


def test_ionic_contamination_class3_tighter_limit():
    """Verify Class 3 uses the tightened 1.20 μg/cm² internal limit."""
    res = analyze_ionic_contamination(rose_measured_ug_cm2=1.30, target_class="Class 3")
    assert res.rose_limit_ug_cm2 == 1.20
    assert res.is_rose_compliant is False


def test_enig_plating_healthy():
    """Verify in-window ENIG stack reports low black-pad risk."""
    res = analyze_enig_plating(
        finish_type="enig",
        gold_thickness_um=0.08,
        nickel_thickness_um=4.0,
        phosphorus_wt_pct=8.5,
    )
    assert res.violations == []
    assert res.black_pad_risk == "low"
    assert res.gold_embrittlement_risk is False


def test_enig_plating_black_pad_high_risk():
    """Verify high-P + over-thick gold + rework escalation reaches high risk."""
    res = analyze_enig_plating(
        finish_type="enig",
        gold_thickness_um=0.30,  # > 0.20 window and > 0.25 embrittlement
        nickel_thickness_um=3.5,
        phosphorus_wt_pct=11.5,  # > 10 wt%
        rework_cycles=2,
        soldering_process="wave",
    )
    assert res.gold_embrittlement_risk is True
    assert res.black_pad_risk == "high"
    layers = {v.layer for v in res.violations}
    assert "gold" in layers and "phosphorus" in layers


def test_enepig_palladium_barrier_suppresses_risk():
    """Verify an in-spec palladium barrier downgrades black-pad risk on ENEPIG."""
    res = analyze_enig_plating(
        finish_type="enepig",
        gold_thickness_um=0.08,
        nickel_thickness_um=4.0,
        phosphorus_wt_pct=8.5,
        palladium_thickness_um=0.20,
    )
    assert res.violations == []
    assert res.black_pad_risk == "low"
    assert res.wire_bondable is True


def test_erc_rule_48_ionic_contamination():
    """Verify ERC rule 48 fires on ROSE exceedance metadata."""
    modules = {
        "__meta__": {
            "rose_ionic_ug_cm2": 1.90,
            "max_bias_voltage_v": 48.0,
            "min_conductor_gap_mm": 0.15,
        },
        "U1": {"package": "QFN", "value": "MCU"},
    }
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.1"]}])
    codes = [i["code"] for i in issues]
    assert "IONIC_CONTAMINATION_EXCEEDANCE" in codes


def test_erc_rule_49_black_pad():
    """Verify ERC rule 49 fires on out-of-control ENIG plating metadata."""
    modules = {
        "__meta__": {
            "surface_finish": "ENIG",
            "gold_thickness_um": 0.32,
            "nickel_thickness_um": 3.5,
            "phosphorus_wt_pct": 11.5,
            "rework_cycles": 2,
        },
        "U1": {"package": "QFN", "value": "MCU"},
    }
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.1"]}])
    codes = [i["code"] for i in issues]
    assert "BLACK_PAD_NICKEL_CORROSION_RISK" in codes


def test_mcp_server_ionic_and_enig_tools():
    """Verify MCP server dispatches both new tools."""
    res_ion = handle_tool_call(
        "analyze_ionic_contamination",
        {"rose_measured_ug_cm2": 0.80},
    )
    assert not res_ion.get("isError")
    assert '"is_rose_compliant": true' in res_ion["content"][0]["text"]

    res_pl = handle_tool_call(
        "analyze_enig_plating",
        {"finish_type": "enepig", "palladium_thickness_um": 0.20},
    )
    assert not res_pl.get("isError")
    assert '"black_pad_risk": "low"' in res_pl["content"][0]["text"]
