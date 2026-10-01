"""Unit tests for the standard Model Context Protocol (MCP) server."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_mcp_tool_call_list_blocks():
    req = {
        "jsonrpc": "2.0",
        "id": 4,
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
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "validate_netlist",
            "arguments": {"netlist": good_netlist},
        },
    }
    resp = mcp.process_message(req)
    res = json.loads(resp["result"]["content"][0]["text"])
    assert res["valid"] is True


def test_mcp_unknown_method():
    req = {"jsonrpc": "2.0", "id": 99, "method": "unknown/method"}
    resp = mcp.process_message(req)
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_mcp_unknown_tool():
    req = {
        "jsonrpc": "2.0",
        "id": 100,
        "method": "tools/call",
        "params": {"name": "non_existent_tool", "arguments": {}},
    }
    resp = mcp.process_message(req)
    assert "error" in resp
    assert resp["error"]["code"] == -32000
