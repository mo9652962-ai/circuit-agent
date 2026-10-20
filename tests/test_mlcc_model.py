"""Tests for the real MLCC behaviour model.

The important property of this module is that it is *calibrated against
published measurements*, not tuned until the tests pass. Every numeric assertion
below names the measurement it comes from, so a future change that breaks the
calibration fails here with a message pointing at the source.

Two independent published datapoints anchor the DC-bias curve and the ageing
law; a third anchors the brown-out arithmetic against a reference task whose
answer is public.
"""

from __future__ import annotations

import pytest

from client import mlcc_model as m
from client.mcp_server import handle_tool_call

# --------------------------------------------------------------------------- #
# Calibration against published measurements
# --------------------------------------------------------------------------- #


def test_dc_bias_curve_reproduces_the_published_measurement():
    """22 µF 6.3 V X5R 0805 delivers 11.4 µF at 4.7 V bias — measured.

    Source: EEBench task write-up (atopile, 2026), which reports this exact
    submission: 22 µF nominally, 11.4 µF effective at 4.7 V bias, and a
    protected rail that fell through its 3 V floor after 0.85 ms instead of the
    required 20 ms. Fresh part, so ageing ≈ 1 and tolerance is excluded.
    """
    eff = m.effective_capacitance(
        marked_capacitance_uf=22.0,
        rated_v=6.3,
        applied_v=4.7,
        case_size="0805",
        dielectric="X5R",
        ambient_c=25.0,
        hours_in_service=1.0,
        tolerance_pct=0.0,
        ac_level="large",
    )
    assert eff.effective_capacitance_uf == pytest.approx(11.4, abs=0.05), (
        f"model returns {eff.effective_capacitance_uf} µF, published measurement is 11.4 µF"
    )


def test_ageing_law_reproduces_the_published_4500_hour_measurement():
    """A 10 µF part held near its bias limit drops below 5 µF after 4500 h.

    Source: OS Engineering measurement note — 10 µF parts fell to ~7 µF on
    application of a 6 V bias, then to under 5 µF after 4500 hours. Modelled
    from the 7 µF post-bias starting point.
    """
    retention, _ = m.ageing_retention(4500.0, "X5R", under_dc_bias=True)
    after = 7.0 * retention
    assert after < 5.0, f"model gives {after:.2f} µF after 4500 h, measurement is < 5 µF"
    # And it must not be absurdly pessimistic either: a decade-scale loss, not
    # a total wipeout.
    assert after > 3.0, f"model gives {after:.2f} µF, which over-predicts loss"


def test_dc_bias_retention_at_rated_is_inside_the_published_band():
    """At rated voltage the same nominal part loses 35–65% across vendors."""
    for case, dielectric in (("0402", "X5R"), ("0603", "X5R"), ("0805", "X5R"), ("1206", "X7R")):
        retention, confidence = m.dc_bias_retention(6.3, 6.3, case, dielectric)
        assert 0.30 <= retention <= 0.65, f"{case} {dielectric} at rated: {retention}"
        assert confidence == "band"


def test_larger_case_retains_more_capacitance_under_the_same_bias():
    """Field per dielectric thickness is the mechanism; a bigger case wins."""
    small, _ = m.dc_bias_retention(3.3, 6.3, "0402", "X5R")
    large, _ = m.dc_bias_retention(3.3, 6.3, "1210", "X5R")
    assert large > small, f"1210 ({large}) should beat 0402 ({small}) under identical bias"


def test_dc_bias_retention_is_monotonic_in_bias():
    """More bias can never mean more capacitance."""
    previous = 1.0
    for v in (0.0, 0.5, 1.0, 2.0, 3.3, 5.0, 6.3):
        retention, _ = m.dc_bias_retention(v, 6.3, "0805", "X5R")
        assert retention <= previous + 1e-9, f"retention rose at {v} V"
        previous = retention


