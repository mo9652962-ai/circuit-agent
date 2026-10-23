# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`gate_production_readiness` MCP tool (70th tool).** One call takes a
  natural-language requirement through synthesis, placement, autorouting, the
  9-layer fab bundle plus BOM and CPL, and the manufacturing validator, and
  returns a single `production_ready` verdict with the blocking defects. A CI job
  or an assembly house decides go/no-go without reading five separate reports.

- **SMT stencil layers (`.gtp` / `.gbp`).** The bundle had no paste layer, so no
  SMT line could print paste and every board was a hand-solder job regardless of
  what the BOM listed. Apertures follow IPC-7525B (land reduced 0.05 mm per side);
  through-hole pins get none, and the bottom stencil is empty when every part is
  on top.

- **Teardrop reinforcement at via entries.** Built from the actual routed wire
  that lands on each via — the entry angle is derived, not assumed — and emitted
  as G36/G37 filled regions. Drill wander alone is allowed 0.075 mm, which on a
  0.6/0.3 via is the entire annular ring at the trace neck.

### Fixed

- **Copper layers carried no via annular ring.** The drill file had the holes and
  the copper had nothing around them: every via was a hole punched through a trace
  with no metal to plate onto. Vias are now flashed on both copper layers at their
  padstack diameter (`Via[0.6-0.3]` → 0.6 mm land, 0.15 mm ring per side).

- **Silkscreen was drawn straight across pads.** Legend printed on a mask opening
  blocks wetting and leaves a cold joint or a solder ball. Outlines are now
  clipped by subtracting the mask openings (plus 0.15 mm per IPC-SM-840) from each
  edge — subtraction, not whole-edge drop, because dropping erased the legend on
  every part whose body sits between its own pads.

- **A package with no stencil passed validation**, and the solder-mask dam was
  never measured. The validator now requires the stencil and reads the tightest
  dam from the real mask Gerber against the 0.08 mm process floor; below it the
  web scums during development and bridges the pins at reflow.

- **`export_jlcpcb_cpl` hardcoded a 70 × 50 outline**, so on any other board size
  every placement row pointed outside the edge cuts.

- **A local import silently broke earlier MCP branches.** A bare
  `from x import name` inside `handle_tool_call` makes the name local to the whole
  function, so `synthesize_circuit` and the BOM/CPL exports referenced a variable
  before assignment (ruff F823). The gate's imports are now aliased.

### Changed

- Version 0.18.0.

### Fixed (earlier in this release)

- **The autorouter reported success on shorted boards.** `autoroute_circuit`
  returned "12/12 nets routed" for a board carrying 36 real crossings: the
  `grid` engine searches an 8-neighbour lattice, so two 45-degree traces can pass
  through the same 2x2 cell block while each occupies a different lattice point.
  The engine was also never actually selectable — `_route_with_correct_units`
  accepted `engine` and then always called `build_routing_result`, so `exact` and
  `room` silently ran the grid router. With the parameter wired through, `exact`
  and `room` route the same board at 0 crossings.

- **A router's "complete" was accepted as a fab-ready board.** Completion only
  means a path was found; the `exact` engine returned 100% on the ESP32-C3 node
  while leaving a 0.060 mm gap between GND and P3.3V against a 0.100 mm rule.
  `autoroute_circuit` now runs the physical DRC on its own output and picks the
  best engine by (complete, then error-free, then quietest), recording the
  attempts in `engines_tried`.

- **The DRC counted pads as acid traps.** Corner detection paired any two
  segments sharing a vertex, so every pad where several branches converge read as
  a 0-degree fold: 89 "acid traps" on an orthogonal route with no acute corner.
  Corners are now measured along each ordered polyline, and a bend inside a pad
  land is not a crevice — the etchant sees the pad outline.

- **The DRC reported 1723 violations for 4 real defects.** Width, clearance and
  right-angle findings were emitted per segment instead of per net, burying the
  four acid traps. Findings are now aggregated: one entry per net (width), per
  net pair and layer (clearance), per net with a count (right-angle corners).

- **The DRC routed at the fab's minimum, not the board's default.** It re-routed
  with `trace_width_mm=min_trace_width_mm` (0.127 mm), geometry no design would
  ship, then reported width violations against it.

### Added

- `run_pcb_drc` MCP tool: physical DRC audit of a routed board (true
  copper-to-copper clearance, acid traps, power-trace width, board-edge and
  keepout intrusion, differential-pair skew) with severity, location and a
  concrete fix per finding.

### Fixed (continued)

