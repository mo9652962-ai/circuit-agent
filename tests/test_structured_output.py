"""Contract tests for the structured-output channel and its declared schemas.

The specification's rule is narrow and testable: when a tool declares an
``outputSchema``, the server MUST return ``structuredContent`` conforming to it,
and when both ``content`` and ``structuredContent`` are present they MUST be
semantically equivalent. Those two sentences are what this file pins.

The highest-value test here is
``test_every_declared_output_schema_validates_real_output`` — it calls each tool
for real and validates the response, so a schema cannot drift away from the code
without a failure.
"""

from __future__ import annotations

import json

import pytest

from client import mcp_schema
from client import mcp_server as mcp
from client.structured_output import (
    extract_structured_payload,
    validate_against_schema,
    with_structured_content,
)


def _call_tool(name: str, arguments: dict) -> dict:
    resp = mcp.process_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    )
    return resp["result"]


# Realistic arguments per tool, so the contract is checked against a successful
# call rather than an error path.
TOOL_ARGUMENTS: dict[str, dict] = {
    "calculate_effective_capacitance": {
        "marked_capacitance_uf": 22.0,
        "rated_v": 6.3,
        "applied_v": 4.7,
        "case_size": "0805",
        "dielectric": "X5R",
    },
    "size_hold_up_capacitor": {
        "load_current_ma": 53.8,
        "v_start": 5.0,
        "v_floor": 3.0,
        "required_hold_time_ms": 20.0,
        "rated_v": 6.3,
    },
    "analyze_rc_filter_effective": {
        "r_ohm": 1000.0,
        "marked_c_uf": 10.0,
        "rated_v": 6.3,
        "applied_v": 5.0,
    },
    "analyze_divider_tolerance": {
        "v_in": 3.3,
        "r1_ohm": 10000.0,
        "r2_ohm": 10000.0,
        "tolerance_pct": 1.0,
    },
    "analyze_resistor_error_budget": {
        "nominal_ohm": 10000.0,
        "tolerance_pct": 1.0,
        "tcr_ppm_per_c": 100.0,
        "delta_temp_c": 40.0,
    },
    "solve_feedback_divider": {"v_out": 5.0, "v_ref": 0.8},
}


# --------------------------------------------------------------------------- #
# The two channels are equivalent
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("tool_name", sorted(TOOL_ARGUMENTS))
def test_structured_content_is_semantically_equivalent_to_content(tool_name):
    """Spec: when both fields are present they MUST carry the same information."""
    result = _call_tool(tool_name, TOOL_ARGUMENTS[tool_name])
    assert "structuredContent" in result, f"{tool_name} produced no structured channel"
    text_payload = json.loads(result["content"][0]["text"])
    assert result["structuredContent"] == text_payload, (
        f"{tool_name}: the two channels disagree — a client reading one and a program "
        "reading the other would see different answers"
    )


def test_structured_content_is_a_json_object_not_a_string():
    result = _call_tool("calculate_effective_capacitance", TOOL_ARGUMENTS["calculate_effective_capacitance"])
    assert isinstance(result["structuredContent"], dict)
    assert not isinstance(result["structuredContent"], str)


def test_list_shaped_tools_also_get_structured_content():
    """A tool returning a JSON array must not be dropped by the object-only path."""
    result = _call_tool("list_circuit_blocks", {})
    assert isinstance(result["structuredContent"], list)
    assert len(result["structuredContent"]) >= 19


# --------------------------------------------------------------------------- #
# Errors get no structured payload
# --------------------------------------------------------------------------- #


def test_error_result_has_no_structured_content():
    """There is no schema-conforming document for a failed call, so none is invented."""
    result = _call_tool("definitely_not_a_tool", {})
    assert result["isError"] is True
    assert "structuredContent" not in result


def test_error_from_a_real_tool_has_no_structured_content():
    """A real tool called with bad arguments fails without fabricating a payload."""
    result = _call_tool("calculate_effective_capacitance", {"marked_capacitance_uf": -1.0, "rated_v": 6.3, "applied_v": 1.0})
    assert result.get("isError") is True
    assert "structuredContent" not in result


# --------------------------------------------------------------------------- #
# Prose and document tools are left alone
# --------------------------------------------------------------------------- #


def test_prose_output_gets_no_structured_content():
    """A tool that returns a rendered diagram has no data object to publish."""
    from client.synthesizer import synthesize_from_prompt

    spec = synthesize_from_prompt("ESP32-C3 温湿度节点")
    result = _call_tool("render_circuit_topology", {"modules": spec["modules"]})
    assert "structuredContent" not in result
    assert result["content"][0]["type"] == "text"


def test_file_export_gets_no_structured_content():
    """An export tool returns a document, not a data object."""
    from client.synthesizer import synthesize_from_prompt

    spec = synthesize_from_prompt("ESP32-C3 温湿度节点")
    result = _call_tool("export_kicad_netlist", {"modules": spec["modules"], "netlist": spec["netlist"]})
    assert "structuredContent" not in result


# --------------------------------------------------------------------------- #
# Declared output schemas validate real output
# --------------------------------------------------------------------------- #


