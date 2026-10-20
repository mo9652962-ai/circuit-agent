"""Tests for passive tolerance analysis.

Every numeric assertion is anchored to a published worked example, so a future
change that breaks the arithmetic fails with a message naming the source rather
than silently producing a plausible number.

The most important test here is
``test_divider_rss_uses_sensitivity_not_percentage_rss`` — it pins the one
methodological point that separates a correct analysis from a wrong one.
"""

from __future__ import annotations

import math

import pytest

from client import tolerance_analysis as t
from client.mcp_server import handle_tool_call

# --------------------------------------------------------------------------- #
# The resistor error model, against the ADI worked example
# --------------------------------------------------------------------------- #


def test_resistor_band_reproduces_the_adi_worked_example():
    """100 Ω, ±1%, 100 ppm/°C, 5% life, 85 °C excursion → 93.15 to 106.85 Ω.

    Source: Analog Devices, "An Inside Look at High-Speed ADC Accuracy Part 3".
    The linear (worst-case) sum is 1% + 0.85% + 5% = 6.85%, i.e. 93.15–106.85 Ω.
    """
    band = t.resistor_value_band(
        nominal_ohm=100.0,
        tolerance_pct=1.0,
        tcr_ppm_per_c=100.0,
        delta_temp_c=85.0,
        life_drift_pct=5.0,
        life_hours_specified=5000.0,
        life_hours_required=5000.0,
    )
    assert band["worst_case_min_ohm"] == pytest.approx(93.15, abs=0.01)
    assert band["worst_case_max_ohm"] == pytest.approx(106.85, abs=0.01)
    # And the component terms, individually.
    assert band["tolerance_pct"] == pytest.approx(1.0)
    assert band["tcr_pct"] == pytest.approx(0.85)
    assert band["life_drift_pct"] == pytest.approx(5.0)


def test_life_drift_scales_with_sqrt_of_time_not_linearly():
    """Random walk, not a ramp: 1000 h → 10 kh is ×3.16, not ×10.

    Same ADI reference: multiplying a 1000 h figure by 8.77 for a year is "much
    too pessimistic"; the sqrt of the ratio is the honest scaling.
    """
    base = t.resistor_value_band(1000.0, 0.0, 0.0, 0.0, 2.0, 1000.0, 1000.0)
    ten_x = t.resistor_value_band(1000.0, 0.0, 0.0, 0.0, 2.0, 1000.0, 10000.0)
    assert base["life_drift_pct"] == pytest.approx(2.0)
    assert ten_x["life_drift_pct"] == pytest.approx(2.0 * math.sqrt(10), rel=1e-6)
    assert ten_x["life_drift_pct"] < 10.0, "linear scaling would give 20%"


def test_resistor_band_reports_the_dominant_term():
    """A 1% thick-film part over 60 °C is TCR-dominated, not tolerance-dominated."""
    band = t.resistor_value_band(10000.0, 1.0, 200.0, 60.0)
    assert band["dominant_term"] == "tcr"


def test_thin_film_is_tolerance_dominated_at_the_same_grade():
    band = t.resistor_value_band(10000.0, 1.0, 25.0, 60.0)
    assert band["dominant_term"] == "tolerance"


def test_rss_band_is_tighter_than_linear_band():
    band = t.resistor_value_band(10000.0, 1.0, 100.0, 50.0, 2.0, 1000.0, 1000.0)
    assert band["rss_total_pct"] < band["linear_total_pct"]
    assert band["min_ohm"] > band["worst_case_min_ohm"]


# --------------------------------------------------------------------------- #
# Divider tolerance — worst case vs statistical
# --------------------------------------------------------------------------- #


def test_divider_worst_case_is_symmetric_for_equal_resistors():
    """R1 = R2 with equal tolerances: the output band is symmetric about V_in/2."""
    result = t.divider_tolerance(3.3, 10000.0, 10000.0, tolerance_pct=1.0)
    assert result.v_out_nominal == pytest.approx(1.65)
    assert result.v_out_worst_min == pytest.approx(1.65 * (1 - 0.01), rel=1e-6)
    assert result.v_out_worst_max == pytest.approx(1.65 * (1 + 0.01), rel=1e-6)


def test_divider_worst_case_equals_corner_enumeration():
    """Verify the closed form against a brute-force four-corner sweep."""
    v_in, r1, r2, tol = 5.0, 4700.0, 1000.0, 0.01
    result = t.divider_tolerance(v_in, r1, r2, tolerance_pct=1.0)

    corners = []
    for r1f in (1 - tol, 1 + tol):
        for r2f in (1 - tol, 1 + tol):
            corners.append(v_in * (r2 * r2f) / (r1 * r1f + r2 * r2f))

    assert result.v_out_worst_min == pytest.approx(min(corners), rel=1e-9)
    assert result.v_out_worst_max == pytest.approx(max(corners), rel=1e-9)


