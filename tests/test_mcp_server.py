"""Unit tests for the standard Model Context Protocol (MCP) server.

Covers the full MCP Triad:
  - Tools (synthesize_circuit, search_lcsc_parts, list_circuit_blocks, validate_netlist, calculate_trace_impedance, calculate_bom_cost)
  - Resources (netlist-schema, cpl-standard, catalog, jlc-smt, reference examples)
  - Prompts (design_hardware_project, audit_schematic_netlist, optimize_bom_cost)
  - Lifecycle & Protocol (initialize, ping, templates, error codes)
"""

from __future__ import annotations

import json

import pytest

from client import mcp_server as mcp


def test_mcp_initialize():
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = mcp.process_message(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "result" in resp
    res = resp["result"]
    assert res["protocolVersion"] == "2024-11-05"
    assert res["serverInfo"]["name"] == "circuit-agent-mcp"
    assert "tools" in res["capabilities"]
    assert "resources" in res["capabilities"]
    assert "prompts" in res["capabilities"]


def test_mcp_ping():
    req = {"jsonrpc": "2.0", "id": 42, "method": "ping"}
    resp = mcp.process_message(req)
    assert resp["id"] == 42
    assert resp["result"] == {}


def test_mcp_tools_list():
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    resp = mcp.process_message(req)
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "synthesize_circuit" in tool_names
    assert "search_lcsc_parts" in tool_names
    assert "list_circuit_blocks" in tool_names
    assert "validate_netlist" in tool_names
    assert "calculate_trace_impedance" in tool_names
    assert "calculate_bom_cost" in tool_names
    assert "list_supported_chips" in tool_names
    assert "register_custom_chip" in tool_names
    assert "calculate_ipc2152_trace_current" in tool_names
    assert "audit_industrial_dfx" in tool_names
    assert "export_kicad_netlist" in tool_names
    assert "export_manufacturing_bom" in tool_names
    assert "calculate_parametric_circuit" in tool_names
    assert "render_circuit_topology" in tool_names
    assert "run_erc" in tool_names
    assert len(tools) == 15


def test_mcp_tool_call_synthesize():
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "synthesize_circuit",
            "arguments": {
                "prompt": "基于 ESP32-C3 的环境监测节点，带 Type-C 供电、I2C 传感器插座、RS485",
            },
        },
    }
    resp = mcp.process_message(req)
    assert "result" in resp
    content = resp["result"]["content"]
    assert len(content) == 1
    data = json.loads(content[0]["text"])
    assert data["chip_id"] == "ESP32-C3"
    assert "U_485" in data["modules"]


def test_mcp_tool_call_search_lcsc():
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "search_lcsc_parts",
            "arguments": {"query": "SP3485", "limit": 2},
        },
    }
    resp = mcp.process_message(req)
    assert "result" in resp
    data = json.loads(resp["result"]["content"][0]["text"])
    assert isinstance(data, list)
    assert len(data) > 0
    assert any("3485" in str(p.get("package") or "") or "3485" in str(p.get("part_number") or "") or "3485" in str(p.get("description") or "") or "3485" in str(p.get("lcsc_part") or "") for p in data)


def test_mcp_tool_call_list_blocks():
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "list_circuit_blocks",
            "arguments": {},
        },
    }
    resp = mcp.process_message(req)
    data = json.loads(resp["result"]["content"][0]["text"])
    assert len(data) >= 10
    names = [b["name"] for b in data]
    assert "RS485_Transceiver" in names
    assert "CAN_Transceiver" in names
    assert "Battery_TP4056" in names


def test_mcp_tool_call_validate_netlist():
    good_netlist = {
        "connections": [
            {"net": "/GND", "points": ["U1.1", "C1.2"]},
            {"net": "/+3.3V", "points": ["U1.2", "C1.1"]},
        ]
    }
    req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "validate_netlist",
            "arguments": {"netlist": good_netlist},
        },
    }
    resp = mcp.process_message(req)
    res = json.loads(resp["result"]["content"][0]["text"])
    assert res["valid"] is True


