"""Standard Model Context Protocol (MCP) Server for CircuitAgent (Community Edition).

Speaks MCP ``2026-07-28`` (stateless core) and answers legacy handshake clients
back to ``2024-11-05``. The protocol layer lives in :mod:`client.mcp_protocol`;
this module only dispatches.

Surface:
    1. Tools — 58 deterministic hardware-engineering tools (synthesis, ERC,
       DFM/DFA/DFT audits, calculators, manufacturing exporters).
    2. Resources — ``circuit://`` URIs exposing the netlist schema, CPL standard,
       DFX rule book, block catalogue and reference netlists.
    3. Prompts — slash-command engineering workflows.

Runs over stdio (JSON-RPC 2.0). Compatible with Claude Desktop, Cursor, Windsurf
and any MCP client on 2026-07-28 or older.
Implemented using only the Python standard library (zero external pip packages).

Usage:
    python -m client.mcp_server
    circuit-agent-mcp
"""

from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

from .chip_rules import (
    list_supported_chips,
    register_chip_rule,
)
from .circuit_blocks import (
    block_battery_tp4056,
    block_button,
    block_buzzer,
    block_can_transceiver,
    block_crystal_clock,
    block_esd_can_tvs,
    block_esd_rs485_tvs,
    block_esd_usb_tvs,
    block_fiducial_marks,
    block_i2c_header,
    block_led,
    block_power_ldo_3v3,
    block_power_pi_filter,
    block_reverse_polarity_protection,
    block_rs485_transceiver,
    block_sensor_aht20,
    block_sensor_mpu6050,
    block_testpoint_matrix,
    block_usb_c_power,
)
from .erc import erc_gate, run_erc
from .export_engine import (
    export_jlcpcb_bom,
    export_jlcpcb_cpl,
    export_kicad_netlist,
    render_ascii_topology,
)
from .industrial_dfx import (
    IPC2221_CLEARANCES,
    audit_industrial_dfx,
    calculate_ipc2152,
    solve_trace_width_ipc2152,
)
from .lcsc_client import search_lcsc_parts
from .mcp_protocol import (
    CATALOG_TTL_MS,
    DISCOVER_INSTRUCTIONS,
    PROTOCOL_VERSION,
    RESOURCE_TTL_MS,
    SUPPORTED_VERSIONS,
    complete,
    discover_result,
    is_supported,
    requested_version,
    server_info,
    unsupported_version_error,
    with_cache,
)
from .mcp_schema import AVAILABLE_PROMPTS, AVAILABLE_RESOURCES, AVAILABLE_TOOLS
from .parametric_equations import (
    calculate_i2c_pullup,
    calculate_ldo_thermal,
    calculate_rc_filter,
    solve_resistor_divider,
)
from .structured_output import with_structured_content
from .synthesizer import synthesize_from_prompt

logger = logging.getLogger("circuit_agent_mcp")

#: Re-exported for callers that used to read it off this module.
__all_protocol__ = PROTOCOL_VERSION

#: Single source of truth for the version stamp. ``client.__version__`` is the
#: package version; the server advertises it so a client can tell two builds
#: apart. Read lazily to avoid a circular import at module load.
def _server_version() -> str:
    from . import __version__

    return __version__


SERVER_INFO = {
    "name": "circuit-agent-mcp",
    "version": _server_version(),
}

REPO_ROOT = Path(__file__).resolve().parent.parent


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
        block_sensor_aht20,
        block_sensor_mpu6050,
        block_esd_usb_tvs,
        block_esd_rs485_tvs,
        block_esd_can_tvs,
        block_reverse_polarity_protection,
        block_power_pi_filter,
        block_fiducial_marks,
        block_testpoint_matrix,
    ]
    catalog = []
    for f in factories:
        blk = f()
        catalog.append(
            {
                "name": blk.name,
                "description": blk.description,
                "components": [
                    {"ref": c.ref, "kind": c.kind, "value": c.value, "package": c.package, "lcsc": c.lcsc}
                    for c in blk.components
                ],
                "nets": list(blk.nets.keys()),
                "properties": blk.properties,
            }
        )
    return catalog


def _solve_impedance(
    mode: str,
    target_z: float,
    h_mm: float = 0.1,
    er: float = 4.2,
    t_mm: float = 0.035,
    s_mm: float = 0.15,
) -> dict[str, Any]:
    """Solve microstrip or differential pair impedance using IPC-2141 formulation."""
    if h_mm <= 0 or er <= 1.0 or target_z <= 0:
        raise ValueError("Invalid physical dielectric parameters")

    def calc_z(w: float) -> float:
        denom = 0.8 * w + t_mm
        arg = max(1.0001, (5.98 * h_mm) / max(denom, 1e-4))
        z0 = (87.0 / math.sqrt(er + 1.41)) * math.log(arg)
        if mode == "single":
            return z0
        coupling = 1.0 - 0.48 * math.exp(-0.96 * s_mm / h_mm)
        return 2.0 * z0 * max(0.2, coupling)

    low_w, high_w = 0.08, 3.0
    best_w = low_w
    best_z = calc_z(best_w)

    for _ in range(60):
        mid = (low_w + high_w) / 2.0
        z_mid = calc_z(mid)
        best_w = mid
        best_z = z_mid
        if abs(z_mid - target_z) < 0.05:
            break
        if z_mid > target_z:
            low_w = mid
        else:
            high_w = mid

    vp_c = 1.0 / math.sqrt(0.475 * er + 0.67)
    delay_ps_per_mm = (1.0 / (3e8 * vp_c)) * 1e12 / 1000.0

    return {
        "mode": mode,
        "target_z_ohms": target_z,
        "achieved_z_ohms": round(best_z, 2),
        "trace_width_mm": round(best_w, 3),
        "trace_gap_mm": s_mm if mode == "differential" else None,
        "trace_thickness_mm": t_mm,
        "dielectric_h_mm": h_mm,
        "dielectric_er": er,
        "propagation_delay_ps_per_mm": round(delay_ps_per_mm, 2),
        "design_rule_recommendation": (
            f"Route {mode} traces with width={round(best_w, 3)}mm"
            + (f", gap={s_mm}mm" if mode == "differential" else "")
            + f" over solid GND plane. Max length mismatch: 1.0mm (~{round(delay_ps_per_mm * 1.0, 1)}ps delay)."
        ),
    }


def _calc_bom_breakdown(queries: list[str]) -> dict[str, Any]:
    """Calculate PCBA bill-of-materials cost breakdown including JLCPCB feeder surcharge."""
    total_parts_cny = 0.0
    basic_count = 0
    ext_count = 0
    details = []

    for q in queries:
        matches = search_lcsc_parts(q, limit=1)
        if matches:
            m = matches[0]
            is_basic = m.get("is_basic", False)
            lib = "Basic" if is_basic else "Extended"
            price_usd = m.get("price_usd", 0.0) or 0.0
            price_cny = round(price_usd * 7.2, 3)

            if is_basic:
                basic_count += 1
            else:
                ext_count += 1

            total_parts_cny += price_cny
            details.append(
                {
                    "query": q,
                    "lcsc": m.get("lcsc_part"),
                    "title": m.get("part_number") or m.get("description"),
                    "package": m.get("package"),
                    "price_usd": price_usd,
                    "price_cny": price_cny,
                    "library_type": lib,
                    "stock": m.get("stock", 0),
                }
            )
        else:
            details.append({"query": q, "status": "not_found", "price_cny": 0.0})

    feeder_surcharge = ext_count * 20.0
    total_estimated = total_parts_cny + feeder_surcharge

    tips = []
    if ext_count > 0:
        tips.append(
            f"Found {ext_count} Extended library part(s) incurring ¥{feeder_surcharge:.2f} in feeder change fees. "
            f"Replacing them with JLCPCB Basic parts will save up to ¥{feeder_surcharge:.2f} per batch."
        )
    if basic_count > 0:
        tips.append(f"{basic_count} part(s) matched the JLCPCB Basic library with ¥0 feeder surcharge.")

    return {
        "total_estimated_cny": round(total_estimated, 2),
        "bare_components_cost_cny": round(total_parts_cny, 2),
        "feeder_surcharge_cny": round(feeder_surcharge, 2),
        "basic_parts_count": basic_count,
        "extended_parts_count": ext_count,
        "details": details,
        "optimization_tips": tips,
    }


