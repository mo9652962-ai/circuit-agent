"""Standard Model Context Protocol (MCP) Server for CircuitAgent (Community Edition).

Runs over stdio (JSON-RPC 2.0). Compatible with Claude Desktop, Cursor, and Windsurf.
Implemented using only Python standard library (no extra pip dependencies needed).

Usage:
    python -m client.mcp_server
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from .circuit_blocks import (
    block_battery_tp4056,
    block_button,
    block_buzzer,
    block_can_transceiver,
    block_crystal_clock,
    block_i2c_header,
    block_led,
    block_power_ldo_3v3,
    block_rs485_transceiver,
    block_usb_c_power,
)
from .lcsc_client import search_lcsc_parts
from .synthesizer import synthesize_from_prompt

logger = logging.getLogger("circuit_agent_mcp")

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "circuit-agent-mcp",
    "version": "0.1.0",
}

AVAILABLE_TOOLS = [
    {
        "name": "synthesize_circuit",
        "description": (
            "Synthesize a deterministic hardware netlist and component modules from a natural language prompt. "
            "Supported MCUs: STM32F103, ESP32-C3, ESP32-S3, RP2040, STC89C52. "
            "Peripherals: Type-C, LDO, Crystal, Buttons, LEDs, Buzzer, I2C, RS485, CAN, TP4056 Battery."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Natural language prompt describing the target board and peripherals.",
                }
            },
        },
    },
    {
        "name": "search_lcsc_parts",
        "description": (
            "Query live LCSC / JLCPCB component inventory, stock, package, and pricing with zero API keys required. "
            "Features 24-hour disk cache and exponential backoff."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Component part number, model, or description (e.g. 'CH340N', 'SP3485', 'TP4056').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of component matches to return (default: 5).",
                    "default": 5,
                },
            },
        },
    },
    {
        "name": "list_circuit_blocks",
        "description": "List all pre-validated CircuitBlocks available in the hardware DSL catalog.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "validate_netlist",
        "description": "Validate a hardware netlist dictionary against the formal CircuitAgent JSON Schema specification.",
        "inputSchema": {
            "type": "object",
            "required": ["netlist"],
            "properties": {
                "netlist": {
                    "type": "object",
                    "description": "Netlist dictionary containing 'connections' list with 'net' and 'points'.",
                }
            },
        },
    },
]


def _get_catalog() -> list[dict[str, Any]]:
    factories = [
        block_usb_c_power,
        block_power_ldo_3v3,
        block_crystal_clock,
        block_button,
        block_led,
        block_buzzer,
        block_i2c_header,
        block_rs485_transceiver,
        block_can_transceiver,
        block_battery_tp4056,
    ]
    catalog = []
    for f in factories:
        blk = f()
        catalog.append({
            "name": blk.name,
            "description": blk.description,
            "components": [
                {"ref": c.ref, "kind": c.kind, "value": c.value, "package": c.package, "lcsc": c.lcsc}
                for c in blk.components
            ],
            "nets": list(blk.nets.keys()),
            "properties": blk.properties,
        })
    return catalog


def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "synthesize_circuit":
        prompt = arguments.get("prompt", "")
        if not prompt:
            raise ValueError("Parameter 'prompt' is required")
        res = synthesize_from_prompt(prompt)
        return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}]}

    if name == "search_lcsc_parts":
        query = arguments.get("query", "")
        limit = arguments.get("limit", 5)
        if not query:
            raise ValueError("Parameter 'query' is required")
        parts = search_lcsc_parts(query, limit=limit)
        return {"content": [{"type": "text", "text": json.dumps(parts, ensure_ascii=False, indent=2)}]}

    if name == "list_circuit_blocks":
        cat = _get_catalog()
        return {"content": [{"type": "text", "text": json.dumps(cat, ensure_ascii=False, indent=2)}]}

    if name == "validate_netlist":
        netlist = arguments.get("netlist", {})
        if not isinstance(netlist, dict):
            raise ValueError("Parameter 'netlist' must be a JSON object")

        schema_path = Path(__file__).resolve().parent.parent / "specs" / "netlist_schema.json"
        errors = []
        if schema_path.exists():
            try:
                import jsonschema
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                jsonschema.validate(instance=netlist, schema=schema)
            except ImportError:
                # Basic validation without external dependency
                if "connections" not in netlist:
                    errors.append("Missing required field 'connections'")
                elif not isinstance(netlist["connections"], list):
                    errors.append("Field 'connections' must be a list")
                else:
                    for i, c in enumerate(netlist["connections"]):
                        if not isinstance(c, dict) or "net" not in c or "points" not in c:
                            errors.append(f"Connection #{i} missing 'net' or 'points'")
            except Exception as e:
                errors.append(str(e))
        else:
            errors.append("Schema file specs/netlist_schema.json not found")

        result = {
            "valid": len(errors) == 0,
            "errors": errors,
        }
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}

    raise ValueError(f"Unknown tool: '{name}'")


def process_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": SERVER_INFO,
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {},
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": AVAILABLE_TOOLS,
            },
        }

    if method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        try:
            res = handle_tool_call(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": res,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32000,
                    "message": str(e),
                },
            }

    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Method '{method}' not found",
            },
        }

    return None


def run_stdio_server():
    """Main stdio loop for MCP server."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = process_message(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {e}",
                },
            }
            sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