def test_mcp_tool_call_calculate_impedance():
    # Differential 90 ohm USB
    req_diff = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "calculate_trace_impedance",
            "arguments": {
                "mode": "differential",
                "target_z": 90.0,
                "dielectric_h_mm": 0.1,
                "dielectric_er": 4.2,
                "trace_gap_mm": 0.15,
            },
        },
    }
    resp = mcp.process_message(req_diff)
    res = json.loads(resp["result"]["content"][0]["text"])
    assert res["mode"] == "differential"
    assert abs(res["achieved_z_ohms"] - 90.0) < 0.5
    assert res["trace_width_mm"] > 0.1
    assert "propagation_delay_ps_per_mm" in res

    # Single-ended 50 ohm RF
    req_single = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "calculate_trace_impedance",
            "arguments": {
                "mode": "single",
                "target_z": 50.0,
                "dielectric_h_mm": 0.1,
                "dielectric_er": 4.2,
            },
        },
    }
    resp = mcp.process_message(req_single)
    res = json.loads(resp["result"]["content"][0]["text"])
    assert res["mode"] == "single"
    assert abs(res["achieved_z_ohms"] - 50.0) < 0.5
    assert res["trace_width_mm"] > 0.1


def test_mcp_tool_call_calculate_bom_cost():
    req = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {
            "name": "calculate_bom_cost",
            "arguments": {
                "queries": ["STM32F103C8T6", "SP3485", "0603 10k"],
            },
        },
    }
    resp = mcp.process_message(req)
    res = json.loads(resp["result"]["content"][0]["text"])
    assert "total_estimated_cny" in res
    assert "feeder_surcharge_cny" in res
    assert len(res["details"]) == 3


def test_mcp_resources_list():
    req = {"jsonrpc": "2.0", "id": 10, "method": "resources/list", "params": {}}
    resp = mcp.process_message(req)
    resources = resp["result"]["resources"]
    uris = [r["uri"] for r in resources]
    assert "circuit://specs/netlist-schema" in uris
    assert "circuit://specs/cpl-standard" in uris
    assert "circuit://blocks/catalog" in uris
    assert "circuit://rules/jlc-smt" in uris
    assert "circuit://examples/esp32c3-minimal" in uris
    assert "circuit://examples/stm32f103-controller" in uris
    assert "circuit://examples/rp2040-dualcore" in uris
    assert "circuit://specs/ipc-dfx-rules" in uris
    assert len(resources) == 8


def test_mcp_resources_templates_list():
    req = {"jsonrpc": "2.0", "id": 11, "method": "resources/templates/list", "params": {}}
    resp = mcp.process_message(req)
    assert "resourceTemplates" in resp["result"]


def test_mcp_resources_read_schema():
    req = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "resources/read",
        "params": {"uri": "circuit://specs/netlist-schema"},
    }
    resp = mcp.process_message(req)
    contents = resp["result"]["contents"]
    assert len(contents) == 1
    assert contents[0]["mimeType"] == "application/json"
    schema = json.loads(contents[0]["text"])
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"


def test_mcp_resources_read_rules_and_blocks():
    # Rules
    req_rules = {
        "jsonrpc": "2.0",
        "id": 13,
        "method": "resources/read",
        "params": {"uri": "circuit://rules/jlc-smt"},
    }
    resp = mcp.process_message(req_rules)
    contents = resp["result"]["contents"]
    rules = json.loads(contents[0]["text"])
    assert rules["stackup"]["name"] == "JLC04161H"
    assert rules["pricing"]["extended_feeder_cny"] == 20.0

    # Catalog
    req_catalog = {
        "jsonrpc": "2.0",
        "id": 14,
        "method": "resources/read",
        "params": {"uri": "circuit://blocks/catalog"},
    }
    resp = mcp.process_message(req_catalog)
    cat = json.loads(resp["result"]["contents"][0]["text"])
    assert len(cat) >= 10


