"""Tests for IPC-2581B fabrication data export, ERC rules 27-28, and MCP tool 41."""

import xml.etree.ElementTree as ET

from client.erc import run_erc
from client.ipc2581_exporter import export_ipc2581
from client.mcp_server import handle_tool_call

MAX_XML_BYTES = 1_000_000


def safe_parse_xml(xml_txt: str) -> ET.Element:
    """Parse trusted, self-generated IPC-2581 XML with DTD/entity hardening.

    ElementTree accepts internal DTD entity expansion on untrusted input; our exporter
    never emits a DOCTYPE, so we reject any DOCTYPE/ENTITY marker and oversize payloads
    before parsing (local defense-in-depth per secure-parsing guidance). The default
    xmlns is then stripped so assertions can use plain tag paths.
    """
    data = xml_txt.encode("utf-8")
    if len(data) > MAX_XML_BYTES:
        raise ValueError("XML payload exceeds size limit")
    head = data[:4096].decode("utf-8", errors="ignore")
    if "<!DOCTYPE" in head or "<!ENTITY" in xml_txt:
        raise ValueError("DTD declarations are not allowed in IPC-2581 handoff")
    root = ET.fromstring(xml_txt)
    for el in root.iter():
        if isinstance(el.tag, str) and el.tag.startswith("{"):
            el.tag = el.tag.split("}", 1)[1]
    return root


def _modules():
    return {
        "U1": {"kind": "MCU", "value": "ESP32-C3-WROOM-02", "package": "Module-ESP32-C3", "position": [30.0, 20.0]},
        "C1": {"kind": "CAPACITOR", "value": "100nF", "package": "0402", "position": [40.0, 20.0]},
    }


def test_ipc2581_wellformed_xml_and_structure():
    """Verify exported XML parses and contains Content/Step/Bom/Components/Nets/Profile."""
    xml_txt = export_ipc2581(
        modules=_modules(),
        connections=[{"net": "/GND", "points": ["U1.GND", "C1.2"]}],
        board_width_mm=60.0,
        board_height_mm=40.0,
        project_name="DEMO_2581",
    )
    root = safe_parse_xml(xml_txt)
    assert root.tag == "IPC-2581"
    assert root.get("revision") == "B"

    content = root.find("Content")
    assert content is not None
    step = content.find("Step")
    assert step is not None
    assert step.get("name") == "STEP_PCB"

    assert step.find("Stackup") is not None
    assert step.find("Profile") is not None


def test_ipc2581_bom_components_nets_content():
    """Verify BOM items, placed components, and net pin membership."""
    xml_txt = export_ipc2581(
        modules=_modules(),
        connections=[{"net": "/GND", "points": ["U1.GND", "C1.2"]}],
    )
    root = safe_parse_xml(xml_txt)
    step = root.find("Content/Step")

    items = step.findall("Bom/Item")
    assert {i.get("refDes") for i in items} == {"U1", "C1"}
    assert items[0].get("MPN") == "100nF" or items[1].get("MPN") == "100nF"

    comps = step.findall("CadData/Components/Component")
    assert len(comps) == 2
    u1 = next(c for c in comps if c.get("refDes") == "U1")
    assert u1.get("x") == "30.0"
    assert u1.get("y") == "20.0"

    nets = step.findall("CadData/Nets/Net")
    assert len(nets) == 1
    pins = nets[0].findall("Pin")
    assert {p.get("component") for p in pins} == {"U1", "C1"}


def test_ipc2581_xml_escaping():
    """Verify special characters in values are escaped and output stays well-formed."""
    xml_txt = export_ipc2581(
        modules={"X1": {"kind": "IC", "value": 'A&B"C'}},
        connections=[{"net": "/NET_X", "points": ["X1.P1"]}],
    )
    root = safe_parse_xml(xml_txt)  # must not raise
    item = root.find("Content/Step/Bom/Item")
    assert item.get("MPN") == 'A&B"C'


def test_erc_rules_27_and_28():
    """Verify ERC rules 27 (BGA escape unplanned) and 28 (NPTH plating conflict)."""
    # Rule 27
    modules = {"U1": {"kind": "IC", "package": "BGA-64", "escape_planned": False}}
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.GND"]}])
    codes = [i["code"] for i in issues]
    assert "BGA_ESCAPE_ROUTING_UNPLANNED" in codes

    # Planned BGA passes
    modules_ok = {"U1": {"kind": "IC", "package": "BGA-64", "escape_planned": True}}
    issues_ok = run_erc(modules_ok, [{"net": "/GND", "points": ["U1.GND"]}])
    assert "BGA_ESCAPE_ROUTING_UNPLANNED" not in [i["code"] for i in issues_ok]

    # Rule 28
    connections = [
        {"net": "/MOUNT_HOLE", "points": ["H1.1"], "properties": {"hole_type": "npth", "plated": True}},
    ]
    issues_28 = run_erc({}, connections)
    codes_28 = [i["code"] for i in issues_28]
    assert "NPTH_PLATING_CONFLICT" in codes_28


def test_mcp_server_ipc2581_tool():
    """Verify MCP server dispatches export_ipc2581 (tool 41)."""
    res = handle_tool_call(
        "export_ipc2581",
        {
            "modules": _modules(),
            "connections": [{"net": "/3V3", "points": ["U1.VCC", "C1.1"]}],
            "board_width_mm": 60.0,
            "board_height_mm": 40.0,
            "project_name": "MCP_2581",
        },
    )
    assert not res.get("isError")
    xml_txt = res["content"][0]["text"]
    root = safe_parse_xml(xml_txt)
    assert root.tag == "IPC-2581"
    assert root.find("Content/Step/Bom") is not None
