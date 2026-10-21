<p align="center">
  <img src="docs/images/banner-1200x640.png" alt="CircuitAgent Banner" width="100%">
</p>

<p align="center">
  <strong>Prompt → Schematic → Layout → 3D Enclosure → Fabrication Bundle</strong>
</p>

<p align="center">
  <a href="https://mo9652962-ai.github.io/circuit-agent/"><img src="https://img.shields.io/badge/Demo-Live%20EDA%20Workbench-success?style=flat-square&logo=googlechrome&logoColor=white" alt="Live Demo"></a>
  <a href="https://github.com/mo9652962-ai/circuit-agent/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/mo9652962-ai/circuit-agent/ci.yml?style=flat-square&label=CI" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="tests/"><img src="https://img.shields.io/badge/Tests-383%20passing-success?style=flat-square" alt="Tests"></a>
  <a href="https://github.com/mo9652962-ai/circuit-agent/releases"><img src="https://img.shields.io/badge/Release-v0.4.1-blueviolet?style=flat-square" alt="Release"></a>
  <a href="https://github.com/modelcontextprotocol/registry"><img src="https://img.shields.io/badge/MCP_Registry-circuit--agent-black?style=flat-square" alt="MCP Registry"></a>
  <img src="https://img.shields.io/badge/KiCad-10.0%20Export-314CE0?style=flat-square&logo=kicad&logoColor=white" alt="KiCad 10">
</p>

<p align="center">
  <a href="https://mo9652962-ai.github.io/circuit-agent/"><b>🌐 Live EDA Workbench</b></a>
  ·
  <a href="README.md"><b>🇨🇳 中文说明</b></a>
  ·
  <a href="README_EN.md"><b>🇬🇧 English</b></a>
  ·
  <a href="#mcp-server-integration">🔌 MCP Server</a>
  ·
  <a href="#supported-circuit-blocks">🧩 19+ CircuitBlocks</a>
  ·
  <a href="#industrial-dfx-audit--thermalclearance-simulation">🏭 Industrial DFX</a>
  ·
  <a href="#3--export-manufacturing-data--solve-parametric-equations">📐 KiCad/BOM Export</a>
  ·
  <a href="https://github.com/mo9652962-ai/circuit-agent/issues">💬 Issues</a>
</p>

---

## Overview

Allowing LLMs to directly output raw traces, footprints, and copper coordinates invariably produces DRC violations and short-circuits. **CircuitAgent** constrains language models to **pre-verified, auditable circuit building blocks** (CircuitBlocks DSL) and emits deterministic netlists governed by Pydantic contracts and JSON Schema.

The LLM is tasked with architectural block selection and parameterization—not trace drawing.

<p align="center">
  <img src="docs/images/demo.gif" alt="CircuitAgent Pro Demo" width="85%">
</p>

```text
Natural language prompt
        │
        ▼
┌────────────────────────┐
│  CircuitBlocks DSL     │  keyword → audited sub-circuits (deterministic)
└────────────────────────┘
        │
        ▼
┌────────────────────────┐
│  Netlist contract      │  Pydantic / JSON Schema (SSOT)
└────────────────────────┘
        │
   ┌────┴─────┐
   ▼          ▼
┌────────┐ ┌──────────────────┐
│ LCSC   │ │ REST / MCP APIs  │
│ client │ │ (community layer)│
└────────┘ └──────────────────┘
```

---

## Quick Start

**Option A · Install from PyPI (recommended)**

```bash
pip install circuit-agent-client
```

**Option B · Use from source**

```bash
git clone https://github.com/mo9652962-ai/circuit-agent.git
cd circuit-agent
```

**Zero runtime dependencies** — pure Python standard library, install-and-run with no third-party packages pulled in.  
To run the test suite: `pip install -e ".[dev]"`

### 1 · Synthesize a Hardware Netlist in One Line

```python
from client.synthesizer import synthesize_from_prompt

spec = synthesize_from_prompt(
    "ESP32-C3 environmental monitoring node with Type-C power, I2C sensor socket, LED and 2 buttons"
)

print(spec["chip_id"])                            # ESP32-C3
print(len(spec["modules"]))                       # Number of components
print(spec["netlist"]["connections"][0])          # First electrical connection
print(spec["unmatched"])                          # Requested but NOT supported yet (actionable)
print(spec["not_requested"])                      # Optional blocks the prompt did not mention
```

The mapping is **deterministic**: identical prompts yield byte-for-byte identical intermediate representations.

`unmatched` and `not_requested` are deliberately separate signals. `unmatched` lists
capabilities the caller asked for that this DSL cannot build yet (e.g. `ethernet`,
`relay`, `motor_driver`) and is what an agent should surface to the user;
`not_requested` is purely informational — those blocks were never mentioned.

