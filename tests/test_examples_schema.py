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


# --------------------------------------------------------------------------- #
# Real Draft-07 validation
#
# The hand-written assertions above check the invariants we care about most, but
# they do not prove the schema itself is the source of truth. This test does:
# it runs the actual `specs/netlist_schema.json` against every example. If the
# schema and the examples ever disagree, this fails.
# --------------------------------------------------------------------------- #

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema is a dev dependency (pip install -e '.[dev]')")


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_validates_against_real_json_schema(path: Path):
    """Every example must validate against the published schema, and the schema
    must actually be strict enough to reject a malformed netlist."""
    data = _load(path)
    jsonschema.validate(instance=data, schema=SCHEMA)


def test_schema_rejects_a_malformed_netlist():
    """Guard against the schema silently degrading into a no-op.

    A schema that accepts anything would make the test above meaningless, so
    assert it genuinely rejects a netlist missing its required fields.
    """
    broken = {"chip_id": "ESP32-C3", "connections": "not-a-list"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=broken, schema=SCHEMA)


# --------------------------------------------------------------------------- #
# The synthesizer's own output must satisfy the published contract
#
# This is the test that actually keeps the schema honest: the examples are
# hand-maintained, but `synthesize_from_prompt` is what users call. If the two
# ever drift, the contract is a lie.
# --------------------------------------------------------------------------- #

PROMPTS = [
    "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键",
    "基于 STM32F103 的工业网关，带 RS485、CAN总线 和 锂电池充电",
    "工业级 STM32F103 RS485 采集卡，带 Type-C、AHT20 和 TVS 防护",
    "RP2040 双核开发板，带 Type-C 供电和晶振",
    "STC89C52RC 最小系统板，带 Type-C 供电",
    "ESP32-C3 板，带 Type-C 供电、以太网口和继电器输出",
]


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p[:28])
def test_synthesizer_output_conforms_to_schema(prompt: str):
    from client.synthesizer import synthesize_from_prompt

    spec = synthesize_from_prompt(prompt)
    jsonschema.validate(instance=spec, schema=SCHEMA)


def test_synthesizer_output_is_deterministic_under_schema():
    """Same prompt twice must produce identical structures (determinism contract)."""
    from client.synthesizer import synthesize_from_prompt

    a = synthesize_from_prompt(PROMPTS[0])
    b = synthesize_from_prompt(PROMPTS[0])
    assert json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)