def test_mcp_resources_read_unknown():
    req = {
        "jsonrpc": "2.0",
        "id": 15,
        "method": "resources/read",
        "params": {"uri": "circuit://non-existent/resource"},
    }
    resp = mcp.process_message(req)
    assert "error" in resp
    assert resp["error"]["code"] == -32002


def test_mcp_prompts_list():
    req = {"jsonrpc": "2.0", "id": 16, "method": "prompts/list", "params": {}}
    resp = mcp.process_message(req)
    prompts = resp["result"]["prompts"]
    names = [p["name"] for p in prompts]
    assert "design_hardware_project" in names
    assert "audit_schematic_netlist" in names
    assert "optimize_bom_cost" in names
    assert "audit_industrial_compliance" in names
    assert len(prompts) == 4


def test_mcp_prompts_get():
    req = {
        "jsonrpc": "2.0",
        "id": 17,
        "method": "prompts/get",
        "params": {
            "name": "design_hardware_project",
            "arguments": {
                "requirements": "基于 STM32F103 的 RS485 采集板",
                "target_mcu": "STM32F103",
                "power_source": "USB-C",
            },
        },
    }
    resp = mcp.process_message(req)
    assert "result" in resp
    res = resp["result"]
    assert "messages" in res
    assert len(res["messages"]) == 1
    assert "STM32F103" in res["messages"][0]["content"]["text"]


def test_mcp_unknown_method():
    req = {"jsonrpc": "2.0", "id": 99, "method": "unknown/method"}
    resp = mcp.process_message(req)
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_mcp_unknown_tool_returns_is_error():
    req = {
        "jsonrpc": "2.0",
        "id": 100,
        "method": "tools/call",
        "params": {"name": "non_existent_tool", "arguments": {}},
    }
    resp = mcp.process_message(req)
    assert "result" in resp
    assert resp["result"].get("isError") is True


def test_mcp_tool_call_calculate_ipc2152():
    req = {
        "jsonrpc": "2.0",
        "id": 101,
        "method": "tools/call",
        "params": {
            "name": "calculate_ipc2152_trace_current",
            "arguments": {"mode": "solve_current", "trace_width_mm": 0.5, "copper_oz": 1.0, "temp_rise_c": 20.0},
        },
    }
    resp = mcp.process_message(req)
    assert "result" in resp
    data = json.loads(resp["result"]["content"][0]["text"])
    assert "max_current_a" in data
    assert data["max_current_a"] > 1.5

    req_solve = {
        "jsonrpc": "2.0",
        "id": 102,
        "method": "tools/call",
        "params": {
            "name": "calculate_ipc2152_trace_current",
            "arguments": {"mode": "solve_width", "target_current_a": 2.0},
        },
    }
    resp_solve = mcp.process_message(req_solve)
    data_solve = json.loads(resp_solve["result"]["content"][0]["text"])
    assert data_solve["trace_width_mm"] > 0.4


def test_mcp_tool_call_audit_industrial_dfx():
    netlist = {
        "components": [
            {"ref": "J1", "kind": "CONNECTOR", "value": "USB-C-16P"},
            {"ref": "U1", "kind": "MCU", "value": "STM32F103"},
        ],
        "connections": [
            {"net": "/VBUS", "points": ["J1.VBUS", "U1.VDD"]},
            {"net": "/GND", "points": ["J1.GND", "U1.VSS"]},
        ],
    }
    req = {
        "jsonrpc": "2.0",
        "id": 103,
        "method": "tools/call",
        "params": {
            "name": "audit_industrial_dfx",
            "arguments": {"netlist": netlist},
        },
    }
    resp = mcp.process_message(req)
    assert "result" in resp
    data = json.loads(resp["result"]["content"][0]["text"])
    assert "score" in data
    assert "violations" in data
    assert any(v["rule_id"] == "EMC-01" for v in data["violations"])


