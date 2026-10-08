<p align="center">
  <img src="docs/images/banner-1200x640.png" alt="CircuitAgent Banner" width="100%">
</p>

<p align="center">
  <strong>Prompt → Schematic → Layout → 3D Enclosure → Fabrication Bundle</strong>
</p>

<p align="center">
  <a href="https://github.com/mo9652962-ai/circuit-agent/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/mo9652962-ai/circuit-agent/ci.yml?style=flat-square&label=CI" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="tests/"><img src="https://img.shields.io/badge/Tests-240%20passing-success?style=flat-square" alt="Tests"></a>
  <a href="https://github.com/mo9652962-ai/circuit-agent/releases"><img src="https://img.shields.io/badge/Release-v0.1.6-blueviolet?style=flat-square" alt="Release"></a>
  <a href="https://github.com/modelcontextprotocol/registry"><img src="https://img.shields.io/badge/MCP_Registry-circuit--agent-black?style=flat-square" alt="MCP Registry"></a>
  <img src="https://img.shields.io/badge/KiCad-10.0%20Export-314CE0?style=flat-square&logo=kicad&logoColor=white" alt="KiCad 10">
</p>

<p align="center">
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

It currently exposes **24 tools**, 8 resources (`circuit://` URIs) and 4 engineering prompts (slash-commands).

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
13. `calculate_parametric_circuit`: Closed-form parametric design solvers — E96 resistor dividers, LDO thermal/junction temperature, I2C pull-ups, RC filters.
14. `render_circuit_topology`: Render a structured ASCII architecture diagram of power domains, buses and subsystems.
15. `run_erc`: Netlist-level Electrical Rules Check gate — floating nets, missing GND, unknown designators, missing power domain, missing decoupling, differential bus termination; blocking/error issues gate BOM/CPL delivery.
16. `analyze_power_tree`: System-level power distribution architecture and thermal analyzer — load currents, regulator dropout headroom, and LDO junction temperature estimates ($T_j$).
17. `calculate_ipc2221_clearance`: Calculate minimum conductor clearance based on IPC-2221B Table 6-1 voltage and classification (B1 internal, B2 external uncoated, B4 coated, A6 leads).
18. `export_specctra_dsn`: Generate universal Specctra DSN (v15.0) auto-router interchange file with heuristic auto-placement for automated track routing in Freerouting or KiCad.
19. `export_kicad_schematic`: Export native modern KiCad 8/9 S-Expression schematic (.kicad_sch) directly viewable and editable in Eeschema with sheet layout and component symbols.
20. `audit_supply_chain`: Supply chain multi-sourcing resilience auditor (ISO 9001 audit), identifying single-source bottlenecks and mapping pin-compatible second-source drop-in replacements with LCSC cross-references.
21. `calculate_differential_skew`: High-speed differential pair intra-pair propagation delay skew solver (USB 2.0 HS ≤10ps, Ethernet ≤25ps, CAN-FD ≤50ps) with serpentine tuning geometry calculations.
22. `export_ipc_d356`: Generate universal IPC-D-356A ASCII bare-board electrical test netlist file for industrial flying probe testers (AEMG, ATG, MicroCraft) and bed-of-nails test fixtures.
23. `export_gerber_bundle`: Generate native fabrication-ready Gerber RS-274X layer bundle (Edge_Cuts .gm1, Top Copper .gtl, Top Mask .gts, Top Silkscreen .gto) directly from placed modules and netlists.
24. `calculate_pcb_stackup_impedance`: Standard industrial 4-layer (JLC04161H) and 6-layer (JLC06161H) stackup matrices with IPC-2141A controlled impedance solver for RF 50Ω, USB 90Ω, Ethernet 100Ω, and CAN/RS485 120Ω.

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
- [ ] Multi-layer placement & routing solver
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