- **USB data path was never connected.** The Type-C receptacle exposed only
  VBUS/GND/CC, so the USBLC6 ESD array sat on two nets of its own: `/USB_DP` and
  `/USB_DM` each had exactly two endpoints, both on the protector. The ERC's
  per-net point count saw 2 points and passed. The receptacle now carries A6/B6
  (D+) and A7/B7 (D-), the controller binds to them, and a new
  `DIFF_PAIR_PROTECTION_ONLY` rule fails any differential pair that reaches fewer
  than two distinct signal parts.

- **MCU native-USB pins were unusable.** ESP32-C3 IO18/IO19 and ESP32-S3
  IO19/IO20 were listed as hard `reserved_pins`, so the allocator rejected the
  one binding those pins exist for. They moved to a new `conditional_pins` field:
  held out of the default allocation, usable by the signal they name. RP2040's
  hard-wired GPIO4/GPIO5 pair is now allocated too, with I2C0 relocated to
  GPIO6/GPIO7 so the data lines and the sensor bus stop competing for two pads.

- **Power-only receptacles produced dangling pairs.** A controller with no USB
  peripheral (STC89C52) still got D+/D- on the connector plus an ESD array. The
  receptacle now takes `with_data`, chosen from the detected chip rule, and a
  5 V inlet has no data nets at all.

- **0.5 mm-pitch pads were 0.5 mm wide.** USB-C used `Pad_SMD` (0.50 x 0.60 mm)
  on a 0.5 mm pitch, so adjacent pads touched and formed a solid copper wall at
  the connector. The grid router steps by (width + clearance) and found no
  channel, leaving CC1/CC2 unrouted — the ESP32-C3 node sat at 83.3% forever.
  Added `Pad_SMD_0p5mm` (0.30 mm wide, 0.20 mm gap) and matched it by package
  family. The first attempt matched a bare `"0.5mm"` substring, which also caught
  `LQFP-48_7x7mm_P0.5mm` and gave an IC connector land, stranding every SPI net
  on the Ethernet gateway; the rule now matches `USB-C`/`FPC`/`TYPE-C` only.

- **`autoroute_pcb` used coarser rules than the function it wraps.** The MCP tool
  defaulted to 0.254 mm width / 0.200 mm clearance while `autoroute_circuit`
  defaults to 0.150/0.100. A 0.454 mm grid cannot pass a 0.5 mm pitch, so the
  tool returned 66.7% on a board the library routed at 100%. Both the DSN and
  autoroute branches of the tool now share the library defaults.

- **CC pull-downs were placed 19 mm from the receptacle.** They fell through to
  the generic passive stage at a default coordinate. Type-C sink resistors now
  anchor to the receptacle's own edges: they set the charger's 5 V offer and a
  long CC trace is an antenna on the negotiation line.

- **Half of every differential pair was outside its net class.** The class filter
  matched `"DN"` while the net is named `USB_DM`, so only D+ received the 0.180 mm
  communication rule and D- stayed on the 0.150 mm default. A pair routed at two
  widths is a skew and impedance mismatch. CC1/CC2 were not in any class either;
  all four now share `COMM_BUS`.

### Added

- `tests/test_routing_quality.py`: 11 tests. Four reference boards must route
  100%; the rest pin fine-pitch land width, package-family matching, CC
  placement, mounting keep-out geometry, MCP/library parity, the USB data path,
  and the power-only case. Each was verified to fail against the reintroduced
  defect — the USB test initially passed because it matched `U_TVS_USB1` on the
  substring "USB", and was tightened to require `J_USB1` by reference.

## [0.15.0] — 2026-10-21

### Fixed

- **SES coordinate units**: `freeroute`'s writer emits routing coordinates as
  integers while the session declares `(resolution mm 1000)`, i.e. 1/1000 mm. A
  pad at (10.25, 27.5) mm was written as `10 28` — up to half a millimetre of
  error, larger than a 0603 pad. `autoroute_circuit` now builds the routing result
  itself, scales coordinates and widths into resolution units, and hands the
  scaled result to the writer. `parse_ses_routing` reads the divisor from the file
  instead of assuming millimetres, so reported trace lengths are true again
  (previously inflated 1000x by the same mismatch).

- **Gerber pads**: pads are flashed at each component's real *pin* position
  (placement origin + footprint pin offset) with a land size derived from the
  package. The previous exporter flashed one uniform 1.6x1.0 mm pad at every
  component *centroid*, so no pad coincided with anything a part could solder to.

- **Gerber tracks**: copper layers carry the autorouter's actual SES geometry.
  The previous exporter drew one straight segment between each net's two
  component centroids — copper that shorts whatever lies between them. A net the
  router could not complete now draws nothing, which is the truthful state.