def test_zero_bias_retains_everything():
    retention, _ = m.dc_bias_retention(0.0, 6.3, "0805", "X5R")
    assert retention == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Class I parts have none of these mechanisms
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("dielectric", ["C0G", "NP0"])
def test_class_one_has_no_bias_ageing_or_temperature_loss(dielectric):
    eff = m.effective_capacitance(
        marked_capacitance_uf=1.0,
        rated_v=50.0,
        applied_v=25.0,
        case_size="0603",
        dielectric=dielectric,
        ambient_c=85.0,
        hours_in_service=100000.0,
        tolerance_pct=5.0,
    )
    assert eff.dc_bias_factor == 1.0
    assert eff.ageing_factor == 1.0
    assert eff.temperature_factor == 1.0
    # Only tolerance applies: ±5% → 0.95 worst case.
    assert eff.effective_capacitance_uf == pytest.approx(0.95)
    assert eff.confidence == "physical"


def test_class_one_aged_forever_is_unchanged():
    """Class I is a linear dielectric: 100 kh of ageing costs nothing."""
    retention, confidence = m.ageing_retention(100_000.0, "C0G")
    assert retention == 1.0
    assert confidence == "physical"


# --------------------------------------------------------------------------- #
# The factor stack multiplies
# --------------------------------------------------------------------------- #


def test_factors_multiply_to_the_reported_retention():
    eff = m.effective_capacitance(
        marked_capacitance_uf=10.0,
        rated_v=6.3,
        applied_v=5.0,
        case_size="0603",
        dielectric="X5R",
        ambient_c=70.0,
        hours_in_service=10000.0,
        tolerance_pct=10.0,
    )
    product = (
        eff.dc_bias_factor
        * eff.ac_level_factor
        * eff.temperature_factor
        * eff.ageing_factor
        * eff.tolerance_factor
    )
    assert product == pytest.approx(eff.retention_fraction, rel=1e-6)
    assert eff.effective_capacitance_uf == pytest.approx(10.0 * eff.retention_fraction, rel=1e-6)


def test_compounding_loss_is_worse_than_any_single_mechanism():
    """The whole point: individual losses look tolerable, together they are not."""
    eff = m.effective_capacitance(
        marked_capacitance_uf=10.0,
        rated_v=6.3,
        applied_v=5.0,
        case_size="0603",
        dielectric="X5R",
        ambient_c=85.0,
        hours_in_service=87600.0,  # 10 years
        tolerance_pct=20.0,
    )
    worst_single = min(
        eff.dc_bias_factor,
        eff.ac_level_factor,
        eff.temperature_factor,
        eff.ageing_factor,
        eff.tolerance_factor,
    )
    assert eff.retention_fraction < worst_single, (
        "compounded retention must be worse than the worst single factor"
    )
    assert eff.retention_fraction < 0.5


def test_high_bias_fraction_produces_a_derating_warning():
    eff = m.effective_capacitance(10.0, 6.3, 6.0, "0805", "X5R")
    assert any("of rated" in note for note in eff.notes)


def test_low_retention_produces_a_sizing_warning():
    eff = m.effective_capacitance(10.0, 6.3, 6.3, "0402", "Y5V", tolerance_pct=20.0)
    assert eff.retention_fraction < 0.5
    assert any("marked value" in note for note in eff.notes)


# --------------------------------------------------------------------------- #
# Measured input beats the band estimate
# --------------------------------------------------------------------------- #


def test_measured_retention_overrides_the_band_and_flags_confidence():
    eff = m.effective_capacitance(
        marked_capacitance_uf=10.0,
        rated_v=6.3,
        applied_v=5.0,
        case_size="0805",
        dielectric="X5R",
        measured_retention_at_bias=0.62,
        tolerance_pct=0.0,
        ambient_c=25.0,
        hours_in_service=1.0,
        ac_level="large",
    )
    assert eff.dc_bias_factor == pytest.approx(0.62)
    assert eff.confidence == "measured"
    assert any("datasheet curve" in note for note in eff.notes)


def test_band_estimate_is_labelled_band():
    eff = m.effective_capacitance(10.0, 6.3, 5.0, "0805", "X5R")
    assert eff.confidence == "band"
    assert any("BAND estimate" in note for note in eff.notes)


def test_out_of_range_measured_retention_is_rejected():
    with pytest.raises(m.MLCCModelError):
        m.effective_capacitance(10.0, 6.3, 5.0, measured_retention_at_bias=1.5)
    with pytest.raises(m.MLCCModelError):
        m.effective_capacitance(10.0, 6.3, 5.0, measured_retention_at_bias=0.0)


