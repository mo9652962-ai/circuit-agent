"""CircuitAgent ERC & DFX CI Gate CLI.

Command-line entry point for GitHub Actions and CI pipelines to audit
netlist electrical rules (ERC) and physical manufacturability (DRC).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from .erc import run_erc

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("circuit-gate")

SEVERITY_WEIGHTS = {
    "info": 0,
    "warning": 1,
    "error": 2,
    "blocking": 3,
    "critical": 3,
}


def evaluate_gate(issues: list[dict[str, Any]], threshold: str = "error") -> tuple[bool, dict[str, int]]:
    th_weight = SEVERITY_WEIGHTS.get(threshold.lower(), 2)
    counts = {"info": 0, "warning": 0, "error": 0, "blocking": 0, "critical": 0}

    failing_count = 0
    for issue in issues:
        sev = str(issue.get("severity", "info")).lower()
        if sev in counts:
            counts[sev] += 1
        w = SEVERITY_WEIGHTS.get(sev, 0)
        if w >= th_weight:
            failing_count += 1

    passed = failing_count == 0
    return passed, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="CircuitAgent ERC & DFX CI Gate")
    parser.add_argument("input_file", help="Path to netlist JSON or hardware spec file")
    parser.add_argument(
        "--severity-threshold",
        choices=["info", "warning", "error", "blocking"],
        default="error",
        help="Severity threshold to fail the gate (default: error)",
    )
    parser.add_argument("--out", default="erc-out", help="Output directory for reports")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.is_file():
        log.error(f"::error::Netlist input file not found: {input_path}")
        return 2

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error(f"::error::Failed to parse JSON from {input_path}: {exc}")
        return 2

    # Support both direct netlist dict or wrapped spec dict
    modules = data.get("modules") or {}
    connections = data.get("connections") or []
    if "netlist" in data and isinstance(data["netlist"], dict):
        modules = data["netlist"].get("modules", modules)
        connections = data["netlist"].get("connections", connections)

    log.info(f"[*] Auditing {len(modules)} modules and {len(connections)} nets across 56 ERC rules...")
    issues = run_erc(modules, connections)

    passed, counts = evaluate_gate(issues, args.severity_threshold)

    # Format GitHub Actions annotations
    for issue in issues:
        sev = str(issue.get("severity", "info")).lower()
        title = issue.get("title", "")
        detail = issue.get("detail", "")
        rule_id = issue.get("rule_id", "ERC")
        src = issue.get("source", "")
        msg = f"[{rule_id}] {title} — {detail} (Standard: {src})"
        if sev in ("error", "blocking", "critical"):
            log.error(f"::error::{msg}")
        elif sev == "warning":
            log.warning(f"::warning::{msg}")
        else:
            log.info(f"::notice::{msg}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / "erc-report.json"
    report_payload = {
        "passed": passed,
        "severity_threshold": args.severity_threshold,
        "counts": counts,
        "total_issues": len(issues),
        "issues": issues,
    }
    report_file.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"[+] ERC report written to: {report_file}")

    if not passed:
        log.error(f"❌ ERC Gate FAILED (Threshold: {args.severity_threshold})")
        return 1

    log.info("✅ ERC Gate PASSED: Clean electrical rules and components.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
