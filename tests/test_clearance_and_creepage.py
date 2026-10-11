"""Tests for SMT nozzle clearance, creepage isolation slot, ERC rules 34-35, and MCP tools 47-48."""

from client.creepage_slot import calculate_creepage_isolation_slot, get_required_creepage
from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.smt_placement_clearance import calculate_smt_placement_clearance


def test_smt_placement_clearance_nozzle_risk():
    """Verify tall component next to low component within 2.0mm flags collision risk."""
    modules = {
        "C1": {"kind": "CAPACITOR", "package": "0402", "position": [10.0, 10.0]},  # H=0.5mm
        "C2": {"kind": "CAPACITOR", "package": "ELECTROLYTIC-D8", "position": [11.0, 10.5]},  # H=10.5mm, dist ≈ 1.12mm
        "R1": {"kind": "RESISTOR", "package": "0603", "position": [40.0, 30.0]},  # far away
    }
    rep = calculate_smt_placement_clearance(modules)
    assert rep.collision_risks_count >= 1
    assert rep.tall_components_count == 1
    assert rep.low_components_count == 2
    # Layer 0 must have low components, last layer must have tall component
    assert "C1" in rep.placement_priority_layers[0]
    assert "C2" in rep.placement_priority_layers[-1]


def test_creepage_slot_mains_voltage():
    """Verify 220V with 1.5mm distance plans an isolation slot to achieve >= 2.5mm creepage."""
    req = get_required_creepage(220.0)
    assert req >= 1.25

    # 500V requires 2.5mm creepage. Direct distance between conductors:
    # Cond1 at (10, 20), Cond2 at (12, 20), radius 0.5 -> center dist = 2.0mm, direct dist = 1.0mm < 2.5mm
    res = calculate_creepage_isolation_slot(
        voltage_v=500.0,
        cond1_coords=(10.0, 20.0),
        cond2_coords=(12.0, 20.0),
        conductor_radius_mm=0.5,
        slot_width_mm=1.2,
        slot_extension_mm=2.5,
    )
    assert res.is_slot_required is True
    assert res.required_creepage_mm == 2.5
    assert res.direct_surface_dist_mm == 1.0
    assert res.slot_length_mm == 6.0  # 2*(0.5 + 2.5) = 6.0mm
    # With slot, effective path around slot perimeter >= 2.5mm
    assert res.effective_creepage_with_slot_mm >= 2.5
    assert res.is_compliant is True


def test_erc_rules_34_and_35():
    """Verify ERC rules 34 (SMT collision) and 35 (creepage violation without slot)."""
    # Rule 34: collision risk
    modules = {
        "C_LOW": {"kind": "CAPACITOR", "package": "0402", "position": [10.0, 10.0]},
        "T_HIGH": {"kind": "TRANSFORMER", "package": "TRANSFORMER", "position": [11.0, 10.5]},
    }
    issues_34 = run_erc(modules, [{"net": "/GND", "points": ["C_LOW.1"]}])
    codes_34 = [i["code"] for i in issues_34]
    assert "TALL_COMPONENT_SMT_COLLISION_RISK" in codes_34

    # Rule 35: high voltage without slot
    connections = [
        {
            "net": "/AC_MAINS_220V",
            "points": ["J1.1"],
            "properties": {"voltage_v": 250.0, "clearance_mm": 1.0, "has_isolation_slot": False},
        }
    ]
    issues_35 = run_erc({}, connections)
    codes_35 = [i["code"] for i in issues_35]
    assert "CREEPAGE_DISTANCE_VIOLATION_WITHOUT_SLOT" in codes_35

    # With slot passes
    connections[0]["properties"]["has_isolation_slot"] = True
    issues_ok = run_erc({}, connections)
    assert "CREEPAGE_DISTANCE_VIOLATION_WITHOUT_SLOT" not in [i["code"] for i in issues_ok]


def test_mcp_server_clearance_and_creepage_tools():
    """Verify MCP server handles calculate_smt_placement_clearance and calculate_creepage_isolation_slot."""
    # 1. SMT placement clearance
    res_clr = handle_tool_call(
        "calculate_smt_placement_clearance",
        {
            "modules": {
                "R1": {"kind": "RESISTOR", "package": "0402", "position": [10.0, 10.0]},
                "L1": {"kind": "INDUCTOR", "package": "0805", "position": [20.0, 20.0]},
            }
        },
    )
    assert not res_clr.get("isError")
    assert '"placement_priority_layers"' in res_clr["content"][0]["text"]

    # 2. Creepage isolation slot
    res_slot = handle_tool_call(
        "calculate_creepage_isolation_slot",
        {
            "voltage_v": 220.0,
            "cond1_coords": [10.0, 10.0],
            "cond2_coords": [13.0, 10.0],
        },
    )
    assert not res_slot.get("isError")
    assert '"effective_creepage_with_slot_mm"' in res_slot["content"][0]["text"]
