"""Structured tool results: the machine channel next to the model channel.

MCP 2026-07-28 defines two output channels for ``tools/call``:

* ``content`` — model-oriented. A language model reads text; this is the only
  part of the result a conversational agent actually sees. Token cost and
  readability matter here.
* ``structuredContent`` — machine-oriented. For programmatic tool use, code
  generation, typed orchestration and strict ``outputSchema`` validation.

The specification is explicit that when both are present they **must be
semantically equivalent** — the same information, presented twice for two
different consumers. Clients are told not to forward both to a model as if they
were distinct inputs.

This module implements that equivalence rather than approximating it. Every tool
in this server already returns its payload as a JSON document in a text block,
so the structured channel is derived by parsing that same document. One source
of truth, two presentations, no possibility of drift between them.

Why derive instead of hand-writing per tool
-------------------------------------------
Sixty-four tools hand-annotating a second representation would drift the first
time someone edits one branch and not the other. Deriving guarantees the two
channels agree by construction, and a test asserts it for every tool.

What is deliberately *not* done
-------------------------------
Errors are not given a structured payload. An ``isError`` result means the call
failed, and there is no schema-conforming document to hand a program — inventing
an error object shape would be a contract no client asked for. Errors stay
text-only, which is also what the spec's own examples show.
"""

from __future__ import annotations

import json
from typing import Any

#: Result keys that belong to the protocol envelope, not to the tool's payload.
#: A tool whose JSON happens to contain these keys would otherwise have its own
#: data mistaken for transport metadata.
RESERVED_KEYS = frozenset({"content", "structuredContent", "isError", "resultType", "ttlMs", "cacheScope"})


def extract_structured_payload(result: dict[str, Any]) -> dict[str, Any] | list[Any] | None:
    """Recover the structured payload from a tool result, or ``None``.

    Returns the parsed JSON when the result is a successful call carrying exactly
    one text block whose body is a JSON object or array. Returns ``None`` for
    errors, for plain-prose text, and for multi-block results — in each of those
    cases there is no single document to publish, and guessing would put
    something in the machine channel that no ``outputSchema`` describes.
    """
    if result.get("isError"):
        return None
    blocks = result.get("content")
    if not isinstance(blocks, list) or len(blocks) != 1:
        return None
    block = blocks[0]
    if not isinstance(block, dict) or block.get("type") != "text":
        return None
    text = block.get("text")
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    # Cheap guard before paying for a parse on every call.
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        payload = json.loads(stripped)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, (dict, list)):
        return None
    return payload


def with_structured_content(result: dict[str, Any]) -> dict[str, Any]:
    """Attach ``structuredContent`` derived from the result's own text block.

    Idempotent: a result that already carries ``structuredContent`` is returned
    unchanged, so a handler that builds its own (with a hand-tuned schema) is not
    overwritten by the derived one.
    """
    if "structuredContent" in result:
        return result
    payload = extract_structured_payload(result)
    if payload is None:
        return result
    enriched = dict(result)
    enriched["structuredContent"] = payload
    return enriched


def payload_keys(result: dict[str, Any]) -> set[str]:
    """Top-level keys of a result's structured payload — used by tests."""
    payload = result.get("structuredContent")
    if isinstance(payload, dict):
        return set(payload)
    return set()


def validate_against_schema(payload: Any, schema: dict[str, Any]) -> list[str]:
    """Minimal structural validation of a payload against a JSON-Schema subset.

    Not a general validator — the repository's hard constraint is that ``client/``
    imports nothing outside the standard library, so ``jsonschema`` is unavailable
    here. This covers the keywords this project's own ``outputSchema``
    declarations use: ``type``, ``properties``, ``required``, ``items``, ``enum``.
    Anything outside that subset is ignored rather than guessed at.

    Returns a list of human-readable problems; empty means conforming.
    """
    problems: list[str] = []

    def _type_ok(value: Any, expected: str) -> bool:
        if expected == "object":
            return isinstance(value, dict)
        if expected == "array":
            return isinstance(value, list)
        if expected == "string":
            return isinstance(value, str)
        if expected == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected == "boolean":
            return isinstance(value, bool)
        if expected == "null":
            return value is None
        return True

    def _walk(value: Any, node: dict[str, Any], path: str) -> None:
        expected = node.get("type")
        if isinstance(expected, str) and not _type_ok(value, expected):
            problems.append(f"{path}: expected {expected}, got {type(value).__name__}")
            return

        if "enum" in node and value not in node["enum"]:
            problems.append(f"{path}: {value!r} not in enum {node['enum']}")

        if isinstance(value, dict):
            for key in node.get("required", []):
                if key not in value:
                    problems.append(f"{path}: missing required key '{key}'")
            props = node.get("properties")
            if isinstance(props, dict):
                for key, sub in props.items():
                    if key in value and isinstance(sub, dict):
                        _walk(value[key], sub, f"{path}.{key}")

        if isinstance(value, list):
            items = node.get("items")
            if isinstance(items, dict):
                for index, item in enumerate(value):
                    _walk(item, items, f"{path}[{index}]")

    _walk(payload, schema, "$")
    return problems