- **Excellon drill**: holes come only from through-hole component pins,
  router-placed vias, and declared mounting holes. The previous exporter drilled a
  0.3 mm hole at `centroid + (0.8, 0.8)` for every SMD part and a second hole
  2.54 mm beside every connector — 23 of 27 holes on the ESP32-C3 reference board
  traced to no design feature. Alias pin names that share one physical pad (a
  USB-C shell pin is both `GND` and `1`) are de-duplicated.

- **Solder mask**: openings track real pad positions, expanded by a per-side
  mask allowance (`MASK_EXPANSION_MM`). The bottom mask opens only for
  through-hole pads instead of opening nothing at all.

- **Silkscreen**: outlines use each package's body dimensions instead of one
  uniform 3.6x2.4 mm box for every part.

### Added

- `PACKAGE_HALF_EXTENTS` and `BODY_DIMS_MM` as module-level tables in
  `placement_engine`, shared by the placement collision maths and the silkscreen
  generator, so a part's outline matches the space it reserves.

- `export_gerber_bundle` accepts `placements` and `ses_text`; the MCP tool
  `export_gerber_bundle` gains `autoroute` (default true) and `ses_text` so a fab
  bundle carries routed geometry by default.

- `tests/test_fab_output_fidelity.py`: 9 tests asserting the bundle describes the
  design rather than a plausible approximation. Each was verified to fail against
  the previous implementation; two first-draft assertions passed against the old
  code and were rewritten to check absolute positions instead of internal
  consistency.

## [0.15.0] — 2026-10-21

### Added

- `autoroute_pcb` MCP tool (#66): Native Python multi-layer PCB layout and auto-routing
  engine (Specctra DSN in, SES out) with zero JVM/external dependencies.
- `client/router_engine.py`: Structured routing metrics analysis including net completion
  rates, total trace length (in mm), via counts, and layer utilization.
- Expanded `STANDARD_PIN_OFFSETS` with exact pin coordinates for `ESP32-S3-WROOM-1`,
  `LQFP-48`, `LQFP-48_7x7mm_P0.5mm`, and `HTSSOP-28` motor drivers.

### Fixed

- MCU Centering: Strict priority-based MCU classification prevents peripheral ICs
  (transceivers, regulators) from stealing geometric center coordinates.
- Decoupling Adsorption: Placement sequence reordering allows peripheral decoupling
  capacitors (`C_485`, `C_CAN`, `C_ETH`) to cluster tightly (<5mm) adjacent to their target ICs,
  using courtyard-accurate offsets (`IC half-extent + cap half-extent + gap`) instead of
  a hard-coded magic distance.
- Collision Avoidance: Replaced the blind linear shift loop with a bounded expanding-ring
  search around each component's *desired* position, so local placement intent
  (decoupling, crystal, ESD protection) survives conflict resolution instead of being
  flung to a far corner. Anchors resolve first; passives yield.
- Specctra DSN Compliance: Added complete `(library ...)` image blocks with calibrated
  padstack definitions (`Pad_SMD`, `Pad_SMD_Fine`, `Pad_TH`, `Via[0.6-0.3]`), Specctra
  standard `(pins Comp-Pin ...)` syntax, board-edge and mounting-hole `keepout` geometry,
  an RF antenna keepout for wireless MCUs, and per-class routing rules
  (`POWER` / `MOTOR_POWER` / `COMM_BUS`).

### Changed

- Default routing geometry tightened from `0.254/0.200mm` to `0.150/0.100mm`
  (trace width / clearance), which matches real 2-layer JLCPCB-class fabrication and
  lifts dense-board routing completion from ~65% to ~99% across the bundled reference
  circuit set (Ethernet gateway and 51-MCU RS485 board now reach 100%).

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
- A contract-sync test module that fails the build when the declarative MCP surface
  (`client/mcp_schema.py`), the live dispatcher, the version metadata or the READMEs
  drift apart — this is the regression guard for the exact class of staleness that
  let the English README advertise 6 tools while the server exposed 14.
- CI jobs for `ruff` lint and synthesiser determinism.

### Changed

- `client/mcp_server.py` split: the 400 lines of declarative tool/resource/prompt
  definitions moved to `client/mcp_schema.py`, taking the server from 1,173 to 766
  lines and making the published MCP contract reviewable on its own.

### Documentation

- English README resynchronised with the code: tool count (6 → 14), resource count
  (7 → 8), prompt count (3 → 4), block count (10 → 19), test count (120 → 240) and
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