def test_divider_rss_uses_sensitivity_not_percentage_rss():
    """The methodological point: RSS the *voltage* contributions, not the %.

    For a 1:1 divider with ±1% parts, naive RSS of the percentages would give
    1%·sqrt(2)/2 ≈ 0.71% by accident of the topology. For an asymmetric divider
    the two methods diverge, and sensitivity propagation is the correct one
    because the output is a quotient of random variables (TI SNVA112).
    """
    result = t.divider_tolerance(5.0, 4700.0, 1000.0, tolerance_pct=1.0)

    # Sensitivity of the output to each resistor, computed independently here.
    total = 5700.0
    sens_r1 = -5.0 * 1000.0 / total**2
    sens_r2 = 5.0 * 4700.0 / total**2
    expected_rss_v = math.sqrt((abs(sens_r1) * 4700.0 * 0.01) ** 2 + (abs(sens_r2) * 1000.0 * 0.01) ** 2)

    assert result.v_out_max - result.v_out_nominal == pytest.approx(expected_rss_v, rel=1e-6)
    assert result.sensitivity_r1 == pytest.approx(sens_r1, rel=1e-6)
    assert result.sensitivity_r2 == pytest.approx(sens_r2, rel=1e-6)


def test_divider_rss_is_tighter_than_worst_case():
    result = t.divider_tolerance(3.3, 10000.0, 10000.0, tolerance_pct=1.0)
    assert result.error_rss_pct < result.error_worst_pct


def test_divider_names_the_dominant_resistor():
    """R2 sensitivity is R1/(R1+R2)² — with a small R2, R1 dominates the error."""
    result = t.divider_tolerance(5.0, 4700.0, 1000.0, tolerance_pct=1.0)
    # |dV/dR1|·dR1 = 5·1000/5700² · 47 = 0.0145 V
    # |dV/dR2|·dR2 = 5·4700/5700² · 10 = 0.0072 V  -> R1 dominates
    assert result.dominant_resistor == "r1"


def test_matched_pair_ratio_tolerance_collapses_the_error():
    """The biggest free accuracy win: a matched pair is far better than its parts."""
    unmatched = t.divider_tolerance(3.3, 10000.0, 10000.0, tolerance_pct=1.0)
    matched = t.divider_tolerance(3.3, 10000.0, 10000.0, tolerance_pct=1.0, ratio_tolerance_pct=0.05)
    assert matched.error_rss_pct < unmatched.error_rss_pct / 10
    assert matched.error_rss_pct == pytest.approx(0.05, rel=1e-6)
    assert any("Matched pair" in note for note in matched.notes)


def test_supply_tolerance_is_an_independent_contribution():
    """A perfect divider on a ±5% rail is still ±5% wrong."""
    result = t.divider_tolerance(3.3, 10000.0, 10000.0, tolerance_pct=0.0, v_in_tolerance_pct=5.0)
    assert result.error_rss_pct == pytest.approx(5.0, rel=1e-6)


def test_tcr_warning_fires_when_tcr_beats_tolerance():
    result = t.divider_tolerance(
        3.3,
        10000.0,
        10000.0,
        tolerance_pct=0.1,
        tcr_ppm_per_c=200.0,
        delta_temp_c=60.0,
    )
    assert any("TCR contributes" in note for note in result.notes)
    assert any("would not help" in note for note in result.notes)


def test_large_worst_case_error_is_flagged():
    result = t.divider_tolerance(3.3, 10000.0, 10000.0, tolerance_pct=10.0)
    assert any("exceeds 5%" in note for note in result.notes)


def test_divider_rejects_invalid_inputs():
    with pytest.raises(t.ToleranceError):
        t.divider_tolerance(3.3, 0.0, 10000.0)
    with pytest.raises(t.ToleranceError):
        t.divider_tolerance(0.0, 10000.0, 10000.0)
    with pytest.raises(t.ToleranceError):
        t.divider_tolerance(3.3, 10000.0, 10000.0, ratio_tolerance_pct=-1.0)


# --------------------------------------------------------------------------- #
# Feedback divider synthesis
# --------------------------------------------------------------------------- #


def test_feedback_divider_hits_the_target_within_e96_resolution():
    result = t.divider_ratio_for_target(v_out=5.0, v_ref=0.8, r_total_ohm=100_000.0)
    # The snapped pair cannot be exact, but it must be within a couple of percent.
    assert abs(result["snap_error_pct"]) < 3.0
    assert result["v_out_actual"] == pytest.approx(5.0, rel=0.03)
    assert "static offset" in result["note"]


