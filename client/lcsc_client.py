"""LCSC & EasyEDA Component Search Client (Public Edition)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


def search_lcsc_parts(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Query live component specifications, stock, and pricing from public data gateway."""
    url = "https://easyeda.com/api/components/search"
    body = urllib.parse.urlencode({"wd": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return [{"error": f"Network or gateway error: {exc}", "query": query}]

    results: list[dict[str, Any]] = []
    items = data.get("result", {}).get("lists", []) if isinstance(data, dict) else []
    for item in items[:limit]:
        results.append({
            "part_number": item.get("display_title", item.get("title", "")),
            "lcsc_part": item.get("part", item.get("lcsc", "")),
            "package": item.get("package", ""),
            "stock": item.get("stock", 0),
            "price_usd": item.get("price", 0.0),
            "description": item.get("description", ""),
        })

    return results


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "CH340N"
    print(f"Searching: {q}")
    for p in search_lcsc_parts(q):
        print(p)
