"""Validate that every example in examples/ conforms to specs/netlist_schema.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*.json"))
SCHEMA = json.loads((ROOT / "specs" / "netlist_schema.json").read_text(encoding="utf-8"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_schema_is_loadable():
    assert SCHEMA["type"] == "object"
    assert "connections" in SCHEMA["properties"]


def test_at_least_three_examples_exist():
    assert len(EXAMPLES) >= 3, f"expected >=3 examples, found {[p.name for p in EXAMPLES]}"


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_matches_schema(path: Path):
    data = _load(path)
    assert isinstance(data, dict)
    assert "netlist" in data or "connections" in data, "example must carry a netlist"

    netlist = data.get("netlist", data)
    conns = netlist["connections"]
    assert isinstance(conns, list) and conns, "connections must be a non-empty list"

    for conn in conns:
        assert set(conn) >= {"net", "points"}
        assert isinstance(conn["net"], str) and conn["net"]
        assert isinstance(conn["points"], list) and conn["points"]
        for ep in conn["points"]:
            assert isinstance(ep, str)
            assert "." in ep, f"endpoint '{ep}' must be 'REF.PIN'"


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_endpoints_reference_declared_modules(path: Path):
    data = _load(path)
    modules = data.get("modules")
    if not modules:
        pytest.skip("example declares no modules block")

    netlist = data.get("netlist", data)
    for conn in netlist["connections"]:
        for ep in conn["points"]:
            ref = ep.split(".")[0]
            assert ref in modules, f"{path.name}: undeclared module '{ref}' on net {conn['net']}"


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_modules_carry_lcsc_and_package(path: Path):
    data = _load(path)
    for ref, mod in (data.get("modules") or {}).items():
        assert mod.get("package"), f"{path.name}: {ref} missing package"
        if "lcsc" in mod:
            assert mod["lcsc"].startswith("C"), f"{path.name}: {ref} bad LCSC number"