### 2 · Query Live LCSC Stock & Pricing (Key-Free)

```python
from client.lcsc_client import search_lcsc_parts

for part in search_lcsc_parts("CH340N", limit=3):
    print(f"[{part['lcsc_part']}] {part['part_number']} | {part['package']} | "
          f"Stock {part['stock']} | ${part['price_usd']} | {part['part_class']}")
```

```text
[C506813] CH340N | SOP-8_L5.0-W4.0-P1.27-LS6.0-BL | Stock 196 | $0.5537 | Extended Part
```

Features **exponential backoff + hard timeout + 24h disk TTL cache + defensive parsing**. Network drops fall back to cache gracefully without raising exceptions.

### 3 · Export Manufacturing Data & Solve Parametric Equations

```python
from client.export_engine import export_kicad_netlist, export_jlcpcb_bom
from client.parametric_equations import solve_resistor_divider, calculate_ldo_thermal

# KiCad 6-10 S-Expression netlist — import straight into Pcbnew, no schematic needed
print(export_kicad_netlist(spec, title="MyBoard"))

# JLCPCB production BOM (grouped, Basic/Extended classified)
print(export_jlcpcb_bom(spec))

# Pick an optimal E96 divider pair for 12V -> 3.3V
print(solve_resistor_divider(v_in=12.0, v_out_target=3.3))

# Is a SOT-23 LDO going to melt at 800mA?
print(calculate_ldo_thermal(v_in=24.0, v_out=3.3, i_load_a=0.8, package="SOT-23").recommendation)
```

---

## Block Catalogue

| Block | Description | Critical Design Rules |
|:---|:---|:---|
| `block_usb_c_power` | USB Type-C Input | Dual 5.1k CC pull-downs (Sink role) |
| `block_power_ldo_3v3` | AMS1117-3.3V LDO | 10µF input/output bypass decoupling |
| `block_crystal_clock` | Passive Crystal Osc | Declares `guard_ring` for RF ground shield |
| `block_button` | Debounced Key | 10k pull-up + 100nF RC debounce filter |
| `block_led` | Status Indicator | Series current-limiting resistor |
| `block_buzzer` | Active Buzzer | S8050 NPN driver + 1N4148W freewheeling diode |
| `block_i2c_header` | I2C Header Socket | Dual 4.7k pull-ups on SCL/SDA |
| `block_rs485_transceiver` | SP3485 RS485 Fieldbus | 120Ω differential termination + 100nF decoupling + 3P header |
| `block_can_transceiver` | SN65HVD230 3.3V CAN Node | 120Ω termination + 10k slope control (High-speed mode) |
| `block_battery_tp4056` | TP4056 1A Li-Ion Charger | 1.2k current limit + dual CHG/STD LEDs + 2P battery terminal |
| `block_sensor_aht20` | AHT20 Temperature & Humidity | Industrial I2C bus + decoupling, DFN-6 (LCSC C2757850) |
| `block_sensor_mpu6050` | MPU-6050 6-Axis IMU | 3-axis gyro + 3-axis accel, bypass decoupling, QFN-24 (C24112) |
| `block_esd_usb_tvs` | USB High-Speed ESD Array | USBLC6-2SC6 ultra-low junction capacitance (0.6pF), SOT-23-6 |
| `block_esd_rs485_tvs` | RS-485 Industrial Surge TVS | SM712 asymmetric bidirectional (−7V / +12V working range) |
| `block_esd_can_tvs` | CAN Bus Dual-Line TVS | PESD1CAN 24V automotive-grade dual-line array, SOT-23 |
| `block_reverse_polarity_protection` | Input Reverse-Polarity Guard | Schottky SS34 **or** low-drop P-MOSFET (AO3401A) |
| `block_power_pi_filter` | Input EMI π Filter | Ferrite bead (600Ω @ 100MHz) + bulk decoupling |
| `block_fiducial_marks` | SMT Optical Fiducials | 3× 1.0mm bare copper pads, 2.0mm mask opening (DFA) |
| `block_testpoint_matrix` | ICT Test-Point Matrix | 1.0mm SMD pads covering power rails, ground, SWD, UART |
| `block_watchdog_supervisor` | TPS3823 watchdog/reset supervisor | 1.6s WDI petting + push-pull reset (industrial MCU anti-runaway, IEC 61508 practice) |
| `block_ethernet_phy_w5500` | W5500 SPI Ethernet MAC/PHY | 10/100M PHY + RJ45 with integrated transformer & LEDs (HR911105A) + 25MHz crystal |
| `block_isolated_adc_ina219` | INA219 I2C power/current monitor | 0.1Ω 2W 1% precision shunt resistor + real-time bus telemetry |
| `block_motor_driver_drv8825` | DRV8825 2.5A 45V stepper driver | 1/32 microstepping + 100µF 50V bulk cap + XH-4P terminal |
| `block_optocoupler_isolated_io` | PC817 5000Vrms isolated input | 2.4k limiter + reverse diode for 24V industrial PLC signals |