def test_mcp_tool_call_export_kicad_and_bom():
    netlist = {
        "components": [
            {"ref": "R1", "value": "10k", "package": "0603", "lcsc": "C25804"},
            {"ref": "R2", "value": "10k", "package": "0603", "lcsc": "C25804"},
            {"ref": "C1", "value": "100nF", "package": "0603", "lcsc": "C14663"},
        ],
        "connections": [
            {"net": "/VBUS", "points": ["R1.1", "C1.1"]},
            {"net": "/GND", "points": ["R2.2", "C1.2"]},
        ],
    }

    # Test export_kicad_netlist
    req_net = {
        "jsonrpc": "2.0",
        "id": 104,
        "method": "tools/call",
        "params": {"name": "export_kicad_netlist", "arguments": {"netlist": netlist, "title": "TestBoard"}},
    }
    resp_net = mcp.process_message(req_net)
    assert "result" in resp_net
    net_str = resp_net["result"]["content"][0]["text"]
    assert '(export (version "E")' in net_str
    assert '(comp (ref "R1")' in net_str

    # Test export_manufacturing_bom
    req_bom = {
        "jsonrpc": "2.0",
        "id": 105,
        "method": "tools/call",
        "params": {"name": "export_manufacturing_bom", "arguments": {"netlist": netlist}},
    }
    resp_bom = mcp.process_message(req_bom)
    assert "result" in resp_bom
    bom_str = resp_bom["result"]["content"][0]["text"]
    assert "R1,R2" in bom_str
    assert "Basic Part" in bom_str

    # Test render_circuit_topology
    req_top = {
        "jsonrpc": "2.0",
        "id": 106,
        "method": "tools/call",
        "params": {"name": "render_circuit_topology", "arguments": {"netlist": netlist}},
    }
    resp_top = mcp.process_message(req_top)
    assert "result" in resp_top
    top_str = resp_top["result"]["content"][0]["text"]
    assert "SYSTEM ARCHITECTURE TOPOLOGY" in top_str


def test_mcp_tool_call_calculate_parametric():
    # Test divider
    req_div = {
        "jsonrpc": "2.0",
        "id": 107,
        "method": "tools/call",
        "params": {
            "name": "calculate_parametric_circuit",
            "arguments": {
                "type": "resistor_divider",
                "params": {"v_in": 12.0, "v_out_target": 3.3, "max_quiescent_current_ma": 2.0},
            },
        },
    }
    resp_div = mcp.process_message(req_div)
    assert "result" in resp_div
    data_div = json.loads(resp_div["result"]["content"][0]["text"])
    assert data_div["v_out_actual"] == pytest.approx(3.3, rel=0.02)

    # Test LDO thermal
    req_ldo = {
        "jsonrpc": "2.0",
        "id": 108,
        "method": "tools/call",
        "params": {
            "name": "calculate_parametric_circuit",
            "arguments": {
                "type": "ldo_thermal",
                "params": {"v_in": 5.0, "v_out": 3.3, "i_load_a": 0.2, "package": "SOT-223"},
            },
        },
    }
    resp_ldo = mcp.process_message(req_ldo)
    assert "result" in resp_ldo
    data_ldo = json.loads(resp_ldo["result"]["content"][0]["text"])
    assert data_ldo["is_safe"] is True

    # Test I2C pullup
    req_i2c = {
        "jsonrpc": "2.0",
        "id": 109,
        "method": "tools/call",
        "params": {
            "name": "calculate_parametric_circuit",
            "arguments": {
                "type": "i2c_pullup",
                "params": {"v_cc": 3.3, "bus_capacitance_pf": 150.0, "mode": "fast"},
            },
        },
    }
    resp_i2c = mcp.process_message(req_i2c)
    assert "result" in resp_i2c
    data_i2c = json.loads(resp_i2c["result"]["content"][0]["text"])
    assert data_i2c["recommended_standard_ohm"] > 0

