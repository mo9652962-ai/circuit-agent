"""Contract tests for the MCP 2026-07-28 stateless core.

These are not "does the server run" tests — the rest of the suite covers that.
They pin the specific wire behaviours that changed in 2026-07-28 and that a
client will break on if we regress:

* ``server/discover`` exists and is the stdio probe;
* ``resultType`` is stamped on every result;
* ``ttlMs`` / ``cacheScope`` are present on the cacheable list endpoints;
* an unknown declared protocol version is rejected with the spec's error code;
* the legacy ``initialize`` path still negotiates, because a server that drops
  it silently breaks every client built before 2026;
* ``tools/list`` order is deterministic (the spec asks for it so client and
  prompt caches can hit).
"""

from __future__ import annotations

import pytest

from client import mcp_protocol as proto
from client import mcp_server as mcp


def _call(method: str, params: dict | None = None, msg_id: int = 1):
    msg: dict = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        msg["params"] = params
    return mcp.process_message(msg)


def _modern(params: dict | None = None) -> dict:
    """Params carrying the 2026-07-28 per-request `_meta` block."""
    base = {
        "_meta": {
            proto.META_PROTOCOL_VERSION: proto.PROTOCOL_VERSION,
            proto.META_CLIENT_INFO: {"name": "test-client", "version": "1.0.0"},
            proto.META_CLIENT_CAPABILITIES: {},
        }
    }
    if params:
        base.update(params)
    return base


# --------------------------------------------------------------------------- #
# server/discover
# --------------------------------------------------------------------------- #


def test_server_discover_is_implemented():
    """Servers MUST implement server/discover in 2026-07-28."""
    resp = _call("server/discover")
    assert "error" not in resp
    result = resp["result"]
    assert proto.PROTOCOL_VERSION in result["supportedVersions"]
    assert result["supportedVersions"][0] == proto.PROTOCOL_VERSION, (
        "preferred version must be first — clients take supportedVersions[0]"
    )
    assert result["resultType"] == "complete"


def test_server_discover_reports_identity_and_capabilities():
    result = _call("server/discover")["result"]
    info = result["_meta"][proto.META_SERVER_INFO]
    assert info["name"] == "circuit-agent-mcp"
    # The version must track the package, not a hardcoded literal that drifts.
    import client

    assert info["version"] == client.__version__
    assert set(result["capabilities"]) == {"tools", "resources", "prompts"}


def test_server_discover_carries_cache_hints():
    result = _call("server/discover")["result"]
    assert isinstance(result["ttlMs"], int) and result["ttlMs"] > 0
    assert result["cacheScope"] in ("public", "private")


def test_server_discover_instructions_are_operational():
    """`instructions` is read by an LLM, so it must name the real entry point."""
    instructions = _call("server/discover")["result"]["instructions"]
    assert "synthesize_circuit" in instructions
    assert "run_erc" in instructions
    # It must also warn about the only networked tool.
    assert "search_lcsc_parts" in instructions


def test_server_discover_works_without_any_meta():
    """A legacy client that probes with a bare request must still get an answer."""
    resp = mcp.process_message({"jsonrpc": "2.0", "id": 1, "method": "server/discover"})
    assert "error" not in resp


# --------------------------------------------------------------------------- #
# resultType on every result
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "method,params",
    [
        ("ping", None),
        ("tools/list", None),
        ("resources/list", None),
        ("resources/templates/list", None),
        ("prompts/list", None),
        ("tools/call", {"name": "list_circuit_blocks", "arguments": {}}),
        ("prompts/get", {"name": "optimize_bom_cost", "arguments": {}}),
        ("resources/read", {"uri": "circuit://blocks/catalog"}),
    ],
)
def test_every_result_is_stamped_complete(method, params):
    resp = _call(method, params)
    assert "error" not in resp, f"{method} errored: {resp.get('error')}"
    assert resp["result"]["resultType"] == "complete", f"{method} missing resultType"


def test_result_type_survives_a_tool_error():
    """An isError result is still a *completed* request at the protocol layer."""
    resp = _call("tools/call", {"name": "definitely_not_a_tool", "arguments": {}})
    assert resp["result"]["isError"] is True
    assert resp["result"]["resultType"] == "complete"


# --------------------------------------------------------------------------- #
# Cache hints on list endpoints
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "method",
    ["tools/list", "resources/list", "resources/templates/list", "prompts/list"],
)
def test_list_endpoints_are_cacheable(method):
    result = _call(method)["result"]
    assert result["ttlMs"] == proto.CATALOG_TTL_MS
    assert result["cacheScope"] == "public"


def test_resource_read_is_private_cacheable():
    """A read reflects local files, so it must not be shared between callers."""
    result = _call("resources/read", {"uri": "circuit://blocks/catalog"})["result"]
    assert result["ttlMs"] == proto.RESOURCE_TTL_MS
    assert result["cacheScope"] == "private"