Every block's pin numbers, LCSC part numbers and package names are cross-checked
against datasheets and the LCSC catalogue before being frozen.
`tests/test_circuit_blocks.py` enforces the invariants: unique designators, every
component carries a footprint and an LCSC number, every net endpoint resolves to a
declared component, and every block ties to `/GND`.

---

## MCP Server (AI Agent Integration)

CircuitAgent bundles a standards-compliant JSON-RPC 2.0 stdio MCP Server written in pure Python standard library (zero external pip packages required). It connects out of the box with **Claude Desktop**, **Cursor**, and **Windsurf**.

It currently exposes **68 tools**, 8 resources (`circuit://` URIs) and 4 engineering prompts (slash-commands).

### Protocol revision: MCP `2026-07-28`

The server implements the **2026-07-28 stateless core** and stays backward compatible with handshake clients down to `2024-11-05`:

| Capability | Status |
|:---|:---|
| `server/discover` | ✅ Mandatory method — versions, capabilities and identity in one exchange; also the stdio backward-compatibility probe |
| Handshake-free requests | ✅ Every request self-describes its protocol version and client capabilities in `params._meta`; works without `initialize` |
| `resultType` | ✅ All results carry `"complete"` (or `"input_required"`); older clients safely ignore it |
| Cache hints | ✅ `tools/list` / `resources/list` / `prompts/list` return `ttlMs` + `cacheScope` |
| Deterministic ordering | ✅ Tool catalogue order is stable so client and upstream prompt caches hit |
| Error-code allocation | ✅ Uses the spec-reserved `-32020`–`-32099` range; resource-not-found moved to `-32602` |
| Legacy handshake | ✅ `initialize` retained with version negotiation, so pre-2026 clients keep working |
| **Structured output** | ✅ Dual channel: `content` for the model, `structuredContent` for programs, strictly semantically equivalent; 6 electrical tools declare `outputSchema` |

### Dual-channel output

MCP 2026-07-28 defines two output channels for `tools/call`, and requires them to be **semantically equivalent** when both are present:

- `content` — model-oriented. A language model only reads this one; token cost and readability win here.
- `structuredContent` — machine-oriented. For code generation, typed orchestration and strict `outputSchema` validation.

This server **derives one from the other**: tools already return JSON, so the structured channel is produced by parsing that same document, which makes disagreement impossible (a test asserts it across the whole catalogue). File-export tools (KiCad netlist, Gerber, IPC-2581, BOM CSV) and the ASCII topology renderer declare no `outputSchema` — they produce documents, not data objects, and a schema for them would only describe a string container. Error results carry no structured payload either: a failed call has no schema-conforming document, and inventing an error object shape would be a contract nobody asked for.

The `instructions` field of `server/discover` is written for an LLM to read: call `synthesize_circuit` for a netlist,
gate it with `run_erc`, then `audit_industrial_dfx` and `validate_manufacturing_package`, and only then export.
Everything named `calculate_*` / `analyze_*` is a pure function (no network, no state) and safe to probe;
`search_lcsc_parts` is the only networked tool, and it is key-free.

### Start stdio Server
```bash
python -m client.mcp_server
```

