# Reddit Publication Posts: r/KiCad, r/PrintedCircuitBoard & r/electronics

---

## 1. Post for `r/KiCad`

### Post Title
`Why letting LLMs draw PCB traces is a mistake, and how we solved AI hardware design using a block DSL that outputs native KiCad 8/9/10 schematics`

### Post Content (Markdown)

```markdown
Hi r/KiCad,

Over the past year, we've seen dozens of AI-for-hardware projects attempting to feed an LLM a prompt and expecting it to output raw Cartesian coordinates for PCB traces, solder masks, and pad locations. 

The result is almost always the same: **hallucinated pinouts, short circuits, floating power planes, and broken schematics**. LLMs are probabilistic language models—they are fundamentally incapable of spatial routing or checking trace impedances without a formal solver.

To solve this, I open-sourced **[CircuitAgent](https://github.com/mo9652962-ai/circuit-agent)** (MIT).

### The Core Paradigm: Architecture by LLM, Physics by Compiler
Instead of letting the AI draw arbitrary copper, CircuitAgent constrains the model to **pre-verified, auditable circuit building blocks (CircuitBlocks DSL)**:
- The AI acts as an architect: picking blocks (e.g. `ESP32-C3 Microcontroller`, `TPS62825 3A DCDC`, `INA219 Power Monitor`, `W5500 Ethernet`) and defining system parameters (e.g. `VIN=12V`, `VOUT=3.3V`, `I2C bus address`).
- The Python compiler runs deterministic topological validation, solves electrical equations (IPC-2141 impedance, LDO dissipation $P_d$, decoupling capacitance minimums), and executes 44 Electrical Rule Checks (ERC).
- It emits clean, native **KiCad S-Expression schematic files (`.kicad_sch`)** that you can open and edit directly in Eeschema, plus **Specctra 15.0 DSN auto-routing files**.

### What you can export:
1. **KiCad 8/9/10 Schematics**: Native `.kicad_sch` with symbols, hierarchical pins, and annotated netlabels.
2. **Interactive HTML BOM**: Single-file interactive BOM with dual-highlighting (similar to InteractiveHtmlBom).
3. **Specctra DSN**: Ready for auto-routers like Freerouting.
4. **Live LCSC BOM**: Matches real, in-stock JLCPCB / LCSC part numbers.
5. **56 MCP Tools**: Official Model Context Protocol tools for Cursor and Claude Desktop.

### Interactive Zero-Friction Web Demo:
You can play with the synthesizer and explore the dark-mode EDA workbench directly in your browser:
👉 **Live Web Workbench**: https://mo9652962-ai.github.io/circuit-agent/

### Try it via CLI / uvx:
```bash
pip install circuit-agent-client
# or run the MCP server directly:
uvx --from circuit-agent-client circuit-agent-mcp
```

We have 383 unit tests passing in CI. All code, block schemas, and ERC rules are open under MIT:
GitHub: https://github.com/mo9652962-ai/circuit-agent

Would love to get your thoughts on the CircuitBlocks architecture and hear what building blocks you'd like added next!
```