# --------------------------------------------------------------------------- #
# Tool, Resource & Prompt Handlers
# --------------------------------------------------------------------------- #


def _resolve_export_input(arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Normalise what a caller passes to an export tool.

    Export tools were strict: they read ``arguments["netlist"]`` and nothing
    else. But ``synthesize_circuit`` returns ``{"modules": ..., "netlist": ...}``,
    so the obvious call — feed the synthesizer's own output straight into an
    export — silently produced an empty document. That is the worst failure mode
    available: exit code 0, a valid-looking file, no components in it.

    Three shapes are accepted, in order:

    1. The full ``synthesize_circuit`` result (has ``modules``) — passed through.
    2. A bare netlist under ``netlist`` — passed through.
    3. The arguments themselves, if they already look like a netlist.

    Returns ``None`` when nothing usable was supplied, so the caller can report
    the error instead of exporting an empty file.
    """
    netlist = arguments.get("netlist")
    if isinstance(netlist, dict) and netlist:
        # Shape 1: synthesizer output nested under `netlist` still carries modules.
        return netlist

    modules = arguments.get("modules")
    if isinstance(modules, dict) and modules:
        # Shape 2: the whole synthesizer result, modules at the top level.
        return arguments

    if isinstance(netlist, dict):
        # Shape 3: an explicitly empty netlist. Not usable, but the caller did
        # pass the right key — let them know the components are the problem.
        return None

    # Shape 4: arguments are the netlist ({"connections": [...]}).
    if arguments.get("connections"):
        return arguments

    return None


def _export_input_error(tool_name: str) -> dict[str, Any]:
    """Error result for an export call that carried no components."""
    return {
        "isError": True,
        "content": [
            {
                "type": "text",
                "text": (
                    f"{tool_name} received no components. Pass the full `synthesize_circuit` "
                    "output, or an object containing a non-empty `modules` map, or a netlist "
                    "with `connections`."
                ),
            }
        ],
    }


def _bom_row_count(bom_csv: str) -> int:
    """Count component rows in a JLCPCB BOM, excluding the header and blanks."""
    lines = [ln for ln in bom_csv.splitlines() if ln.strip()]
    return max(0, len(lines) - 1)


def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "synthesize_circuit":
            prompt = arguments.get("prompt", "")
            if not prompt:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'prompt' is required"}]}
            chip_id = arguments.get("chip_id")
            custom_chip = arguments.get("custom_chip")
            pin_mapping = arguments.get("pin_mapping")
            res = synthesize_from_prompt(
                prompt,
                chip_id=chip_id,
                custom_chip=custom_chip,
                pin_mapping=pin_mapping,
            )
            # ERC 门禁随合成一并输出（合成即体检）
            try:
                res["erc"] = erc_gate(run_erc(res["modules"], res["netlist"]["connections"]))
            except Exception as e:
                logger.warning("ERC failed: %s", e)
            return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}]}

        if name == "run_erc":
            netlist = arguments.get("netlist", {})
            modules = arguments.get("modules", {})
            if not isinstance(netlist, dict) or "connections" not in netlist:
                return {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": "Parameter 'netlist' with 'connections' is required (synthesize_circuit 输出可直接传入)",
                        }
                    ],
                }
            issues = run_erc(modules, netlist.get("connections") or [])
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"issues": issues, "gate": erc_gate(issues)}, ensure_ascii=False, indent=2),
                    }
                ]
            }

        if name == "list_supported_chips":
            chips = list_supported_chips()
            return {"content": [{"type": "text", "text": json.dumps(chips, ensure_ascii=False, indent=2)}]}

        if name == "register_custom_chip":
            # `register_chip_rule` indexes data["chip_id"] directly, so a missing
            # field surfaced as "Tool execution error: 'chip_id'" — a KeyError
            # rendered as a message with no hint about what to fix. A tool whose
            # contract is an inputSchema should answer in terms of that schema.
            if not arguments.get("chip_id"):
                return {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Parameter 'chip_id' is required — a unique identifier such as "
                                "'CH32V003F4P6'. Fields are passed flat (not nested under 'rule'): "
                                "chip_id, package, supply_voltage, pins, pin_numbers, "
                                "reserved_pins, peripheral_routes, default_gpio_assignments."
                            ),
                        }
                    ],
                }
            rule = register_chip_rule(arguments)
            return {"content": [{"type": "text", "text": json.dumps(rule.to_dict(), ensure_ascii=False, indent=2)}]}

        if name == "search_lcsc_parts":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 5)
            if not query:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'query' is required"}]}
            parts = search_lcsc_parts(query, limit=limit)
            return {"content": [{"type": "text", "text": json.dumps(parts, ensure_ascii=False, indent=2)}]}

        if name == "list_circuit_blocks":
            cat = _get_catalog()
            return {"content": [{"type": "text", "text": json.dumps(cat, ensure_ascii=False, indent=2)}]}

        if name == "validate_netlist":
            netlist = arguments.get("netlist", {})
            if not isinstance(netlist, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameter 'netlist' must be a JSON object"}],
                }

            schema_path = REPO_ROOT / "specs" / "netlist_schema.json"
            errors = []
            if schema_path.exists():
                try:
                    import jsonschema

                    schema = json.loads(schema_path.read_text(encoding="utf-8"))
                    jsonschema.validate(instance=netlist, schema=schema)
                except ImportError:
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

            result = {"valid": len(errors) == 0, "errors": errors}
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}

        if name == "calculate_trace_impedance":
            mode = arguments.get("mode", "differential")
            target_z = float(arguments.get("target_z", 90.0))
            h_mm = float(arguments.get("dielectric_h_mm", 0.1))
            er = float(arguments.get("dielectric_er", 4.2))
            t_mm = float(arguments.get("trace_thickness_mm", 0.035))
            s_mm = float(arguments.get("trace_gap_mm", 0.15))

            calc_res = _solve_impedance(mode, target_z, h_mm, er, t_mm, s_mm)
            return {"content": [{"type": "text", "text": json.dumps(calc_res, ensure_ascii=False, indent=2)}]}

        if name == "calculate_bom_cost":
            queries = arguments.get("queries", [])
            if not isinstance(queries, list) or not queries:
                return {
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "Parameter 'queries' must be a non-empty list of component names"}
                    ],
                }
            bom_res = _calc_bom_breakdown(queries)
            return {"content": [{"type": "text", "text": json.dumps(bom_res, ensure_ascii=False, indent=2)}]}

        if name == "calculate_ipc2152_trace_current":
            mode = arguments.get("mode", "solve_current")
            copper_oz = float(arguments.get("copper_oz", 1.0))
            temp_rise_c = float(arguments.get("temp_rise_c", 20.0))
            layer = arguments.get("layer", "external")
            if mode == "solve_width":
                target_i = float(arguments.get("target_current_a", 1.0))
                ipc_res = solve_trace_width_ipc2152(target_i, copper_oz=copper_oz, temp_rise_c=temp_rise_c, layer=layer)
            else:
                width_mm = float(arguments.get("trace_width_mm", 0.254))
                ipc_res = calculate_ipc2152(width_mm, copper_oz=copper_oz, temp_rise_c=temp_rise_c, layer=layer)
            return {"content": [{"type": "text", "text": json.dumps(ipc_res.to_dict(), ensure_ascii=False, indent=2)}]}

        if name == "audit_industrial_dfx":
            netlist = arguments.get("netlist", {})
            if not isinstance(netlist, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameter 'netlist' must be a JSON object"}],
                }
            dfx_rep = audit_industrial_dfx(netlist)
            return {"content": [{"type": "text", "text": json.dumps(dfx_rep.to_dict(), ensure_ascii=False, indent=2)}]}

        if name == "export_kicad_netlist":
            netlist = _resolve_export_input(arguments)
            title = arguments.get("title", "CircuitAgent_Design")
            if netlist is None:
                return _export_input_error("export_kicad_netlist")
            kicad_str = export_kicad_netlist(netlist, title=title)
            return {"content": [{"type": "text", "text": kicad_str}]}

        if name == "export_manufacturing_bom":
            netlist = _resolve_export_input(arguments)
            if netlist is None:
                return _export_input_error("export_manufacturing_bom")
            bom_csv = export_jlcpcb_bom(netlist)
            # An empty BOM is not a successful export: it means the components
            # were never found, and a manufacturing file with no rows is a
            # dangerous thing to hand someone.
            if _bom_row_count(bom_csv) == 0:
                return {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "BOM export produced zero component rows. The input carried no "
                                "components — pass the full `synthesize_circuit` output, or an object "
                                "with a non-empty `modules` map."
                            ),
                        }
                    ],
                }
            return {"content": [{"type": "text", "text": bom_csv}]}

        if name == "export_manufacturing_cpl":
            netlist = _resolve_export_input(arguments)
            if netlist is None:
                return _export_input_error("export_manufacturing_cpl")
            cpl_csv = export_jlcpcb_cpl(netlist, default_layer=arguments.get("default_layer", "Top"))
            # Same reasoning as the BOM: an empty placement file is not an
            # export, it is an assembly order with nothing to place.
            if _bom_row_count(cpl_csv) == 0:
                return {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "CPL export produced zero placement rows. Pass the full "
                                "`synthesize_circuit` output, or an object with a non-empty "
                                "`modules` map."
                            ),
                        }
                    ],
                }
            return {"content": [{"type": "text", "text": cpl_csv}]}

        if name == "calculate_parametric_circuit":
            p_type = arguments.get("type")
            params = arguments.get("params", {})
            if not isinstance(params, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameter 'params' must be a JSON object"}],
                }

            if p_type == "resistor_divider":
                v_in = float(params.get("v_in", 5.0))
                v_out = float(params.get("v_out_target", 3.3))
                max_i = float(params.get("max_quiescent_current_ma", 1.0))
                series = params.get("series", "E96")
                res = solve_resistor_divider(v_in, v_out, max_quiescent_current_ma=max_i, series=series)
                return {"content": [{"type": "text", "text": json.dumps(res.to_dict(), ensure_ascii=False, indent=2)}]}

            if p_type == "ldo_thermal":
                v_in = float(params.get("v_in", 5.0))
                v_out = float(params.get("v_out", 3.3))
                i_load = float(params.get("i_load_a", 0.1))
                pkg = params.get("package", "SOT-223")
                res = calculate_ldo_thermal(v_in, v_out, i_load, package=pkg)
                return {"content": [{"type": "text", "text": json.dumps(res.to_dict(), ensure_ascii=False, indent=2)}]}

            if p_type == "i2c_pullup":
                v_cc = float(params.get("v_cc", 3.3))
                c_bus = float(params.get("bus_capacitance_pf", 100.0))
                mode = params.get("mode", "fast")
                res = calculate_i2c_pullup(v_cc, bus_capacitance_pf=c_bus, mode=mode)
                return {"content": [{"type": "text", "text": json.dumps(res.to_dict(), ensure_ascii=False, indent=2)}]}

            if p_type == "rc_filter":
                fc = float(params["cutoff_freq_hz"]) if "cutoff_freq_hz" in params else None
                r = float(params["r_ohm"]) if "r_ohm" in params else None
                c = float(params["c_f"]) if "c_f" in params else None
                res = calculate_rc_filter(cutoff_freq_hz=fc, r_ohm=r, c_f=c)
                return {"content": [{"type": "text", "text": json.dumps(res.to_dict(), ensure_ascii=False, indent=2)}]}

            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown parametric calculation type: '{p_type}'"}],
            }

        if name == "render_circuit_topology":
            netlist = arguments.get("netlist", {})
            if not isinstance(netlist, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameter 'netlist' must be a JSON object"}],
                }
            diag = render_ascii_topology(netlist)
            return {"content": [{"type": "text", "text": diag}]}

        if name == "analyze_power_tree":
            modules = arguments.get("modules", {})
            netlist = arguments.get("netlist", {})
            if not isinstance(modules, dict) or not isinstance(netlist, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameters 'modules' and 'netlist' must be objects"}],
                }
            amb = float(arguments.get("ambient_temp_c", 25.0))
            from .power_tree import analyze_power_tree

            pt = analyze_power_tree(modules, netlist.get("connections") or [], ambient_temp_c=amb)
            return {"content": [{"type": "text", "text": json.dumps(pt.to_dict(), ensure_ascii=False, indent=2)}]}

        if name == "calculate_ipc2221_clearance":
            v = float(arguments.get("peak_voltage_v", 5.0))
            ctype = str(arguments.get("conductor_type", "B2"))
            from .parametric_equations import calculate_ipc2221_clearance

            res = calculate_ipc2221_clearance(v, ctype)
            return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}]}

        if name == "export_specctra_dsn":
            modules = arguments.get("modules", {})
            netlist = arguments.get("netlist", {})
            if not isinstance(modules, dict) or not isinstance(netlist, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameters 'modules' and 'netlist' must be objects"}],
                }
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            tw = float(arguments.get("trace_width_mm", 0.254))
            cl = float(arguments.get("clearance_mm", 0.200))
            from .placement_engine import export_specctra_dsn

            dsn_txt = export_specctra_dsn(
                modules,
                netlist.get("connections") or [],
                board_width_mm=bw,
                board_height_mm=bh,
                trace_width_mm=tw,
                clearance_mm=cl,
            )
            return {"content": [{"type": "text", "text": dsn_txt}]}

        if name == "export_kicad_schematic":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            connections = arguments.get("connections", [])
            title = arguments.get("title", "Hardware Design")
            from .kicad_schematic import generate_kicad_schematic

            sch_txt = generate_kicad_schematic(modules, connections, title=title)
            return {"content": [{"type": "text", "text": sch_txt}]}

        if name == "audit_supply_chain":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            from .supply_chain_auditor import audit_supply_chain

            rep = audit_supply_chain(modules)
            return {"content": [{"type": "text", "text": json.dumps(rep.to_dict(), ensure_ascii=False, indent=2)}]}

        if name == "calculate_differential_skew":
            dl = float(arguments.get("trace_length_delta_mm", 0.0))
            proto = str(arguments.get("protocol", "USB2_HS"))
            er = float(arguments.get("dielectric_er", 4.2))
            tw = float(arguments.get("trace_width_mm", 0.254))
            h = float(arguments.get("height_mm", 0.100))
            from .differential_skew import solve_differential_pair_skew

            res = solve_differential_pair_skew(dl, protocol=proto, dielectric_er=er, trace_width_mm=tw, height_mm=h)
            return {"content": [{"type": "text", "text": json.dumps(res.to_dict(), ensure_ascii=False, indent=2)}]}

        if name == "export_ipc_d356":
            modules = arguments.get("modules", {})
            netlist = arguments.get("netlist", {})
            if not isinstance(modules, dict) or not isinstance(netlist, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameters 'modules' and 'netlist' must be objects"}],
                }
            job = str(arguments.get("job_name", "CIRCUIT_AGENT_PCB"))
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            from .ipc_d356_exporter import export_ipc_d356

            d356_txt = export_ipc_d356(
                modules,
                netlist.get("connections") or [],
                job_name=job,
                board_width_mm=bw,
                board_height_mm=bh,
            )
            return {"content": [{"type": "text", "text": d356_txt}]}

        if name == "export_gerber_bundle":
            modules = arguments.get("modules", {})
            netlist = arguments.get("netlist", {})
            if not isinstance(modules, dict) or not isinstance(netlist, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameters 'modules' and 'netlist' must be objects"}],
                }
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            from .gerber_exporter import export_gerber_bundle

            bundle = export_gerber_bundle(
                modules,
                netlist.get("connections") or [],
                board_width_mm=bw,
                board_height_mm=bh,
            )
            return {"content": [{"type": "text", "text": json.dumps(bundle, ensure_ascii=False, indent=2)}]}

        if name == "calculate_pcb_stackup_impedance":
            s_id = str(arguments.get("stackup_id", "JLC04161H"))
            from .stackup_engine import get_stackup_profile, solve_target_trace_width

            prof = get_stackup_profile(s_id)
            resp = prof.to_dict()
            custom_z = arguments.get("solve_custom_z_ohms")
            if custom_z is not None:
                resp["solved_custom_width_mm"] = solve_target_trace_width(float(custom_z))
            return {"content": [{"type": "text", "text": json.dumps(resp, ensure_ascii=False, indent=2)}]}

        if name == "export_excellon_drill":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            connections = arguments.get("connections", [])
            job = str(arguments.get("job_name", "CIRCUIT_AGENT_PCB"))
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            from .excellon_exporter import export_excellon_drill

            drl_txt = export_excellon_drill(
                modules, connections=connections, job_name=job, board_width_mm=bw, board_height_mm=bh
            )
            return {"content": [{"type": "text", "text": drl_txt}]}

        if name == "generate_interactive_bom":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            title = str(arguments.get("title", "PCBA First Article Assembly Inspection"))
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            from .interactive_bom_generator import generate_interactive_bom_html

            ibom_html = generate_interactive_bom_html(modules, title=title, board_width_mm=bw, board_height_mm=bh)
            return {"content": [{"type": "text", "text": ibom_html}]}

        if name == "calculate_smt_feeder_matrix":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            from .smt_feeder_matrix import generate_smt_feeder_matrix

            matrix_rep = generate_smt_feeder_matrix(modules)
            return {
                "content": [{"type": "text", "text": json.dumps(matrix_rep.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "export_openpnp_job":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            from .pnp_machine_exporter import export_openpnp_job_csv

            pnp_txt = export_openpnp_job_csv(modules, board_width_mm=bw, board_height_mm=bh)
            return {"content": [{"type": "text", "text": pnp_txt}]}

        if name == "calculate_ipc7351_land_pattern":
            pkg = arguments.get("package", "")
            if not pkg:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'package' is required"}]}
            density = str(arguments.get("density", "B"))
            lead_type = arguments.get("lead_type")
            overall_l = arguments.get("overall_length_l")
            lead_w = arguments.get("lead_width_w")
            lead_t = arguments.get("lead_contact_t")
            lead_pitch = arguments.get("lead_pitch")
            from .ipc7351_calculator import calculate_ipc7351_land_pattern

            res_pat = calculate_ipc7351_land_pattern(
                package=pkg,
                density=density,
                lead_type=lead_type,
                overall_length_l=float(overall_l) if overall_l is not None else None,
                lead_width_w=float(lead_w) if lead_w is not None else None,
                lead_contact_t=float(lead_t) if lead_t is not None else None,
                lead_pitch=float(lead_pitch) if lead_pitch is not None else None,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(res_pat.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_pcb_panel_rails":
            bw = arguments.get("board_width_mm")
            bh = arguments.get("board_height_mm")
            if bw is None or bh is None:
                return {
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "Parameters 'board_width_mm' and 'board_height_mm' are required"}
                    ],
                }
            gx = int(arguments.get("grid_x", 2))
            gy = int(arguments.get("grid_y", 2))
            depan = str(arguments.get("depaneling_method", "v_cut"))
            rw = float(arguments.get("rail_width_mm", 5.0))
            sp = arguments.get("board_spacing_mm")
            sides = str(arguments.get("rail_sides", "left_right"))
            from .panel_frame import calculate_pcb_panel_rails

            res_panel = calculate_pcb_panel_rails(
                board_width_mm=float(bw),
                board_height_mm=float(bh),
                grid_x=gx,
                grid_y=gy,
                depaneling_method=depan,
                rail_width_mm=rw,
                board_spacing_mm=float(sp) if sp is not None else None,
                rail_sides=sides,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(res_panel.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_ict_testpoints":
            conns = arguments.get("connections", [])
            if not isinstance(conns, list):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameter 'connections' must be a list"}],
                }
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            min_pad = float(arguments.get("min_pad_diameter_mm", 1.0))
            min_pitch = float(arguments.get("min_probe_pitch_mm", 2.0))
            from .ict_testpoints import calculate_ict_testpoints

            rep_ict = calculate_ict_testpoints(
                connections=conns,
                board_width_mm=bw,
                board_height_mm=bh,
                min_pad_diameter_mm=min_pad,
                min_probe_pitch_mm=min_pitch,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_ict.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_bga_escape_routing":
            b_cnt = int(arguments.get("ball_count", 64))
            b_pitch = float(arguments.get("ball_pitch_mm", 0.8))
            b_pad = float(arguments.get("ball_pad_dia_mm", 0.4))
            v_drill = float(arguments.get("via_drill_mm", 0.2))
            v_pad = float(arguments.get("via_pad_dia_mm", 0.45))
            tr_w = float(arguments.get("trace_width_mm", 0.10))
            from .bga_escape_router import calculate_bga_escape_routing

            rep_bga = calculate_bga_escape_routing(
                ball_count=b_cnt,
                ball_pitch_mm=b_pitch,
                ball_pad_dia_mm=b_pad,
                via_drill_mm=v_drill,
                via_pad_dia_mm=v_pad,
                trace_width_mm=tr_w,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_bga.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_teardrop_reinforcement":
            vias = arguments.get("vias", [])
            if not isinstance(vias, list):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'vias' must be a list"}]}
            def_tr_w = float(arguments.get("default_trace_width_mm", 0.20))
            style = str(arguments.get("teardrop_style", "curved"))
            from .teardrop_engine import calculate_teardrop_reinforcement

            rep_td = calculate_teardrop_reinforcement(
                vias=vias, default_trace_width_mm=def_tr_w, teardrop_style=style
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_td.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_copper_thieving_balance":
            bw = arguments.get("board_width_mm")
            bh = arguments.get("board_height_mm")
            if bw is None or bh is None:
                return {
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "Parameters 'board_width_mm' and 'board_height_mm' are required"}
                    ],
                }
            top_cu = arguments.get("top_copper_area_mm2")
            bot_cu = arguments.get("bot_copper_area_mm2")
            margin = float(arguments.get("keepout_margin_mm", 2.0))
            pitch = float(arguments.get("pattern_pitch_mm", 2.54))
            from .copper_thieving import calculate_copper_thieving_balance

            rep_cu = calculate_copper_thieving_balance(
                board_width_mm=float(bw),
                board_height_mm=float(bh),
                top_copper_area_mm2=float(top_cu) if top_cu is not None else None,
                bot_copper_area_mm2=float(bot_cu) if bot_cu is not None else None,
                keepout_margin_mm=margin,
                pattern_pitch_mm=pitch,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_cu.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_via_stitching_array":
            pw = float(arguments.get("pad_width_mm", 5.0))
            ph = float(arguments.get("pad_height_mm", 5.0))
            cx = float(arguments.get("center_x_mm", 0.0))
            cy = float(arguments.get("center_y_mm", 0.0))
            drill = float(arguments.get("drill_dia_mm", 0.30))
            pitch = float(arguments.get("grid_pitch_mm", 1.20))
            is_rf = bool(arguments.get("is_rf_shielding_fence", False))
            from .via_stitching import calculate_via_stitching_array

            rep_stitch = calculate_via_stitching_array(
                pad_width_mm=pw,
                pad_height_mm=ph,
                center_x_mm=cx,
                center_y_mm=cy,
                drill_dia_mm=drill,
                grid_pitch_mm=pitch,
                is_rf_shielding_fence=is_rf,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_stitch.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_serpentine_tuning_geometry":
            delta_l = arguments.get("delta_length_mm")
            if delta_l is None:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'delta_length_mm' is required"}]}
            tw = float(arguments.get("trace_width_mm", 0.15))
            sx = float(arguments.get("start_x_mm", 10.0))
            sy = float(arguments.get("start_y_mm", 20.0))
            ex = float(arguments.get("end_x_mm", 30.0))
            ey = float(arguments.get("end_y_mm", 20.0))
            from .serpentine_tuning import calculate_serpentine_tuning_geometry

            rep_serp = calculate_serpentine_tuning_geometry(
                delta_length_mm=float(delta_l),
                trace_width_mm=tw,
                start_x_mm=sx,
                start_y_mm=sy,
                end_x_mm=ex,
                end_y_mm=ey,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_serp.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_stencil_aperture_ratios":
            apertures = arguments.get("apertures", [])
            if not isinstance(apertures, list) or not apertures:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameter 'apertures' must be a non-empty list"}],
                }
            foil_um = float(arguments.get("foil_thickness_um", 100.0))
            min_ar = float(arguments.get("min_area_ratio", 0.66))
            min_asp = float(arguments.get("min_aspect_ratio", 1.5))
            from .stencil_aperture import calculate_stencil_aperture_ratios

            rep_st = calculate_stencil_aperture_ratios(
                apertures=apertures,
                foil_thickness_um=foil_um,
                min_area_ratio=min_ar,
                min_aspect_ratio=min_asp,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_st.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_fiducial_layout":
            bw = arguments.get("board_width_mm")
            bh = arguments.get("board_height_mm")
            if bw is None or bh is None:
                return {
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "Parameters 'board_width_mm' and 'board_height_mm' are required"}
                    ],
                }
            comps = arguments.get("fine_pitch_components", [])
            edge = float(arguments.get("edge_clearance_mm", 5.0))
            thresh = float(arguments.get("fine_pitch_threshold_mm", 0.5))
            from .fiducial_optimizer import calculate_fiducial_layout

            rep_fid = calculate_fiducial_layout(
                board_width_mm=float(bw),
                board_height_mm=float(bh),
                fine_pitch_components=comps if isinstance(comps, list) else [],
                edge_clearance_mm=edge,
                fine_pitch_threshold_mm=thresh,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_fid.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_via_protection_plan":
            vias = arguments.get("vias", [])
            if not isinstance(vias, list) or not vias:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'vias' must be a non-empty list"}]}
            from .via_protection import calculate_via_protection_plan

            rep_vp = calculate_via_protection_plan(vias=vias)
            return {
                "content": [{"type": "text", "text": json.dumps(rep_vp.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_solder_paste_volume":
            apertures = arguments.get("apertures", [])
            if not isinstance(apertures, list) or not apertures:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'apertures' must be a non-empty list"}]}
            foil_um = float(arguments.get("foil_thickness_um", 100.0))
            eta = float(arguments.get("transfer_efficiency", 0.90))
            standoff = float(arguments.get("target_standoff_mm", 0.10))
            from .solder_paste_volume import calculate_solder_paste_volume

            rep_pv = calculate_solder_paste_volume(
                apertures=apertures,
                foil_thickness_um=foil_um,
                transfer_efficiency=eta,
                target_standoff_mm=standoff,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_pv.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "export_ipc2581":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict) or not modules:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be a non-empty object"}]}
            conns = arguments.get("connections", [])
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            stack = arguments.get("stackup_layers")
            proj = str(arguments.get("project_name", "HARDWARE_PROJECT"))
            from .ipc2581_exporter import export_ipc2581

            xml_txt = export_ipc2581(
                modules=modules,
                connections=conns if isinstance(conns, list) else [],
                board_width_mm=bw,
                board_height_mm=bh,
                stackup_layers=stack if isinstance(stack, list) else None,
                project_name=proj,
            )
            return {"content": [{"type": "text", "text": xml_txt}]}

        if name == "export_assembly_drawing_svg":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict) or not modules:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be a non-empty object"}]}
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            mirrored = bool(arguments.get("mirrored_bottom", True))
            dtitle = str(arguments.get("title", "PCBA ASSEMBLY DRAWING"))
            rev = str(arguments.get("revision", "A"))
            from .assembly_drawing import export_assembly_drawing_svg

            drawing = export_assembly_drawing_svg(
                modules=modules,
                board_width_mm=bw,
                board_height_mm=bh,
                mirrored_bottom=mirrored,
                title=dtitle,
                revision=rev,
            )
            return {"content": [{"type": "text", "text": drawing.svg}]}

        if name == "diff_netlists":
            old_modules = arguments.get("old_modules")
            new_modules = arguments.get("new_modules")
            old_conns = arguments.get("old_connections")
            new_conns = arguments.get("new_connections")
            if not isinstance(old_modules, dict) or not isinstance(new_modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameters 'old_modules' and 'new_modules' must be objects"}]}
            if not isinstance(old_conns, list) or not isinstance(new_conns, list):
                return {"isError": True, "content": [{"type": "text", "text": "Parameters 'old_connections' and 'new_connections' must be lists"}]}
            from .netlist_diff import diff_netlists

            rep_diff = diff_netlists(
                old_modules=old_modules,
                old_connections=old_conns,
                new_modules=new_modules,
                new_connections=new_conns,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_diff.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "generate_assembly_process_plan":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict) or not modules:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be a non-empty object"}]}
            from .process_planner import generate_assembly_process_plan

            rep_plan = generate_assembly_process_plan(modules=modules)
            return {
                "content": [{"type": "text", "text": json.dumps(rep_plan.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "optimize_panel_grid":
            bw = arguments.get("board_width_mm")
            bh = arguments.get("board_height_mm")
            if bw is None or bh is None:
                return {
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "Parameters 'board_width_mm' and 'board_height_mm' are required"}
                    ],
                }
            max_grid = int(arguments.get("max_grid", 4))
            max_panel = float(arguments.get("max_panel_mm", 300.0))
            rail = float(arguments.get("rail_width_mm", 5.0))
            from .panel_optimizer import optimize_panel_grid

            rep_opt = optimize_panel_grid(
                board_width_mm=float(bw),
                board_height_mm=float(bh),
                max_grid=max_grid,
                max_panel_mm=max_panel,
                rail_width_mm=rail,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_opt.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_fab_cost":
            layers = int(arguments.get("layers", 4))
            qty = int(arguments.get("quantity", 5))
            bw = float(arguments.get("board_width_mm", 100.0))
            bh = float(arguments.get("board_height_mm", 100.0))
            color = str(arguments.get("solder_mask_color", "green"))
            finish = str(arguments.get("surface_finish", "hasl_lead_free"))
            thick = str(arguments.get("thickness_mm", "1.6"))
            lead = str(arguments.get("lead_time", "normal"))
            from .fab_cost import calculate_fab_cost

            res_fab = calculate_fab_cost(
                layers=layers,
                quantity=qty,
                board_width_mm=bw,
                board_height_mm=bh,
                solder_mask_color=color,
                surface_finish=finish,
                thickness_mm=thick,
                lead_time=lead,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(res_fab.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_smt_placement_clearance":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            bw = float(arguments.get("board_width_mm", 70.0))
            bh = float(arguments.get("board_height_mm", 50.0))
            min_tall = float(arguments.get("min_tall_component_height_mm", 4.0))
            min_env = float(arguments.get("min_clearance_envelope_mm", 2.0))
            from .smt_placement_clearance import calculate_smt_placement_clearance

            rep_smt = calculate_smt_placement_clearance(
                modules=modules,
                board_width_mm=bw,
                board_height_mm=bh,
                min_tall_component_height_mm=min_tall,
                min_clearance_envelope_mm=min_env,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_smt.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_creepage_isolation_slot":
            v = float(arguments.get("voltage_v", 220.0))
            c1 = arguments.get("cond1_coords")
            c2 = arguments.get("cond2_coords")
            if not isinstance(c1, (list, tuple)) or not isinstance(c2, (list, tuple)):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameters 'cond1_coords' and 'cond2_coords' must be arrays"}],
                }
            r_c = float(arguments.get("conductor_radius_mm", 1.0))
            w_slot = float(arguments.get("slot_width_mm", 1.2))
            ext_slot = float(arguments.get("slot_extension_mm", 2.0))
            is_reinf = bool(arguments.get("is_reinforced_insulation", False))
            from .creepage_slot import calculate_creepage_isolation_slot

            res_slot = calculate_creepage_isolation_slot(
                voltage_v=v,
                cond1_coords=(float(c1[0]), float(c1[1])),
                cond2_coords=(float(c2[0]), float(c2[1])),
                conductor_radius_mm=r_c,
                slot_width_mm=w_slot,
                slot_extension_mm=ext_slot,
                is_reinforced_insulation=is_reinf,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(res_slot.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "analyze_impedance_tolerance":
            z_t = float(arguments.get("target_z0_ohms", 50.0))
            w_m = float(arguments.get("trace_width_mm", 0.38))
            h_m = float(arguments.get("dielectric_height_mm", 0.20))
            t_m = float(arguments.get("copper_thickness_mm", 0.035))
            er_v = float(arguments.get("dielectric_er", 4.2))
            w_tol = float(arguments.get("width_tolerance_pct", 10.0))
            h_tol = float(arguments.get("height_tolerance_pct", 10.0))
            from .impedance_tolerance_analyzer import analyze_impedance_tolerance

            rep_tol = analyze_impedance_tolerance(
                target_z0_ohms=z_t,
                trace_width_mm=w_m,
                dielectric_height_mm=h_m,
                copper_thickness_mm=t_m,
                dielectric_er=er_v,
                width_tolerance_pct=w_tol,
                height_tolerance_pct=h_tol,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_tol.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "evaluate_material_cti_creepage":
            v = float(arguments.get("working_voltage_v", 220.0))
            clr = float(arguments.get("actual_clearance_mm", 2.0))
            cti = float(arguments.get("substrate_cti_v", 175.0))
            pd = int(arguments.get("pollution_degree", 2))
            ins = str(arguments.get("insulation_type", "Basic"))
            from .material_cti_evaluator import evaluate_material_cti_creepage

            rep_cti = evaluate_material_cti_creepage(
                working_voltage_v=v,
                actual_clearance_mm=clr,
                substrate_cti_v=cti,
                pollution_degree=pd,
                insulation_type=ins,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_cti.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_wave_solder_orientation_audit":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            flow_dir = str(arguments.get("flow_direction", "X+"))
            from .wave_solder_orientation import calculate_wave_solder_orientation_audit

            rep_ori = calculate_wave_solder_orientation_audit(modules, flow_direction=flow_dir)
            return {
                "content": [{"type": "text", "text": json.dumps(rep_ori.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_press_fit_hole_compliance":
            pins = arguments.get("pins", [])
            if not isinstance(pins, list) or not pins:
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'pins' must be a non-empty list"}]}
            nom_d = float(arguments.get("nominal_finished_dia_mm", 1.00))
            t_cu = float(arguments.get("min_copper_plating_um", 25.0))
            from .press_fit_analyzer import calculate_press_fit_hole_compliance

            rep_pf = calculate_press_fit_hole_compliance(
                pins=pins,
                nominal_finished_dia_mm=nom_d,
                min_copper_plating_um=t_cu,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_pf.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "audit_fab_capabilities":
            f_id = str(arguments.get("fab_id", "jlcpcb_standard"))
            tw = float(arguments.get("min_trace_width_mm", 0.127))
            tc = float(arguments.get("min_trace_clearance_mm", 0.127))
            vd = float(arguments.get("min_via_drill_mm", 0.200))
            vp = float(arguments.get("min_via_pad_mm", 0.450))
            bt = float(arguments.get("board_thickness_mm", 1.600))
            ms = float(arguments.get("min_slot_width_mm", 0.800))
            from .fab_capabilities import audit_fab_capabilities

            rep_fab = audit_fab_capabilities(
                fab_id=f_id,
                min_trace_width_mm=tw,
                min_trace_clearance_mm=tc,
                min_via_drill_mm=vd,
                min_via_pad_mm=vp,
                board_thickness_mm=bt,
                min_slot_width_mm=ms,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_fab.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "validate_manufacturing_package":
            artifacts = arguments.get("artifacts_dict", {})
            if not isinstance(artifacts, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'artifacts_dict' must be an object"}]}
            # A caller who passes `artifacts` (the natural name) instead of
            # `artifacts_dict` used to get a clean-looking report saying all
            # eight deliverables were missing — indistinguishable from a design
            # that produced nothing. Say what actually happened.
            if not artifacts:
                for alias in ("artifacts", "files", "package"):
                    if isinstance(arguments.get(alias), dict) and arguments[alias]:
                        return {
                            "isError": True,
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        f"Parameter name mismatch: received '{alias}' but this tool takes "
                                        "'artifacts_dict'. An empty artifacts_dict reports every deliverable "
                                        "as missing, which is indistinguishable from an empty design."
                                    ),
                                }
                            ],
                        }
                return {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "'artifacts_dict' is empty. Pass a mapping of filename -> content, e.g. "
                                "{'board-Edge_Cuts.gm1': ..., 'bom.csv': ..., 'cpl.csv': ...}."
                            ),
                        }
                    ],
                }
            modules = arguments.get("modules")
            j_name = str(arguments.get("job_name", "PCB_PROJECT"))
            from .mfg_validator import validate_manufacturing_package

            rep_mfg = validate_manufacturing_package(
                artifacts_dict=artifacts,
                modules=modules if isinstance(modules, dict) else None,
                job_name=j_name,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_mfg.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "audit_ipc6012_class_compliance":
            t_cls = str(arguments.get("target_class", "Class 2"))
            ext_ring = float(arguments.get("external_annular_ring_mm", 0.125))
            int_ring = float(arguments.get("internal_annular_ring_mm", 0.100))
            brk = bool(arguments.get("has_hole_breakout", False))
            brk_ang = float(arguments.get("breakout_angle_deg", 0.0))
            avg_cu = float(arguments.get("avg_copper_barrel_um", 22.0))
            min_cu = float(arguments.get("min_copper_barrel_um", 19.0))
            red_pct = float(arguments.get("conductor_width_reduction_pct", 5.0))
            min_dam = float(arguments.get("min_solder_mask_dam_mm", 0.090))
            from .ipc6012_auditor import audit_ipc6012_class_compliance

            rep_6012 = audit_ipc6012_class_compliance(
                target_class=t_cls,
                external_annular_ring_mm=ext_ring,
                internal_annular_ring_mm=int_ring,
                has_hole_breakout=brk,
                breakout_angle_deg=brk_ang,
                avg_copper_barrel_um=avg_cu,
                min_copper_barrel_um=min_cu,
                conductor_width_reduction_pct=red_pct,
                min_solder_mask_dam_mm=min_dam,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_6012.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "optimize_smt_feeder_setup":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            cart_cap = int(arguments.get("feeder_cart_capacity", 80))
            b_size = int(arguments.get("batch_size", 1000))
            c_parts = arguments.get("common_parts_list")
            from .smt_feeder_optimizer import optimize_smt_feeder_setup

            plan_smt = optimize_smt_feeder_setup(
                modules=modules,
                feeder_cart_capacity=cart_cap,
                batch_size=b_size,
                common_parts_list=c_parts if isinstance(c_parts, list) else None,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(plan_smt.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "calculate_copper_pour_current_drop":
            if "current_a" not in arguments:
                return {"isError": True, "content": [{"type": "text", "text": "Missing required parameter 'current_a'"}]}
            i_load = float(arguments["current_a"])
            cu_wt = float(arguments.get("copper_weight_oz", 1.0))
            l_eff = float(arguments.get("effective_length_mm", 50.0))
            w_eff = float(arguments.get("effective_width_mm", 20.0))
            w_bot = float(arguments["bottleneck_width_mm"]) if "bottleneck_width_mm" in arguments else None
            t_amb = float(arguments.get("ambient_temp_c", 25.0))
            dt_allow = float(arguments.get("max_allowed_temp_rise_c", 30.0))
            j_ceil = float(arguments.get("max_allowed_current_density_a_per_mm2", 35.0))
            from .copper_pour_analyzer import calculate_copper_pour_current_drop

            rep_pour = calculate_copper_pour_current_drop(
                current_a=i_load,
                copper_weight_oz=cu_wt,
                effective_length_mm=l_eff,
                effective_width_mm=w_eff,
                bottleneck_width_mm=w_bot,
                ambient_temp_c=t_amb,
                max_allowed_temp_rise_c=dt_allow,
                max_allowed_current_density_a_per_mm2=j_ceil,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_pour.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "audit_component_msl_floor_life":
            modules = arguments.get("modules", {})
            if not isinstance(modules, dict):
                return {"isError": True, "content": [{"type": "text", "text": "Parameter 'modules' must be an object"}]}
            exp_def = float(arguments.get("exposed_hours_default", 48.0))
            t_amb = float(arguments.get("ambient_temp_c", 25.0))
            rh_amb = float(arguments.get("ambient_rh_pct", 55.0))
            from .msl_manager import audit_component_msl_floor_life

            rep_msl = audit_component_msl_floor_life(
                modules=modules,
                exposed_hours_default=exp_def,
                ambient_temp_c=t_amb,
                ambient_rh_pct=rh_amb,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_msl.to_dict(), ensure_ascii=False, indent=2)}]
            }

        # --- Real MLCC behaviour (marked value ≠ in-circuit value) ---------- #
        if name == "calculate_effective_capacitance":
            from .mlcc_model import effective_capacitance

            rep_eff = effective_capacitance(
                marked_capacitance_uf=float(arguments.get("marked_capacitance_uf", 10.0)),
                rated_v=float(arguments.get("rated_v", 6.3)),
                applied_v=float(arguments.get("applied_v", 0.0)),
                case_size=str(arguments.get("case_size", "0805")),
                dielectric=str(arguments.get("dielectric", "X5R")),
                ambient_c=float(arguments.get("ambient_c", 25.0)),
                hours_in_service=float(arguments.get("hours_in_service", 1000.0)),
                ac_level=str(arguments.get("ac_level", "small_signal")),
                tolerance_pct=(
                    float(arguments["tolerance_pct"]) if arguments.get("tolerance_pct") is not None else None
                ),
                measured_retention_at_bias=(
                    float(arguments["measured_retention_at_bias"])
                    if arguments.get("measured_retention_at_bias") is not None
                    else None
                ),
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_eff.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "size_hold_up_capacitor":
            from .mlcc_model import hold_up_capacitance

            rep_hold = hold_up_capacitance(
                load_current_ma=float(arguments.get("load_current_ma", 10.0)),
                v_start=float(arguments.get("v_start", 5.0)),
                v_floor=float(arguments.get("v_floor", 3.0)),
                required_hold_time_ms=float(arguments.get("required_hold_time_ms", 20.0)),
                rated_v=(float(arguments["rated_v"]) if arguments.get("rated_v") is not None else None),
                case_size=str(arguments.get("case_size", "0805")),
                dielectric=str(arguments.get("dielectric", "X5R")),
                ambient_c=float(arguments.get("ambient_c", 25.0)),
                hours_in_service=float(arguments.get("hours_in_service", 1000.0)),
                tolerance_pct=float(arguments.get("tolerance_pct", 10.0)),
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_hold.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "analyze_rc_filter_effective":
            from .mlcc_model import rc_cutoff_with_effective_c

            rep_rc = rc_cutoff_with_effective_c(
                r_ohm=float(arguments.get("r_ohm", 1000.0)),
                marked_c_uf=float(arguments.get("marked_c_uf", 10.0)),
                rated_v=float(arguments.get("rated_v", 6.3)),
                applied_v=float(arguments.get("applied_v", 0.0)),
                case_size=str(arguments.get("case_size", "0805")),
                dielectric=str(arguments.get("dielectric", "X5R")),
                ambient_c=float(arguments.get("ambient_c", 25.0)),
                hours_in_service=float(arguments.get("hours_in_service", 1000.0)),
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_rc, ensure_ascii=False, indent=2)}]
            }

        # --- Tolerance corners (nominal is not a specification) ------------ #
        if name == "analyze_divider_tolerance":
            from .tolerance_analysis import divider_tolerance

            rep_div = divider_tolerance(
                v_in=float(arguments.get("v_in", 3.3)),
                r1_ohm=float(arguments.get("r1_ohm", 10000.0)),
                r2_ohm=float(arguments.get("r2_ohm", 10000.0)),
                tolerance_pct=float(arguments.get("tolerance_pct", 1.0)),
                tcr_ppm_per_c=float(arguments.get("tcr_ppm_per_c", 0.0)),
                delta_temp_c=float(arguments.get("delta_temp_c", 0.0)),
                life_drift_pct=float(arguments.get("life_drift_pct", 0.0)),
                ratio_tolerance_pct=(
                    float(arguments["ratio_tolerance_pct"])
                    if arguments.get("ratio_tolerance_pct") is not None
                    else None
                ),
                v_in_tolerance_pct=float(arguments.get("v_in_tolerance_pct", 0.0)),
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_div.to_dict(), ensure_ascii=False, indent=2)}]
            }

        if name == "analyze_resistor_error_budget":
            from .tolerance_analysis import resistor_value_band, tcr_penalty_over_temperature

            band = resistor_value_band(
                nominal_ohm=float(arguments.get("nominal_ohm", 10000.0)),
                tolerance_pct=float(arguments.get("tolerance_pct", 1.0)),
                tcr_ppm_per_c=float(arguments.get("tcr_ppm_per_c", 0.0)),
                delta_temp_c=float(arguments.get("delta_temp_c", 0.0)),
                life_drift_pct=float(arguments.get("life_drift_pct", 0.0)),
                life_hours_specified=float(arguments.get("life_hours_specified", 1000.0)),
                life_hours_required=float(arguments.get("life_hours_required", 1000.0)),
            )
            dominance = tcr_penalty_over_temperature(
                tolerance_pct=float(arguments.get("tolerance_pct", 1.0)),
                tcr_ppm_per_c=float(arguments.get("tcr_ppm_per_c", 0.0)),
                delta_temp_c=float(arguments.get("delta_temp_c", 0.0)),
            )
            payload = {"value_band": band, "dominance": dominance}
            return {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]
            }

        if name == "solve_feedback_divider":
            from .tolerance_analysis import divider_ratio_for_target

            rep_fb = divider_ratio_for_target(
                v_out=float(arguments.get("v_out", 5.0)),
                v_ref=float(arguments.get("v_ref", 0.8)),
                r_total_ohm=float(arguments.get("r_total_ohm", 100000.0)),
            )
            return {
                "content": [{"type": "text", "text": json.dumps(rep_fb, ensure_ascii=False, indent=2)}]
            }

        return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: '{name}'"}]}
    except Exception as e:
        return {"isError": True, "content": [{"type": "text", "text": f"Tool execution error: {e}"}]}


def handle_resource_read(uri: str) -> dict[str, Any]:
    res_files = {
        "circuit://specs/netlist-schema": ("application/json", REPO_ROOT / "specs" / "netlist_schema.json"),
        "circuit://specs/cpl-standard": ("text/markdown", REPO_ROOT / "specs" / "cpl_standard.md"),
        "circuit://examples/esp32c3-minimal": ("application/json", REPO_ROOT / "examples" / "esp32c3_example.json"),
        "circuit://examples/stm32f103-controller": (
            "application/json",
            REPO_ROOT / "examples" / "stm32f103_example.json",
        ),
        "circuit://examples/rp2040-dualcore": ("application/json", REPO_ROOT / "examples" / "rp2040_example.json"),
    }

    if uri in res_files:
        mime, path = res_files[uri]
        if path.exists():
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": mime,
                        "text": path.read_text(encoding="utf-8"),
                    }
                ]
            }
        raise ValueError(f"Resource file not found on disk: {path}")

    if uri == "circuit://blocks/catalog":
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(_get_catalog(), ensure_ascii=False, indent=2),
                }
            ]
        }

    if uri == "circuit://specs/ipc-dfx-rules":
        rules = {
            "ipc_2152_formulas": {
                "external_layer": "I = 0.048 * (dT^0.44) * (Area_mil2^0.725)",
                "internal_layer": "I = 0.024 * (dT^0.44) * (Area_mil2^0.725)",
                "copper_thickness_1oz_mil": 1.378,
            },
            "ipc_2221_clearances": [
                {"max_v": v, "internal_mm": i, "external_uncoated_mm": eu, "external_coated_mm": ec}
                for v, i, eu, ec in IPC2221_CLEARANCES
            ],
            "industrial_dfx_criteria": {
                "dft_min_testpoint_dia_mm": 1.0,
                "dft_min_grid_pitch_mm": 2.0,
                "dfa_min_optical_fiducials": 3,
                "emc_esd_level": "IEC 61000-4-2 Level 4 (15kV Air, 8kV Contact)",
            },
        }
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(rules, ensure_ascii=False, indent=2),
                }
            ]
        }

    if uri == "circuit://rules/jlc-smt":
        rules = {
            "stackup": {
                "name": "JLC04161H",
                "layers": 4,
                "copper_layers": ["Top", "In1.Cu (GND)", "In2.Cu (PWR)", "Bottom"],
                "outer_copper_oz": 1.0,
                "inner_copper_oz": 0.5,
                "outer_dielectric_h_mm": 0.1,
                "core_dielectric_h_mm": 1.0,
                "er": 4.2,
            },
            "design_rules_mm": {
                "min_trace_width": 0.127,
                "min_trace_clearance": 0.127,
                "min_via_diameter": 0.45,
                "min_via_drill": 0.2,
                "differential_usb_90_width": 0.144,
                "differential_usb_90_gap": 0.15,
                "decoupling_cap_max_distance": 4.0,
            },
            "pricing": {
                "smt_setup_cny": 50.0,
                "basic_feeder_cny": 0.0,
                "extended_feeder_cny": 20.0,
            },
        }
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(rules, ensure_ascii=False, indent=2),
                }
            ]
        }

    raise ValueError(f"Unknown resource URI: '{uri}'")


def handle_prompt_get(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "design_hardware_project":
        reqs = arguments.get("requirements", "")
        mcu = arguments.get("target_mcu", "ESP32-C3")
        pwr = arguments.get("power_source", "USB-C")
        user_prompt = (
            f"You are an expert Electronic Design Automation (EDA) and Hardware Synthesis Agent.\n\n"
            f"Target Project Requirements: {reqs}\n"
            f"Target MCU: {mcu}\n"
            f"Power Source: {pwr}\n\n"
            f"Please execute the following engineering workflow:\n"
            f"1. Query `list_circuit_blocks` or inspect `circuit://blocks/catalog` for available pre-audited modules.\n"
            f"2. Use `synthesize_circuit` with the target requirements to generate a formal netlist and module specification.\n"
            f"3. For high-speed differential pairs (USB 90Ω, CAN 120Ω), run `calculate_trace_impedance` to verify layout width and spacing.\n"
            f"4. Run `calculate_bom_cost` on the parts list to estimate PCBA component cost and identify JLCPCB Extended feeder surcharges.\n"
            f"5. Validate the final netlist data structure against the schema using `validate_netlist`."
        )
        return {
            "description": f"Synthesize and audit hardware project: {reqs[:40]}...",
            "messages": [{"role": "user", "content": {"type": "text", "text": user_prompt}}],
        }

    if name == "audit_schematic_netlist":
        netlist_json = arguments.get("netlist_json", "")
        user_prompt = (
            f"You are a Senior Principal Electrical Engineer conducting a strict hardware DRC and Signal/Power Integrity review.\n\n"
            f"Netlist Data to Audit:\n{netlist_json}\n\n"
            f"Audit Gates to Check:\n"
            f"- Gate 1 (Power Integrity): Ensure decoupling capacitors exist for all VCC/VDD rails with max distance ≤ 4.0mm.\n"
            f"- Gate 2 (Interface Standards): For USB-C interfaces, verify CC1 and CC2 each have a 5.1kΩ pull-down resistor to GND.\n"
            f"- Gate 3 (Fieldbus & Differentials): Verify RS485 and CAN transceivers have 120Ω differential termination resistors.\n"
            f"- Gate 4 (Clock Integrity): External crystals must have 22pF load capacitors and a GND guard ring declared.\n"
            f"- Gate 5 (DFM & SMT): Verify all components have valid footprints and LCSC part numbers matching JLCPCB rules."
        )
        return {
            "description": "Senior EE physical inspection and design rule check",
            "messages": [{"role": "user", "content": {"type": "text", "text": user_prompt}}],
        }

    if name == "optimize_bom_cost":
        components = arguments.get("components", "")
        user_prompt = (
            f"You are a PCBA Manufacturing Cost Optimization Specialist.\n\n"
            f"Component List to Analyze:\n{components}\n\n"
            f"Please execute the following steps:\n"
            f"1. Use `search_lcsc_parts` and `calculate_bom_cost` to analyze each component.\n"
            f"2. Identify any Extended library components that incur a ¥20 feeder change surcharge.\n"
            f"3. Recommend pin-compatible Basic library alternatives (e.g. standard 0603/0805 passives, common diodes, standard LDOs).\n"
            f"4. Summarize total potential cost savings for a 5-board prototype run and a 100-board batch run."
        )
        return {
            "description": "PCBA BOM cost reduction and Basic library substitution",
            "messages": [{"role": "user", "content": {"type": "text", "text": user_prompt}}],
        }

    if name == "audit_industrial_compliance":
        netlist_json = arguments.get("netlist_json", "")
        user_prompt = (
            f"You are an Industrial Hardware Quality and Compliance Chief Engineer.\n\n"
            f"Target Netlist to Audit for Industrial Grade Deployment:\n{netlist_json}\n\n"
            f"Please execute the following industrial audit procedure:\n"
            f"1. Run `audit_industrial_dfx` on the netlist to check DFT testpoint matrix, DFA optical fiducials, and EMC/ESD protection.\n"
            f"2. For high-current power traces, use `calculate_ipc2152_trace_current` to verify trace width and temperature rise (ΔT ≤ 20°C).\n"
            f"3. Verify electrical clearances against IPC-2221 Table 6-1 for working supply voltages.\n"
            f"4. Check for TVS diode protection on external exposed ports (USB USBLC6-2SC6, RS-485 SM712, CAN PESD1CAN).\n"
            f"5. Issue a formal Pass/Fail decision with actionable remediation steps for any detected vulnerabilities."
        )
        return {
            "description": "Enterprise-grade industrial compliance review (IPC-2152/2221, DFT, DFA, TVS)",
            "messages": [{"role": "user", "content": {"type": "text", "text": user_prompt}}],
        }

    raise ValueError(f"Unknown prompt: '{name}'")


# --------------------------------------------------------------------------- #
# Main Dispatcher
# --------------------------------------------------------------------------- #


def process_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    # --- 2026-07-28 stateless core ---------------------------------------- #
    # `server/discover` is mandatory in this revision and is also the stdio
    # backward-compatibility probe: a modern client calls it first and only
    # falls back to `initialize` when the method is unknown.
    if method == "server/discover":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": discover_result(_server_version(), DISCOVER_INSTRUCTIONS),
        }

    # A request that declares its protocol version must declare a known one.
    # Legacy callers (no `_meta`) skip this check entirely.
    claimed = requested_version(params)
    if not is_supported(claimed):
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": unsupported_version_error(str(claimed)),
        }

    # Legacy handshake, retained only for clients on pre-2026 revisions.
    if method == "initialize":
        client_version = params.get("protocolVersion")
        # Echo the client's version when we know it, otherwise advertise ours.
        negotiated = client_version if client_version in SUPPORTED_VERSIONS else PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": negotiated,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": server_info(_server_version()),
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": complete({}),
        }

    # --- Tools ---
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": complete(
                with_cache(
                    {"tools": AVAILABLE_TOOLS},
                    ttl_ms=CATALOG_TTL_MS,
                    scope="public",
                )
            ),
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        res = handle_tool_call(tool_name, tool_args)
        # Two output channels per 2026-07-28: `content` for the model,
        # `structuredContent` for programmatic callers. Derived from the same
        # document so the two cannot disagree (see client.structured_output).
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": complete(with_structured_content(res)),
        }

    # --- Resources ---
    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": complete(
                with_cache(
                    {"resources": AVAILABLE_RESOURCES},
                    ttl_ms=CATALOG_TTL_MS,
                    scope="public",
                )
            ),
        }

    if method == "resources/templates/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": complete(
                with_cache(
                    {"resourceTemplates": []},
                    ttl_ms=CATALOG_TTL_MS,
                    scope="public",
                )
            ),
        }

    if method == "resources/read":
        uri = params.get("uri", "")
        try:
            res = handle_resource_read(uri)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": complete(
                    with_cache(res, ttl_ms=RESOURCE_TTL_MS, scope="private")
                ),
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    # -32602 (Invalid Params) since 2026-07-28; the old -32002
                    # resource-not-found code is retired for this purpose.
                    "code": -32602,
                    "message": str(e),
                },
            }

    # --- Prompts ---
    if method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": complete(
                with_cache(
                    {"prompts": AVAILABLE_PROMPTS},
                    ttl_ms=CATALOG_TTL_MS,
                    scope="public",
                )
            ),
        }

    if method == "prompts/get":
        prompt_name = params.get("name", "")
        prompt_args = params.get("arguments", {})
        try:
            res = handle_prompt_get(prompt_name, prompt_args)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": complete(res),
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32602,
                    "message": str(e),
                },
            }

    # Method not found
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
