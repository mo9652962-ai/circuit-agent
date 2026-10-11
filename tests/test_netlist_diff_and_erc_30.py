"""Tests for ECO netlist diff, ERC rule 30, and MCP tool 43."""

from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.netlist_diff import diff_netlists


def _rev_a():
    modules = {
        "U1": {"kind": "MCU", "value": "ESP32-C3", "package": "Module-ESP32-C3"},
        "R1": {"kind": "RESISTOR", "value": "10k", "package": "0402"},
        "C1": {"kind": "CAPACITOR", "value": "100nF", "package": "0402"},
    }
    connections = [
        {"net": "/GND", "points": ["U1.GND", "C1.2"]},
        {"net": "/3V3", "points": ["U1.VCC", "C1.1"]},
        {"net": "/SDA", "points": ["U1.IO9", "R1.1"]},
    ]
    return modules, connections


def _rev_b():
    modules = {
        "U1": {"kind": "MCU", "value": "ESP32-C3", "package": "Module-ESP32-C3"},
        "R1": {"kind": "RESISTOR", "value": "4.7k", "package": "0402"},  # value changed
        "C1": {"kind": "CAPACITOR", "value": "100nF", "package": "0402"},
        "C2": {"kind": "CAPACITOR", "value": "10uF", "package": "0805"},  # added
    }
    connections = [
        {"net": "/GND", "points": ["U1.GND", "C1.2", "C2.2"]},  # pin added
        {"net": "/3V3", "points": ["U1.VCC", "C1.1"]},
        # /SDA removed
        {"net": "/SCL", "points": ["U1.IO8", "R1.1"]},  # new net
    ]
    return modules, connections


def test_diff_netlists_full_eco():
    """Verify component/net/pin level ECO changes and MAJOR severity."""
    rep = diff_netlists(*_rev_a(), *_rev_b())

    assert rep.added_components == ["C2"]
    assert rep.removed_components == []
    assert len(rep.changed_components) == 1
    ch = rep.changed_components[0]
    assert (ch.ref, ch.field, ch.old, ch.new) == ("R1", "value", "10k", "4.7k")

    assert rep.added_nets == ["/SCL"]
    assert rep.removed_nets == ["/SDA"]
    assert len(rep.changed_nets) == 1
    assert rep.changed_nets[0].net == "/GND"
    assert rep.changed_nets[0].added_pins == ["C2.2"]

    assert rep.eco_severity == "MAJOR"
    assert rep.total_changes == 5


def test_diff_netlists_minor_and_none():
    """Verify MINOR for value-only change and NONE for identical netlists."""
    old_m, old_c = _rev_a()
    new_m = {"U1": old_m["U1"], "R1": {"kind": "RESISTOR", "value": "22k", "package": "0402"}, "C1": old_m["C1"]}
    rep_minor = diff_netlists(old_m, old_c, new_m, old_c)
    assert rep_minor.eco_severity == "MINOR"

    rep_none = diff_netlists(old_m, old_c, old_m, old_c)
    assert rep_none.eco_severity == "NONE"
    assert rep_none.total_changes == 0


def test_erc_rule_30_mounting_holes_missing():
    """Verify ERC rule 30 (MOUNTING_HOLES_MISSING)."""
    modules = {f"U{i}": {"kind": "IC", "value": f"CHIP{i}"} for i in range(1, 9)}  # 8 ICs
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.GND"]}])
    codes = [i["code"] for i in issues]
    assert "MOUNTING_HOLES_MISSING" in codes

    modules_ok = dict(modules)
    modules_ok["H1"] = {"kind": "MOUNT_HOLE", "value": "M3"}
    issues_ok = run_erc(modules_ok, [{"net": "/GND", "points": ["U1.GND"]}])
    assert "MOUNTING_HOLES_MISSING" not in [i["code"] for i in issues_ok]


def test_mcp_server_diff_netlists_tool():
    """Verify MCP server dispatches diff_netlists (tool 43)."""
    res = handle_tool_call(
        "diff_netlists",
        {
            "old_modules": _rev_a()[0],
            "old_connections": _rev_a()[1],
            "new_modules": _rev_b()[0],
            "new_connections": _rev_b()[1],
        },
    )
    assert not res.get("isError")
    data = res["content"][0]["text"]
    assert '"eco_severity": "MAJOR"' in data
