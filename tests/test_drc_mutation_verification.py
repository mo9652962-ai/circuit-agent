"""Mutation verification for the DRC tests, wired into the suite.

`verify_drc_tests.py` (repo root) reintroduces four historical
`client/pcb_drc.py` defects one at a time and requires the targeted test
to fail for each. A test that passes both before and after a fix proves
nothing, so this wrapper runs the script as part of the normal suite —
CI picks it up with no workflow change.

The script mutates `client/pcb_drc.py` on disk and restores it in a
finally block; the mutations are only ever imported by the subprocesses
the script spawns, never by this test process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_drc_mutation_verification():
    result = subprocess.run(
        [sys.executable, "verify_drc_tests.py"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=1200,
    )
    assert result.returncode == 0, (
        "DRC mutation verification failed — a reintroduced defect was not "
        f"caught by its test:\n{result.stdout}\n{result.stderr}"
    )
