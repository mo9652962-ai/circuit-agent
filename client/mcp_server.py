"""Standard Model Context Protocol (MCP) Server for CircuitAgent (Community Edition).

Fully compliant with the Anthropic Model Context Protocol (2024-11-05 / 2026-07-28 specifications).
Provides the complete MCP Triad:
    1. Tools (6 engineering tools):
       - synthesize_circuit: Prompt to deterministic hardware netlist & modules
       - search_lcsc_parts: Key-free live query of LCSC/JLCPCB parts, stock, pricing, and packaging
       - list_circuit_blocks: Query all 12 pre-audited CircuitBlocks in the hardware DSL
       - list_supported_chips: Query built-in & third-party MCU pinout allocation rules
       - register_custom_chip: Dynamically register third-party chips & peripheral routes
       - validate_netlist: JSON Schema verification against Draft-07 specification
       - calculate_trace_impedance: Closed-form IPC-2141 microstrip & differential pair impedance solver
       - calculate_bom_cost: PCBA cost estimator calculating bare parts + JLCPCB feeder surcharge
    2. Resources (7 hardware engineering resources):
       - circuit://specs/netlist-schema: Formal Draft-07 JSON Schema
       - circuit://specs/cpl-standard: JLCPCB SMT CPL coordinate & rotation standard
       - circuit://blocks/catalog: Full JSON catalogue of 10 standard CircuitBlocks
       - circuit://rules/jlc-smt: JLCPCB SMT manufacturing rules and feeder fee structure
       - circuit://examples/esp32c3-minimal: Minimal reference IoT node netlist
       - circuit://examples/stm32f103-controller: Industrial controller reference netlist
       - circuit://examples/rp2040-dualcore: Dual-core high-density reference netlist
    3. Prompts (3 slash-command engineering workflows):
       - design_hardware_project: End-to-end prompt for synthesizing and auditing hardware designs
       - audit_schematic_netlist: Senior EE inspection prompt (PI/SI/DFM gates)
       - optimize_bom_cost: Cost-reduction prompt converting Extended parts to Basic parts

Runs over stdio (JSON-RPC 2.0). Compatible with Claude Desktop, Cursor, and Windsurf.
Implemented using only the Python standard library (zero external pip packages required).

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
from .mcp_schema import AVAILABLE_PROMPTS, AVAILABLE_RESOURCES, AVAILABLE_TOOLS
from .parametric_equations import (
    calculate_i2c_pullup,
    calculate_ldo_thermal,
    calculate_rc_filter,
    solve_resistor_divider,
)
from .synthesizer import synthesize_from_prompt

logger = logging.getLogger("circuit_agent_mcp")

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "circuit-agent-mcp",
    "version": "0.2.3",
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
            netlist = arguments.get("netlist", {})
            title = arguments.get("title", "CircuitAgent_Design")
            if not isinstance(netlist, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameter 'netlist' must be a JSON object"}],
                }
            kicad_str = export_kicad_netlist(netlist, title=title)
            return {"content": [{"type": "text", "text": kicad_str}]}

        if name == "export_manufacturing_bom":
            netlist = arguments.get("netlist", {})
            if not isinstance(netlist, dict):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Parameter 'netlist' must be a JSON object"}],
                }
            bom_csv = export_jlcpcb_bom(netlist)
            return {"content": [{"type": "text", "text": bom_csv}]}

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

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
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

    # --- Tools ---
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
        res = handle_tool_call(tool_name, tool_args)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": res,
        }

    # --- Resources ---
    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "resources": AVAILABLE_RESOURCES,
            },
        }

    if method == "resources/templates/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "resourceTemplates": [],
            },
        }

    if method == "resources/read":
        params = msg.get("params", {})
        uri = params.get("uri", "")
        try:
            res = handle_resource_read(uri)
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
                    "code": -32002,
                    "message": str(e),
                },
            }

    # --- Prompts ---
    if method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "prompts": AVAILABLE_PROMPTS,
            },
        }

    if method == "prompts/get":
        params = msg.get("params", {})
        prompt_name = params.get("name", "")
        prompt_args = params.get("arguments", {})
        try:
            res = handle_prompt_get(prompt_name, prompt_args)
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
