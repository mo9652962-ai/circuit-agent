"""Tests for client.cli_erc_gate CLI runner."""

from __future__ import annotations

import json
import subprocess
import sys

from client.cli_erc_gate import evaluate_gate


def test_evaluate_gate_severity_weights():
    issues = [
        {"severity": "info", "rule_id": "INFO_1"},
        {"severity": "warning", "rule_id": "WARN_1"},
        {"severity": "error", "rule_id": "ERR_1"},
    ]
    # Default threshold error -> fails because of ERR_1
    passed, counts = evaluate_gate(issues, threshold="error")
    assert passed is False
    assert counts["error"] == 1
    assert counts["warning"] == 1
    assert counts["info"] == 1

    # Threshold blocking -> passes because error < blocking
    passed_blocking, _ = evaluate_gate(issues, threshold="blocking")
    assert passed_blocking is True


def test_cli_gate_missing_file(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "client.cli_erc_gate", str(tmp_path / "nonexistent.json")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "not found" in proc.stderr.lower() or "not found" in proc.stdout.lower()


def test_cli_gate_valid_netlist(tmp_path):
    netlist = {
        "modules": {
            "R1": {"kind": "RESISTOR", "value": "10k", "package": "0603"},
            "C1": {"kind": "CAPACITOR", "value": "100nF", "package": "0402"},
        },
        "connections": [
            {"net": "/VCC", "points": ["R1.1", "C1.1"]},
            {"net": "/GND", "points": ["R1.2", "C1.2"]},
        ],
    }
    netlist_file = tmp_path / "netlist.json"
    netlist_file.write_text(json.dumps(netlist), encoding="utf-8")
    out_dir = tmp_path / "out"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "client.cli_erc_gate",
            str(netlist_file),
            "--out",
            str(out_dir),
            "--severity-threshold",
            "error",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert (out_dir / "erc-report.json").is_file()
    rep = json.loads((out_dir / "erc-report.json").read_text(encoding="utf-8"))
    assert rep["passed"] is True
