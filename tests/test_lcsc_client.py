"""Tests for the LCSC live client: parsing, caching, and offline degradation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from client import lcsc_client


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch):
    """Never touch the developer's real cache during tests."""
    monkeypatch.setattr(lcsc_client, "CACHE_PATH", tmp_path / "cache.json")
    yield


SAMPLE_PAYLOAD = {
    "success": True,
    "result": {
        "lists": {
            "lcsc": [
                {
                    "title": "CH340N USB to serial",
                    "dataStr": {"head": {"c_para": {
                        "BOM_Supplier Part": "C506813",
                        "BOM_Manufacturer Part": "CH340N",
                        "package": "SOP-8_L5.0-W4.0-P1.27-LS6.0-BL",
                        "JLCPCB Part Class": "Extended Part",
                    }}},
                    "lcsc": {"stock": 196, "price": 0.5537},
                },
                {
                    "title": "no supplier part -> skipped",
                    "dataStr": {"head": {"c_para": {}}},
                    "lcsc": {},
                },
            ]
        }
    },
}


def test_parse_extracts_core_fields():
    out = lcsc_client._parse(SAMPLE_PAYLOAD, limit=5)
    assert len(out) == 1, "rows without an LCSC number must be dropped"
    row = out[0]
    assert row["lcsc_part"] == "C506813"
    assert row["part_number"] == "CH340N"
    assert row["stock"] == 196
    assert row["is_basic"] is False
    assert row["part_class"] == "Extended Part"


def test_parse_respects_limit():
    out = lcsc_client._parse(SAMPLE_PAYLOAD, limit=0)
    assert out == []


@pytest.mark.parametrize("payload", [
    {},
    {"result": None},
    {"result": {}},
    {"result": {"lists": None}},
    {"result": {"lists": {}}},
    {"result": {"lists": {"lcsc": None}}},
    {"result": {"lists": []}},
    {"result": {"lists": "unexpected string"}},
    {"result": {"lists": {"lcsc": ["not-a-dict"]}}},
])
def test_parse_survives_schema_drift(payload):
    """Upstream nesting has changed before; parsing must never raise."""
    assert lcsc_client._parse(payload, limit=5) == []


def test_parse_accepts_flat_list_shape():
    """A future upstream may return a bare list instead of a dict."""
    payload = {"result": {"lists": SAMPLE_PAYLOAD["result"]["lists"]["lcsc"]}}
    out = lcsc_client._parse(payload, limit=5)
    assert len(out) == 1
    assert out[0]["lcsc_part"] == "C506813"


def test_network_failure_returns_empty_list(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(lcsc_client, "_fetch_raw", boom)
    assert lcsc_client.search_lcsc_parts("CH340N") == []


def test_cache_roundtrip_and_reuse(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(query, timeout, retries):
        calls["n"] += 1
        return SAMPLE_PAYLOAD

    monkeypatch.setattr(lcsc_client, "_fetch_raw", fake_fetch)

    first = lcsc_client.search_lcsc_parts("CH340N", limit=1)
    second = lcsc_client.search_lcsc_parts("CH340N", limit=1)

    assert first == second
    assert calls["n"] == 1, "second call must be served from cache"
    assert lcsc_client.CACHE_PATH.is_file()
    assert json.loads(lcsc_client.CACHE_PATH.read_text(encoding="utf-8"))


def test_stale_cache_used_when_network_dies(monkeypatch):
    monkeypatch.setattr(lcsc_client, "_fetch_raw",
                        lambda q, t, r: SAMPLE_PAYLOAD)
    warm = lcsc_client.search_lcsc_parts("CH340N", limit=1)
    assert warm

    # Expire the entry, then kill the network.
    cache = json.loads(lcsc_client.CACHE_PATH.read_text(encoding="utf-8"))
    for entry in cache.values():
        entry["ts"] = 0
    lcsc_client.CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")

    monkeypatch.setattr(lcsc_client, "_fetch_raw", lambda q, t, r: None)
    assert lcsc_client.search_lcsc_parts("CH340N", limit=1) == warm


def test_cache_disabled_bypasses_disk(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(query, timeout, retries):
        calls["n"] += 1
        return SAMPLE_PAYLOAD

    monkeypatch.setattr(lcsc_client, "_fetch_raw", fake_fetch)
    lcsc_client.search_lcsc_parts("CH340N", limit=1, use_cache=False)
    lcsc_client.search_lcsc_parts("CH340N", limit=1, use_cache=False)
    assert calls["n"] == 2
