# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.6] — 2026-10-03

### Fixed

- `synthesize_from_prompt` no longer misreports unrequested optional blocks as
  `unmatched`. The response now carries two distinct diagnostic lists:
  - `unmatched` — features the caller asked for that this DSL cannot build yet
    (e.g. `ethernet`, `relay`, `motor_driver`). This is the actionable capability
    signal an agent should surface.
  - `not_requested` — optional blocks the prompt simply did not mention.
- A bare lowercase `can` no longer synthesizes a CAN transceiver. The ordinary
  English verb ("a board that **can** drive a relay") previously matched the CAN
  token. CAN-bus intent now requires an explicit bus marker or the uppercase
  acronym `CAN`.
- The industrial DFX audit can no longer certify a near-empty board as
  industrial-grade. Deduction-only scoring rewarded having nothing to deduct, so a
  1-component stub scored 91/`A+`/`passed`. Scores are now capped by design
  substance (`40 + 3 × component count`, saturating at 100 from 20 parts), and
  `passed` additionally requires at least 8 components.
- `specs/netlist_schema.json` now matches what the code actually emits. The schema
  previously required a root-level `connections` array, while the synthesizer nests
  it under `netlist` — meaning no example or synthesizer output ever validated
  against the published contract. The schema now accepts the canonical nested shape
  (and the flat shape for hand-authored input), and its `kind` enum covers the
  component types the block catalogue actually uses (`TVS`, `MOSFET`, `ZENER`,
  `FIDUCIAL`, `TESTPOINT`, `TRANSISTOR`, …).

### Added

- **Industrial DFX audit engine** (`client/industrial_dfx.py`) covering DFM, DFA,
  DFT and DFC, with weighted scoring, letter grading and a Markdown report.
- **IPC rule engine** — IPC-2152 conductor current-carrying capacity (and inverse
  trace-width solving, with copper weight and inner-layer derating) plus IPC-2221
  voltage creepage and clearance lookups.
- **Protection blocks** — USB high-speed ESD array (USBLC6-2SC6), RS-485 industrial
  surge TVS (SM712), CAN bus dual-line TVS (PESD1CAN), reverse-polarity protection
  (SS34 / AO3401A), power π filter, optical fiducials and an ICT test-point matrix.
  Catalogue grows from 12 to 19 blocks.
- **Manufacturing & EDA exporters** (`client/export_engine.py`) — KiCad 6–10
  S-Expression netlist export, JLCPCB production BOM (grouped, Basic/Extended
  classified), JLCPCB CPL with tape-and-reel rotation corrections, and an ASCII
  system topology renderer.
- **Parametric design solvers** (`client/parametric_equations.py`) — E96/E24 series
  snapping, optimal resistor divider synthesis, LDO thermal and junction-temperature
  analysis, I2C pull-up sizing per NXP UM10204, and RC filter solving.
- Four new MCP tools (`export_kicad_netlist`, `export_manufacturing_bom`,
  `calculate_parametric_circuit`, `render_circuit_topology`), bringing the total to
  14, plus the `circuit://specs/ipc-dfx-rules` resource and the
  `/audit_industrial_compliance` prompt.
- Real JSON Schema validation in the test suite — every example, and every prompt
  the synthesizer supports, is now validated against `specs/netlist_schema.json`,
  with a negative test proving the schema is not a no-op.
- CI jobs for `ruff` lint and synthesiser determinism.

### Documentation

- English README resynchronised with the code: tool count (6 → 14), resource count
  (7 → 8), prompt count (3 → 4), block count (10 → 19), test count (120 → 224) and
  release badge (v0.1.5 → v0.1.6).
- Roadmap checkboxes corrected in both READMEs — AHT20/MPU6050 sensor blocks and the
  custom chip pin-mapping engine were already shipped but still listed as pending.
- Added `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` and
  `CITATION.cff`.
- Added `web/README.md` explaining that `web/index.html` is a frontend that requires
  a Pro backend, so it is no longer a silent dead end.
- `server.json` version realigned to the package version, with the description kept
  within the MCP Registry's 100-character limit.
- Both READMEs now document the `unmatched` / `not_requested` distinction explicitly.

## [0.1.5] — 2026-10-02

### Added

- AHT20 temperature/humidity and MPU-6050 6-axis IMU sensor blocks, with decoupling
  and charge-pump components and verified LCSC part numbers.
- Third-party chip pinout rules (`client/chip_rules.py`) with built-in support for
  CH32V003F4P6, STM32G030F6P6 and ATmega328P, plus dynamic registration of custom
  MCUs and physical pin-conflict blocking.
- Two MCP tools (`list_supported_chips`, `register_custom_chip`).

### Fixed

- All version metadata synchronised to 0.1.5, and PyPI install documented as the
  primary quickstart path.

## [0.1.4] — 2026-10-01

### Added

- MCP Registry registration (`server.json`) with an OIDC token-free publish workflow.

### Fixed

- Registry description compressed to satisfy the 100-character limit.

## [0.1.3] — 2026-10-01

### Added

- First PyPI release via Trusted Publishing, with CycloneDX SBOM and PEP 740
  attestations in the publish workflow.

## [0.1.2] — 2026-10-01

### Added

- Complete MCP Triad: 6 tools, 7 resources and 3 engineering prompts.
- IPC-2141 microstrip / differential-pair impedance solver and the PCBA BOM cost
  calculator with JLCPCB Extended-library surcharge detection.

## [0.1.1] — 2026-10-01

### Added

- Industrial blocks: RS-485 transceiver (SP3485), CAN transceiver (SN65HVD230) and
  TP4056 Li-Ion charger.
- Standard stdio MCP server implemented on the Python standard library alone.
- CircuitAgent Pro dark industrial web interface (`web/index.html`).

## [0.1.0] — 2026-10-01

### Added

- Initial public release: CircuitBlocks DSL with deterministic keyword mapping,
  the key-free LCSC parts client, the netlist JSON Schema, three MCU reference
  netlists, bilingual documentation and the CI matrix.

[0.1.6]: https://github.com/mo9652962-ai/circuit-agent/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/mo9652962-ai/circuit-agent/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/mo9652962-ai/circuit-agent/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/mo9652962-ai/circuit-agent/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/mo9652962-ai/circuit-agent/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mo9652962-ai/circuit-agent/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mo9652962-ai/circuit-agent/releases/tag/v0.1.0