def test_feedback_divider_reports_snap_error_as_a_real_number():
    result = t.divider_ratio_for_target(v_out=3.3, v_ref=0.6)
    assert isinstance(result["snap_error_pct"], float)
    assert result["r1_ohm"] > 0 and result["r2_ohm"] > 0


def test_feedback_divider_rejects_a_target_below_the_reference():
    with pytest.raises(t.ToleranceError):
        t.divider_ratio_for_target(v_out=0.5, v_ref=0.8)


# --------------------------------------------------------------------------- #
# Required tolerance grade
# --------------------------------------------------------------------------- #


def test_required_grade_solves_the_error_budget():
    """Target 1%, other sources 0.6% → 0.8% allowed → the 0.5% grade fits."""
    result = t.required_tolerance_grade(1.0, [0.6])
    assert result["feasible"] is True
    assert result["recommended_tolerance_pct"] <= 0.8
    assert result["resulting_total_rss_pct"] <= 1.0


def test_required_grade_reports_infeasible_when_others_already_exceed():
    result = t.required_tolerance_grade(1.0, [0.8, 0.8])
    assert result["feasible"] is False
    assert "no tolerance grade can meet it" in result["reason"]


def test_required_grade_picks_the_loosest_grade_that_works():
    """Cost discipline: do not recommend a tighter part than the budget needs."""
    result = t.required_tolerance_grade(2.0, [0.0])
    assert result["recommended_grade"] == "2%"


# --------------------------------------------------------------------------- #
# TCR dominance
# --------------------------------------------------------------------------- #


def test_tcr_dominance_says_the_truth_about_buying_tighter_tolerance():
    verdict = t.tcr_penalty_over_temperature(tolerance_pct=0.1, tcr_ppm_per_c=200.0, delta_temp_c=60.0)
    assert verdict["dominant"] == "tcr"
    assert "waste money" in verdict["recommendation"]


def test_tolerance_dominance_at_low_tcr():
    verdict = t.tcr_penalty_over_temperature(tolerance_pct=1.0, tcr_ppm_per_c=10.0, delta_temp_c=20.0)
    assert verdict["dominant"] == "tolerance"


def test_comparable_terms_are_reported_as_comparable():
    verdict = t.tcr_penalty_over_temperature(tolerance_pct=1.0, tcr_ppm_per_c=170.0, delta_temp_c=60.0)
    assert verdict["dominant"] == "comparable"


# --------------------------------------------------------------------------- #
# MCP tool wiring
# --------------------------------------------------------------------------- #


def _call(name: str, arguments: dict) -> dict:
    import json

    result = handle_tool_call(name, arguments)
    assert not result.get("isError"), result.get("content")
    return json.loads(result["content"][0]["text"])


def test_mcp_tool_divider_tolerance():
    data = _call("analyze_divider_tolerance", {"v_in": 3.3, "r1_ohm": 10000, "r2_ohm": 10000})
    assert data["v_out_nominal"] == pytest.approx(1.65)
    assert data["error_worst_pct"] == pytest.approx(1.0, abs=1e-6)
    assert data["dominant_resistor"] in ("r1", "r2")


def test_mcp_tool_resistor_error_budget():
    data = _call(
        "analyze_resistor_error_budget",
        {"nominal_ohm": 100.0, "tolerance_pct": 1.0, "tcr_ppm_per_c": 100.0, "delta_temp_c": 85.0,
         "life_drift_pct": 5.0, "life_hours_specified": 5000.0, "life_hours_required": 5000.0},
    )
    assert data["value_band"]["worst_case_min_ohm"] == pytest.approx(93.15, abs=0.01)
    assert "dominance" in data


def test_mcp_tool_feedback_divider():
    data = _call("solve_feedback_divider", {"v_out": 5.0, "v_ref": 0.8})
    assert data["r1_ohm"] > 0
    assert "snap_error_pct" in data


def test_new_tolerance_tools_are_declared_and_read_only():
    from client.mcp_schema import AVAILABLE_TOOLS

    names = {x["name"] for x in AVAILABLE_TOOLS}
    for tool in ("analyze_divider_tolerance", "analyze_resistor_error_budget", "solve_feedback_divider"):
        assert tool in names
        decl = next(x for x in AVAILABLE_TOOLS if x["name"] == tool)
        assert decl["annotations"]["readOnlyHint"] is True
        assert decl["annotations"]["openWorldHint"] is False
