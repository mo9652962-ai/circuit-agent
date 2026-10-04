"""Tests for KiCad 8/9 S-Expression schematic export and supply chain multi-sourcing auditor."""

from client.kicad_schematic import generate_kicad_schematic
from client.supply_chain_auditor import audit_supply_chain
from client.synthesizer import synthesize_from_prompt


def test_generate_kicad_schematic_s_expression():
    """Verify generated .kicad_sch conforms to modern KiCad S-Expression format."""
    res = synthesize_from_prompt("STM32F103 USB-C LDO CAN")
    sch_txt = generate_kicad_schematic(
        res["modules"],
        res["netlist"]["connections"],
        title="Industrial Node V1",
        company="Industrial Corp",
    )
    assert sch_txt.startswith("(kicad_sch")
    assert '(generator "CircuitAgent")' in sch_txt
    assert '(title "Industrial Node V1")' in sch_txt
    assert '(company "Industrial Corp")' in sch_txt
    assert "(lib_symbols" in sch_txt
    assert 'property "Reference" "U_CAN"' in sch_txt
    assert 'property "Footprint"' in sch_txt
    assert "(sheet_instances" in sch_txt
    assert sch_txt.rstrip().endswith(")")


def test_audit_supply_chain_multi_sourcing():
    """Verify supply chain auditor matches second-source alternates and flags single sources."""
    res = synthesize_from_prompt("ESP32-C3 USB-C LDO RS485")
    report = audit_supply_chain(res["modules"])

    assert report.total_components >= 5
    assert report.resilience_score_pct > 50.0

    # LDO (AMS1117-3.3) and RS485 (SP3485) have known second-source alternates
    ldo_item = next((it for it in report.items if "LDO" in it.ref), None)
    assert ldo_item is not None
    assert ldo_item.has_second_source is True
    assert len(ldo_item.second_sources) >= 1
    assert any("1117" in alt["part"] for alt in ldo_item.second_sources)

    rs485_item = next((it for it in report.items if it.ref == "U_485"), None)
    assert rs485_item is not None
    assert rs485_item.has_second_source is True
    assert any("MAX485" in alt["part"] or "3485" in alt["part"] for alt in rs485_item.second_sources)

    assert len(report.recommendations) >= 1


def test_mcp_tools_schematic_and_supply_chain():
    """Verify MCP tools export_kicad_schematic and audit_supply_chain execute cleanly."""
    from client.mcp_server import handle_tool_call

    res = synthesize_from_prompt("STM32F103 CAN RS485")

    # 1. export_kicad_schematic
    out_sch = handle_tool_call("export_kicad_schematic", {
        "modules": res["modules"],
        "connections": res["netlist"]["connections"],
        "title": "Automated Unit Test",
    })
    assert "isError" not in out_sch
    sch_content = out_sch["content"][0]["text"]
    assert "(kicad_sch" in sch_content
    assert '(title "Automated Unit Test")' in sch_content

    # 2. audit_supply_chain
    out_sc = handle_tool_call("audit_supply_chain", {
        "modules": res["modules"],
    })
    assert "isError" not in out_sc
    import json
    sc_data = json.loads(out_sc["content"][0]["text"])
    assert "resilience_score_pct" in sc_data
    assert "items" in sc_data and "recommendations" in sc_data
