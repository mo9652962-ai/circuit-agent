"""Declarative MCP surface: tools, resources and prompts.

This module is pure data — no logic, no imports beyond the standard library.
Keeping it separate from :mod:`client.mcp_server` means the published MCP
contract (14 tools / 8 resources / 4 prompts) can be reviewed, diffed and
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
    },
    {
        "name": "list_supported_chips",
        "description": "List all registered MCU chips and third-party pinout allocation rules (e.g. CH32V003, STM32G030, ATmega328P).",
        "inputSchema": {
            "type": "object",
            "properties": {},
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
        "description": "List all 10 pre-validated CircuitBlocks available in the hardware DSL catalog.",
        "inputSchema": {
            "type": "object",
            "properties": {},
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
                "modules": {"type": "object", "description": "Component modules dict (from synthesize_circuit output)."},
                "netlist": {"type": "object", "description": "Netlist dict with 'connections' (from synthesize_circuit output)."},
                "board_width_mm": {"type": "number", "description": "PCB width in mm (default: 70.0).", "default": 70.0},
                "board_height_mm": {"type": "number", "description": "PCB height in mm (default: 50.0).", "default": 50.0},
                "trace_width_mm": {"type": "number", "description": "Default routing trace width in mm (default: 0.254 / 10mil).", "default": 0.254},
                "clearance_mm": {"type": "number", "description": "Default routing clearance in mm (default: 0.200 / 8mil).", "default": 0.200},
            },
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
                "modules": {"type": "object", "description": "Component modules dict (from synthesize_circuit output)."},
                "connections": {"type": "array", "description": "Netlist connections list (optional).", "default": []},
                "title": {"type": "string", "description": "Schematic sheet title block title.", "default": "Hardware Design"},
            },
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
                "modules": {"type": "object", "description": "Component modules dict (from synthesize_circuit output)."},
            },
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
# Catalog & Impedance Solvers
# --------------------------------------------------------------------------- #
