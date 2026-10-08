# Privacy Policy for CircuitAgent

**Last Updated:** October 2026

CircuitAgent is a local-first engineering AI synthesis engine and Model Context Protocol (MCP) server. We respect developer privacy and design our software around zero-telemetry, zero-data-collection principles.

## 1. Local Execution & Intellectual Property Ownership
- All circuit synthesis, netlist generation, parametric calculations, IPC compliance checks, and KiCad / BOM exports execute **100% locally** on your machine.
- Your design prompts, proprietary schematics, netlists, component choices, and hardware IP **never leave your local environment**.

## 2. Network & External Communications
- **LCSC / EasyEDA Public Component Lookups:** When invoking `search_lcsc_parts` or `calculate_bom_cost`, CircuitAgent dispatches an anonymous, read-only HTTP GET request to public component catalogs (`easyeda.com`) to query publicly available part specifications, stock, and pricing.
- **Zero Credentials & Zero Telemetry:** No API keys, credentials, machine identifiers, session cookies, or telemetry analytics are transmitted. CircuitAgent contains zero tracking pixels, zero analytics SDKs, and zero phone-home mechanisms.
- **Local Disk Caching:** Queried public component data is cached locally on disk with exponential backoff to minimize outbound network requests.

## 3. Storage & MCP Runtime
- CircuitAgent operates over standard MCP stdio (`stdin` / `stdout`) using JSON-RPC 2.0.
- No remote databases or hosted backends are required or queried.

## 4. Contact & Security
For security issues or questions regarding this policy, please refer to [SECURITY.md](SECURITY.md) or open an issue on GitHub at [mo9652962-ai/circuit-agent](https://github.com/mo9652962-ai/circuit-agent).
