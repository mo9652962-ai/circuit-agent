"""Tests for IPC-6012E Class 1/2/3 auditor, SMT feeder trolley optimizer, and ERC rules 42-43."""

from client.erc import run_erc
from client.ipc6012_auditor import audit_ipc6012_class_compliance
from client.mcp_server import handle_tool_call
from client.smt_feeder_optimizer import optimize_smt_feeder_setup


def test_audit_ipc6012_class2_standard_pass():
    """Verify standard industrial board parameters pass Class 2 requirements."""
    rep = audit_ipc6012_class_compliance(
        target_class="Class 2",
        external_annular_ring_mm=0.100,
        internal_annular_ring_mm=0.075,
        avg_copper_barrel_um=22.0,
        min_copper_barrel_um=19.0,
        min_solder_mask_dam_mm=0.080,
    )
    assert rep.is_compliant is True
    assert rep.violations_count == 0


def test_audit_ipc6012_class3_strict_breakout_and_copper():
    """Verify Class 3 strictly forbids hole breakout and requires avg copper >= 25um."""
    rep = audit_ipc6012_class_compliance(
        target_class="Class 3",
        external_annular_ring_mm=0.040,  # below 0.050mm (2 mil)
        has_hole_breakout=True,  # strictly forbidden in Class 3!
        avg_copper_barrel_um=21.0,  # below 25um
    )
    assert rep.is_compliant is False
    assert rep.violations_count >= 3
    crit_list = [v.criterion for v in rep.violations]
    assert "hole_breakout_forbidden" in crit_list
    assert "external_annular_ring" in crit_list
    assert "copper_barrel_avg_thickness" in crit_list


def test_optimize_smt_feeder_setup_group_technology():
    """Verify SMT feeder optimizer allocates common parts and calculates slot spans."""
    modules = {
        "C1": {"package": "0402", "value": "100nF", "part_number": "C0402_100NF"},
        "C2": {"package": "0402", "value": "100nF", "part_number": "C0402_100NF"},
        "C3": {"package": "0402", "value": "100nF", "part_number": "C0402_100NF"},
        "R1": {"package": "0402", "value": "10k", "part_number": "R0402_10K"},
        "U1": {"package": "SOIC-8", "value": "RS485", "part_number": "MAX485"},
        "U2": {"package": "QFN-32", "value": "MCU", "part_number": "ESP32-C3"},
    }
    plan = optimize_smt_feeder_setup(modules, feeder_cart_capacity=80, batch_size=500)

    assert plan.total_feeder_slots_capacity == 80
    assert plan.slots_occupied >= 6
    assert plan.unique_reels_count == 4
    assert plan.common_feeder_block_count >= 2  # 100nF and 10k are common
    assert plan.estimated_changeover_time_saved_min >= 4.0
    # SOIC-8 uses 16mm tape (2 slots), QFN uses 24mm tape (3 slots)
    tape_widths = {s.part_number: s.tape_width for s in plan.feeder_slots}
    assert tape_widths["MAX485"] == "16mm"
    assert tape_widths["ESP32-C3"] == "24mm"


def test_erc_rule_42_class3_breakout():
    """Verify ERC rule 42 (CLASS3_ANNULAR_RING_BREAKOUT_FORBIDDEN)."""
    modules = {"__meta__": {"ipc_class": "Class 3"}}
    connections = [
        {
            "net": "/CRITICAL_SIG",
            "points": ["U1.1"],
            "properties": {"annular_ring_mm": 0.030, "hole_breakout": True},
        }
    ]
    issues = run_erc(modules, connections)
    codes = [i["code"] for i in issues]
    assert "CLASS3_ANNULAR_RING_BREAKOUT_FORBIDDEN" in codes


def test_erc_rule_43_smt_feeder_capacity_exceeded():
    """Verify ERC rule 43 triggers warning when cart capacity is exceeded."""
    # Create 10 large QFN ICs (each 3 slots = 30 slots) on a tiny 20-slot cart
    modules = {
        f"U{i}": {"package": "QFN", "value": f"IC_{i}", "part_number": f"CHIP_{i}"}
        for i in range(10)
    }
    modules["__meta__"] = {"feeder_cart_capacity": 20}
    issues = run_erc(modules, [{"net": "/GND", "points": ["U0.1"]}])
    codes = [i["code"] for i in issues]
    assert "SMT_FEEDER_CAPACITY_EXCEEDED" in codes


def test_mcp_server_ipc6012_and_smt_feeder_tools():
    """Verify MCP server handles audit_ipc6012_class_compliance and optimize_smt_feeder_setup."""
    res_6012 = handle_tool_call(
        "audit_ipc6012_class_compliance",
        {"target_class": "Class 2", "external_annular_ring_mm": 0.125},
    )
    assert not res_6012.get("isError")
    assert '"is_compliant": true' in res_6012["content"][0]["text"]

    res_smt = handle_tool_call(
        "optimize_smt_feeder_setup",
        {
            "modules": {
                "C1": {"package": "0402", "value": "100nF"},
                "R1": {"package": "0402", "value": "10k"},
            }
        },
    )
    assert not res_smt.get("isError")
    assert '"slots_occupied": 2' in res_smt["content"][0]["text"]