### Claude Desktop Configuration (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "circuit-agent": {
      "command": "python",
      "args": ["-m", "client.mcp_server"],
      "cwd": "/path/to/circuit-agent"
    }
  }
}
```

### Exposed Tools
1. `synthesize_circuit`: Natural-language prompt to deterministic netlist & module specification.
2. `search_lcsc_parts`: Key-free live query of LCSC/JLCPCB parts, stock, pricing, and packaging.
3. `list_circuit_blocks`: List all 24 pre-validated hardware DSL blocks.
4. `validate_netlist`: Validate netlists against the formal CircuitAgent JSON Schema.
5. `calculate_trace_impedance`: Microstrip & differential pair trace impedance solver (IPC-2141 / Wheeler) for USB 90Ω, RF 50Ω, CAN 120Ω.
6. `calculate_bom_cost`: PCBA bill-of-materials cost breakdown calculator with JLCPCB Extended library surcharge detection.
7. `list_supported_chips`: Enumerate supported MCU models and their hard pin-allocation rules.
8. `register_custom_chip`: Dynamically register third-party MCU physical pin constraints and peripheral maps.
9. `calculate_ipc2152_trace_current`: IPC-2152 conductor current-carrying capacity, or solve required trace width for a target current (copper weight, ΔT, inner-layer derating).
10. `audit_industrial_dfx`: Industrial DFX (DFM/DFA/DFT/DFC) compliance auditor — returns a weighted score, graded verdict, categorised findings and a Markdown report.
11. `export_kicad_netlist`: Export a standard KiCad S-Expression netlist (`.net`) importable into KiCad 6/7/8/9/10 Pcbnew.
12. `export_manufacturing_bom`: Generate a production JLCPCB SMT BOM CSV with designator grouping and Basic/Extended classification.
12b. `export_manufacturing_cpl`: Generate the JLCPCB pick-and-place (CPL/pos) file: designator, centre coordinates, layer, rotation. The BOM and CPL are delivered as a pair — a part in the BOM but absent here is purchased and never soldered, and the fault surfaces at functional test rather than at assembly.
13. `calculate_parametric_circuit`: Closed-form parametric design solvers — E96 resistor dividers, LDO thermal/junction temperature, I2C pull-ups, RC filters.
14. `render_circuit_topology`: Render a structured ASCII architecture diagram of power domains, buses and subsystems.
15. `run_erc`: Netlist-level Electrical Rules Check gate — 40+ rules covering floating nets, missing GND, unknown designators, missing power domain, missing decoupling, differential bus termination and more; every finding carries a severity and a standard reference, and blocking/error issues gate BOM/CPL delivery. The `MLCC_EFFECTIVE_CAPACITANCE_DEFICIT` rule recomputes each capacitor's real capacitance under its rated bias and warns below 60% retention; when a part carries no bias metadata the rule abstains rather than inventing one.
16. `analyze_power_tree`: System-level power distribution architecture and thermal analyzer — load currents, regulator dropout headroom, and LDO junction temperature estimates ($T_j$).
17. `calculate_ipc2221_clearance`: Calculate minimum conductor clearance based on IPC-2221B Table 6-1 voltage and classification (B1 internal, B2 external uncoated, B4 coated, A6 leads).
18. `export_specctra_dsn`: Generate universal Specctra DSN (v15.0) auto-router interchange file with heuristic auto-placement for automated track routing in Freerouting or KiCad.
18b. `autoroute_pcb`: Native Python PCB layout & multi-layer autorouter engine generating standard Specctra SES session tracks and physical routing metrics (completion rate, total wire length, via count, layer utilization) with zero JVM dependencies.
19. `export_kicad_schematic`: Export native modern KiCad 8/9 S-Expression schematic (.kicad_sch) directly viewable and editable in Eeschema with sheet layout and component symbols.
20. `audit_supply_chain`: Supply chain multi-sourcing resilience auditor (ISO 9001 audit), identifying single-source bottlenecks and mapping pin-compatible second-source drop-in replacements with LCSC cross-references.
21. `calculate_differential_skew`: High-speed differential pair intra-pair propagation delay skew solver (USB 2.0 HS ≤10ps, Ethernet ≤25ps, CAN-FD ≤50ps) with serpentine tuning geometry calculations.
22. `export_ipc_d356`: Generate universal IPC-D-356A ASCII bare-board electrical test netlist file for industrial flying probe testers (AEMG, ATG, MicroCraft) and bed-of-nails test fixtures.
23. `export_gerber_bundle`: Generate native fabrication-ready Gerber RS-274X layer bundle (Edge_Cuts .gm1, Top Copper .gtl, Top Mask .gts, Top Silkscreen .gto) directly from placed modules and netlists.
24. `calculate_pcb_stackup_impedance`: Standard industrial 4-layer (JLC04161H) and 6-layer (JLC06161H) stackup matrices with IPC-2141A controlled impedance solver for RF 50Ω, USB 90Ω, Ethernet 100Ω, and CAN/RS485 120Ω.
25. `export_excellon_drill`: Generate production IPC-NC-349 Excellon CNC drill file (.drl) with metric tool headers (T01C... T02C...), completing the 5-layer PCB manufacturing bundle for automated CNC drilling machines.
26. `generate_interactive_bom`: Generate a lightweight self-contained single-file Interactive HTML BOM (iBOM, InteractiveHtmlBom-compatible) with interactive component grouping table, vector SVG board map, and bidirectional hover/click inspection.
27. `calculate_smt_feeder_matrix`: SMT pick-and-place feeder slot allocator (8/12/16/24mm) and nozzle tooling matrix optimizer (502~506) adhering to EIA-481 and OpenPnP/Juki standards.
28. `export_openpnp_job`: Export automated OpenPnP and industrial SMT pick-and-place board job CSV (part, designator, X/Y coords, rotation, nozzle ID, feeder slot assignment).
29. `calculate_ipc7351_land_pattern`: IPC-7351B surface mount land pattern and courtyard boundary solver (Toe, Heel, Side solder goals, RMS tolerances) across Density Levels A (Most), B (Nominal), and C (Least).
30. `calculate_pcb_panel_rails`: SMT automated assembly panel frame calculator with breakaway process rails, conveyor clamp clearances, SMEMA tooling holes (NPTH Φ3.2mm), optical fiducials, and de-paneling features (V-Cut or mouse-bites) per IPC-2221B Section 8.4 and IPC-SMEMA-9851.
31. `calculate_ict_testpoints`: Automated In-Circuit Test (ICT) bed-of-nails testpoint allocator and fault coverage analyzer (B.Cu Φ1.0mm/2.54mm grid) per IPC-9252 and IPC-2221B with probe head style assignments (crown, spear, serrated).
32. `calculate_bga_escape_routing`: BGA diagonal 45° dogbone via fanout geometry solver, escape channel clearance verification, and minimum PCB signal layer demand estimator per IPC-7095 Section 5.2.
33. `calculate_teardrop_reinforcement`: Tangent arc and linear teardrop fillet reinforcement solver for PCB vias and pads, preventing thermal stress fractures and guaranteeing IPC-2221B Section 9.1.5 and IPC-A-600J Class 3 breakout compliance.
34. `calculate_copper_thieving_balance`: Layer copper density balance solver evaluating reflow thermal bow/twist warpage risk (IPC-TM-650 2.4.22 ≤0.75%), generating non-functional dummy copper thieving dot/grid patterns per IPC-2221B Section 10.1.1.
35. `calculate_via_stitching_array`: Thermal via array solver for QFN/power exposed pads (IPC-7093 Section 7.2) or RF ground shielding fence arrays (IPC-2141A <= lambda/10 pitch) with thermal resistance metrics.
36. `calculate_serpentine_tuning_geometry`: High-speed differential pair serpentine delay tuning geometry solver guaranteeing self-coupling avoidance (S >= 3W, H >= 3W) per IPC-2141A Section 5.3.
37. `calculate_stencil_aperture_ratios`: Per-aperture area ratio (>= 0.66) and aspect ratio (>= 1.5) compliance evaluator per IPC-7525, identifying paste-release-deficient fine-pitch apertures that cause tombstoning, opens, and BGA head-in-pillow defects.
38. `calculate_fiducial_layout`: Asymmetric 3-point global optical fiducial layout generator (180° rotation unambiguous) with automatic diagonal local fiducials for <= 0.5mm fine-pitch components per IPC-2221B Section 12 and JEDEC J-STD-020.
39. `calculate_via_protection_plan`: IPC-4761 via protection type selector (Type I ~ VII) by assembly context: Type VII filled-and-capped (VIPPO) mandatory for BGA via-in-pad, Type V fill for thermal pads, Type IV tent+plug for BGA channels, Type II tent for free vias.
40. `calculate_solder_paste_volume`: Per-aperture deposited solder paste volume assessment against target joint volume per IPC-7525A transfer analysis (accepted ratio window 1.0 ~ 2.5), flagging starved joints and excessive paste defects.
41. `export_ipc2581`: Export a simplified IPC-2581B single-file intelligent fabrication data package (XML) — stackup, BOM, placed components, net pin membership, and board profile — replacing the legacy Gerber+Excellon+TXT handoff bundle accepted by Siemens X / Altium / Zuken and major EMS houses.
42. `export_assembly_drawing_svg`: Scaled PCBA assembly drawing SVG per ASME Y14.5 and IPC-2221B Section 11 — body outlines with refDes labels, polarity marks (pin-1 dots, cathode bars, plus frames), mirrored bottom view, and ASME Y14.100 title block (revision / scale / check signature).
43. `diff_netlists`: Engineering Change Order (ECO) netlist diff engine — reports added/removed components, value/package changes, added/removed nets, pin membership moves, and ECO severity (NONE/MINOR/MAJOR) between two netlist revisions, supporting PLM change management hand-off to manufacturing, procurement, and test.
44. `generate_assembly_process_plan`: Mixed-assembly process route planner — classifies each component into SMD reflow / THT wave / THT manual / mechanical stages per IPC-A-610G Section 7 and outputs the 10-stage EMS routing (SPI -> reflow -> AOI -> THT insert -> wave/selective -> manual -> ICT -> FCT -> coating -> packing).
45. `optimize_panel_grid`: Panel grid utilization optimizer — enumerates grid_x x grid_y combinations with rail layouts and de-paneling methods (V-cut / mouse-bites), filters layouts exceeding the fab panel limit (default 300x300mm), and ranks feasible options by material utilization percentage.
46. `calculate_fab_cost`: PCB fabrication cost estimator — tiered pricing model (2/4/6 layers x 5/10/30/100 quantity tiers, area surcharge beyond 100x100mm, solder mask color, surface finish HASL/ENIG/OSP, thickness, lead-time factor) returning total and per-unit estimates.
47. `calculate_smt_placement_clearance`: SMT nozzle Z-clearance & height envelope analyzer — evaluates keepout envelopes (min 2.0mm horizontal gap) between tall components (H >= 4.0mm) and low components (0402/0603) and generates layered placement priority sequences per IPC-SM-782 and OpenPnP.
48. `calculate_creepage_isolation_slot`: High-voltage creepage isolation slot calculator — assesses conductor spacing against IPC-2221B Table 6-1 and IEC 62368-1, planning milled air isolation slots (width, length, endpoints, and expanded path) when surface distance is insufficient.
49. `analyze_impedance_tolerance`: Characteristic impedance manufacturing tolerance & sensitivity analyzer — models Polar SI9000 parameter variations (H +-10%, W +-10%, T +-15%, Er +-5%) to calculate Zmin/Zmax, sensitivities (dZ/dW, dZ/dH), and yield within +-10% target per IPC-2141A.
50. `evaluate_material_cti_creepage`: Substrate Comparative Tracking Index (CTI) & creepage evaluator — classifies Material Groups (Group I >=600V to Group IIIb) per IEC 62368-1 Table 25 and IPC-2221B, calculating safety margins under Pollution Degrees 1/2/3 and recommending high-CTI laminates.
51. `calculate_wave_solder_orientation_audit`: Wave soldering component orientation & shadow auditor — audits chip passives (0603/0805) perpendicular to wave flow (prevents tombstoning), SOIC ICs parallel to flow (prevents pin bridging), and 3xH shadow keepout envelopes per IPC-7351B Section 3.1.4 and SMTA guidelines.
52. `calculate_press_fit_hole_compliance`: Press-fit compliant pin PTH tolerance analyzer — evaluates finished hole diameter (standard 0.94mm~1.09mm) and copper barrel plating (>=25μm) per IPC-9797 and IEC 60352-5, estimating insertion and retention forces to prevent barrel tear or vibration disconnects.
53. `audit_fab_capabilities`: PCB fab house capability profile auditor — checks layout design parameters against real-world fab house constraints (JLCPCB standard/advanced, PCBWay, OSH Park) including min trace/space, min via drill, annular rings, aspect ratio, and slot widths to prevent engineering query (EQ) holds.
54. `validate_manufacturing_package`: Headless manufacturing package validator — validates 5-layer Gerbers, Excellon drill files, BOM, and CPL for completeness, non-emptiness, and refDes consistency, computing a SHA-256 tamper-proof ledger for automated CI/CD release pipelines.
55. `audit_ipc6012_class_compliance`: Rigid PCB qualification and Class 1/2/3 acceptance criteria auditor per IPC-6012E and IPC-A-600J — audits external/internal annular rings, zero-breakout constraints for Class 3, average PTH barrel copper plating (Class 3 >= 25μm), conductor width reduction limits, and solder mask dam widths.
56. `optimize_smt_feeder_setup`: SMT pick-and-place feeder trolley allocation optimizer — applies Group Technology (GT) to pin common passive reels (100nF, 10k) on standard 80-slot feeder carts (Panasonic NPM / Fuji NXT / ASM SIPLACE), clusters high-density reels near the gantry centroid to minimize travel time, and forecasts reel run-out exhaustion points per batch size per IPC-9851.
57. `calculate_copper_pour_current_drop`: Polygon copper pour and power busbar DC IR-drop & thermal density analyzer — models sheet resistance, total resistance, voltage drop, and Joule power dissipation per IPC-2152 Section 5.0 and IEC 60092-352, checking bottleneck constriction current density (<=35.0 A/mm²) to prevent trace blistering or delamination.
58. `audit_component_msl_floor_life`: SMD moisture sensitivity level (MSL) shop floor life and baking auditor — tracks plastic package (BGA/QFN/CSP/TQFP) open-bag ambient exposure time against JEDEC J-STD-033D and IPC-M-109 limits, flagging expired devices and prescribing standardized dehumidification bake schedules (125°C or 40°C desiccant bake) to prevent 260°C reflow popcorning delamination.
59. `calculate_effective_capacitance`: Real MLCC capacitance at operating conditions — **the marked value is not the value in circuit**. Multiplies the four compounding loss mechanisms: DC bias (dominant, typically 35–65% loss at rated voltage and worse in small cases), AC signal level, temperature coefficient, and logarithmic dielectric ageing, then applies part tolerance. Returns the full factor stack so the dominant killer is identifiable. Class I (C0G/NP0) correctly short-circuits to tolerance-only. Pass a measured retention from a datasheet curve (Murata SimSurfing / TDK SEAT) to replace the band estimate and get `confidence="measured"`.
60. `size_hold_up_capacitor`: Brown-out ride-through reservoir sizing — solves C = I·t/ΔV in **effective** farads, then divides by the retention at the worst-case bias in the window to report the marked value you must actually buy. Reports achieved hold time, shortfall, and required marked capacitance. Sizing from the marked value is exactly how a design "passes" and then delivers 0.85 ms of hold-up against a 20 ms spec.
61. `analyze_rc_filter_effective`: RC filter cutoff computed from the capacitance the part actually has, not the marked value. A nominal 1 kHz filter built with an X5R part retaining only 40% under bias cuts at 2.5 kHz. Returns nominal vs actual cutoff, drift percentage and cause, and keeps operating-condition derating explicitly separate from part tolerance — two independent error sources.
62. `analyze_divider_tolerance`: Divider tolerance band — **nominal is not a specification**. Reports both the exact worst case (four-corner enumeration, exact because the transfer function is monotonic in each resistor) and the realistic statistical band (first-order sensitivity propagation). The methodological point: the output is a quotient of random variables, so naive RSS of percentage tolerances is invalid (TI SNVA112 states this explicitly) — the partial derivatives must convert each uncertainty to a voltage contribution first. Includes TCR, sqrt-of-time life drift, supply tolerance and matched-pair ratio tolerance, and names the resistor that dominates the error budget.
63. `analyze_resistor_error_budget`: End-of-life resistance band from the four-term error model (value tolerance + TCR + life drift + matched-network ratio tolerance). Reports both the RSS band and the linear worst-case band and names the dominant term — buying a ±0.1% thick-film part to fix an accuracy problem usually does nothing, because its 200 ppm/°C TCR already contributes 1.2% over a 60 °C excursion. Life drift scales with the square root of the time ratio (random walk, not a ramp).
64. `solve_feedback_divider`: Exact R1/R2 feedback pair for a regulator or comparator target, plus the static error the E96 snap adds. The ideal pair almost never exists in E96, and that snap error is a **systematic offset, not a tolerance**: it is identical on every board and must be budgeted separately from the tolerance band.
65. `calculate_high_speed_skin_depth_loss`: High-frequency skin effect depth and copper foil surface roughness attenuation analyzer — calculates skin depth, Hammerstad-Jensen roughness correction factor (Ksr), and conductor attenuation (dB/inch) for 1GHz to 50GHz signals (PCIe 5.0/6.0, 112G PAM4) per IPC-4562B and IPC-2141A across standard ED, VLP, and HVLP/RTF foils.
66. `calculate_bare_board_test_parameters`: Bare-board continuity and isolation test parameter planner & dielectric safety auditor — plans IPC-9252B Class 1/2/3 test voltages (50V, 100V, 250V DC) and continuity thresholds (signal <= 10Ω, power <= 2Ω), automatically derating test voltage to 100V on fine-pitch (<0.100mm) or sensitive RF nets to prevent micro-arc dielectric breakdown.

### Exposed Resources
Directly mount specifications and catalogues into model context via `circuit://` URIs:
- `circuit://specs/netlist-schema`: The formal Draft-07 JSON Schema.
- `circuit://specs/cpl-standard`: JLCPCB SMT coordinate and rotation offset specifications.
- `circuit://specs/ipc-dfx-rules`: IPC-2152 current/temperature limits and IPC-2221 voltage creepage clearances.
- `circuit://blocks/catalog`: Complete catalogue of 24 standard CircuitBlocks (pins, nets, LCSC part numbers).
- `circuit://rules/jlc-smt`: JLCPCB SMT physical rules, 4-layer stackup (JLC04161H), and fee schedules.
- `circuit://examples/esp32c3-minimal`: ESP32-C3 minimal IoT node reference netlist.
- `circuit://examples/stm32f103-controller`: STM32F103 industrial controller reference netlist.
- `circuit://examples/rp2040-dualcore`: RP2040 high-density dual-core reference netlist.

