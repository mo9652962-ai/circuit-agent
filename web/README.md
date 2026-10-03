# CircuitAgent Pro — Web Workspace (frontend only)

`index.html` is the dark-industrial EDA workspace UI shown in the project's
`docs/images/demo.gif`.

## Important: this is a frontend, and it needs a backend

This file is **not** a standalone demo. It is a single-page client that talks to a
local **CircuitAgent Pro** service over HTTP:

| Endpoint | Purpose |
|:---|:---|
| `GET  /health` | Connection check shown in the status bar |
| `POST /synthesize` | Prompt → netlist |
| `GET  /examples/{chip}` | Load a golden reference netlist |
| `GET  /runs` | Run history |

The backend defaults to `http://127.0.0.1:8890` and is **not** part of this
community repository — the Pro compiler (multi-layer placement & routing solver,
parametric 3D enclosure generation, Senior EE DRC gate) is developed separately and
communicates with this client through the published data contracts in
[`../specs/`](../specs/).

Opening `index.html` directly will render the interface, but the status bar will
read **未连接 (127.0.0.1:8890)** because nothing is listening.

## What you can still use it for

- **Visual reference** — the layout, design tokens and component states are a real
  working example of the Pro workspace, useful if you are building your own client
  against the `specs/` contracts.
- **Point it at your own backend** — the API base URL is editable in the UI (and
  defaults to `location.origin` when served over HTTP), so any service implementing
  the four endpoints above will drive it.

## What the community edition gives you instead

Everything that does not need the Pro compiler is available as a library and as an
MCP server — see the [main README](../README.md):

```bash
pip install circuit-agent-client
python -m client.mcp_server      # stdio MCP server for Claude Desktop / Cursor
```

That includes prompt→netlist synthesis, live LCSC part selection, the industrial
DFX audit engine, KiCad/JLCPCB exporters and the parametric design solvers.