# --------------------------------------------------------------------------- #
# Brown-out hold-up: the case that ships broken
# --------------------------------------------------------------------------- #


def test_hold_up_arithmetic_matches_the_reference_task():
    """EEBench energy-meter task: 5 V collapsing to a 3 V floor for 20 ms.

    The published reference answer is 545 µF effective on a 93 Ω load. This is
    the constant-current arithmetic I·t/ΔV, so it is checkable by hand:
    5/93 A × 20 ms / 2 V = 537.6 µF.
    """
    result = m.hold_up_capacitance(
        load_current_ma=5.0 / 93.0 * 1000.0,
        v_start=5.0,
        v_floor=3.0,
        required_hold_time_ms=20.0,
        rated_v=6.3,
        case_size="0805",
        dielectric="X5R",
        hours_in_service=1000.0,
    )
    assert result.required_capacitance_uf == pytest.approx(537.6, abs=1.0)
    # The reference answer is ~545 µF; we are within 2% and slightly conservative.
    assert abs(result.required_capacitance_uf - 545.0) / 545.0 < 0.02


def test_hold_up_reports_a_marked_value_larger_than_the_effective_need():
    """The gap between the two numbers is the bug that ships."""
    result = m.hold_up_capacitance(
        load_current_ma=53.8,
        v_start=5.0,
        v_floor=3.0,
        required_hold_time_ms=20.0,
        rated_v=6.3,
        case_size="0805",
        dielectric="X5R",
    )
    assert result.marked_capacitance_uf > result.required_capacitance_uf
    # Retention under 5 V on a 6.3 V part is severe, so the multiplier is large.
    assert result.marked_capacitance_uf > 3 * result.required_capacitance_uf


def test_hold_up_that_meets_the_spec_passes():
    result = m.hold_up_capacitance(10.0, 5.0, 3.0, 5.0, rated_v=16.0, dielectric="X7R")
    assert result.passes is True
    assert result.margin_ms >= 0


def test_hold_up_defaults_rated_voltage_to_twice_the_start():
    result = m.hold_up_capacitance(10.0, 5.0, 3.0, 20.0)
    assert any("rated_v defaulted" in note for note in result.notes)
    # 2× 5 V = 10 V, above the 6.3 V minimum.
    assert "10.0 V" in " ".join(result.notes)


def test_hold_up_rejects_a_floor_above_the_start():
    with pytest.raises(m.MLCCModelError, match="headroom"):
        m.hold_up_capacitance(10.0, 3.0, 5.0, 20.0)


def test_hold_up_rejects_non_positive_current():
    with pytest.raises(m.MLCCModelError):
        m.hold_up_capacitance(0.0, 5.0, 3.0, 20.0)


# --------------------------------------------------------------------------- #
# RC filter drift
# --------------------------------------------------------------------------- #


def test_rc_filter_drift_is_reported_and_directional():
    """A biased Class II part loses capacitance, so the cutoff rises."""
    result = m.rc_cutoff_with_effective_c(
        r_ohm=1000.0,
        marked_c_uf=10.0,
        rated_v=6.3,
        applied_v=5.0,
        case_size="0805",
        dielectric="X5R",
    )
    assert result["actual_cutoff_hz"] > result["nominal_cutoff_hz"]
    assert result["drift_pct"] > 0
    assert result["effective_capacitance_uf"] < 10.0


def test_rc_filter_with_class_one_has_no_drift():
    """Class I has no bias/ageing/temperature loss, so the cutoff does not move."""
    result = m.rc_cutoff_with_effective_c(
        r_ohm=1000.0,
        marked_c_uf=10.0,
        rated_v=50.0,
        applied_v=25.0,
        dielectric="C0G",
    )
    # Tolerance defaults to 0 here: this helper isolates the operating-condition
    # effect, so a Class I part has exactly zero drift.
    assert result["drift_pct"] == pytest.approx(0.0, abs=1e-6)
    assert result["tolerance_included"] is False


def test_rc_filter_tolerance_can_be_added_explicitly():
    """Opting into tolerance moves the cutoff even for a Class I part."""
    result = m.rc_cutoff_with_effective_c(
        r_ohm=1000.0,
        marked_c_uf=10.0,
        rated_v=50.0,
        applied_v=25.0,
        dielectric="C0G",
        tolerance_pct=10.0,
    )
    assert result["drift_pct"] > 5.0
    assert result["tolerance_included"] is True