### Reusable Engineering Prompts (Slash-Commands)
- `/design_hardware_project`: Guided end-to-end hardware synthesis, impedance check, and schema validation.
- `/audit_schematic_netlist`: Senior Principal EE inspection prompt (PI/SI/DFM gates, decoupling capacitor proximity).
- `/optimize_bom_cost`: PCBA BOM cost reduction prompt substituting Extended parts for Basic library parts.
- `/audit_industrial_compliance`: Industrial DFX review — IPC-2152 current/temperature, IPC-2221 creepage, DFT test-point coverage and port-level TVS protection.

---

## Data Contracts & Specs

- [`specs/netlist_schema.json`](specs/netlist_schema.json) — Full Netlist & Circuit JSON Schema (Draft-07)
- [`specs/cpl_standard.md`](specs/cpl_standard.md) — JLCPCB SMT coordinate standard & angle compensation table
- [`examples/`](examples/) — Verified golden netlists for STM32F103, ESP32-C3, and RP2040

---

## Test Suite & CI

```bash
pytest tests/ -q      # 240 passed
```

GitHub Actions matrix tests against `ubuntu-latest` and `windows-latest` across Python 3.10, 3.11, and 3.12.
Two additional jobs validate that every `examples/` netlist conforms to the JSON
Schema, and that the README quickstart plus the LCSC client's offline degradation
path both work on a bare runner with no network.

