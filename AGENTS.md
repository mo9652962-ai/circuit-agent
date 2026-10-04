# AGENTS.md — Project Orientation for AI Coding Agents

> Guidance for AI coding agents (Claude Code, Cursor, Codex, Hermes) working on CircuitAgent.

## Project Overview

CircuitAgent is an open-source, deterministic AI hardware synthesis engine and Model Context Protocol (MCP) server. It translates natural language circuit prompts into verified hardware blocks, KiCad netlists, and JLCPCB manufacturing packages without electrical hallucinations.

## Toolchain & Verification

- **Runtime**: Python 3.10+ (Standard library only for `client/`)
- **Test Runner**: `pytest tests/ -q` (Must pass all 240+ tests before submitting changes)
- **Contract Guard**: `pytest tests/test_contract_sync.py` (Guards README badge counts, block lists, equations, and MCP tool catalogs against code drift)
- **Linter**: `ruff check .`

## Directory Structure

| Directory | Purpose |
|:---|:---|
| `client/` | Pure stdlib MCP Server implementation (`mcp_server.py`), LCSC client, DFX rules, and equation solvers |
| `specs/` | Declarative block definitions, schemas, and verification fixtures |
| `tests/` | Comprehensive test suite (240 unit & regression tests) |
| `web/` | Standalone interactive web showcase |

## Non-Negotiable Constraints

1. **Zero Runtime Dependencies in `client/`**: `client/` must strictly use the Python standard library. Do not import third-party libraries (`requests`, `pydantic`, `numpy`, etc.) in `client/`.
2. **Contract-Sync Invariant**: Every number, block name, and equation mentioned in `README.md` and `README_EN.md` is strictly guarded by `tests/test_contract_sync.py`. If you add a block or modify an equation, update the code, tests, and both READMEs in lockstep.
3. **No Credential Storage**: Never introduce code reading or requiring API keys. LCSC queries are unauthenticated and key-free.
4. **Local-First & Safe**: Circuit generation is local and deterministic. Do not introduce remote evaluation or telemetry.
