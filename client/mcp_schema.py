"""Declarative MCP surface: tools, resources and prompts.

This module is pure data — no logic, no imports beyond the standard library.
Keeping it separate from :mod:`client.mcp_server` means the published MCP
contract (54 tools / 8 resources / 4 prompts) can be reviewed, diffed and
validated on its own, without reading a 1,100-line server implementation.

If you change anything here, update ``README.md`` and ``README_EN.md`` in the
same pull request — the tool and resource counts are documented in both.
"""

from __future__ import annotations

AVAILABLE_TOOLS = [
    {
        "name": "synthesize_circuit",
        "description": (
            "Synthesize a deterministic hardware netlist and component modules from a natural language prompt. "
            "Supported MCUs: STM32F103, ESP32-C3, ESP32-S3, RP2040, STC89C52, CH32V003, STM32G030, ATmega328P. "
            "Peripherals: Type-C, LDO, Crystal, Buttons, LEDs, Buzzer, I2C, RS485, CAN, TP4056 Battery, "
            "AHT20 Temp/Humidity Sensor, MPU6050 6-Axis Motion Sensor."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Natural language circuit description, e.g. '基于 CH32V003 的 AHT20 温湿度与 MPU6050 姿态传感器节点'",
                },
                "chip_id": {
                    "type": "string",
                    "description": "Optional explicit MCU chip model (e.g. 'CH32V003F4P6', 'STM32G030F6P6', 'ATmega328P', 'STM32F103C8T6')",
                },
                "custom_chip": {
                    "type": "object",
                    "description": "Optional third-party chip definition with custom pinout, package, and peripheral multiplexing rules",
                },
                "pin_mapping": {
                    "type": "object",
                    "description": "Optional custom signal-to-pin allocations, e.g. {'/SCL': 'PC2', '/SDA': 'PC1'}",
                },
            },
            "required": ["prompt"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "list_supported_chips",
        "description": "List all registered MCU chips and third-party pinout allocation rules (e.g. CH32V003, STM32G030, ATmega328P).",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "register_custom_chip",
        "description": "Register or dynamically override a third-party microcontroller pinout and peripheral multiplexing rule.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Unique identifier, e.g. 'CH32V003F4P6'"},
                "mcu_family": {"type": "string", "description": "MCU family, e.g. 'QingKe-RISC-V', 'ARM-Cortex-M0+'"},
                "package": {"type": "string", "description": "Physical package, e.g. 'TSSOP-20', 'QFN-32'"},
                "supply_voltage": {"type": "number", "description": "Operating voltage (typically 3.3 or 5.0)"},
                "pins": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of available GPIO and power pins",
                },
                "pin_numbers": {
                    "type": "object",
                    "description": "Map of pin names to physical pin numbers, e.g. {'PD1': '8'}",
                },
                "reserved_pins": {
                    "type": "object",
                    "description": "Map of reserved pins and reasons, e.g. {'PD1': 'SWDIO', 'NRST': 'RESET'}",
                },
                "peripheral_routes": {
                    "type": "object",
                    "description": "Peripheral routing defaults, e.g. {'I2C1': {'I2C_SCL': 'PC2', 'I2C_SDA': 'PC1'}}",
                },
                "default_gpio_assignments": {
                    "type": "object",
                    "description": "Default signal mappings, e.g. {'/LED1': 'PD4'}",
                },
                "description": {"type": "string", "description": "Human-readable description of the chip"},
            },
            "required": ["chip_id", "pins"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
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
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "list_circuit_blocks",
        "description": "List all 10 pre-validated CircuitBlocks available in the hardware DSL catalog.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "run_erc",
        "description": (
            "Run deterministic Electrical Rules Check (ERC) on a netlist: floating nets, missing GND, "
            "unknown designators, missing power domain, missing decoupling. Every finding carries "
            "severity + source; blocking/error issues gate BOM/CPL delivery."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["netlist"],
            "properties": {
                "netlist": {
                    "type": "object",
                    "description": "Netlist dict with 'connections' (synthesize_circuit output passes directly).",
                },
                "modules": {
                    "type": "object",
                    "description": "Optional modules dict (ref -> {kind, value, package, lcsc}) for component-aware rules.",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
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
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_trace_impedance",
        "description": (
            "Calculate characteristic impedance (Z0) or differential impedance (Zdiff) for PCB microstrip traces "
            "using IPC-2141 / Wheeler equations. Solves exact trace width W and spacing S for target impedance (e.g. 50Ω RF, 90Ω USB, 120Ω RS485/CAN)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["mode", "target_z"],
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["single", "differential"],
                    "description": "Trace mode: 'single' for single-ended microstrip, 'differential' for edge-coupled microstrip pair.",
                },
                "target_z": {
                    "type": "number",
                    "description": "Target impedance in ohms (e.g. 50.0 for single-ended, 90.0 for USB differential, 120.0 for CAN/RS485).",
                },
                "dielectric_h_mm": {
                    "type": "number",
                    "description": "Dielectric height between trace and reference ground plane in mm (default: 0.1mm for JLC04161H 4-layer).",
                    "default": 0.1,
                },
                "dielectric_er": {
                    "type": "number",
                    "description": "Relative dielectric permittivity (Er) (default: 4.2 for FR4).",
                    "default": 4.2,
                },
                "trace_thickness_mm": {
                    "type": "number",
                    "description": "Finished copper thickness in mm (default: 0.035mm for 1oz copper).",
                    "default": 0.035,
                },
                "trace_gap_mm": {
                    "type": "number",
                    "description": "Spacing between differential traces in mm (only used in differential mode, default: 0.15mm).",
                    "default": 0.15,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_bom_cost",
        "description": (
            "Calculate PCBA component cost breakdown and estimate JLCPCB SMT manufacturing surcharges. "
            "Identifies Basic library parts (¥0 feeder fee) vs Extended library parts (+¥20/type feeder fee) and suggests cost optimizations."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["queries"],
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of component names, models, or descriptions (e.g. ['STM32F103C8T6', 'SP3485', '0603 10k']).",
                }
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "calculate_ipc2152_trace_current",
        "description": (
            "Calculate conductor current-carrying capacity or solve required PCB trace width "
            "according to IPC-2152 standards for given copper weight (oz), temperature rise (ΔT °C), and layer position."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["mode"],
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["solve_current", "solve_width"],
                    "description": "'solve_current' calculates max Amps for given trace_width_mm; 'solve_width' calculates required mm for target_current_a.",
                },
                "trace_width_mm": {
                    "type": "number",
                    "description": "Trace width in mm (required for 'solve_current').",
                },
                "target_current_a": {
                    "type": "number",
                    "description": "Target continuous current in Amperes (required for 'solve_width').",
                },
                "copper_oz": {
                    "type": "number",
                    "description": "Finished copper thickness in ounces (default: 1.0 oz = 35 um).",
                    "default": 1.0,
                },
                "temp_rise_c": {
                    "type": "number",
                    "description": "Allowable conductor temperature rise above ambient in °C (default: 20.0 °C).",
                    "default": 20.0,
                },
                "layer": {
                    "type": "string",
                    "enum": ["external", "internal"],
                    "description": "Conductor layer position: 'external' (outer copper) or 'internal' (inner plane).",
                    "default": "external",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "audit_industrial_dfx",
        "description": (
            "Execute an enterprise-grade DFX (DFM/DFA/DFT/DFC/EMC) compliance audit on a schematic netlist. "
            "Verifies optical fiducials (MARK points), ICT testpoint coverage on power/debug rails, "
            "IEC 61000-4-2 TVS surge protection on exposed ports (USB, RS485, CAN), reverse polarity protection, and SMT costs."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["netlist"],
            "properties": {
                "netlist": {
                    "type": "object",
                    "description": "Hardware netlist dictionary containing 'components' and 'connections'.",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_kicad_netlist",
        "description": "Export standard KiCad S-Expression netlist (.net) compatible with KiCad 6/7/8/9/10 Pcbnew.",
        "inputSchema": {
            "type": "object",
            "required": ["netlist"],
            "properties": {
                "netlist": {"type": "object", "description": "Hardware netlist dictionary or synthesis result."},
                "title": {
                    "type": "string",
                    "description": "Schematic / board project title.",
                    "default": "CircuitAgent_Design",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_manufacturing_bom",
        "description": "Generate production-ready JLCPCB SMT BOM CSV with part grouping, designator aggregation, and Basic/Extended classification.",
        "inputSchema": {
            "type": "object",
            "required": ["netlist"],
            "properties": {
                "netlist": {"type": "object", "description": "Hardware netlist dictionary or synthesis result."},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_manufacturing_cpl",
        "description": "Generate the JLCPCB SMT pick-and-place (CPL/pos) file with designator, centre X/Y in mm, layer and rotation. Required alongside the BOM for assembly: a part in the BOM but absent here is purchased and never soldered.",
        "inputSchema": {
            "type": "object",
            "required": ["netlist"],
            "properties": {
                "netlist": {"type": "object", "description": "Hardware netlist dictionary or synthesis result."},
                "default_layer": {
                    "type": "string",
                    "description": "Layer to assign when the netlist does not specify one (default 'Top').",
                    "default": "Top",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_parametric_circuit",
        "description": "Solve discrete parametric circuit equations: optimal E96 resistor dividers, LDO thermal dissipation, I2C bus pullups, or RC filters.",
        "inputSchema": {
            "type": "object",
            "required": ["type", "params"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["resistor_divider", "ldo_thermal", "i2c_pullup", "rc_filter"],
                    "description": "Type of parametric calculation to perform.",
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Calculation arguments: for 'resistor_divider' (v_in, v_out_target, max_quiescent_current_ma); "
                        "for 'ldo_thermal' (v_in, v_out, i_load_a, package); "
                        "for 'i2c_pullup' (v_cc, bus_capacitance_pf, mode); "
                        "for 'rc_filter' (cutoff_freq_hz, r_ohm, c_f)."
                    ),
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "render_circuit_topology",
        "description": "Render a clean, structured ASCII architectural diagram of power domains, buses, and connected subsystems.",
        "inputSchema": {
            "type": "object",
            "required": ["netlist"],
            "properties": {
                "netlist": {"type": "object", "description": "Hardware netlist dictionary or synthesis result."},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "analyze_power_tree",
        "description": (
            "Analyze system-level power distribution architecture, load current budgets (typical & peak mA), "
            "regulator dropout headroom, and LDO thermal dissipation / junction temperature estimates."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules", "netlist"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "netlist": {
                    "type": "object",
                    "description": "Netlist dict with 'connections' (from synthesize_circuit output).",
                },
                "ambient_temp_c": {
                    "type": "number",
                    "description": "Operating ambient temperature in °C (default: 25.0).",
                    "default": 25.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_ipc2221_clearance",
        "description": (
            "Calculate minimum electrical clearance (conductor spacing) according to IPC-2221B Table 6-1 "
            "based on peak voltage and conductor classification (B1 internal, B2 external uncoated, B4 coated, A6 leads)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["peak_voltage_v"],
            "properties": {
                "peak_voltage_v": {
                    "type": "number",
                    "description": "Peak working or test voltage in Volts (e.g., 5.0, 12.0, 24.0, 230.0).",
                },
                "conductor_type": {
                    "type": "string",
                    "enum": ["B1", "B2", "B4", "A6"],
                    "description": "Conductor classification: B1 (internal), B2 (external uncoated), B4 (coated), A6 (leads). Default: B2.",
                    "default": "B2",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_specctra_dsn",
        "description": (
            "Generate universal Specctra DSN (v15.0) auto-router interchange file for automated PCB track routing "
            "in Freerouting, Cadence Specctra, Altium, or KiCad. Includes heuristic component auto-placement."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules", "netlist"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "netlist": {
                    "type": "object",
                    "description": "Netlist dict with 'connections' (from synthesize_circuit output).",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
                "trace_width_mm": {
                    "type": "number",
                    "description": "Default routing trace width in mm (default: 0.254 / 10mil).",
                    "default": 0.254,
                },
                "clearance_mm": {
                    "type": "number",
                    "description": "Default routing clearance in mm (default: 0.200 / 8mil).",
                    "default": 0.200,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "autoroute_pcb",
        "description": (
            "Execute automated native PCB layout and multi-layer track routing on circuit specifications. "
            "Generates standard Specctra SES (Session) routing data and comprehensive physical metrics "
            "(completion rate, total track length, via count, layer utilization) with zero JVM dependencies."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules", "netlist"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "netlist": {
                    "type": "object",
                    "description": "Netlist dict with 'connections' (from synthesize_circuit output).",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
                "trace_width_mm": {
                    "type": "number",
                    "description": "Default routing trace width in mm (default: 0.150 / 6mil).",
                    "default": 0.150,
                },
                "clearance_mm": {
                    "type": "number",
                    "description": "Default routing clearance in mm (default: 0.100 / 4mil).",
                    "default": 0.100,
                },
                "engine": {
                    "type": "string",
                    "description": (
                        "Autorouting engine track. 'exact' (default) is orthogonal and DRC-verified; "
                        "'grid' is 8-connected and can leave diagonal shorts; 'room' uses continuous "
                        "expansion rooms (may leave nets unrouted on dense boards)."
                    ),
                    "default": "exact",
                    "enum": ["grid", "exact", "room"],
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_kicad_schematic",
        "description": (
            "Export modern KiCad 8/9 S-Expression schematic file (.kicad_sch) directly viewable and editable "
            "in KiCad Eeschema with sheet layout, component symbols, pin references, and LCSC attributes."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "connections": {"type": "array", "description": "Netlist connections list (optional).", "default": []},
                "title": {
                    "type": "string",
                    "description": "Schematic sheet title block title.",
                    "default": "Hardware Design",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "audit_supply_chain",
        "description": (
            "Audit BOM component multi-sourcing resilience (ISO 9001 supply chain audit), identifying single-source "
            "bottlenecks and mapping pin-compatible second-source drop-in replacements with LCSC cross-references."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_differential_skew",
        "description": (
            "Solve high-speed differential pair intra-pair propagation delay skew (USB 2.0 HS ≤10ps, Ethernet ≤25ps, CAN-FD ≤50ps) "
            "and calculate required serpentine length matching tuning bumps count and geometry."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["trace_length_delta_mm"],
            "properties": {
                "trace_length_delta_mm": {
                    "type": "number",
                    "description": "Measured trace length mismatch in mm (P minus N).",
                },
                "protocol": {
                    "type": "string",
                    "enum": ["USB2_HS", "USB2_FS", "ETH_100M", "CAN_FD", "RS485"],
                    "description": "Target protocol standard (default: USB2_HS).",
                    "default": "USB2_HS",
                },
                "dielectric_er": {
                    "type": "number",
                    "description": "Relative dielectric permittivity Er (default: 4.2).",
                    "default": 4.2,
                },
                "trace_width_mm": {
                    "type": "number",
                    "description": "Trace width in mm (default: 0.254).",
                    "default": 0.254,
                },
                "height_mm": {
                    "type": "number",
                    "description": "Dielectric height to reference plane in mm (default: 0.100).",
                    "default": 0.100,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_ipc_d356",
        "description": (
            "Generate universal IPC-D-356A ASCII bare-board electrical test netlist file for flying probe testers "
            "(AEMG, ATG, MicroCraft) and bed-of-nails PCB fabrication test fixtures."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules", "netlist"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "netlist": {
                    "type": "object",
                    "description": "Netlist dict with 'connections' (from synthesize_circuit output).",
                },
                "job_name": {
                    "type": "string",
                    "description": "Fabrication PCB job name.",
                    "default": "CIRCUIT_AGENT_PCB",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "Board width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "Board height in mm (default: 50.0).",
                    "default": 50.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_gerber_bundle",
        "description": (
            "Generate native fabrication-ready Gerber RS-274X + Excellon bundle (Edge_Cuts .gm1, Top/Bottom "
            "Copper .gtl/.gbl, Top/Bottom Mask .gts/.gbs, Top Silkscreen .gto, drill .drl) directly from placed "
            "modules and netlist, eliminating GUI EDA dependency. Copper layers carry real footprint pads and the "
            "autorouter's actual track geometry."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules", "netlist"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "netlist": {
                    "type": "object",
                    "description": "Netlist dict with 'connections' (from synthesize_circuit output).",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
                "autoroute": {
                    "type": "boolean",
                    "description": (
                        "Run the autorouter first so the copper layers carry real tracks (default: true). "
                        "Set false to export pads only, i.e. an unrouted board."
                    ),
                    "default": True,
                },
                "ses_text": {
                    "type": "string",
                    "description": (
                        "Optional Specctra SES session text from a previous autoroute_pcb call. "
                        "Overrides 'autoroute' and avoids routing twice."
                    ),
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_pcb_stackup_impedance",
        "description": (
            "Lookup standard industrial 4-layer (JLC04161H) and 6-layer (JLC06161H) PCB stackup matrices and solve "
            "target controlled impedance trace widths (50Ω RF, 90Ω USB, 100Ω Ethernet, 120Ω CAN/485, IPC-2141A)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "stackup_id": {
                    "type": "string",
                    "enum": ["JLC04161H", "JLC06161H"],
                    "description": "Standard industrial stackup model (default: JLC04161H).",
                    "default": "JLC04161H",
                },
                "solve_custom_z_ohms": {
                    "type": "number",
                    "description": "Optional custom single-ended target impedance in Ohms to solve required trace width.",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_excellon_drill",
        "description": (
            "Generate production IPC-NC-349 Excellon CNC drill file (.drl) with metric tool headers (T01C... T02C...), "
            "completing the 5-layer PCB manufacturing bundle for automated CNC drilling machines."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "connections": {"type": "array", "description": "Netlist connections list (optional).", "default": []},
                "job_name": {
                    "type": "string",
                    "description": "PCB fabrication job name.",
                    "default": "CIRCUIT_AGENT_PCB",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "generate_interactive_bom",
        "description": (
            "Generate a lightweight self-contained single-file Interactive HTML BOM (iBOM, InteractiveHtmlBom-compatible) "
            "with interactive component grouping table, vector SVG board map, and bidirectional hover/click inspection."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "title": {
                    "type": "string",
                    "description": "Inspection page title.",
                    "default": "PCBA First Article Assembly Inspection",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_smt_feeder_matrix",
        "description": (
            "Optimize SMT pick-and-place feeder slot allocation (8mm/12mm/16mm/24mm) and nozzle tooling selection "
            "(502/503/504/505/506) according to EIA-481 carrier tape standard and OpenPnP/Juki machine matrices."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_openpnp_job",
        "description": (
            "Generate production OpenPnP and industrial SMT pick-and-place board job CSV (part, designator, X/Y coords, "
            "rotation, nozzle ID, feeder slot assignment) for automated robotic assembly."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_ipc7351_land_pattern",
        "description": (
            "Calculate mathematically compliant surface mount land pattern geometry (pad width X, pad length Y, "
            "pad center distance C, and courtyard boundary bounds) based on IPC-7351B standards across "
            "Density Levels A (Most), B (Nominal), and C (Least)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["package"],
            "properties": {
                "package": {
                    "type": "string",
                    "description": "Standard footprint name (e.g. '0805', '0603', 'SOIC-8', 'QFN-32', 'TSSOP-14') or custom.",
                },
                "density": {
                    "type": "string",
                    "description": "IPC-7351B Density Level: 'A' (Most/M), 'B' (Nominal/N, default), or 'C' (Least/L).",
                    "default": "B",
                },
                "lead_type": {
                    "type": "string",
                    "description": "Component lead style: 'chip', 'gullwing', 'no_lead' (QFN/DFN), or 'j_lead'.",
                },
                "overall_length_l": {
                    "type": "number",
                    "description": "Optional component overall tip-to-tip span (mm).",
                },
                "lead_width_w": {
                    "type": "number",
                    "description": "Optional component lead width (mm).",
                },
                "lead_contact_t": {
                    "type": "number",
                    "description": "Optional component lead contact length/band (mm).",
                },
                "lead_pitch": {
                    "type": "number",
                    "description": "Optional pin center-to-center pitch (mm) for multi-lead packages.",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_pcb_panel_rails",
        "description": (
            "Calculate SMT automated assembly panel frame with breakaway process rails, conveyor clamp clearances, "
            "SMEMA tooling holes (NPTH Φ3.2mm), optical fiducials (Φ1.0mm/Φ3.0mm mask), and de-paneling features "
            "(V-Cut score lines or perforated mouse-bites) per IPC-2221B Section 8.4 and IPC-SMEMA-9851."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["board_width_mm", "board_height_mm"],
            "properties": {
                "board_width_mm": {
                    "type": "number",
                    "description": "Single PCB outline width (mm).",
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "Single PCB outline height (mm).",
                },
                "grid_x": {
                    "type": "integer",
                    "description": "Number of boards in X direction (default: 2).",
                    "default": 2,
                },
                "grid_y": {
                    "type": "integer",
                    "description": "Number of boards in Y direction (default: 2).",
                    "default": 2,
                },
                "depaneling_method": {
                    "type": "string",
                    "description": "De-paneling method: 'v_cut' (default) or 'mouse_bites'.",
                    "default": "v_cut",
                },
                "rail_width_mm": {
                    "type": "number",
                    "description": "Conveyor clamping rail width in mm (default: 5.0, min: 3.0 per SMEMA).",
                    "default": 5.0,
                },
                "board_spacing_mm": {
                    "type": "number",
                    "description": "Spacing between individual boards in mm (default: 0 for V-cut, 2.0 for mouse-bites).",
                },
                "rail_sides": {
                    "type": "string",
                    "description": "Rail placement: 'left_right' (default), 'top_bottom', or 'all_four'.",
                    "default": "left_right",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_ict_testpoints",
        "description": (
            "Analyze PCB netlist testability, allocate automated bed-of-nails In-Circuit Test (ICT) testpoints (B.Cu Φ1.0mm), "
            "assign probe tip types (crown, spear, serrated), and verify fault coverage percentage per IPC-9252 & IPC-2221B."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["connections"],
            "properties": {
                "connections": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Netlist connections list (from synthesize_circuit output).",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
                "min_pad_diameter_mm": {
                    "type": "number",
                    "description": "Testpad diameter in mm (default: 1.0).",
                    "default": 1.0,
                },
                "min_probe_pitch_mm": {
                    "type": "number",
                    "description": "Minimum probe center-to-center pitch in mm (default: 2.0).",
                    "default": 2.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_bga_escape_routing",
        "description": (
            "Calculate BGA diagonal dogbone via fanout geometry, escape channel trace widths and clearances, "
            "and minimum signal layer requirements per IPC-7095 Section 5.2."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["ball_count"],
            "properties": {
                "ball_count": {
                    "type": "integer",
                    "description": "Total BGA ball count (e.g. 64, 100, 144, 256).",
                    "default": 64,
                },
                "ball_pitch_mm": {
                    "type": "number",
                    "description": "BGA ball center-to-center pitch in mm (default: 0.8).",
                    "default": 0.8,
                },
                "ball_pad_dia_mm": {
                    "type": "number",
                    "description": "BGA solder ball pad diameter in mm (default: 0.4).",
                    "default": 0.4,
                },
                "via_drill_mm": {
                    "type": "number",
                    "description": "Fanout via drill diameter in mm (default: 0.2).",
                    "default": 0.2,
                },
                "via_pad_dia_mm": {
                    "type": "number",
                    "description": "Fanout via pad outer diameter in mm (default: 0.45).",
                    "default": 0.45,
                },
                "trace_width_mm": {
                    "type": "number",
                    "description": "Escape routing neck-down trace width in mm (default: 0.10).",
                    "default": 0.10,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_teardrop_reinforcement",
        "description": (
            "Calculate tangent teardrop fillets for PCB vias, circular pads, and testpoints to prevent drill breakout, "
            "eliminate mechanical/thermal crack stress, and comply with IPC-2221B Section 9.1.5 and IPC-A-600J Class 3."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["vias"],
            "properties": {
                "vias": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of via objects ({'x_mm', 'y_mm', 'pad_dia_mm', 'drill_dia_mm', 'trace_angle_deg'}).",
                },
                "default_trace_width_mm": {
                    "type": "number",
                    "description": "Default trace width in mm (default: 0.20).",
                    "default": 0.20,
                },
                "teardrop_style": {
                    "type": "string",
                    "description": "Fillet geometry: 'curved' (default) or 'linear'.",
                    "default": "curved",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_copper_thieving_balance",
        "description": (
            "Calculate layer copper density balance between top and bottom layers, assess reflow thermal bow/twist "
            "warpage risk (IPC-TM-650 2.4.22 <= 0.75%), and generate non-functional dummy copper thieving dot/grid patterns "
            "per IPC-2221B Section 10.1.1."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["board_width_mm", "board_height_mm"],
            "properties": {
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                },
                "top_copper_area_mm2": {
                    "type": "number",
                    "description": "Optional top copper area in mm².",
                },
                "bot_copper_area_mm2": {
                    "type": "number",
                    "description": "Optional bottom copper area in mm².",
                },
                "keepout_margin_mm": {
                    "type": "number",
                    "description": "Keepout margin from board edge in mm (default: 2.0).",
                    "default": 2.0,
                },
                "pattern_pitch_mm": {
                    "type": "number",
                    "description": "Thieving dot pitch in mm (default: 2.54).",
                    "default": 2.54,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_via_stitching_array",
        "description": (
            "Calculate thermal via matrix array under QFN/power exposed pads (IPC-7093 Section 7.2) or RF ground "
            "shielding fence via arrays (IPC-2141A <= lambda/10 pitch) with thermal resistance reduction metrics."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pad_width_mm": {
                    "type": "number",
                    "description": "Exposed pad width in mm (default: 5.0).",
                    "default": 5.0,
                },
                "pad_height_mm": {
                    "type": "number",
                    "description": "Exposed pad height in mm (default: 5.0).",
                    "default": 5.0,
                },
                "center_x_mm": {
                    "type": "number",
                    "description": "Center X coordinate in mm (default: 0.0).",
                    "default": 0.0,
                },
                "center_y_mm": {
                    "type": "number",
                    "description": "Center Y coordinate in mm (default: 0.0).",
                    "default": 0.0,
                },
                "drill_dia_mm": {
                    "type": "number",
                    "description": "Via drill diameter in mm (default: 0.30).",
                    "default": 0.30,
                },
                "grid_pitch_mm": {
                    "type": "number",
                    "description": "Via center-to-center pitch in mm (default: 1.20).",
                    "default": 1.20,
                },
                "is_rf_shielding_fence": {
                    "type": "boolean",
                    "description": "Whether to generate dual-side ground shielding fence for RF microstrip (default: false).",
                    "default": False,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_serpentine_tuning_geometry",
        "description": (
            "Calculate high-speed differential pair serpentine delay tuning meander geometry, ensuring self-coupling "
            "suppression (S >= 3W, H >= 3W) and generating vertex paths per IPC-2141A Section 5.3."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["delta_length_mm"],
            "properties": {
                "delta_length_mm": {
                    "type": "number",
                    "description": "Target added delay length in mm (e.g. 3.5).",
                },
                "trace_width_mm": {
                    "type": "number",
                    "description": "Trace width in mm (default: 0.15).",
                    "default": 0.15,
                },
                "start_x_mm": {
                    "type": "number",
                    "description": "Start X coordinate in mm (default: 10.0).",
                    "default": 10.0,
                },
                "start_y_mm": {
                    "type": "number",
                    "description": "Start Y coordinate in mm (default: 20.0).",
                    "default": 20.0,
                },
                "end_x_mm": {
                    "type": "number",
                    "description": "End X coordinate in mm (default: 30.0).",
                    "default": 30.0,
                },
                "end_y_mm": {
                    "type": "number",
                    "description": "End Y coordinate in mm (default: 20.0).",
                    "default": 20.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_stencil_aperture_ratios",
        "description": (
            "Evaluate SMT stencil aperture area ratio (>= 0.66 laser-cut) and aspect ratio (>= 1.5) compliance "
            "per IPC-7525 Stencil Design Guidelines, identifying paste-release-deficient apertures."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["apertures"],
            "properties": {
                "apertures": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of apertures ({ref, shape: 'rect'|'circle', width_mm, length_mm}).",
                },
                "foil_thickness_um": {
                    "type": "number",
                    "description": "Stencil foil thickness in μm (default: 100).",
                    "default": 100,
                },
                "min_area_ratio": {
                    "type": "number",
                    "description": "Minimum acceptable area ratio (default: 0.66).",
                    "default": 0.66,
                },
                "min_aspect_ratio": {
                    "type": "number",
                    "description": "Minimum acceptable aspect ratio (default: 1.5).",
                    "default": 1.5,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_fiducial_layout",
        "description": (
            "Generate asymmetric 3-point global optical fiducial layout (L-shape, 180° rotation unambiguous) and "
            "2-point local fiducials for fine-pitch components per IPC-2221B Section 12 and JEDEC J-STD-020."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["board_width_mm", "board_height_mm"],
            "properties": {
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm.",
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm.",
                },
                "fine_pitch_components": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Fine-pitch components ({ref, pitch_mm, x_mm, y_mm, half_diagonal_mm}).",
                },
                "edge_clearance_mm": {
                    "type": "number",
                    "description": "Fiducial center clearance from board edge in mm (default: 5.0).",
                    "default": 5.0,
                },
                "fine_pitch_threshold_mm": {
                    "type": "number",
                    "description": "Component pitch below which local fiducials are required (default: 0.5).",
                    "default": 0.5,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_via_protection_plan",
        "description": (
            "Select IPC-4761 via protection types (Type I ~ VII) per via assembly context: Type VII filled-and-capped "
            "(VIPPO) mandatory for BGA via-in-pad, Type V fill for thermal pads, Type IV tent+plug for BGA channels, "
            "Type II tent for free vias."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["vias"],
            "properties": {
                "vias": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Via list ({id, in_pad, land_type: 'bga'|'thermal'|'signal', in_bga_pitch, vippo_filled}).",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_solder_paste_volume",
        "description": (
            "Assess per-aperture deposited solder paste volume against target joint volume per IPC-7525A transfer "
            "analysis (accepted ratio window 1.0 ~ 2.5), flagging starved joints and excessive paste defects."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["apertures"],
            "properties": {
                "apertures": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Aperture list ({ref, shape: 'rect'|'circle', width_mm, length_mm}).",
                },
                "foil_thickness_um": {
                    "type": "number",
                    "description": "Stencil foil thickness in μm (default: 100).",
                    "default": 100,
                },
                "transfer_efficiency": {
                    "type": "number",
                    "description": "Paste transfer efficiency η (default: 0.90; nano-coated laser-cut foil).",
                    "default": 0.90,
                },
                "target_standoff_mm": {
                    "type": "number",
                    "description": "Target solder standoff height in mm (default: 0.10).",
                    "default": 0.10,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_ipc2581",
        "description": (
            "Export a simplified IPC-2581B single-file intelligent fabrication data package (XML) — stackup, BOM, "
            "placed components, nets with pin membership, and board profile — replacing the legacy "
            "Gerber+Excellon+TXT handoff bundle accepted by Siemens X / Altium / Zuken / EMS houses."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "connections": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Netlist connections list.",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
                "stackup_layers": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional stackup layers ({name, class: 'CONDUCTOR'|'DIELECTRIC', thickness_um, material}).",
                },
                "project_name": {
                    "type": "string",
                    "description": "Project/organization name embedded in the XML (default: HARDWARE_PROJECT).",
                    "default": "HARDWARE_PROJECT",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_assembly_drawing_svg",
        "description": (
            "Generate a scaled PCBA assembly drawing SVG per ASME Y14.5 and IPC-2221B Section 11: body outlines with "
            "refDes labels, polarity marks (pin-1 dots, cathode bars, plus frames), mirrored bottom view, and an "
            "ASME Y14.100 title block with revision and check signature."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output, with positions).",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
                "mirrored_bottom": {
                    "type": "boolean",
                    "description": "Render bottom view mirrored in X (default: true).",
                    "default": True,
                },
                "title": {
                    "type": "string",
                    "description": "Drawing title (default: PCBA ASSEMBLY DRAWING).",
                    "default": "PCBA ASSEMBLY DRAWING",
                },
                "revision": {
                    "type": "string",
                    "description": "Drawing revision letter (default: A).",
                    "default": "A",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "diff_netlists",
        "description": (
            "Engineering Change Order (ECO) netlist diff: compare two netlist revisions and report added/removed "
            "components, value/package changes, added/removed nets, pin membership moves, total change count, and "
            "ECO severity (NONE / MINOR / MAJOR) for PLM change management."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["old_modules", "old_connections", "new_modules", "new_connections"],
            "properties": {
                "old_modules": {
                    "type": "object",
                    "description": "Revision A component modules dict.",
                },
                "old_connections": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Revision A connections list.",
                },
                "new_modules": {
                    "type": "object",
                    "description": "Revision B component modules dict.",
                },
                "new_connections": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Revision B connections list.",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "generate_assembly_process_plan",
        "description": (
            "Generate a mixed-assembly process route plan: classify each component into SMD reflow / THT wave / "
            "THT manual / mechanical stages per IPC-A-610G Section 7, output the 10-stage EMS routing "
            "(SPI -> reflow -> AOI -> THT insert -> wave -> manual -> ICT -> FCT -> coating -> packing)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "optimize_panel_grid",
        "description": (
            "Enumerate panel grid combinations (grid_x x grid_y, rail sides, V-cut vs mouse-bites), filter options "
            "exceeding the max panel size (default 300x300mm fab limit), and rank feasible layouts by material "
            "utilization percentage."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["board_width_mm", "board_height_mm"],
            "properties": {
                "board_width_mm": {
                    "type": "number",
                    "description": "Single board width in mm.",
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "Single board height in mm.",
                },
                "max_grid": {
                    "type": "integer",
                    "description": "Maximum grid count per axis (default: 4).",
                    "default": 4,
                },
                "max_panel_mm": {
                    "type": "number",
                    "description": "Maximum panel dimension in mm (default: 300.0).",
                    "default": 300.0,
                },
                "rail_width_mm": {
                    "type": "number",
                    "description": "Conveyor rail width in mm (default: 5.0).",
                    "default": 5.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_fab_cost",
        "description": (
            "Estimate PCB fabrication cost from fab-house published tiered pricing: layers (2/4/6), quantity tiers "
            "(5/10/30/100), area surcharge beyond 100x100mm, solder mask color, surface finish (HASL/ENIG/OSP), "
            "board thickness, and lead time (normal/48h/24h). Estimate only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "layers": {
                    "type": "integer",
                    "description": "Layer count (2, 4, or 6; default 4).",
                    "default": 4,
                },
                "quantity": {
                    "type": "integer",
                    "description": "Board quantity (default 5).",
                    "default": 5,
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "Board width in mm (default 100).",
                    "default": 100.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "Board height in mm (default 100).",
                    "default": 100.0,
                },
                "solder_mask_color": {
                    "type": "string",
                    "description": "Solder mask color: green (free), red/yellow/blue (+25), black/white (+40), matte (+60).",
                    "default": "green",
                },
                "surface_finish": {
                    "type": "string",
                    "description": "Surface finish: hasl_lead (free), hasl_lead_free (+15), enig (+80), osp (free), silver (+45).",
                    "default": "hasl_lead_free",
                },
                "thickness_mm": {
                    "type": "string",
                    "description": "Board thickness in mm: 0.6/0.8/1.0/1.2/1.6 (default)/2.0.",
                    "default": "1.6",
                },
                "lead_time": {
                    "type": "string",
                    "description": "Lead time: normal (x1.0), fast_48h (x1.5), urgent_24h (x2.5).",
                    "default": "normal",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_smt_placement_clearance",
        "description": (
            "Analyze SMT pick-and-place nozzle collision clearance between tall (H >= 4.0mm) and low components, "
            "evaluate nozzle keepout envelopes (min 2.0mm horizontal gap), and generate layered placement priority "
            "sequences (lowest to tallest) per IPC-SM-782 and OpenPnP guidelines."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output, with positions).",
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "Board width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "Board height in mm (default: 50.0).",
                    "default": 50.0,
                },
                "min_tall_component_height_mm": {
                    "type": "number",
                    "description": "Threshold height for tall components in mm (default: 4.0).",
                    "default": 4.0,
                },
                "min_clearance_envelope_mm": {
                    "type": "number",
                    "description": "Minimum required horizontal clearance between tall and low components (default: 2.0).",
                    "default": 2.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_creepage_isolation_slot",
        "description": (
            "Evaluate high-voltage electrical creepage compliance per IPC-2221B Table 6-1 and IEC 62368-1, "
            "and plan an air isolation milled slot (slot width, length, endpoints, and expanded effective creepage path) "
            "between high-voltage and low-voltage conductors when surface distance is insufficient."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["voltage_v", "cond1_coords", "cond2_coords"],
            "properties": {
                "voltage_v": {
                    "type": "number",
                    "description": "Operating voltage difference between conductors (e.g. 220.0).",
                },
                "cond1_coords": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Coordinates [x, y] of first conductor.",
                },
                "cond2_coords": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Coordinates [x, y] of second conductor.",
                },
                "conductor_radius_mm": {
                    "type": "number",
                    "description": "Conductor/pad radius in mm (default: 1.0).",
                    "default": 1.0,
                },
                "slot_width_mm": {
                    "type": "number",
                    "description": "Width of milled isolation slot in mm (default: 1.2).",
                    "default": 1.2,
                },
                "slot_extension_mm": {
                    "type": "number",
                    "description": "Slot extension past conductor edges in mm (default: 2.0).",
                    "default": 2.0,
                },
                "is_reinforced_insulation": {
                    "type": "boolean",
                    "description": "Whether reinforced insulation (2x clearance) is required per IEC 62368-1 (default: false).",
                    "default": False,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "analyze_impedance_tolerance",
        "description": (
            "Analyze PCB characteristic impedance manufacturing tolerance window and sensitivities per IPC-2141A "
            "and Polar SI9000 models: evaluates dielectric height (+-10%), trace width (+-10%), copper thickness (+-15%), "
            "and Er (+-5%) cumulative variations, calculating Zmin, Zmax, dZ/dW, dZ/dH, and yield within +-10% target."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_z0_ohms": {
                    "type": "number",
                    "description": "Target characteristic impedance (default: 50.0).",
                    "default": 50.0,
                },
                "trace_width_mm": {
                    "type": "number",
                    "description": "Nominal trace width in mm (default: 0.38).",
                    "default": 0.38,
                },
                "dielectric_height_mm": {
                    "type": "number",
                    "description": "Nominal dielectric height in mm (default: 0.20).",
                    "default": 0.20,
                },
                "copper_thickness_mm": {
                    "type": "number",
                    "description": "Nominal copper thickness in mm (default: 0.035 for 1oz).",
                    "default": 0.035,
                },
                "dielectric_er": {
                    "type": "number",
                    "description": "Substrate dielectric constant (default: 4.2 for FR-4).",
                    "default": 4.2,
                },
                "width_tolerance_pct": {
                    "type": "number",
                    "description": "Trace width tolerance percentage (default: 10.0).",
                    "default": 10.0,
                },
                "height_tolerance_pct": {
                    "type": "number",
                    "description": "Dielectric height tolerance percentage (default: 10.0).",
                    "default": 10.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "evaluate_material_cti_creepage",
        "description": (
            "Evaluate substrate Comparative Tracking Index (CTI) Material Group (Group I >= 600V to Group IIIb) "
            "and required safety creepage under Pollution Degrees 1/2/3 and Basic/Reinforced insulation per "
            "IEC 62368-1 Table 25 and IPC-2221B, calculating safety margins and recommending high-CTI laminates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "working_voltage_v": {
                    "type": "number",
                    "description": "Operating rms/DC voltage (default: 220.0).",
                    "default": 220.0,
                },
                "actual_clearance_mm": {
                    "type": "number",
                    "description": "Actual physical conductor spacing in mm (default: 2.0).",
                    "default": 2.0,
                },
                "substrate_cti_v": {
                    "type": "number",
                    "description": "Substrate CTI rating in Volts (default: 175.0 for standard FR-4; 600.0 for Group I).",
                    "default": 175.0,
                },
                "pollution_degree": {
                    "type": "integer",
                    "description": "Pollution degree 1, 2, or 3 (default: 2).",
                    "default": 2,
                },
                "insulation_type": {
                    "type": "string",
                    "description": "Insulation classification: 'Basic' (default) or 'Reinforced'.",
                    "default": "Basic",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_wave_solder_orientation_audit",
        "description": (
            "Audit bottom-side SMD component wave soldering orientation angles and hydrodynamic shadowing per IPC-7351B "
            "and SMTA guidelines: chip passives (0603/0805) perpendicular to flow to prevent tombstoning, SOIC ICs parallel "
            "to flow to prevent solder bridging, and 3xH shadow keepout zones behind tall components."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (with rotation_deg, position, and package).",
                },
                "flow_direction": {
                    "type": "string",
                    "description": "Conveyor wave flow direction: 'X+' (default), 'X-', 'Y+', or 'Y-'.",
                    "default": "X+",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_press_fit_hole_compliance",
        "description": (
            "Evaluate automotive and industrial solderless press-fit compliant pin (eye-of-the-needle) finished hole diameter "
            "tolerances (standard 0.94mm ~ 1.09mm) and copper barrel plating thickness (>= 25μm) per IPC-9797 and IEC 60352-5, "
            "estimating insertion and retention forces to prevent inner-layer tear or vibration disconnects."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["pins"],
            "properties": {
                "pins": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of press-fit pin dicts ({pin_id, connector_ref, drill_dia_mm, copper_thickness_um, finished_dia_mm}).",
                },
                "nominal_finished_dia_mm": {
                    "type": "number",
                    "description": "Nominal compliant pin hole diameter in mm (default: 1.00).",
                    "default": 1.00,
                },
                "min_copper_plating_um": {
                    "type": "number",
                    "description": "Minimum barrel copper plating thickness in μm (default: 25.0).",
                    "default": 25.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "audit_fab_capabilities",
        "description": (
            "Audit PCB layout physical design rules against real-world fab house capabilities (JLCPCB standard/advanced, "
            "PCBWay, OSH Park): verifies min trace width, min clearance, min via drill, annular ring, aspect ratio, "
            "and slot width against published fab process limits to prevent CAM engineering query (EQ) rejections."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "fab_id": {
                    "type": "string",
                    "description": "Fab house identifier: 'jlcpcb_standard' (default), 'jlcpcb_advanced', 'pcbway_standard', 'oshpark_standard'.",
                    "default": "jlcpcb_standard",
                },
                "min_trace_width_mm": {
                    "type": "number",
                    "description": "Smallest conductor trace width in mm (default: 0.127).",
                    "default": 0.127,
                },
                "min_trace_clearance_mm": {
                    "type": "number",
                    "description": "Smallest conductor-to-conductor gap in mm (default: 0.127).",
                    "default": 0.127,
                },
                "min_via_drill_mm": {
                    "type": "number",
                    "description": "Smallest via drill diameter in mm (default: 0.200).",
                    "default": 0.200,
                },
                "min_via_pad_mm": {
                    "type": "number",
                    "description": "Smallest via outer pad diameter in mm (default: 0.450).",
                    "default": 0.450,
                },
                "board_thickness_mm": {
                    "type": "number",
                    "description": "Nominal PCB thickness in mm (default: 1.600).",
                    "default": 1.600,
                },
                "min_slot_width_mm": {
                    "type": "number",
                    "description": "Smallest mechanical milled slot width in mm (default: 0.800).",
                    "default": 0.800,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "gate_production_readiness",
        "description": (
            "One-call industrial release gate: synthesizes from a prompt, places, autoroutes, exports the full "
            "9-layer fab bundle (copper, mask, silk, stencil, drill, BOM, CPL), then runs the manufacturing "
            "validator including solder-mask dam width. Returns a single production_ready verdict plus the "
            "blocking defects, so a CI job or a contract manufacturer can decide go/no-go without reading "
            "five separate reports."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Natural-language circuit description, e.g. 'ESP32-C3 sensor node with USB-C'.",
                },
                "board_width_mm": {"type": "number", "default": 70.0},
                "board_height_mm": {"type": "number", "default": 50.0},
                "job_name": {"type": "string", "default": "PCB_PROJECT"},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "validate_manufacturing_package",
        "description": (
            "Headless manufacturing package validator for automated CI/CD and developer hand-off: checks completeness "
            "and non-emptiness of 5-layer Gerbers, Excellon drill, BOM, and CPL, verifies component refDes consistency, "
            "and calculates SHA-256 cryptographic tamper-proof ledger."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["artifacts_dict"],
            "properties": {
                "artifacts_dict": {
                    "type": "object",
                    "description": "Dict mapping filename (e.g. 'board-Edge_Cuts.gm1', 'bom.csv') to content string or bytes.",
                },
                "modules": {
                    "type": "object",
                    "description": "Optional component modules dict from synthesis for BOM cross-verification.",
                },
                "job_name": {
                    "type": "string",
                    "description": "Project job name for manifest header (default: PCB_PROJECT).",
                    "default": "PCB_PROJECT",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "audit_ipc6012_class_compliance",
        "description": (
            "Audit PCB physical and metallurgical design parameters against IPC-6012E and IPC-A-600J Class 1/2/3 acceptance criteria: "
            "evaluates external/internal annular rings, zero-breakout constraints for Class 3, PTH copper barrel plating thickness "
            "(avg >= 25μm for Class 3), etch conductor width reduction, and solder mask dam widths."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_class": {
                    "type": "string",
                    "description": "Target IPC reliability class: 'Class 1', 'Class 2' (default), or 'Class 3'.",
                    "default": "Class 2",
                },
                "external_annular_ring_mm": {
                    "type": "number",
                    "description": "Smallest external annular ring width in mm (default: 0.125).",
                    "default": 0.125,
                },
                "internal_annular_ring_mm": {
                    "type": "number",
                    "description": "Smallest internal annular ring width in mm (default: 0.100).",
                    "default": 0.100,
                },
                "has_hole_breakout": {
                    "type": "boolean",
                    "description": "Whether drill hole breakout from annular ring is observed (strictly 0° allowed in Class 3).",
                    "default": False,
                },
                "breakout_angle_deg": {
                    "type": "number",
                    "description": "Observed breakout angle in degrees (default: 0.0).",
                    "default": 0.0,
                },
                "avg_copper_barrel_um": {
                    "type": "number",
                    "description": "Average electroplated copper thickness in PTH barrels in μm (default: 22.0).",
                    "default": 22.0,
                },
                "min_copper_barrel_um": {
                    "type": "number",
                    "description": "Minimum thin-point PTH copper plating thickness in μm (default: 19.0).",
                    "default": 19.0,
                },
                "conductor_width_reduction_pct": {
                    "type": "number",
                    "description": "Conductor width reduction percentage from etch defects (default: 5.0).",
                    "default": 5.0,
                },
                "min_solder_mask_dam_mm": {
                    "type": "number",
                    "description": "Smallest solder mask dam width between adjacent exposed pads in mm (default: 0.090).",
                    "default": 0.090,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "optimize_smt_feeder_setup",
        "description": (
            "Optimize SMT pick-and-place feeder trolley allocation (Panasonic NPM / Fuji NXT / ASM SIPLACE standard 80-slot cart): "
            "applies Group Technology (GT) to pin permanent common passive reels (100nF, 10k), places high-frequency reels near "
            "the gantry center to minimize travel time, and forecasts reel run-out exhaustion points per batch size per IPC-9851."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (e.g. from synthesis or netlist).",
                },
                "feeder_cart_capacity": {
                    "type": "integer",
                    "description": "Total feeder slots on trolley cart (default: 80).",
                    "default": 80,
                },
                "batch_size": {
                    "type": "integer",
                    "description": "Production batch size in boards (default: 1000).",
                    "default": 1000,
                },
                "common_parts_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of common component identifiers to pin into the permanent feeder block.",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_copper_pour_current_drop",
        "description": (
            "Calculate DC IR-drop, Joule heating dissipation, and localized bottleneck current density in polygon copper pours "
            "and power busbars per IPC-2152 Section 5.0 and IEC 60092-352, verifying current density <= 35.0 A/mm² to prevent "
            "copper foil delamination or blistering under heavy loads."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["current_a"],
            "properties": {
                "current_a": {
                    "type": "number",
                    "description": "Continuous DC load current in Amperes.",
                },
                "copper_weight_oz": {
                    "type": "number",
                    "description": "Finished copper foil weight in oz (default: 1.0).",
                    "default": 1.0,
                },
                "effective_length_mm": {
                    "type": "number",
                    "description": "Conduction path length from source to load in mm (default: 50.0).",
                    "default": 50.0,
                },
                "effective_width_mm": {
                    "type": "number",
                    "description": "Average conduction width of the copper pour in mm (default: 20.0).",
                    "default": 20.0,
                },
                "bottleneck_width_mm": {
                    "type": "number",
                    "description": "Narrowest constriction neck width (e.g. around cutouts or anti-pads) in mm.",
                },
                "ambient_temp_c": {
                    "type": "number",
                    "description": "Ambient operating temperature in °C (default: 25.0).",
                    "default": 25.0,
                },
                "max_allowed_temp_rise_c": {
                    "type": "number",
                    "description": "Allowable conductor temperature rise ΔT in °C (default: 30.0).",
                    "default": 30.0,
                },
                "max_allowed_current_density_a_per_mm2": {
                    "type": "number",
                    "description": "Maximum safe current density ceiling in A/mm² (default: 35.0).",
                    "default": 35.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "audit_component_msl_floor_life",
        "description": (
            "Audit SMD plastic packages (BGA, QFN, CSP, TQFP) for moisture sensitivity level (MSL 1 to 6) and open-bag shop floor "
            "life per JEDEC J-STD-033D and IPC-M-109, flagging expired components and generating recommended dehumidification "
            "baking schedules (e.g. 125°C for 24h or 40°C for 192h) to prevent 260°C reflow popcorning defects."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict with refDes, package, and optional msl_level or exposed_hours.",
                },
                "exposed_hours_default": {
                    "type": "number",
                    "description": "Default shop floor exposure hours since unsealing moisture barrier bag (default: 48.0).",
                    "default": 48.0,
                },
                "ambient_temp_c": {
                    "type": "number",
                    "description": "Workshop ambient temperature in °C (default: 25.0).",
                    "default": 25.0,
                },
                "ambient_rh_pct": {
                    "type": "number",
                    "description": "Workshop ambient relative humidity percentage (default: 55.0).",
                    "default": 55.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_effective_capacitance",
        "description": (
            "Effective capacitance of a Class II MLCC at real operating conditions — the marked value is not the "
            "value in circuit. Multiplies the four loss mechanisms that compound: DC bias (the dominant one, "
            "typically 35-65% loss at rated voltage and worse in small cases), AC signal level, temperature "
            "coefficient, and logarithmic dielectric ageing, then applies the part tolerance. Returns the full "
            "factor stack so you can see which mechanism hurt most. Class I (C0G/NP0) parts correctly short-circuit "
            "to tolerance-only. Pass measured_retention_at_bias from a datasheet curve (Murata SimSurfing, TDK SEAT) "
            "to replace the band estimate and get confidence='measured'."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["marked_capacitance_uf", "rated_v", "applied_v"],
            "properties": {
                "marked_capacitance_uf": {
                    "type": "number",
                    "description": "The capacitance printed on the reel, in µF.",
                },
                "rated_v": {"type": "number", "description": "The part's rated DC voltage."},
                "applied_v": {
                    "type": "number",
                    "description": "DC bias actually across the part in this circuit, in volts.",
                },
                "case_size": {
                    "type": "string",
                    "description": "EIA case code: 0402, 0603, 0805, 1206 or 1210. Larger cases retain more capacitance under bias.",
                    "default": "0805",
                },
                "dielectric": {
                    "type": "string",
                    "description": "EIA Class II dielectric: X5R, X7R, X8R, Y5V, Z5U, or Class I C0G/NP0.",
                    "default": "X5R",
                },
                "ambient_c": {
                    "type": "number",
                    "description": "Operating ambient temperature in °C.",
                    "default": 25.0,
                },
                "hours_in_service": {
                    "type": "number",
                    "description": "Expected service life in hours, used for the log-time ageing term.",
                    "default": 1000.0,
                },
                "ac_level": {
                    "type": "string",
                    "description": "Signal magnitude class: small_signal (<50 mVrms), moderate (50-500 mVrms), or large (>500 mVrms). Small signals see less capacitance.",
                    "enum": ["small_signal", "moderate", "large"],
                    "default": "small_signal",
                },
                "tolerance_pct": {
                    "type": "number",
                    "description": "The part's capacitance tolerance in percent (e.g. 10 for ±10%). Applied at the pessimistic end.",
                },
                "measured_retention_at_bias": {
                    "type": "number",
                    "description": "Retention fraction (0-1] read from the real datasheet DC-bias curve at applied_v. Replaces the band estimate.",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "size_hold_up_capacitor",
        "description": (
            "Size an MLCC reservoir bank for a brown-out ride-through window in EFFECTIVE farads, then report the "
            "marked value you must actually buy. Solves C = I·t/ΔV for the required effective capacitance and "
            "divides by the retention at the worst-case bias in the window, because sizing from the marked value is "
            "how a design that 'passes' delivers 0.85 ms of hold-up when the spec asked for 20 ms. Reports the "
            "achieved hold time, the shortfall, and the required marked capacitance."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["load_current_ma", "v_start", "v_floor", "required_hold_time_ms"],
            "properties": {
                "load_current_ma": {
                    "type": "number",
                    "description": "Load current drawn from the reservoir during the outage, in mA.",
                },
                "v_start": {
                    "type": "number",
                    "description": "Rail voltage at the moment the source collapses, AFTER any ORing diode drop — not the nominal input.",
                },
                "v_floor": {
                    "type": "number",
                    "description": "Minimum voltage the load tolerates (brown-out floor), in volts.",
                },
                "required_hold_time_ms": {
                    "type": "number",
                    "description": "Required ride-through duration in milliseconds.",
                },
                "rated_v": {
                    "type": "number",
                    "description": "Capacitor rated voltage. Defaults to 2x v_start to keep bias derating near 50%.",
                },
                "case_size": {
                    "type": "string",
                    "description": "EIA case code (0402/0603/0805/1206/1210).",
                    "default": "0805",
                },
                "dielectric": {
                    "type": "string",
                    "description": "EIA dielectric: X5R, X7R, X8R, C0G/NP0.",
                    "default": "X5R",
                },
                "ambient_c": {"type": "number", "description": "Operating ambient in °C.", "default": 25.0},
                "hours_in_service": {
                    "type": "number",
                    "description": "Expected service life in hours.",
                    "default": 1000.0,
                },
                "tolerance_pct": {
                    "type": "number",
                    "description": "Capacitance tolerance in percent.",
                    "default": 10.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "analyze_rc_filter_effective",
        "description": (
            "RC filter cutoff computed from the capacitance the part actually has, not the marked value. A 1 kHz "
            "filter built with a 10 µF X5R part that delivers 4 µF under bias cuts at 2.5 kHz — the nominal "
            "calculation is not wrong, it answers a different question. Returns nominal vs actual cutoff, the drift "
            "percentage, and the retention that caused it."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["r_ohm", "marked_c_uf", "rated_v", "applied_v"],
            "properties": {
                "r_ohm": {"type": "number", "description": "Series resistance in ohms."},
                "marked_c_uf": {"type": "number", "description": "Marked capacitance in µF."},
                "rated_v": {"type": "number", "description": "Capacitor rated DC voltage."},
                "applied_v": {"type": "number", "description": "DC bias across the capacitor, in volts."},
                "case_size": {"type": "string", "description": "EIA case code.", "default": "0805"},
                "dielectric": {"type": "string", "description": "EIA dielectric.", "default": "X5R"},
                "ambient_c": {"type": "number", "description": "Operating ambient in °C.", "default": 25.0},
                "hours_in_service": {
                    "type": "number",
                    "description": "Expected service life in hours.",
                    "default": 1000.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "analyze_divider_tolerance",
        "description": (
            "Tolerance band of a resistor divider — nominal is not a specification. Reports BOTH the exact "
            "worst case (corner enumeration, valid because the transfer function is monotonic in each resistor) "
            "and the realistic statistical band (first-order sensitivity propagation, NOT naive RSS of "
            "percentage tolerances — the output is a quotient of random variables, so RSS-ing the percentages "
            "directly is invalid; TI SNVA112 states this explicitly). Includes TCR, sqrt-of-time life drift, "
            "supply tolerance, and matched-pair ratio tolerance, and names which resistor dominates the error "
            "budget so you fix the right part."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["v_in", "r1_ohm", "r2_ohm"],
            "properties": {
                "v_in": {"type": "number", "description": "Input voltage to the divider, in volts."},
                "r1_ohm": {"type": "number", "description": "High-side resistor (input to midpoint), in ohms."},
                "r2_ohm": {"type": "number", "description": "Low-side resistor (midpoint to ground), in ohms."},
                "tolerance_pct": {
                    "type": "number",
                    "description": "Resistor value tolerance in percent at 25 °C.",
                    "default": 1.0,
                },
                "tcr_ppm_per_c": {
                    "type": "number",
                    "description": "Temperature coefficient in ppm/°C. Thick film is ~200, thin film ~25, metal foil ~2.",
                    "default": 0.0,
                },
                "delta_temp_c": {
                    "type": "number",
                    "description": "Temperature excursion from 25 °C that the design must hold accuracy over.",
                    "default": 0.0,
                },
                "life_drift_pct": {
                    "type": "number",
                    "description": "Life drift percent over the datasheet's stated hours. Scales with sqrt of the time ratio.",
                    "default": 0.0,
                },
                "ratio_tolerance_pct": {
                    "type": "number",
                    "description": "Ratio tolerance for a matched pair in one package. Replaces both absolute tolerances — the biggest free accuracy win.",
                },
                "v_in_tolerance_pct": {
                    "type": "number",
                    "description": "Supply tolerance in percent, treated as an independent contribution.",
                    "default": 0.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "analyze_resistor_error_budget",
        "description": (
            "End-of-life resistance band for one resistor from the four-term error model: value tolerance, "
            "temperature coefficient, life drift, and (for matched networks) ratio tolerance. Reports both the "
            "RSS band and the linear worst-case band, and names the dominant term — because buying a ±0.1% "
            "thick-film part to fix an accuracy problem does nothing when its 200 ppm/°C TCR already contributes "
            "1.2% over a 60 °C excursion. Life drift scales with sqrt of the time ratio (random walk, not a ramp)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["nominal_ohm"],
            "properties": {
                "nominal_ohm": {"type": "number", "description": "Marked resistance in ohms."},
                "tolerance_pct": {"type": "number", "description": "Value tolerance in percent.", "default": 1.0},
                "tcr_ppm_per_c": {"type": "number", "description": "Temperature coefficient in ppm/°C.", "default": 0.0},
                "delta_temp_c": {"type": "number", "description": "Temperature excursion from 25 °C.", "default": 0.0},
                "life_drift_pct": {"type": "number", "description": "Life drift percent over life_hours_specified.", "default": 0.0},
                "life_hours_specified": {
                    "type": "number",
                    "description": "The hours the datasheet's life figure refers to.",
                    "default": 1000.0,
                },
                "life_hours_required": {
                    "type": "number",
                    "description": "The service life the design must meet.",
                    "default": 1000.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "solve_feedback_divider",
        "description": (
            "Exact R1/R2 feedback divider pair for a regulator or comparator target, plus the static error the "
            "E96 snap adds. The ideal pair almost never exists in E96, and that snap error is a wrongness, not a "
            "tolerance: it is identical on every board and must be budgeted separately from the tolerance band."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["v_out", "v_ref"],
            "properties": {
                "v_out": {"type": "number", "description": "Target output voltage."},
                "v_ref": {"type": "number", "description": "Reference voltage at the feedback midpoint."},
                "r_total_ohm": {
                    "type": "number",
                    "description": "Total divider resistance R1+R2, which sets the quiescent current.",
                    "default": 100000.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_high_speed_skin_depth_loss",
        "description": (
            "Calculate high-frequency skin effect depth, Hammerstad surface roughness correction factor (Ksr), and conductor "
            "attenuation per IPC-4562B and IPC-2141A for 1GHz to 50GHz signals (PCIe 5.0/6.0, USB4, 112G PAM4), recommending "
            "standard ED, VLP, or HVLP/RTF copper foil profiles to recover high-speed signal integrity eye margins."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "frequency_ghz": {
                    "type": "number",
                    "description": "Signal frequency in GHz (default: 10.0).",
                    "default": 10.0,
                },
                "trace_width_mm": {
                    "type": "number",
                    "description": "Conductor trace width in mm (default: 0.150).",
                    "default": 0.150,
                },
                "trace_thickness_mm": {
                    "type": "number",
                    "description": "Copper foil thickness in mm (default: 0.035 for 1oz).",
                    "default": 0.035,
                },
                "dielectric_er": {
                    "type": "number",
                    "description": "Substrate relative dielectric constant Er (default: 4.2).",
                    "default": 4.2,
                },
                "foil_type": {
                    "type": "string",
                    "description": "Copper profile: 'standard_ed', 'vlp' (default), or 'hvlp'.",
                    "default": "vlp",
                },
                "custom_rq_um": {
                    "type": "number",
                    "description": "Optional custom RMS roughness Rq in μm.",
                },
                "max_acceptable_ksr": {
                    "type": "number",
                    "description": "Maximum allowable roughness penalty factor (default: 1.85).",
                    "default": 1.85,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_bare_board_test_parameters",
        "description": (
            "Plan IPC-9252B bare-board electrical test recipes (flying probe or bed-of-nails universal grid): establishes "
            "continuity thresholds (signal <= 10Ω, power <= 2Ω) and isolation test voltages (Class 1: 50V, Class 2: 100V, "
            "Class 3: 250V), automatically derating test voltages to 100V on fine-pitch (<0.100mm) or sensitive RF nets to prevent "
            "dielectric breakdown arc-over damage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "nets": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional list of net dicts ({name, min_clearance_mm, is_power, is_sensitive}).",
                },
                "target_class": {
                    "type": "string",
                    "description": "IPC reliability class: 'Class 1', 'Class 2' (default), or 'Class 3'.",
                    "default": "Class 2",
                },
                "tester_type": {
                    "type": "string",
                    "description": "Test equipment: 'flying_probe' (default) or 'universal_grid'.",
                    "default": "flying_probe",
                },
                "min_trace_clearance_mm": {
                    "type": "number",
                    "description": "Minimum conductor clearance on board in mm (default: 0.127).",
                    "default": 0.127,
                },
                "has_sensitive_rf_nets": {
                    "type": "boolean",
                    "description": "Whether board contains sensitive RF/microwave nets (default: False).",
                    "default": False,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "run_pcb_drc",
        "description": (
            "Execute rigorous physical Design Rule Check (DRC) on a routed PCB and return a scored "
            "violation report. Verifies what the router cannot: true copper-to-copper clearance between "
            "different nets (segment-to-segment geometry, not grid cells), acid traps and sub-90-degree "
            "etching crevices (IPC-2221B 10.1.2), trace width vs process capability, board-edge and "
            "mounting-hole keepout intrusion, RF antenna keepout, and high-speed differential pair skew "
            "(IPC-2141A 3.4). Returns severity-tagged violations with measured vs required values plus a "
            "0-100 score; `passed` is false when any blocking error remains."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["modules", "netlist"],
            "properties": {
                "modules": {
                    "type": "object",
                    "description": "Component modules dict (from synthesize_circuit output).",
                },
                "netlist": {
                    "type": "object",
                    "description": "Netlist dict with 'connections' (from synthesize_circuit output).",
                },
                "ses_text": {
                    "type": "string",
                    "description": (
                        "Specctra SES session text to check. When omitted the board is routed first "
                        "with the default exact engine, so the report describes what would actually be "
                        "fabricated."
                    ),
                },
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 70.0).",
                    "default": 70.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
                "min_trace_width_mm": {
                    "type": "number",
                    "description": "Minimum manufacturable trace width in mm (default: 0.127 / 5mil).",
                    "default": 0.127,
                },
                "min_clearance_mm": {
                    "type": "number",
                    "description": "Minimum copper-to-copper clearance in mm (default: 0.100 / 4mil).",
                    "default": 0.100,
                },
                "edge_clearance_mm": {
                    "type": "number",
                    "description": "Minimum copper-to-board-edge setback in mm (default: 0.800).",
                    "default": 0.800,
                },
                "max_diff_skew_mm": {
                    "type": "number",
                    "description": "Maximum allowed USB differential pair length mismatch in mm (default: 1.250).",
                    "default": 1.250,
                },
                "check_acid_traps": {
                    "type": "boolean",
                    "description": "Whether to check acute-angle etching traps and 90-degree high-speed corners (default: true).",
                    "default": True,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "analyze_ionic_contamination",
        "description": (
            "Post-clean ionic contamination (ROSE) and ion chromatography compliance analyzer per IPC-CH-65 and "
            "IPC-TM-650 2.3.25/2.3.28: compares NaCl-equivalent loading against class limits (1.56 μg/cm² standard, "
            "1.20 Class 3), flags per-species halide carryover (chloride 0.70, bromide 0.54 μg/cm²), and scores dendrite/CAF "
            "risk from bias voltage and conductor pitch."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["rose_measured_ug_cm2"],
            "properties": {
                "rose_measured_ug_cm2": {
                    "type": "number",
                    "description": "Measured NaCl-equivalent loading from the ROSE tester in μg/cm².",
                },
                "board_area_cm2": {
                    "type": "number",
                    "description": "Total extracted board area in cm² (default: 100.0).",
                    "default": 100.0,
                },
                "target_class": {
                    "type": "string",
                    "description": "IPC reliability class: 'Class 1', 'Class 2' (default), or 'Class 3'.",
                    "default": "Class 2",
                },
                "species_ug_cm2": {
                    "type": "object",
                    "description": "Optional ion chromatography per-species results in μg/cm² (chloride, bromide, fluoride, nitrate, sulfate, weak_organic_acid).",
                },
                "bias_voltage_v": {
                    "type": "number",
                    "description": "Largest sustained DC bias between adjacent conductors (default: 5.0).",
                    "default": 5.0,
                },
                "min_conductor_gap_mm": {
                    "type": "number",
                    "description": "Smallest biased conductor spacing in mm (default: 0.20).",
                    "default": 0.20,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "analyze_enig_plating",
        "description": (
            "ENIG/ENEPIG plating thickness and black-pad (interfacial nickel corrosion) risk auditor per IPC-4552A and "
            "IPC-4556: verifies gold 0.05~0.20 μm, nickel 3.0~6.0 μm, phosphorus 7~10 wt%, and ENEPIG palladium "
            "0.10~0.30 μm windows; scores galvanic black-pad susceptibility from phosphorus content, gold over-deposition, "
            "rework cycles, and process type, and flags gold >0.25 μm solder embrittlement."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "finish_type": {
                    "type": "string",
                    "description": "Surface finish: 'enig' (default) or 'enepig'.",
                    "default": "enig",
                },
                "gold_thickness_um": {
                    "type": "number",
                    "description": "XRF immersion-gold thickness in μm (default: 0.08).",
                    "default": 0.08,
                },
                "nickel_thickness_um": {
                    "type": "number",
                    "description": "XRF electroless-nickel thickness in μm (default: 4.0).",
                    "default": 4.0,
                },
                "phosphorus_wt_pct": {
                    "type": "number",
                    "description": "Nickel deposit phosphorus content in wt% (default: 8.5).",
                    "default": 8.5,
                },
                "palladium_thickness_um": {
                    "type": "number",
                    "description": "ENEPIG palladium barrier thickness in μm (optional).",
                },
                "rework_cycles": {
                    "type": "integer",
                    "description": "Number of prior soldering/rework thermal excursions (default: 0).",
                    "default": 0,
                },
                "soldering_process": {
                    "type": "string",
                    "description": "Assembly process: 'reflow' (default), 'wave', or 'hand'.",
                    "default": "reflow",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "estimate_solder_joint_thermal_fatigue",
        "description": (
            "IPC-9701A / IPC-D-279 Engelmaier thermal cycling fatigue life estimator for critical SMT "
            "attachments: computes CTE-mismatch shear strain range over the component DNP, applies the "
            "creep-aware cycle exponent (hot dwell and mean joint temperature), and reports cycles-to-63.2%-"
            "failure against the service requirement across TC1-TC4 automotive/aerospace profiles."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component": {
                    "type": "string",
                    "description": "Ref/designation of the worst-case component (default: U1_BGA256).",
                    "default": "U1_BGA256",
                },
                "dnp_mm": {
                    "type": "number",
                    "description": "Distance from board neutral point to farthest joint in mm (default: 15.0).",
                    "default": 15.0,
                },
                "joint_height_mm": {
                    "type": "number",
                    "description": "Solder joint standoff height in mm; BGA ~0.10-0.45, QFN ~0.05 (default: 0.10).",
                    "default": 0.10,
                },
                "condition": {
                    "type": "string",
                    "description": "IPC-9701 profile: 'TC1' 0-100, 'TC2' -25-125, 'TC3' -40-125 (default), 'TC4' -55-125 °C.",
                    "default": "TC3",
                },
                "temp_min_c": {"type": "number", "description": "Explicit cycle minimum °C (overrides condition)."},
                "temp_max_c": {"type": "number", "description": "Explicit cycle maximum °C (overrides condition)."},
                "hot_dwell_min": {
                    "type": "number",
                    "description": "Hot dwell time per cycle in minutes (default: 10.0).",
                    "default": 10.0,
                },
                "pcb_cte_ppm": {
                    "type": "number",
                    "description": "PCB in-plane CTE in ppm/K (default: 15.0 FR-4).",
                    "default": 15.0,
                },
                "package_cte_ppm": {
                    "type": "number",
                    "description": "Package substrate/leadframe CTE in ppm/K (default: 14.0 BT BGA).",
                    "default": 14.0,
                },
                "compliance_factor_f": {
                    "type": "number",
                    "description": "Joint compliance factor (0.5 typical, 1.0 stiff; default: 0.5).",
                    "default": 0.5,
                },
                "required_cycles": {
                    "type": "number",
                    "description": "Service cycles the attachment must survive (default: 3000).",
                    "default": 3000.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "plan_conformal_coating",
        "description": (
            "IPC-CC-830C / IPC-A-610G §10 conformal coating material selector and masking keepout planner: "
            "validates dry-film thickness against the type windows (AR/ER/UR 30-130, SR 50-210, XY 10-50 μm), "
            "flags reworkability conflicts for field-repairable products, and enumerates connector/test-point/"
            "switch masking keepouts from the BOM before the selective-coating program is generated."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "coating_type": {
                    "type": "string",
                    "description": "IPC-CC-830 type: 'AR' acrylic (default), 'ER' epoxy, 'UR' urethane, 'SR' silicone, or 'XY' parylene.",
                    "default": "AR",
                },
                "measured_thickness_um": {
                    "type": "number",
                    "description": "Witness-coupon measured dry-film thickness in μm (default: 75.0).",
                    "default": 75.0,
                },
                "modules": {
                    "type": "object",
                    "description": "Optional BOM modules dict — contact-bearing parts become masking keepouts.",
                },
                "requires_field_rework": {
                    "type": "boolean",
                    "description": "Whether the product must be repairable in service (default: False).",
                    "default": False,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "predict_assembly_mtbf",
        "description": (
            "Telcordia SR-332 / MIL-HDBK-217F part-stress MTBF prediction: classifies the BOM into Telcordia "
            "part classes, applies Arrhenius πT at worst-case ambient, quality πQ (level 1-3), and environment "
            "πE (ground benign 1.0 to airborne 12.0), returns total FIT, MTBF hours/years, 5-year survival "
            "probability, and the top-5 dominant failure-rate contributors."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "part_counts": {
                    "type": "object",
                    "description": "Explicit {part_class: quantity} mapping (Telcordia classes).",
                },
                "modules": {
                    "type": "object",
                    "description": "BOM modules dict — parts are auto-classified by kind/value.",
                },
                "ambient_temp_c": {
                    "type": "number",
                    "description": "Worst-case operating ambient in °C (default: 40.0).",
                    "default": 40.0,
                },
                "environment": {
                    "type": "string",
                    "description": "'ground_benign' | 'ground_fixed' (default) | 'ground_mobile' | 'airborne'.",
                    "default": "ground_fixed",
                },
                "quality_level": {
                    "type": "integer",
                    "description": "Telcordia qualification level 1 (screened 0.8×) / 2 (standard, default) / 3 (uncertified 2.0×).",
                    "default": 2,
                },
                "duty_cycle_derate": {
                    "type": "number",
                    "description": "Operating duty fraction 0-1 applied to total λ (default: 1.0).",
                    "default": 1.0,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "assess_drop_shock_reliability",
        "description": (
            "JEDEC JESD22-B111 board-level drop shock assessor (1500 G / 0.5 ms half-sine, 30 drops): "
            "computes per-component inertial joint loads (F=ma), flags heavy components in board-corner "
            "high-strain flexure zones, estimates board natural frequency (border-ring stiffener aware), "
            "and prescribes underfill / center-migration / boss-fastening mitigations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_width_mm": {
                    "type": "number",
                    "description": "PCB width in mm (default: 80.0).",
                    "default": 80.0,
                },
                "board_height_mm": {
                    "type": "number",
                    "description": "PCB height in mm (default: 50.0).",
                    "default": 50.0,
                },
                "board_mass_g": {
                    "type": "number",
                    "description": "Total assembled board mass in g (default: 60.0).",
                    "default": 60.0,
                },
                "components": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "[{ref, mass_g, x_mm, y_mm, joint_count}] coordinates relative to board center.",
                },
                "test_g": {
                    "type": "number",
                    "description": "Peak shock level in G (default: 1500 per JESD22-B111).",
                    "default": 1500.0,
                },
                "has_border_ring_stiffener": {
                    "type": "boolean",
                    "description": "True when a mid-frame/border ring anchors the board edge (default: False).",
                    "default": False,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "solve_via_current_array",
        "description": (
            "IPC-2152 / IPC-2221 via barrel current capacity and stitching-array solver: computes the "
            "annular barrel cross-section from drill and plating, applies the thermal formula with "
            "internal/external k constants, 40% array current-sharing derate, and IPC-4761 Type VII "
            "fill+cap credit, returning the minimum parallel via count for a rail current."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "current_a": {"type": "number", "description": "Rail current to carry in A (default: 3.0).", "default": 3.0},
                "via_drill_mm": {"type": "number", "description": "Finished drill diameter in mm (default: 0.30).", "default": 0.30},
                "plating_um": {"type": "number", "description": "Copper plating thickness in μm (default: 25.0).", "default": 25.0},
                "is_filled": {"type": "boolean", "description": "IPC-4761 Type VII fill+cap via (default: False).", "default": False},
                "internal_layer": {"type": "boolean", "description": "Transition between internal layers k=0.024 (default: False).", "default": False},
                "max_delta_t_c": {"type": "number", "description": "Allowable barrel temperature rise °C (default: 20.0).", "default": 20.0},
                "max_array_size": {"type": "integer", "description": "Stitching ceiling before recommending wider traces (default: 8).", "default": 8},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "budget_fab_order",
        "description": (
            "JLCPCB / PCBWay headless order cost budget and submission manifest builder: offline math over "
            "public price ladders (layers, quantity, area, finish, SMT, shipping, lead priority), cross-vendor "
            "recommendation, and a SHA-256 tamper-evident manifest over the manufacturing artifacts for CI "
            "order staging — no network, no keys, stdlib-only (macOS laptop or Docker CI runner)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "layers": {"type": "integer", "description": "2 / 4 / 6 layers (default: 2).", "default": 2},
                "qty": {"type": "integer", "description": "Panel quantity: 5/10/30/100 ladder (default: 5).", "default": 5},
                "board_w_mm": {"type": "number", "description": "Outline width mm (default: 70.0).", "default": 70.0},
                "board_h_mm": {"type": "number", "description": "Outline height mm (default: 50.0).", "default": 50.0},
                "surface_finish": {"type": "string", "description": "'hasl_lead_free' (default) | 'enig' | 'osp'.", "default": "hasl_lead_free"},
                "include_smt": {"type": "boolean", "description": "Request PCBA assembly (default: False).", "default": False},
                "smt_parts": {"type": "integer", "description": "Number of SMT placements (default: 0).", "default": 0},
                "shipping": {"type": "string", "description": "'standard' (default) | 'dhl'.", "default": "standard"},
                "lead_priority": {"type": "string", "description": "'economy' | 'standard' (default) | 'expedite'.", "default": "standard"},
                "artifacts": {"type": "object", "description": "Manufacturing artifacts {filename: content} for the SHA-256 submission manifest."},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_qfn_thermal_pad_stencil",
        "description": (
            "IPC-7093A / IPC-7525A QFN and BTC thermal slug window-pane stencil aperture solver: converts solid 100% "
            "paste openings into an optimized matrix grid (50%~70% paste coverage, default 60%) separated by 0.15~0.25mm "
            "bare copper web outgassing channels, preventing solder voiding (>35%), die floating, and perimeter bridging."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pad_width_mm": {"type": "number", "description": "Thermal slug width in mm (default: 4.5).", "default": 4.5},
                "pad_height_mm": {"type": "number", "description": "Thermal slug height in mm (default: 4.5).", "default": 4.5},
                "target_coverage_pct": {"type": "number", "description": "Target paste coverage percentage 50~70% (default: 60.0).", "default": 60.0},
                "web_width_mm": {"type": "number", "description": "Outgassing web channel width in mm (default: 0.20).", "default": 0.20},
                "has_unfilled_thermal_vias": {"type": "boolean", "description": "Whether open unfilled vias exist in the pad (default: False).", "default": False},
                "is_automotive_class3": {"type": "boolean", "description": "Whether strict Class 3 / automotive voiding limit <=15% applies (default: False).", "default": False},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "audit_smt_tombstone_risk",
        "description": (
            "IPC-A-610G §8.3.2.9 / IPC-SM-782 SMT chip passive component thermal relief & tombstoning (Manhattan effect) "
            "risk auditor: checks thermal connection width symmetry between opposite pads on 0201/0402/0603/0805 passives, "
            "flagging direct solid plane connections without thermal relief spokes that create unbalanced wetting torque."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "components": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of passive component dicts ({ref, package, pad1_type, pad2_type, pad1_width_mm, pad2_width_mm}).",
                },
                "default_trace_width_mm": {"type": "number", "description": "Nominal signal trace width in mm (default: 0.20).", "default": 0.20},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_castellated_pad_geometry",
        "description": (
            "IPC-A-600J §2.9 / IPC-6012E §3.6.3 castellated hole (edge plating half-hole) manufacturability solver: "
            "verifies minimum finished hole diameter (>=0.80mm), centerline routing cut offset (|delta| <= 0.05mm), "
            "minimum inward pad extension (>=0.50mm), pitch (>=1.27mm), and barrel copper plating thickness (>=20μm) "
            "to prevent copper barrel tearout and burrs during daughterboard depaneling."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "hole_drill_diameter_mm": {"type": "number", "description": "Finished drill diameter in mm (default: 1.00).", "default": 1.00},
                "center_to_edge_offset_mm": {"type": "number", "description": "Cutter path offset from hole center in mm (default: 0.00).", "default": 0.00},
                "pad_inward_length_mm": {"type": "number", "description": "Inward annular pad extension from board edge in mm (default: 0.80).", "default": 0.80},
                "pad_width_mm": {"type": "number", "description": "Pad width along board perimeter in mm (default: 0.80).", "default": 0.80},
                "pad_pitch_mm": {"type": "number", "description": "Center-to-center pitch between adjacent holes in mm (default: 2.00).", "default": 2.00},
                "copper_plating_thickness_um": {"type": "number", "description": "Barrel copper plating thickness in μm (default: 25.0).", "default": 25.0},
                "solder_mask_clearance_mm": {"type": "number", "description": "Solder mask relief opening margin in mm (default: 0.080).", "default": 0.080},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_pcb_bow_and_twist",
        "description": (
            "IPC-TM-650 2.4.22 / IPC-6012E §3.4.4 PCB bow and twist (warpage & flatness) analyzer: evaluates "
            "residual bimetallic thermal curvature driven by dielectric stackup core/prepreg asymmetry and copper "
            "density gradients, enforcing strict <=0.75% limit for SMT assemblies to prevent BGA Head-in-Pillow (HiP) "
            "open defects and tombstoning."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_length_mm": {"type": "number", "description": "Board longest edge in mm (default: 100.0).", "default": 100.0},
                "board_width_mm": {"type": "number", "description": "Board shortest edge in mm (default: 80.0).", "default": 80.0},
                "board_thickness_mm": {"type": "number", "description": "Total PCB thickness in mm (default: 1.60).", "default": 1.60},
                "layer_count": {"type": "integer", "description": "Total layer count (default: 4).", "default": 4},
                "has_smt_components": {"type": "boolean", "description": "Whether assembly contains SMT parts <=0.75% (default: True).", "default": True},
                "copper_balance_ratio_top_bottom": {"type": "number", "description": "Top-to-bottom copper volume ratio (default: 1.0).", "default": 1.0},
                "dielectric_asymmetry_pct": {"type": "number", "description": "Dielectric core/prepreg thickness asymmetry % (default: 0.0).", "default": 0.0},
                "measured_bow_height_mm": {"type": "number", "description": "Optional measured dial-gauge bow deflection in mm."},
                "measured_twist_height_mm": {"type": "number", "description": "Optional measured corner lift in mm."},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "audit_smt_nozzle_selection",
        "description": (
            "EIA-481 & Juki/Yamaha/Fuji/Panasonic SMT pick-and-place nozzle selector & vacuum audit: verifies "
            "nozzle outer diameter (OD) clearances against tape pocket walls and component margins, inner diameter (ID) "
            "vacuum seal against leakage, and dynamic inertial hold safety factor (SF >= 1.5) under 3G~5G head acceleration "
            "to eliminate pick failure and fly-off."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component_designator": {"type": "string", "description": "Component designator (default: 'U1').", "default": "U1"},
                "package_type": {"type": "string", "description": "Package designation (e.g. '0402', '0603', 'SOT-23', 'QFN-32').", "default": "0603"},
                "component_length_mm": {"type": "number", "description": "Component length in mm."},
                "component_width_mm": {"type": "number", "description": "Component width in mm."},
                "component_height_mm": {"type": "number", "description": "Component height in mm."},
                "component_mass_mg": {"type": "number", "description": "Component mass in milligrams."},
                "specified_nozzle_model": {"type": "string", "description": "Optional explicit nozzle model (e.g. 'Juki-502', 'Yamaha-302A')."},
                "vacuum_pressure_kpa": {"type": "number", "description": "Factory vacuum pressure in kPa (default: 70.0).", "default": 70.0},
                "head_acceleration_g": {"type": "number", "description": "Head acceleration in G (default: 3.5).", "default": 3.5},
                "friction_coefficient": {"type": "number", "description": "Surface friction coefficient (default: 0.30).", "default": 0.30},
                "vendor_preference": {"type": "string", "description": "Vendor preference ('Juki', 'Yamaha', 'Fuji').", "default": "Juki"},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "calculate_trace_fusing_current",
        "description": (
            "IPC-2152 §5.3 & Onderdonk equation short-time transient conductor fusing current and burnout solver: "
            "computes adiabatic fusing current, time-to-melt, FR-4 resin delamination/blister threshold, and Joule action "
            "integral (I²t) for internal/external traces, verifying upstream fuse/PTC protection coordination margin (>=2.0x) "
            "against electrical fire."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "trace_width_mm": {"type": "number", "description": "Trace width in mm (default: 0.50).", "default": 0.50},
                "copper_thickness_um": {"type": "number", "description": "Copper thickness in μm (default: 35.0 for 1oz).", "default": 35.0},
                "trace_layer": {"type": "string", "description": "Layer type ('external' or 'internal') (default: 'external').", "default": "external"},
                "fault_current_a": {"type": "number", "description": "Estimated short-circuit fault current in Amperes (default: 15.0).", "default": 15.0},
                "pulse_duration_s": {"type": "number", "description": "Fault pulse duration in seconds (default: 0.10).", "default": 0.10},
                "ambient_temp_c": {"type": "number", "description": "Initial ambient temperature in °C (default: 25.0).", "default": 25.0},
                "upstream_fuse_rating_a": {"type": "number", "description": "Optional upstream fuse rated current in Amperes."},
                "upstream_fuse_i2t_a2s": {"type": "number", "description": "Optional upstream fuse rated melting I²t in A²s."},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
]

# --------------------------------------------------------------------------- #
# Resource Definitions
# --------------------------------------------------------------------------- #

AVAILABLE_RESOURCES = [
    {
        "uri": "circuit://specs/netlist-schema",
        "name": "CircuitAgent Netlist JSON Schema (Draft-07)",
        "description": "Formal JSON Schema specification for hardware netlists, pin connections, modules, and stackups.",
        "mimeType": "application/json",
    },
    {
        "uri": "circuit://specs/cpl-standard",
        "name": "JLCPCB SMT CPL Standard & Rotation Specification",
        "description": "Standard Cartesian mirror and rotation angle offset specifications for JLC SMT assembly.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "circuit://specs/ipc-dfx-rules",
        "name": "CircuitAgent IPC & Industrial DFX Ruleset Specification",
        "description": "Formal IPC-2152 current/temperature limits, IPC-2221 voltage creepage clearances, and DFT/DFA industrial criteria.",
        "mimeType": "application/json",
    },
    {
        "uri": "circuit://blocks/catalog",
        "name": "CircuitBlocks DSL Catalogue",
        "description": "Complete JSON catalogue of all 19 pre-audited hardware circuit blocks with pins, packages, and LCSC part numbers.",
        "mimeType": "application/json",
    },
    {
        "uri": "circuit://rules/jlc-smt",
        "name": "JLCPCB SMT Engineering Rules & Stackup",
        "description": "Design constraints for JLCPCB manufacturing: JLC04161H 4-layer stackup, clearances, annular rings, and fee structure.",
        "mimeType": "application/json",
    },
    {
        "uri": "circuit://examples/esp32c3-minimal",
        "name": "Reference Netlist: ESP32-C3 Minimal IoT Node",
        "description": "Complete verified reference netlist for an ESP32-C3 environmental sensor board.",
        "mimeType": "application/json",
    },
    {
        "uri": "circuit://examples/stm32f103-controller",
        "name": "Reference Netlist: STM32F103 Industrial Board",
        "description": "Complete verified reference netlist for an STM32F103 industrial controller with Type-C, crystal, and LDO.",
        "mimeType": "application/json",
    },
    {
        "uri": "circuit://examples/rp2040-dualcore",
        "name": "Reference Netlist: RP2040 High-Density Board",
        "description": "Complete verified reference netlist for an RP2040 dual-core controller with 4-layer stackup constraints.",
        "mimeType": "application/json",
    },
]

# --------------------------------------------------------------------------- #
# Prompt Definitions
# --------------------------------------------------------------------------- #

AVAILABLE_PROMPTS = [
    {
        "name": "design_hardware_project",
        "description": "End-to-end guided workflow for synthesizing, calculating, and validating an embedded hardware design.",
        "arguments": [
            {
                "name": "requirements",
                "description": "Hardware requirements and peripherals needed (e.g. '基于 STM32F103 的 RS485 工业温湿度采集板')",
                "required": True,
            },
            {
                "name": "target_mcu",
                "description": "Target microcontroller (STM32F103, ESP32-C3, ESP32-S3, RP2040, STC89C52)",
                "required": False,
            },
            {
                "name": "power_source",
                "description": "Target power source (USB-C, Battery TP4056, DC 12V)",
                "required": False,
            },
        ],
    },
    {
        "name": "audit_schematic_netlist",
        "description": "Senior Principal Electrical Engineer inspection prompt (PI/SI/DFM gates, decoupling rules, differential pairs).",
        "arguments": [
            {
                "name": "netlist_json",
                "description": "Hardware netlist JSON data to be audited.",
                "required": True,
            }
        ],
    },
    {
        "name": "optimize_bom_cost",
        "description": "PCBA manufacturing cost-reduction prompt converting Extended parts to Basic parts to save ¥20 feeder fees.",
        "arguments": [
            {
                "name": "components",
                "description": "Comma-separated or JSON list of component names/part numbers.",
                "required": True,
            }
        ],
    },
    {
        "name": "audit_industrial_compliance",
        "description": "Enterprise-grade industrial compliance review prompt: IPC-2152 current capacity, IPC-2221 voltage creepage, DFT testpoints, and IEC 61000-4-2 TVS protection.",
        "arguments": [
            {
                "name": "netlist_json",
                "description": "Hardware netlist JSON to audit for industrial compliance.",
                "required": True,
            }
        ],
    },
]


# --------------------------------------------------------------------------- #
# Output schemas
# --------------------------------------------------------------------------- #
# Declared in a separate module because an output schema is a promise: the server
# MUST return conforming `structuredContent`, so only tools whose response shape
# is genuinely a contract get one. Applied here rather than inline so the
# declaration stays reviewable in one place.

from .output_schemas import OUTPUT_SCHEMAS as _OUTPUT_SCHEMAS


def _apply_output_schemas(tools: list[dict]) -> None:
    """Attach ``outputSchema`` to the tools that declare one."""
    for tool in tools:
        schema = _OUTPUT_SCHEMAS.get(tool.get("name", ""))
        if schema is not None:
            tool["outputSchema"] = schema


_apply_output_schemas(AVAILABLE_TOOLS)
