"""LCSC / EasyEDA Component Search Client (Community Edition).

Reliability-first design:
  * retry with exponential backoff
  * hard timeout
  * on-disk TTL cache (works offline once warmed)
  * defensive response parsing (upstream schema drift will not raise)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_URL = "https://easyeda.com/api/components/search"
DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 3
BACKOFF_BASE = 0.8
CACHE_TTL_SECONDS = 24 * 3600

CACHE_PATH = Path(
    os.environ.get("CIRCUITAGENT_LCSC_CACHE", "")
    or (Path.home() / ".cache" / "circuit-agent" / "lcsc_cache.json")
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://easyeda.com",
    "Referer": "https://easyeda.com/editor",
}


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #
def _load_cache() -> dict[str, Any]:
    try:
        if CACHE_PATH.is_file():
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass  # cache is an optimization, never a hard dependency


# --------------------------------------------------------------------------- #
# Network layer
# --------------------------------------------------------------------------- #
def _fetch_raw(query: str, timeout: float, retries: int) -> dict[str, Any] | None:
    body = urllib.parse.urlencode({"wd": query}).encode("utf-8")
    last_error: Exception | None = None

    for attempt in range(max(1, retries)):
        req = urllib.request.Request(API_URL, data=body, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            # 4xx (other than 429) will not succeed on retry: stop early.
            if exc.code != 429 and 400 <= exc.code < 500:
                break
        except Exception as exc:  # timeout, DNS, TLS, JSON decode
            last_error = exc

        if attempt < retries - 1:
            time.sleep(BACKOFF_BASE * (2 ** attempt))

    if last_error is not None:
        print(f"[lcsc_client] query '{query}' failed: {last_error}")
    return None


def _parse(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Parse defensively -- upstream nesting has changed before and will again."""
    if limit <= 0:
        return []

    result = payload.get("result") or {}
    lists = result.get("lists") if isinstance(result, dict) else None

    if isinstance(lists, dict):
        items = lists.get("lcsc") or []
    elif isinstance(lists, list):
        items = lists
    else:
        items = []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        c_para = (item.get("dataStr") or {}).get("head", {}).get("c_para", {}) or {}
        lcsc_meta = item.get("lcsc") or {}

        supplier_part = (
            c_para.get("BOM_Supplier Part")
            or c_para.get("Supplier Part")
            or (lcsc_meta.get("number") if isinstance(lcsc_meta, dict) else None)
        )
        if not supplier_part:
            continue

        part_class = c_para.get("JLCPCB Part Class", "Extended Part")
        out.append({
            "lcsc_part": supplier_part,
            "part_number": (
                c_para.get("BOM_Manufacturer Part")
                or c_para.get("Manufacturer Part")
                or item.get("title", "")
            ),
            "package": c_para.get("package", ""),
            "stock": int(lcsc_meta.get("stock", 0) or 0),
            "price_usd": float(lcsc_meta.get("price", 0.0) or 0.0),
            "part_class": part_class,
            "is_basic": part_class == "Basic Part",
            "description": item.get("title", ""),
        })
        if len(out) >= limit:
            break

    return out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def search_lcsc_parts(
    query: str,
    limit: int = 5,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Search live LCSC stock, price and package for any part number.

    Falls back to the on-disk cache (and finally an empty list) when the network
    is unavailable, so callers never have to handle transport exceptions.
    """
    key = f"{query.strip().lower()}|{limit}"
    cache = _load_cache() if use_cache else {}
    entry = cache.get(key)

    if entry and (time.time() - entry.get("ts", 0)) < CACHE_TTL_SECONDS:
        return entry.get("data", [])

    payload = None
    try:
        payload = _fetch_raw(query, timeout, retries)
    except Exception as exc:  # transport layer must never escape to the caller
        print(f"[lcsc_client] transport error for '{query}': {exc}")

    if payload is not None:
        parsed = _parse(payload, limit)
        if parsed:
            cache[key] = {"ts": time.time(), "data": parsed}
            _save_cache(cache)
            return parsed

    # Stale cache beats nothing when the network is down.
    if entry:
        return entry.get("data", [])
    return []


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "CH340N"
    print(f"Searching LCSC: {q}")
    for p in search_lcsc_parts(q):
        print(
            f"  [{p['lcsc_part']}] {p['part_number']} | {p['package']} | "
            f"stock={p['stock']} | ${p['price_usd']} | {p['part_class']}"
        )