# --------------------------------------------------------------------------- #
# Tolerance corners
# --------------------------------------------------------------------------- #


def test_tolerance_corners_are_symmetric_around_nominal():
    corners = m.capacitance_tolerance_corners(10e-6, 10.0)
    assert corners["min_f"] == pytest.approx(9e-6)
    assert corners["max_f"] == pytest.approx(11e-6)
    assert corners["spread_pct"] == pytest.approx(20.0)


def test_tolerance_corners_reject_impossible_bands():
    with pytest.raises(m.MLCCModelError):
        m.capacitance_tolerance_corners(10e-6, 100.0)
    with pytest.raises(m.MLCCModelError):
        m.capacitance_tolerance_corners(0.0, 10.0)


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


def test_unknown_dielectric_is_rejected():
    with pytest.raises(m.MLCCModelError, match="Unknown dielectric"):
        m.effective_capacitance(10.0, 6.3, 5.0, dielectric="X9Z")


def test_negative_applied_voltage_is_rejected():
    with pytest.raises(m.MLCCModelError):
        m.dc_bias_retention(-1.0, 6.3, "0805", "X5R")


def test_temperature_above_the_dielectric_limit_is_rejected():
    with pytest.raises(m.MLCCModelError, match="rated to"):
        m.temperature_retention(100.0, "X5R")  # X5R tops out at 85 °C


def test_x7r_survives_a_temperature_x5r_cannot():
    """X7R to 125 °C, X5R to 85 °C — the difference that picks the part."""
    with pytest.raises(m.MLCCModelError):
        m.temperature_retention(100.0, "X5R")
    retention, _ = m.temperature_retention(100.0, "X7R")
    assert 0.8 < retention < 1.0


def test_unknown_case_size_falls_back_rather_than_failing():
    retention, confidence = m.dc_bias_retention(5.0, 6.3, "9999", "X5R")
    assert 0.0 < retention < 1.0
    assert confidence == "band"


# --------------------------------------------------------------------------- #
# MCP tool wiring
# --------------------------------------------------------------------------- #


def _call(name: str, arguments: dict) -> dict:
    import json

    result = handle_tool_call(name, arguments)
    assert not result.get("isError"), result.get("content")
    return json.loads(result["content"][0]["text"])


def test_mcp_tool_effective_capacitance():
    data = _call(
        "calculate_effective_capacitance",
        {"marked_capacitance_uf": 22.0, "rated_v": 6.3, "applied_v": 4.7, "case_size": "0805"},
    )
    assert data["effective_capacitance_uf"] < 22.0
    assert "dc_bias_factor" in data
    assert "confidence" in data


def test_mcp_tool_hold_up():
    data = _call(
        "size_hold_up_capacitor",
        {
            "load_current_ma": 53.8,
            "v_start": 5.0,
            "v_floor": 3.0,
            "required_hold_time_ms": 20.0,
            "rated_v": 6.3,
        },
    )
    assert data["required_capacitance_uf"] == pytest.approx(537.6, abs=1.0)
    assert data["marked_capacitance_uf"] > data["required_capacitance_uf"]


def test_mcp_tool_rc_filter():
    data = _call(
        "analyze_rc_filter_effective",
        {"r_ohm": 1000.0, "marked_c_uf": 10.0, "rated_v": 6.3, "applied_v": 5.0},
    )
    assert data["actual_cutoff_hz"] > data["nominal_cutoff_hz"]


def test_mcp_tools_are_read_only_and_declared():
    """Every new tool must be in the declarative catalogue with full annotations."""
    from client.mcp_schema import AVAILABLE_TOOLS

    names = {t["name"] for t in AVAILABLE_TOOLS}
    for tool in (
        "calculate_effective_capacitance",
        "size_hold_up_capacitor",
        "analyze_rc_filter_effective",
    ):
        assert tool in names, f"{tool} missing from AVAILABLE_TOOLS"
        decl = next(t for t in AVAILABLE_TOOLS if t["name"] == tool)
        assert decl["annotations"]["readOnlyHint"] is True
        assert decl["annotations"]["openWorldHint"] is False
