"""Tests for assembly process route planner, ERC rule 31, and MCP tool 44."""

from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.process_planner import generate_assembly_process_plan


def _modules():
    return {
        "U1": {"kind": "MCU", "value": "ESP32-C3", "package": "Module-ESP32-C3"},
        "R1": {"kind": "RESISTOR", "value": "10k", "package": "0402"},
        "J1": {"kind": "CONNECTOR", "value": "Terminal-5.0", "package": "TerminalBlock-5.0mm"},
        "U2": {"kind": "REGULATOR", "value": "LM7805", "package": "TO-220"},
        "C1": {"kind": "CAPACITOR", "value": "470uF ELECTROLYTIC", "package": "Radial-D8"},
        "H1": {"kind": "MOUNT_HOLE", "value": "M3", "package": "MOUNT-HOLE-3.2"},
    }


def test_process_plan_classification():
    """Verify SMD / THT wave / THT manual / mechanical classification."""
    rep = generate_assembly_process_plan(_modules())
    assert rep.total_components == 6
    assert rep.smd_count == 2  # U1 module, R1 0402
    assert rep.tht_wave_count == 2  # Terminal + TO-220
    assert rep.tht_manual_count == 1  # Radial electrolytic
    assert rep.mechanical_count == 1  # M3 hole
    assert rep.is_mixed_assembly is True

    routes = {r.ref: r for r in rep.routes}
    assert routes["U1"].process == "SMD_REFLOW"
    assert routes["U2"].process == "THT_WAVE"
    assert routes["C1"].process == "THT_MANUAL"
    assert routes["H1"].process == "MECHANICAL"


def test_process_plan_stages():
    """Verify the 10-stage EMS routing order is present."""
    rep = generate_assembly_process_plan(_modules())
    assert rep.stages[0].startswith("SPI")
    assert any("Reflow" in s for s in rep.stages)
    assert any("ICT" in s for s in rep.stages)
    assert rep.stages[-1].startswith("Packing")


def test_erc_rule_31_tht_wave_unsuitable():
    """Verify ERC rule 31 (THT_WAVE_SOLDERING_UNSUITABLE)."""
    modules = {"K1": {"kind": "RELAY", "package": "RELAY-THT", "wave_solderable": False}}
    issues = run_erc(modules, [{"net": "/GND", "points": ["K1.1"]}])
    codes = [i["code"] for i in issues]
    assert "THT_WAVE_SOLDERING_UNSUITABLE" in codes

    modules_ok = {"K1": {"kind": "RELAY", "package": "RELAY-THT", "wave_solderable": True}}
    issues_ok = run_erc(modules_ok, [{"net": "/GND", "points": ["K1.1"]}])
    assert "THT_WAVE_SOLDERING_UNSUITABLE" not in [i["code"] for i in issues_ok]


def test_mcp_server_process_plan_tool():
    """Verify MCP server dispatches generate_assembly_process_plan (tool 44)."""
    res = handle_tool_call("generate_assembly_process_plan", {"modules": _modules()})
    assert not res.get("isError")
    text = res["content"][0]["text"]
    assert '"is_mixed_assembly": true' in text
    assert '"tht_wave_count": 2' in text
