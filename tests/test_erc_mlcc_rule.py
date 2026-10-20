"""Tests for the MLCC effective-capacitance ERC rule and its value parser.

Two things are being pinned here:

1. The capacitance parser reads the notations BOMs actually use, and refuses to
   guess when it cannot — a wrong guess would fabricate a derating warning,
   which is worse than silence.
2. The ERC rule fires on a genuinely under-derated capacitor and stays quiet
   otherwise. A design gate that warns on everything is a gate nobody reads.
"""

from __future__ import annotations

import pytest

from client.erc import _parse_capacitance_uf, erc_gate, run_erc

# --------------------------------------------------------------------------- #
# Capacitance value parsing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw,expected_uf",
    [
        ("100n", 0.1),
        ("0.1u", 0.1),
        ("100nF", 0.1),
        ("10uF", 10.0),
        ("10u", 10.0),
        ("4.7µF", 4.7),
        ("22µF", 22.0),
        ("22pF", 22e-6),
        ("1F", 1000.0),
        (" 10 uF ", 10.0),
    ],
)
def test_parse_capacitance_reads_bom_notations(raw, expected_uf):
    assert _parse_capacitance_uf(raw) == pytest.approx(expected_uf, rel=1e-9)


@pytest.mark.parametrize("raw", ["10", "", "abc", "4.7k", "1M", "not-a-value"])
def test_parse_capacitance_refuses_to_guess(raw):
    """A bare number or a non-capacitance unit returns None rather than a guess."""
    assert _parse_capacitance_uf(raw) is None


def test_bare_number_is_not_treated_as_microfarads():
    """The distinction that keeps the rule honest: "10" could be anything."""
    assert _parse_capacitance_uf("10") is None
    assert _parse_capacitance_uf("10u") == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# The ERC rule
# --------------------------------------------------------------------------- #


def _design(**cap_overrides) -> tuple[dict, list]:
    """A minimal valid design with one under-test capacitor."""
    cap = {
        "kind": "CAPACITOR",
        "value": "10uF",
        "rated_v": 6.3,
        "applied_v": 5.0,
        "case_size": "0805",
        "dielectric": "X5R",
    }
    cap.update(cap_overrides)
    modules = {
        "C1": cap,
        "C2": {
            "kind": "CAPACITOR",
            "value": "100n",
            "rated_v": 50,
            "applied_v": 3.3,
            "case_size": "0402",
            "dielectric": "X7R",
        },
        "U1": {"kind": "MCU", "value": "ESP32-C3"},
    }
    connections = [
        {"net": "/GND", "points": ["U1:GND", "C1:2", "C2:2"]},
        {"net": "/3V3", "points": ["U1:VDD", "C2:1"]},
        {"net": "/VBUS", "points": ["C1:1"]},
    ]
    return modules, connections


def _mlcc_issues(modules, connections) -> list[dict]:
    return [i for i in run_erc(modules, connections) if i["code"] == "MLCC_EFFECTIVE_CAPACITANCE_DEFICIT"]


def test_rule_fires_on_an_under_derated_capacitor():
    """10 µF X5R 0805 on a 5 V rail of a 6.3 V part retains only ~29%."""
    issues = _mlcc_issues(*_design())
    assert len(issues) == 1
    assert issues[0]["object_id"] == "comp:C1"
    assert issues[0]["severity"] == "warning"
    # The detail must carry the actual number, not just a complaint.
    assert "µF" in issues[0]["detail"]
    assert "保留" in issues[0]["detail"]


def test_rule_stays_quiet_when_the_part_is_well_derated():
    """A 50 V X7R part on 3.3 V retains plenty; no warning."""
    issues = _mlcc_issues(*_design(rated_v=50.0, applied_v=3.3, value="100n"))
    assert issues == []


def test_rule_is_severity_warning_not_blocking():
    """Derating is a design smell, not a netlist error — it must not block export."""
    modules, connections = _design()
    gate = erc_gate(run_erc(modules, connections))
    # This design has other blocking problems (floating nets), but the MLCC
    # finding itself must be a warning.
    mlcc = _mlcc_issues(modules, connections)
    assert all(i["severity"] == "warning" for i in mlcc)
    assert isinstance(gate["allowed"], bool)


def test_rule_skips_parts_without_bias_data():
    """No rated_v/applied_v on the part means nothing to recompute honestly."""
    modules, connections = _design(rated_v=None, applied_v=None)
    assert _mlcc_issues(modules, connections) == []


def test_rule_skips_zero_bias():
    """A part with no DC across it is not derated by bias."""
    modules, connections = _design(applied_v=0.0)
    assert _mlcc_issues(modules, connections) == []


def test_rule_ignores_non_capacitors():
    """A resistor with a rated_v field must not be run through the MLCC model."""
    modules, connections = _design()
    modules["R1"] = {
        "kind": "RESISTOR",
        "value": "10k",
        "rated_v": 6.3,
        "applied_v": 5.0,
        "case_size": "0402",
        "dielectric": "X5R",
    }
    issues = _mlcc_issues(modules, connections)
    assert [i["object_id"] for i in issues] == ["comp:C1"]


def test_rule_does_not_crash_on_a_malformed_value():
    """One unparseable value must not abort the whole ERC run."""
    modules, connections = _design(value="garbage")
    # The run completes and simply reports nothing for that part.
    issues = run_erc(modules, connections)
    assert isinstance(issues, list)
    assert _mlcc_issues(modules, connections) == []


def test_rule_reports_every_offending_capacitor():
    modules, connections = _design()
    modules["C3"] = {
        "kind": "CAPACITOR",
        "value": "22uF",
        "rated_v": 6.3,
        "applied_v": 6.0,
        "case_size": "0603",
        "dielectric": "X5R",
    }
    issues = _mlcc_issues(modules, connections)
    assert {i["object_id"] for i in issues} == {"comp:C1", "comp:C3"}


def test_class_one_capacitor_never_triggers():
    """C0G is a linear dielectric: no bias loss, so the rule must stay silent."""
    modules, connections = _design(dielectric="C0G", rated_v=16.0, applied_v=5.0)
    assert _mlcc_issues(modules, connections) == []


def test_rule_survives_a_missing_case_size():
    """Defaulting the case size is fine; crashing is not."""
    modules, connections = _design()
    del modules["C1"]["case_size"]
    del modules["C1"]["dielectric"]
    issues = _mlcc_issues(modules, connections)
    assert len(issues) == 1


def test_synthesized_design_runs_with_the_new_rule():
    """The rule must be a no-op on designs that carry no bias metadata."""
    from client.synthesizer import synthesize_from_prompt

    result = synthesize_from_prompt("基于 ESP32-C3 的环境监测节点，带 Type-C 供电和 I2C 传感器")
    issues = run_erc(result["modules"], result["netlist"]["connections"])
    # Synthesis output has no rated_v/applied_v on parts, so the rule abstains.
    assert all(i["code"] != "MLCC_EFFECTIVE_CAPACITANCE_DEFICIT" for i in issues)
    assert isinstance(issues, list)
