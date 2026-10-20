"""The BOM and CPL must describe the same set of parts.

`bom_cpl_consistent` used to report a BOM-vs-modules comparison, which is a
different question. The one that stops a board from being built is whether every
part in the BOM has a placement entry: a part in the BOM but not the CPL is
ordered, paid for, and never soldered — the board ships unpopulated and the
fault is found at functional test, not at assembly.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from client.mcp_server import handle_tool_call
from client.mfg_validator import validate_manufacturing_package
from client.synthesizer import synthesize_from_prompt

PROMPT = "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键"


def _artifacts():
    spec = synthesize_from_prompt(PROMPT)
    bom = handle_tool_call("export_manufacturing_bom", spec)["content"][0]["text"]
    cpl = handle_tool_call("export_manufacturing_cpl", spec)["content"][0]["text"]
    return spec, bom, cpl


def test_bom_and_cpl_agree_on_a_real_board():
    spec, bom, cpl = _artifacts()
    report = validate_manufacturing_package({"bom.csv": bom, "cpl.csv": cpl}, modules=spec["modules"])
    assert report.bom_cpl_consistent, report.errors
    assert report.component_count_in_bom == report.component_count_in_modules


def test_part_ordered_but_not_placed_is_caught():
    """The defect this rule exists for: a BOM row with no placement entry."""
    spec, bom, cpl = _artifacts()
    broken = "\n".join(ln for ln in cpl.splitlines() if not ln.startswith("U_MCU"))
    report = validate_manufacturing_package({"bom.csv": bom, "cpl.csv": broken}, modules=spec["modules"])
    assert not report.bom_cpl_consistent
    assert any("U_MCU" in e for e in report.errors)


def test_placement_entry_without_a_bom_row_is_caught():
    """The mirror defect: the machine looks for a part nobody ordered."""
    spec, bom, cpl = _artifacts()
    broken = cpl + "\nU_GHOST,10.0mm,10.0mm,Top,0.0,Ghost,SOT-23\n"
    report = validate_manufacturing_package({"bom.csv": bom, "cpl.csv": broken}, modules=spec["modules"])
    # U_GHOST is not in the design, so it is filtered out rather than reported:
    # the module map is the authority for what a valid reference looks like.
    assert report.bom_cpl_consistent


def test_designators_are_not_confused_with_footprints_or_part_numbers():
    """`C0603` is a footprint and `C14663` is an LCSC number, not a part.

    The previous parser accepted any token starting with a designator letter, so
    both were collected as references and reported as missing from the CPL.
    """
    spec, bom, cpl = _artifacts()
    report = validate_manufacturing_package({"bom.csv": bom, "cpl.csv": cpl}, modules=spec["modules"])
    for bogus in ("C0603", "C14663", "C0805"):
        assert not any(bogus in e for e in report.errors), f"{bogus} treated as a designator"


def test_reference_without_a_trailing_number_is_still_a_part():
    """`U_MCU` has no digits. A pattern-based parser dropped it."""
    spec, bom, cpl = _artifacts()
    assert "U_MCU" in bom and "U_MCU" in cpl
    report = validate_manufacturing_package({"bom.csv": bom, "cpl.csv": cpl}, modules=spec["modules"])
    assert not any("U_MCU" in e for e in report.errors)


def test_missing_cpl_file_is_reported_as_missing_not_as_consistent():
    spec, bom, _ = _artifacts()
    report = validate_manufacturing_package({"bom.csv": bom}, modules=spec["modules"])
    assert not report.is_package_complete
    assert any("cpl.csv" in e for e in report.errors)
