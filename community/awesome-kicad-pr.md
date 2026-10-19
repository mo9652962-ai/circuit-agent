# Awesome-KiCad / Awesome-EDA Pull Request Proposal

PR proposal for adding **CircuitAgent** to curated awesome lists:
- [heitorPB/awesome-kicad](https://github.com/heitorPB/awesome-kicad)
- [salfter/Awesome-KiCad](https://github.com/salfter/Awesome-KiCad)
- [matthewvenn/awesome-eda](https://github.com/matthewvenn/awesome-eda)

---

## 1. PR Title
`Add CircuitAgent to EDA / Schematic Generation / AI Hardware Tools`

---

## 2. PR Description (Markdown)

```markdown
### Summary
Add **[circuit-agent](https://github.com/mo9652962-ai/circuit-agent)** under the **Schematics & Netlist Generation / AI Hardware Tools** section.

### About CircuitAgent
`circuit-agent` is an open-source hardware synthesis DSL, deterministic netlist compiler, and Model Context Protocol (MCP) server. Instead of letting LLMs hallucinate pin coordinates or draw illegal traces, CircuitAgent constrains language models to **pre-verified, unit-tested circuit building blocks** (CircuitBlocks DSL) and emits deterministic KiCad 8/9/10 schematics, Specctra DSN placement files, IPC-2581 manufacturing data, and live LCSC component selections.

- **License**: MIT
- **Features**:
  - 24+ proven industrial building blocks (ESP32-C3, STM32, USB-PD, CAN-FD, RS485, Step-down DCDC, W5500 SPI Ethernet).
  - 44 Electrical Rule Checks (ERC) including high-voltage creepage clearance (IEC 62368-1) and differential skew.
  - Native KiCad `.kicad_sch` S-Expression schematic generation and Specctra 15.0 DSN auto-routing export.
  - 56 official MCP tools compatible with Claude Desktop, Cursor, and uvx.
  - Interactive zero-friction browser EDA workbench: https://mo9652962-ai.github.io/circuit-agent/
- **Test Suite**: 383 unit tests passing.
- **Install**: `pip install circuit-agent-client` or run with `uvx --from circuit-agent-client circuit-agent-mcp`.

Thank you!
```

---

## 3. Markdown Diff

```markdown
* [CircuitAgent](https://github.com/mo9652962-ai/circuit-agent) - AI-driven hardware synthesis DSL and deterministic netlist compiler. Constrains LLMs to validated circuit blocks, emitting native KiCad 8/9/10 schematics, Specctra DSN, IPC-2141 impedance calculations, and live LCSC BOMs. Includes 56 MCP tools and an interactive web EDA workbench.
```
