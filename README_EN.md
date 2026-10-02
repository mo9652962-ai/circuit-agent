<p align="center">
  <img src="docs/images/banner-1200x640.png" alt="CircuitAgent Banner" width="100%">
</p>

<p align="center">
  <strong>Prompt → Schematic → Layout → 3D Enclosure → Fabrication Bundle</strong>
</p>

<p align="center">
  <a href="https://github.com/mo9652962-ai/circuit-agent/actions/workflows/ci.yml"><img src="https://github.com/mo9652962-ai/circuit-agent/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="tests/"><img src="https://img.shields.io/badge/tests-120%20passing-brightgreen.svg" alt="Tests"></a>
  <a href="https://github.com/mo9652962-ai/circuit-agent/releases"><img src="https://img.shields.io/badge/release-v0.1.5-blueviolet.svg" alt="Release"></a>
</p>

<p align="center">
  <a href="README.md"><b>中文说明</b></a> | <a href="README_EN.md"><b>English</b></a>
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
print(spec["unmatched"])                          # Unmatched intents (never silently discarded)
```

The mapping is **deterministic**: identical prompts yield byte-for-byte identical intermediate representations.

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

### 3 · Assemble Custom Circuits Directly

```python
from client.circuit_blocks import block_usb_c_power, block_power_ldo_3v3

blk = block_power_ldo_3v3()
for comp in blk.components:
    print(comp.ref, comp.value, comp.package, comp.lcsc)
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

---

## MCP Server (AI Agent Integration)

CircuitAgent bundles a standards-compliant JSON-RPC 2.0 stdio MCP Server written in pure Python standard library (zero external pip packages required). It connects out of the box with **Claude Desktop**, **Cursor**, and **Windsurf**.

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
3. `list_circuit_blocks`: List all 10 pre-validated hardware DSL blocks.
4. `validate_netlist`: Validate netlists against the formal CircuitAgent JSON Schema.
5. `calculate_trace_impedance`: Microstrip & differential pair trace impedance solver (IPC-2141 / Wheeler) for USB 90Ω, RF 50Ω, CAN 120Ω.
6. `calculate_bom_cost`: PCBA bill-of-materials cost breakdown calculator with JLCPCB Extended library surcharge detection.

### Exposed Resources
Directly mount specifications and catalogues into model context via `circuit://` URIs:
- `circuit://specs/netlist-schema`: The formal Draft-07 JSON Schema.
- `circuit://specs/cpl-standard`: JLCPCB SMT coordinate and rotation offset specifications.
- `circuit://blocks/catalog`: Complete catalogue of 10 standard CircuitBlocks (pins, nets, LCSC part numbers).
- `circuit://rules/jlc-smt`: JLCPCB SMT physical rules, 4-layer stackup (JLC04161H), and fee schedules.
- `circuit://examples/esp32c3-minimal`: ESP32-C3 minimal IoT node reference netlist.
- `circuit://examples/stm32f103-controller`: STM32F103 industrial controller reference netlist.
- `circuit://examples/rp2040-dualcore`: RP2040 high-density dual-core reference netlist.

### Reusable Engineering Prompts (Slash-Commands)
- `/design_hardware_project`: Guided end-to-end hardware synthesis, impedance check, and schema validation.
- `/audit_schematic_netlist`: Senior Principal EE inspection prompt (PI/SI/DFM gates, decoupling capacitor proximity).
- `/optimize_bom_cost`: PCBA BOM cost reduction prompt substituting Extended parts for Basic library parts.

---

## Data Contracts & Specs

- [`specs/netlist_schema.json`](specs/netlist_schema.json) — Full Netlist & Circuit JSON Schema (Draft-07)
- [`specs/cpl_standard.md`](specs/cpl_standard.md) — JLCPCB SMT coordinate standard & angle compensation table
- [`examples/`](examples/) — Verified golden netlists for STM32F103, ESP32-C3, and RP2040

---

## Test Suite & CI

```bash
pytest tests/ -q      # 120 passed
```

GitHub Actions matrix tests against `ubuntu-latest` and `windows-latest` across Python 3.10, 3.11, and 3.12.

---

## Scope & Roadmap

**Included in this community repository**:
Hardware DSL and building blocks, key-free LCSC live parts client, netlist & CPL specifications, standard MCP Server, REST client bridges.

**High-level compiler stages (In active development)**:
Multi-layer physical placement & auto-routing solver, parametric 3D enclosure Boolean geometry, Senior EE physical rule DRC gate.

- [x] Pre-verified block catalogue + deterministic mapping + unit tests
- [x] LCSC live parts client (retry / cache / fallback)
- [x] Formal JSON Schema + 3 MCU golden examples + CI matrix
- [x] CircuitAgent Pro dark industrial web interface (`web/index.html`)
- [x] Industrial fieldbus & power blocks (RS485, CAN bus, TP4056 Li-Ion)
- [x] Standards-compliant stdio MCP Server (Tools + Resources + Prompts)
- [x] Bilingual documentation & official branding
- [ ] Additional sensor blocks (AHT20, MPU6050)
- [ ] Custom MCU pin-mapping override engine

---

## License

[MIT](LICENSE) © 2026 sora
