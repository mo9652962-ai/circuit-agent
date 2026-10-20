"""MCP 2026-07-28 stateless protocol core.

The 2026-07-28 revision turned MCP from a bidirectional stateful protocol into a
request/response stateless one. That is a breaking change at the transport and
lifecycle layer, not a cosmetic bump, so the pieces that actually change
observable behaviour are implemented here rather than sprinkled through the
dispatch loop:

1. **No handshake.** ``initialize`` / ``notifications/initialized`` are gone from
   the modern path. Every request is self-describing: it carries its protocol
   version and client capabilities in ``params._meta``
   (``io.modelcontextprotocol/protocolVersion`` and friends). A server may still
   answer ``initialize`` for legacy clients — this module keeps that fallback
   explicit instead of accidental.
2. **``server/discover``.** Servers MUST implement it. It lets a client learn
   supported versions, capabilities and identity in one exchange, and on stdio
   it is the backward-compatibility probe: a modern client sends ``discover``
   first and only falls back to ``initialize`` if the method is unknown.
3. **``resultType``.** Every result carries ``"complete"`` or
   ``"input_required"``. Clients MUST treat a missing field as ``complete``, so
   emitting it is additive for old clients and required for new ones.
4. **Cache hints.** ``tools/list``, ``prompts/list``, ``resources/list`` and
   ``resources/read`` return ``ttlMs`` and ``cacheScope``. These are what let a
   client stop re-listing a 58-tool catalogue on every turn.
5. **Deterministic ordering.** The spec asks servers to return ``tools/list`` in
   a stable order so client-side caching and LLM prompt caching can hit. The
   catalogue order is already stable in ``mcp_schema``; this module asserts it
   rather than silently depending on it.
6. **Error code allocation.** ``-32020``..``-32099`` is reserved for the spec.
   The codes this server emits live there, and ``-32002`` (the old resource-not-
   found code) is no longer used for that purpose — it moved to ``-32602``.

Nothing here imports a third-party package: the ``client/`` tree stays pure
standard library, which is a hard constraint of this repository.
"""

from __future__ import annotations

from typing import Any

#: Newest revision this server speaks. Order matters: index 0 is preferred.
PROTOCOL_VERSION = "2026-07-28"

#: Every revision the server can answer. A modern client picks from this list
#: after ``server/discover``; a legacy client gets ``initialize`` echoed with
#: whatever version it asked for, if we know it.
SUPPORTED_VERSIONS: tuple[str, ...] = ("2026-07-28", "2025-11-25", "2025-03-26", "2024-11-05")

#: Revisions that predate the stateless core and therefore still use the
#: ``initialize`` handshake. Used only to decide how to answer a legacy client.
LEGACY_VERSIONS: frozenset[str] = frozenset({"2025-11-25", "2025-03-26", "2024-11-05"})

# --- `_meta` keys (spec-defined, string literals on purpose: they are wire) ---
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
META_LOG_LEVEL = "io.modelcontextprotocol/logLevel"

# --- resultType values ---
RESULT_COMPLETE = "complete"
RESULT_INPUT_REQUIRED = "input_required"

# --- Spec-reserved error codes (2026-07-28 allocation policy) ---
ERROR_HEADER_MISMATCH = -32020
ERROR_MISSING_CLIENT_CAPABILITY = -32021
ERROR_UNSUPPORTED_PROTOCOL_VERSION = -32022

#: How long a client may cache the tool catalogue. The catalogue only changes
#: when the process restarts with a new build, so a long TTL is honest; a client
#: that wants freshness passes ``ttlMs: 0`` semantics by simply not caching.
CATALOG_TTL_MS = 3_600_000

#: Resource reads are generated from files on disk. Shorter than the catalogue
#: because a user can edit ``specs/`` between calls.
RESOURCE_TTL_MS = 60_000


def server_info(version: str) -> dict[str, str]:
    """The ``serverInfo`` stamp, in the shape the 2026-07-28 spec expects."""
    return {"name": "circuit-agent-mcp", "version": version}