# --------------------------------------------------------------------------- #
# Protocol version negotiation
# --------------------------------------------------------------------------- #


def test_unsupported_version_is_rejected_with_spec_error_code():
    params = {"_meta": {proto.META_PROTOCOL_VERSION: "1999-01-01"}}
    resp = _call("tools/list", params)
    assert "error" in resp
    assert resp["error"]["code"] == proto.ERROR_UNSUPPORTED_PROTOCOL_VERSION
    # The client needs the supported list to recover, so it travels in `data`.
    assert proto.PROTOCOL_VERSION in resp["error"]["data"]["supportedVersions"]


def test_current_version_is_accepted():
    resp = _call("tools/list", _modern())
    assert "error" not in resp
    assert len(resp["result"]["tools"]) > 0


@pytest.mark.parametrize("version", proto.SUPPORTED_VERSIONS)
def test_every_supported_version_is_accepted(version):
    params = {"_meta": {proto.META_PROTOCOL_VERSION: version}}
    resp = _call("tools/list", params)
    assert "error" not in resp, f"{version} rejected but advertised as supported"


def test_legacy_request_without_meta_is_accepted():
    """No `_meta` means a pre-2026 client; it must keep working."""
    resp = _call("tools/list", {})
    assert "error" not in resp


# --------------------------------------------------------------------------- #
# Legacy initialize handshake
# --------------------------------------------------------------------------- #


def test_initialize_echoes_a_known_client_version():
    resp = _call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
    assert resp["result"]["protocolVersion"] == "2024-11-05"


def test_initialize_falls_back_to_current_for_unknown_version():
    resp = _call("initialize", {"protocolVersion": "1999-01-01", "capabilities": {}})
    assert resp["result"]["protocolVersion"] == proto.PROTOCOL_VERSION


def test_initialize_reports_the_package_version():
    import client

    resp = _call("initialize", {"protocolVersion": "2024-11-05"})
    assert resp["result"]["serverInfo"]["version"] == client.__version__


# --------------------------------------------------------------------------- #
# Deterministic ordering
# --------------------------------------------------------------------------- #


def test_tools_list_order_is_deterministic_across_calls():
    first = [t["name"] for t in _call("tools/list")["result"]["tools"]]
    second = [t["name"] for t in _call("tools/list", msg_id=2)["result"]["tools"]]
    assert first == second


def test_tools_list_matches_catalogue_order():
    from client.mcp_schema import AVAILABLE_TOOLS

    served = [t["name"] for t in _call("tools/list")["result"]["tools"]]
    assert served == [t["name"] for t in AVAILABLE_TOOLS]


# --------------------------------------------------------------------------- #
# mcp_protocol helpers
# --------------------------------------------------------------------------- #


def test_parse_meta_handles_missing_and_malformed():
    assert proto.parse_meta(None) == {}
    assert proto.parse_meta({}) == {}
    assert proto.parse_meta({"_meta": "not-a-dict"}) == {}
    assert proto.parse_meta({"_meta": {"k": "v"}}) == {"k": "v"}


def test_requested_version_returns_none_for_legacy():
    assert proto.requested_version(None) is None
    assert proto.requested_version({}) is None
    assert proto.requested_version(_modern()) == proto.PROTOCOL_VERSION


def test_complete_does_not_overwrite_an_explicit_result_type():
    """`input_required` must survive the stamping helper."""
    stamped = proto.complete({"resultType": proto.RESULT_INPUT_REQUIRED})
    assert stamped["resultType"] == proto.RESULT_INPUT_REQUIRED


def test_error_codes_live_in_the_spec_reserved_range():
    """-32020..-32099 is spec-reserved; -32000..-32019 is implementation-defined."""
    for code in (
        proto.ERROR_HEADER_MISMATCH,
        proto.ERROR_MISSING_CLIENT_CAPABILITY,
        proto.ERROR_UNSUPPORTED_PROTOCOL_VERSION,
    ):
        assert -32099 <= code <= -32020, f"{code} outside the reserved range"


def test_legacy_versions_are_all_supported():
    assert proto.LEGACY_VERSIONS <= set(proto.SUPPORTED_VERSIONS)


def test_is_supported_accepts_none_as_legacy():
    assert proto.is_supported(None) is True
    assert proto.is_supported(proto.PROTOCOL_VERSION) is True
    assert proto.is_supported("1999-01-01") is False


def test_capability_missing_error_names_the_capability():
    err = proto.capability_missing_error("elicitation")
    assert "elicitation" in err["message"]
    assert err["code"] == proto.ERROR_MISSING_CLIENT_CAPABILITY


def test_tool_names_preserves_order():
    tools = [{"name": "b"}, {"name": "a"}]
    assert proto.tool_names(tools) == ["b", "a"]