---

## Scope & Roadmap

**Included in this community repository**:
Hardware DSL and building blocks, key-free LCSC live parts client, netlist & CPL
specifications, industrial DFX audit engine, manufacturing/EDA exporters,
parametric design solvers, standard MCP Server, REST client bridges.

**High-level compiler stages (In active development)**:
Multi-layer physical placement & auto-routing solver, parametric 3D enclosure Boolean
geometry, Senior EE physical rule DRC gate.

- [x] Pre-verified block catalogue + deterministic mapping + unit tests
- [x] LCSC live parts client (retry / cache / fallback)
- [x] Formal JSON Schema + 3 MCU golden examples + CI matrix
- [x] CircuitAgent Pro dark industrial web interface (`web/index.html`)
- [x] Industrial fieldbus & power blocks (RS485, CAN bus, TP4056 Li-Ion)
- [x] Standards-compliant stdio MCP Server (Tools + Resources + Prompts)
- [x] Bilingual documentation & official branding
- [x] Additional sensor blocks (AHT20, MPU6050)
- [x] Custom MCU pin-mapping override engine
- [x] Industrial DFX audit (DFM/DFA/DFT/DFC) + IPC-2152 / IPC-2221 rule engine
- [x] EDA & manufacturing exporters (KiCad netlist, JLCPCB BOM/CPL)
- [x] Parametric design solvers (E96 dividers, LDO thermals, I2C pull-ups, RC)
- [x] Pinout rules for five mainstream MCUs (ESP32-S3 / ESP32-C3 / STM32F103 / RP2040 / STC89C52RC)
- [x] Automatic series power-chain assembly (Type-C → protection → π filter → LDO) with MCU supply/ground binding
- [x] Passive-network tolerance analysis (worst-case + statistical RSS, MLCC DC-bias derating, hold-up sizing)
- [x] MCP dual-channel structured output (`content` + `structuredContent`, 6 tools declaring `outputSchema`)
- [ ] Multi-layer placement & routing solver

