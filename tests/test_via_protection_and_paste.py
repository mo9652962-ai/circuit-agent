"""Tests for IPC-4761 via protection, IPC-7525A paste volume, and ERC rules 25-26."""

import json

from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.solder_paste_volume import calculate_solder_paste_volume
from client.via_protection import calculate_via_protection_plan


def test_via_protection_bga_in_pad_requires_type_vii():
    """Verify via-in-pad on BGA land requires Type VII (VIPPO) and flags wicking when unfilled."""
    rep = calculate_via_protection_plan(
        vias=[
            {"id": "V1", "in_pad": True, "land_type": "bga", "vippo_filled": False},
            {"id": "V2", "in_pad": True, "land_type": "bga", "vippo_filled": True},
        ]
    )
    p1, p2 = rep.plans
    assert p1.recommended_type == "VII"
    assert p1.solder_wicking_risk == "HIGH"
    assert p2.solder_wicking_risk == "NONE"
    assert rep.wicking_risk_count == 1
    assert rep.type_distribution == {"VII": 2}


def test_via_protection_thermal_and_free():
    """Verify thermal pad -> Type V fill and free via -> Type II tent."""
    rep = calculate_via_protection_plan(
        vias=[
            {"id": "VT", "in_pad": True, "land_type": "thermal"},
            {"id": "VF", "in_pad": False, "in_bga_pitch": False},
            {"id": "VC", "in_pad": False, "in_bga_pitch": True},
        ]
    )
    assert rep.plans[0].recommended_type == "V"
    assert rep.plans[1].recommended_type == "II"
    assert rep.plans[2].recommended_type == "IV"


def test_solder_paste_volume_compliant_window():
    """Verify paste volume ratio = t*eta/standoff within [1.0, 2.5] window."""
    rep = calculate_solder_paste_volume(
        apertures=[{"ref": "C1", "shape": "rect", "width_mm": 0.5, "length_mm": 0.25}],
        foil_thickness_um=100.0,
        transfer_efficiency=0.90,
        target_standoff_mm=0.10,
    )
    c = rep.checks[0]
    # ratio = 0.1*0.9/0.10 = 0.9 -> starved (deficient)
    assert c.volume_ratio == 0.9
    assert c.is_compliant is False
    assert rep.deficient_count == 1


def test_solder_paste_volume_excessive():
    """Verify thick foil yields excessive paste flag."""
    rep = calculate_solder_paste_volume(
        apertures=[{"ref": "R1", "shape": "rect", "width_mm": 1.0, "length_mm": 0.6}],
        foil_thickness_um=150.0,
        transfer_efficiency=0.95,
        target_standoff_mm=0.05,  # ratio = 0.15*0.95/0.05 = 2.85 > 2.5
    )
    assert rep.excessive_count == 1
    assert rep.checks[0].is_compliant is False


def test_erc_rules_25_and_26():
    """Verify ERC rules 25 (via-in-pad wicking) and 26 (polarity marking)."""
    # Rule 25
    connections = [
        {"net": "/BGA_A1", "points": ["U1.A1"], "properties": {"has_vias_in_pad": True, "vippo_filled_capped": False}},
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "VIA_IN_PAD_SOLDER_WICKING_RISK" in codes

    # Rule 26: polarized LED without silk marking
    modules = {"D1": {"kind": "LED", "silk_marked": False}, "R1": {"kind": "RESISTOR"}}
    issues_26 = run_erc(modules, [{"net": "/GND", "points": ["R1.1"]}])
    codes_26 = [i["code"] for i in issues_26]
    assert "POLARIZED_MARKING_MISSING" in codes_26

    # Marked LED passes
    modules_ok = {"D1": {"kind": "LED", "silk_marked": True}}
    issues_ok = run_erc(modules_ok, [{"net": "/GND", "points": ["R1.1"]}])
    assert "POLARIZED_MARKING_MISSING" not in [i["code"] for i in issues_ok]


def test_mcp_server_via_protection_and_paste_tools():
    """Verify MCP server handles calculate_via_protection_plan and calculate_solder_paste_volume."""
    res_vp = handle_tool_call(
        "calculate_via_protection_plan",
        {"vias": [{"id": "V1", "in_pad": True, "land_type": "bga"}]},
    )
    assert not res_vp.get("isError")
    data_vp = json.loads(res_vp["content"][0]["text"])
    assert data_vp["total_vias"] == 1
    assert data_vp["plans"][0]["recommended_type"] == "VII"

    res_pv = handle_tool_call(
        "calculate_solder_paste_volume",
        {"apertures": [{"ref": "C1", "shape": "rect", "width_mm": 0.5, "length_mm": 0.25}]},
    )
    assert not res_pv.get("isError")
    data_pv = json.loads(res_pv["content"][0]["text"])
    assert "volume_ratio" in data_pv["checks"][0]
