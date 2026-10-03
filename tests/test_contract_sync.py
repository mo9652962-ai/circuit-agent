"""Guards the published MCP contract and the documentation that quotes it.

Two classes of drift are caught here:

1. The declarative surface (``client/mcp_schema.py``) silently disagreeing with
   what the server actually dispatches. If someone adds a tool definition but
   forgets a handler, every ``tools/list`` consumer sees a tool that errors.
2. The READMEs quoting counts that no longer match the code. That is exactly how
   the English README ended up advertising 6 tools while the server exposed 14.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from client import mcp_schema, mcp_server

REPO_ROOT = Path(__file__).resolve().parent.parent


def _call(method: str, params: dict | None = None):
    msg = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        msg["params"] = params
    return mcp_server.process_message(msg)


# --------------------------------------------------------------------------- #
# Declarative surface vs live dispatch
# --------------------------------------------------------------------------- #


def test_every_declared_tool_has_a_handler():
    """A tool in `tools/list` that cannot be called is a broken promise."""
    declared = {t["name"] for t in mcp_schema.AVAILABLE_TOOLS}
    handled = set()
    for name in declared:
        resp = _call("tools/call", {"name": name, "arguments": {}})
        result = resp.get("result", {})
        # "Unknown tool" is the only outcome that proves a missing handler.
        text = str(result.get("content", ""))
        if result.get("isError") and "Unknown tool" in text:
            continue
        handled.add(name)
    missing = declared - handled
    assert not missing, f"declared but not dispatched: {sorted(missing)}"


def test_unknown_tool_is_rejected():
    resp = _call("tools/call", {"name": "definitely_not_a_tool", "arguments": {}})
    assert resp["result"].get("isError") is True


def test_tool_names_are_unique():
    names = [t["name"] for t in mcp_schema.AVAILABLE_TOOLS]
    assert len(names) == len(set(names)), "duplicate tool name in AVAILABLE_TOOLS"


def test_every_tool_has_a_description_and_schema():
    for tool in mcp_schema.AVAILABLE_TOOLS:
        assert tool.get("name"), "tool missing name"
        assert tool.get("description"), f"{tool['name']} missing description"
        assert isinstance(tool.get("inputSchema"), dict), f"{tool['name']} missing inputSchema"


def test_resources_and_prompts_are_well_formed():
    for res in mcp_schema.AVAILABLE_RESOURCES:
        assert res.get("uri", "").startswith("circuit://"), f"bad resource uri: {res}"
        assert res.get("name"), f"resource {res.get('uri')} missing name"
    for prompt in mcp_schema.AVAILABLE_PROMPTS:
        assert prompt.get("name"), f"prompt missing name: {prompt}"
        assert prompt.get("description"), f"prompt {prompt['name']} missing description"


def test_live_lists_match_the_declarative_module():
    """The server must serve exactly what the declarative module declares."""
    assert len(_call("tools/list")["result"]["tools"]) == len(mcp_schema.AVAILABLE_TOOLS)
    assert len(_call("resources/list")["result"]["resources"]) == len(mcp_schema.AVAILABLE_RESOURCES)
    assert len(_call("prompts/list")["result"]["prompts"]) == len(mcp_schema.AVAILABLE_PROMPTS)


# --------------------------------------------------------------------------- #
# Documentation must quote the real numbers
# --------------------------------------------------------------------------- #


def _counts() -> tuple[int, int, int]:
    return (
        len(mcp_schema.AVAILABLE_TOOLS),
        len(mcp_schema.AVAILABLE_RESOURCES),
        len(mcp_schema.AVAILABLE_PROMPTS),
    )


@pytest.mark.parametrize("readme", ["README.md", "README_EN.md"])
def test_readme_mentions_every_tool(readme: str):
    text = (REPO_ROOT / readme).read_text(encoding="utf-8")
    missing = [t["name"] for t in mcp_schema.AVAILABLE_TOOLS if t["name"] not in text]
    assert not missing, f"{readme} does not document: {missing}"


@pytest.mark.parametrize("readme", ["README.md", "README_EN.md"])
def test_readme_mentions_every_resource(readme: str):
    text = (REPO_ROOT / readme).read_text(encoding="utf-8")
    missing = [r["uri"] for r in mcp_schema.AVAILABLE_RESOURCES if r["uri"] not in text]
    assert not missing, f"{readme} does not document: {missing}"


@pytest.mark.parametrize("readme", ["README.md", "README_EN.md"])
def test_readme_tool_count_is_accurate(readme: str):
    """Catch the 'README says 6, server exposes 14' class of drift."""
    n_tools, _, _ = _counts()
    text = (REPO_ROOT / readme).read_text(encoding="utf-8")
    assert f"{n_tools} tools" in text or f"{n_tools} 大工具" in text or f"{n_tools} 个工具" in text, (
        f"{readme} never states the real tool count ({n_tools})"
    )


@pytest.mark.parametrize("readme", ["README.md", "README_EN.md"])
def test_readme_block_table_lists_every_block(readme: str):
    """The block catalogue table must have one row per shipped block."""
    from client.circuit_blocks import __all__ as block_exports

    expected = len([n for n in block_exports if n.startswith("block_")])
    text = (REPO_ROOT / readme).read_text(encoding="utf-8")
    rows = len(re.findall(r"^\|\s*`block_", text, re.MULTILINE))
    assert rows == expected, f"{readme} lists {rows} blocks, code ships {expected}"


def test_version_is_consistent_across_artefacts():
    """pyproject, package and server metadata must not disagree."""
    import json

    import client

    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert declared, "pyproject.toml has no version"

    server = json.loads((REPO_ROOT / "server.json").read_text(encoding="utf-8"))

    assert client.__version__ == declared.group(1), (
        f"client.__version__={client.__version__} != pyproject={declared.group(1)}"
    )
    assert server["version"] == declared.group(1), (
        f"server.json={server['version']} != pyproject={declared.group(1)}"
    )
    for pkg in server.get("packages", []):
        assert pkg["version"] == declared.group(1), f"server.json package version drift: {pkg}"


def test_server_json_description_fits_the_registry_limit():
    """The MCP Registry rejects descriptions over 100 characters."""
    import json

    server = json.loads((REPO_ROOT / "server.json").read_text(encoding="utf-8"))
    assert len(server["description"]) <= 100, (
        f"server.json description is {len(server['description'])} chars, registry limit is 100"
    )