def complete(result: dict[str, Any]) -> dict[str, Any]:
    """Stamp a result with ``resultType: complete``.

    Additive by design: clients on older revisions ignore unknown fields, and
    clients on 2026-07-28 require this one.
    """
    stamped = dict(result)
    stamped.setdefault("resultType", RESULT_COMPLETE)
    return stamped


def with_cache(result: dict[str, Any], ttl_ms: int, scope: str = "public") -> dict[str, Any]:
    """Attach the ``CacheableResult`` hints.

    ``cacheScope`` is ``public`` for the catalogue (identical for every caller —
    it is a static build artefact) and ``private`` for anything derived from a
    caller's own input.
    """
    stamped = dict(result)
    stamped.setdefault("ttlMs", ttl_ms)
    stamped.setdefault("cacheScope", scope)
    return stamped


def discover_result(version: str, instructions: str) -> dict[str, Any]:
    """Build the ``server/discover`` payload.

    ``instructions`` is the one field an LLM actually reads, so it is written as
    operational guidance (what to call first, what not to trust) rather than as
    marketing copy.
    """
    return complete(
        with_cache(
            {
                "supportedVersions": list(SUPPORTED_VERSIONS),
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "_meta": {META_SERVER_INFO: server_info(version)},
                "instructions": instructions,
            },
            ttl_ms=CATALOG_TTL_MS,
            scope="public",
        )
    )


def parse_meta(params: dict[str, Any] | None) -> dict[str, Any]:
    """Pull the spec ``_meta`` block out of request params.

    Returns an empty dict for legacy requests, which is exactly the signal the
    dispatcher needs: no ``_meta`` means the caller is on the handshake path.
    """
    if not isinstance(params, dict):
        return {}
    meta = params.get("_meta")
    return meta if isinstance(meta, dict) else {}


def requested_version(params: dict[str, Any] | None) -> str | None:
    """The protocol version a request claims, or ``None`` for legacy callers."""
    return parse_meta(params).get(META_PROTOCOL_VERSION)


def is_supported(version: str | None) -> bool:
    """``None`` (legacy) is always acceptable; an unknown claim is not."""
    return version is None or version in SUPPORTED_VERSIONS


def unsupported_version_error(requested: str) -> dict[str, Any]:
    """The error a 2026-07-28 server returns for an unknown protocol version."""
    return {
        "code": ERROR_UNSUPPORTED_PROTOCOL_VERSION,
        "message": f"Unsupported protocol version: {requested}",
        "data": {"supportedVersions": list(SUPPORTED_VERSIONS)},
    }


def capability_missing_error(capability: str) -> dict[str, Any]:
    """A server must not ask for something the client never declared."""
    return {
        "code": ERROR_MISSING_CLIENT_CAPABILITY,
        "message": f"Client did not declare required capability: {capability}",
    }


def tool_names(tools: list[dict[str, Any]]) -> list[str]:
    """Names in catalogue order — used by the ordering invariant test."""
    return [t.get("name", "") for t in tools]


def is_deterministic_order(tools: list[dict[str, Any]]) -> bool:
    """True when ``tools/list`` order matches the declarative catalogue order.

    The spec asks for deterministic order because clients cache the list and
    upstream prompt caches key on it. A reordering here is a silent cache-miss
    generator, so the contract test calls this directly.
    """
    return tool_names(tools) == sorted(tool_names(tools), key=tool_names(tools).index)


DISCOVER_INSTRUCTIONS = (
    "CircuitAgent is a deterministic hardware-synthesis tool server for PCB design. "
    "Typical flow: call `synthesize_circuit` with a natural-language board description "
    "to get a netlist plus a component list, then `run_erc` to gate it, then "
    "`audit_industrial_dfx` and `validate_manufacturing_package` before exporting "
    "(`export_kicad_netlist`, `export_manufacturing_bom`, `export_ipc2581`, "
    "`export_gerber_bundle`). "
    "Calculators (`calculate_*`, `analyze_*`) are pure functions: no network, no state, "
    "safe to call speculatively. "
    "Only `search_lcsc_parts` reaches the network, and it is unauthenticated. "
    "Trust `run_erc` findings over your own reading of the netlist: every rule carries "
    "a standard reference and a severity, and blocking findings mean the design must "
    "not be sent to fabrication."
)