### Supported MCUs

| Chip | Package | Supply | LCSC | Notes |
|:---|:---|:---|:---|:---|
| ESP32-S3 | ESP32-S3-WROOM-1 | 3.3 V | C2913202 | I2C=IO8/IO9, UART0=IO43/IO44, TWAI=IO4/IO5, strapping IO0/3/45/46 reserved |
| ESP32-C3 | ESP32-C3-WROOM-02 | 3.3 V | C2934560 | 11 usable GPIOs, no SWD (JTAG/USB-JTAG); reports `unrouted_signals` when short |
| STM32F103C8T6 | LQFP-48 | 3.3 V | C8734 | CAN on remapped PB8/PB9, keeping PA11/PA12 free for USB |
| RP2040 | QFN-56 | 3.3 V | C2040 | I2C0=GPIO4/5, UART0=GPIO0/1 |
| STC89C52RC | LQFP-44 | 5.0 V | C8769 | No hardware I2C (bit-banged on P1.0/P1.1), no CAN |

Pin data comes from vendor datasheets and official design guidelines, cited in each rule.
Every chip the synthesizer can detect must also be one it can place — those two lists
drifting apart is what once left the MCU off the board entirely while the pipeline
reported success. `tests/test_mcu_placement_and_power_chain.py` pins that.

- [ ] Parametric 3D enclosure generation

---

## ⭐ Star History

If CircuitAgent helps your hardware development workflow, consider giving the repo a star!

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=mo9652962-ai/circuit-agent&type=Date)](https://star-history.com/#mo9652962-ai/circuit-agent&Date)

</div>

## License & Privacy

- License: [MIT License](LICENSE) © 2026 sora
- Privacy Policy: [PRIVACY.md](PRIVACY.md) (Zero telemetry, 100% local synthesis, developer-owned data)