def test_only_tools_with_a_contract_declare_an_output_schema():
    """An output schema is a MUST; declaring one for a free-form tool would be a lie."""
    declared = {t["name"] for t in mcp_schema.AVAILABLE_TOOLS if "outputSchema" in t}
    assert declared == set(TOOL_ARGUMENTS), (
        f"declared={sorted(declared)} but tested={sorted(TOOL_ARGUMENTS)} — "
        "every declared schema must have a probe here, and vice versa"
    )


@pytest.mark.parametrize("tool_name", sorted(TOOL_ARGUMENTS))
def test_every_declared_output_schema_validates_real_output(tool_name):
    """Call the tool for real and validate the response against its own schema."""
    declaration = next(t for t in mcp_schema.AVAILABLE_TOOLS if t["name"] == tool_name)
    schema = declaration["outputSchema"]
    result = _call_tool(tool_name, TOOL_ARGUMENTS[tool_name])
    problems = validate_against_schema(result["structuredContent"], schema)
    assert not problems, f"{tool_name} output violates its own outputSchema: {problems}"


@pytest.mark.parametrize("tool_name", sorted(TOOL_ARGUMENTS))
def test_declared_required_fields_are_all_present(tool_name):
    """The required list is the part a client can rely on; it must be truthful."""
    declaration = next(t for t in mcp_schema.AVAILABLE_TOOLS if t["name"] == tool_name)
    required = declaration["outputSchema"].get("required", [])
    assert required, f"{tool_name} declares an outputSchema with no required fields"
    payload = _call_tool(tool_name, TOOL_ARGUMENTS[tool_name])["structuredContent"]
    missing = [key for key in required if key not in payload]
    assert not missing, f"{tool_name} declares required fields it does not return: {missing}"


def test_output_schema_declares_properties_for_every_required_field():
    """A required field with no property definition is an untyped promise."""
    for tool in mcp_schema.AVAILABLE_TOOLS:
        schema = tool.get("outputSchema")
        if not schema:
            continue
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            assert key in props, f"{tool['name']}: required '{key}' has no property schema"


# --------------------------------------------------------------------------- #
# The helper's own behaviour
# --------------------------------------------------------------------------- #


def test_with_structured_content_does_not_overwrite_an_explicit_payload():
    """A handler that builds its own structured payload keeps it."""
    result = {
        "content": [{"type": "text", "text": '{"derived": true}'}],
        "structuredContent": {"handmade": True},
    }
    enriched = with_structured_content(result)
    assert enriched["structuredContent"] == {"handmade": True}


def test_with_structured_content_is_idempotent():
    once = with_structured_content({"content": [{"type": "text", "text": '{"a": 1}'}]})
    twice = with_structured_content(once)
    assert once == twice


def test_extract_returns_none_for_multiple_text_blocks():
    """Two blocks is not one document; guessing which is the payload would be wrong."""
    result = {
        "content": [
            {"type": "text", "text": '{"a": 1}'},
            {"type": "text", "text": '{"b": 2}'},
        ]
    }
    assert extract_structured_payload(result) is None


def test_extract_returns_none_for_a_bare_scalar():
    """A JSON scalar is a value, not a document with fields."""
    assert extract_structured_payload({"content": [{"type": "text", "text": "42"}]}) is None


def test_extract_handles_non_json_text_without_raising():
    assert extract_structured_payload({"content": [{"type": "text", "text": "not json at all"}]}) is None


def test_extract_handles_missing_content():
    assert extract_structured_payload({}) is None
    assert extract_structured_payload({"content": None}) is None


# --------------------------------------------------------------------------- #
# The mini-validator itself
# --------------------------------------------------------------------------- #


def test_validator_catches_a_missing_required_key():
    problems = validate_against_schema({"a": 1}, {"type": "object", "required": ["b"]})
    assert any("missing required key 'b'" in p for p in problems)


def test_validator_catches_a_wrong_type():
    problems = validate_against_schema({"a": "text"}, {"type": "object", "properties": {"a": {"type": "number"}}})
    assert any("expected number" in p for p in problems)


def test_validator_catches_an_out_of_enum_value():
    problems = validate_against_schema(
        {"c": "maybe"}, {"type": "object", "properties": {"c": {"type": "string", "enum": ["yes", "no"]}}}
    )
    assert any("not in enum" in p for p in problems)


def test_validator_walks_arrays():
    schema = {"type": "object", "properties": {"xs": {"type": "array", "items": {"type": "number"}}}}
    problems = validate_against_schema({"xs": [1, "two", 3]}, schema)
    assert len(problems) == 1
    assert "$.xs[1]" in problems[0]


def test_validator_accepts_a_conforming_payload():
    schema = {
        "type": "object",
        "required": ["n", "s"],
        "properties": {"n": {"type": "number"}, "s": {"type": "string"}},
    }
    assert validate_against_schema({"n": 1.5, "s": "ok"}, schema) == []


def test_validator_does_not_treat_bool_as_a_number():
    """In Python bool is an int subclass; in JSON Schema it is not a number."""
    problems = validate_against_schema(True, {"type": "number"})
    assert problems
