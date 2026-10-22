"""Verify each DRC test fails when its defect is reintroduced.

A test that passes both before and after a fix proves nothing. This script
mutates the source in memory, runs the targeted test, and requires it to fail.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(".")
SRC = ROOT / "client" / "pcb_drc.py"

CASES = [
    (
        "pairwise corners instead of ordered paths",
        "_clean_path",
        # Disable the jitter filter: pad jogs become 26-degree "corners" again.
        ("_MIN_CORNER_LEG_MM = 0.150", "_MIN_CORNER_LEG_MM = 0.0"),
        "tests/test_pcb_drc_physical.py::TestAcidTrapDetection::test_pad_jitter_is_not_a_corner",
    ),
    (
        "no pad-aware corner filter",
        "_inside_pad",
        ("and not _inside_pad(cur, pad_boxes)", ""),
        "tests/test_pcb_drc_physical.py::TestAcidTrapDetection::test_acute_corner_inside_a_pad_is_not_reported",
    ),
    (
        "clearance reported per segment pair",
        "worst_clearance_by_pair",
        # Include the location in the dedup key: every violating segment pair
        # becomes its own finding, which is the defect this test guards against.
        ("key = (s1.net, s2.net, s1.layer)", "key = (s1.net, s2.net, s1.layer, s1.p1)"),
        "tests/test_pcb_drc_physical.py::TestClearanceDetection::test_parallel_traces_report_one_finding",
    ),
    (
        "width reported per segment",
        "power_narrow",
        # Emit one finding per segment instead of one per net.
        (
            "    for net, worst_width in sorted(power_narrow.items()):",
            "    for net, worst_width in sorted(power_narrow.items()) * 3:",
        ),
        "tests/test_pcb_drc_physical.py::TestReportUsability::test_width_findings_are_per_net",
    ),
]


def run(args: list[str]) -> int:
    # Argument list, no shell: the only variable parts are test node ids that
    # come from this file's own CASES table, but there is no reason to involve a
    # shell at all.
    return subprocess.run(args, check=False, capture_output=True, text=True).returncode


def main() -> int:
    backup = SRC.read_text(encoding="utf-8")
    original = backup
    failures = []
    try:
        for label, _needle, (old, new), test in CASES:
            if old not in original:
                print(f"  !! pattern not found for '{label}': {old[:50]}")
                failures.append(label)
                continue
            SRC.write_text(original.replace(old, new, 1), encoding="utf-8", newline="")
            code = run([".venv/Scripts/python.exe", "-m", "pytest", test, "-q", "-x"])
            SRC.write_text(original, encoding="utf-8", newline="")
            if code == 0:
                print(f"  {label:45} NOT CAUGHT — test still passes")
                failures.append(label)
            else:
                print(f"  {label:45} caught defect OK")
    finally:
        SRC.write_text(backup, encoding="utf-8", newline="")
    print()
    if failures:
        print(f"{len(failures)} defect(s) not caught: {failures}")
        return 1
    print("All DRC defects are caught by their tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
