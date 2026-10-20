"""Tolerance analysis for passive networks: what the design does at its corners.

Why this module exists
----------------------
:func:`client.parametric_equations.solve_resistor_divider` returns the *nominal*
output of an optimal E96 pair. Nominal is not a specification. A ±1% divider on a
3.3 V rail produces a tolerance band, and that band is what an ADC sees, what a
comparator trips on, and what a regulator regulates to. Reporting only the
nominal is how a "0.05% accurate" divider turns out to be ±2% in production.

Two different questions, two different methods
----------------------------------------------
**Worst case** — every part simultaneously at the corner that hurts most. This is
a hard bound and it is exact for a divider because ``V_out = V_in·R2/(R1+R2)`` is
monotonic in each resistor: the extremes live at the corners, so enumerating four
corners is not an approximation.

**Statistical (RSS)** — the realistic band. For a *sum* of independent
contributions, root-sum-square is standard practice. For a divider it is **not**
valid to RSS the percentage tolerances directly, because the output is a quotient
of random variables, not a sum — this is stated explicitly in TI's application
note on output-voltage tolerance and is the mistake this module avoids. What *is*
valid is first-order sensitivity propagation: linearise the output around nominal
using the analytic partial derivatives, then RSS the resulting *voltage*
contributions. The perturbation is small (±1%), so the linearisation holds, and
the method stays correct for products and quotients where naive RSS does not.

Both are reported. Worst case is what you must survive; RSS is what you will
typically see. Presenting only one of them is the other half of the mistake.

Resistor error model
--------------------
A resistor's value at end of life is not its marked value. Four independent
contributions, per Analog Devices' signal-chain error model:

1. **Value tolerance** — the marked ±% at 25 °C.
2. **Temperature coefficient** — ppm/°C × the temperature excursion.
3. **Life drift** — a % over a stated number of hours. Scaling it linearly to a
   longer life is far too pessimistic (random walk, not a ramp), so the drift
   grows with the *square root* of the time ratio, per the same reference.
4. **Ratio tolerance** — for parts in one package (a divider network, a matched
   pair), the *ratio* is far better than the absolute values. This is the single
   biggest win available and it is routinely left on the table.

References
----------
- TI SNVA112 "Method For Calculating Output Voltage Tolerances in Adjustable
  Regulators" — worst-case vs RSS, and why RSS is invalid for a quotient.
- Analog Devices "An Inside Look at High-Speed ADC Accuracy Part 3" — the
  four-term resistor error model and the sqrt-of-time life-drift rule.
- Analog Devices AN-1344 — RSS of three 1% resistors gives 1.73%, not 3%.
- Allegro AN296255 — E96/E24 combined-series divider selection and feedback
  bias-current error.

Zero third-party runtime dependencies: Python standard library only.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

#: Common resistor tolerance grades, as percentages.
TOLERANCE_GRADES: dict[str, float] = {
    "0.01%": 0.01,
    "0.05%": 0.05,
    "0.1%": 0.1,
    "0.25%": 0.25,
    "0.5%": 0.5,
    "1%": 1.0,
    "2%": 2.0,
    "5%": 5.0,
}

#: Typical temperature coefficient of resistance, ppm/°C, by technology. Thick
#: film is the cheap default and the one that quietly dominates a "1% accurate"
#: divider over temperature: 200 ppm/°C × 60 °C excursion = 1.2%, more than the
#: tolerance it was bought for.
TCR_PPM_PER_C: dict[str, float] = {
    "thick_film": 200.0,
    "thin_film": 25.0,
    "precision_thin_film": 10.0,
    "wirewound": 20.0,
    "metal_foil": 2.0,
}


class ToleranceError(ValueError):
    """Raised when a tolerance request is physically meaningless."""


def resistor_value_band(
    nominal_ohm: float,
    tolerance_pct: float = 1.0,
    tcr_ppm_per_c: float = 0.0,
    delta_temp_c: float = 0.0,
    life_drift_pct: float = 0.0,
    life_hours_specified: float = 1000.0,
    life_hours_required: float = 1000.0,
) -> dict[str, Any]:
    """End-of-life resistance band for one resistor.

    Returns ``min_ohm`` / ``max_ohm`` and the individual contributions in
    percent, so a caller can see whether tolerance, temperature or life drift is
    the dominant term. That ordering is the whole point of running the numbers:
    a 1% thin-film part at 25 ppm/°C is dominated by its tolerance, while a 1%
    thick-film part at 200 ppm/°C over a 60 °C excursion is dominated by its TCR
    and buying the tighter tolerance was money spent on the wrong parameter.

    ``life_drift_pct`` scales with the square root of the time ratio, not
    linearly — long-term drift is a random walk.
    """
    if nominal_ohm <= 0:
        raise ToleranceError("nominal_ohm must be positive")
    if tolerance_pct < 0:
        raise ToleranceError("tolerance_pct must be non-negative")
    if life_hours_specified <= 0 or life_hours_required <= 0:
        raise ToleranceError("life hours must be positive")

    tol_pct = tolerance_pct
    tcr_pct = (tcr_ppm_per_c * 1e-6) * abs(delta_temp_c) * 100.0

    if life_drift_pct > 0:
        # sqrt-of-time, per the ADI reference: 1000 h -> 10 kh is ×3.16, not ×10.
        life_pct = life_drift_pct * math.sqrt(life_hours_required / life_hours_specified)
    else:
        life_pct = 0.0

    # These are independent random variables, so they RSS. Direct summation
    # would be the pessimistic "everything at once" bound; RSS is what a
    # population actually looks like. Both are returned because which one you
    # need depends on whether you are qualifying a lot or designing a limit.
    rss_pct = math.sqrt(tol_pct**2 + tcr_pct**2 + life_pct**2)
    sum_pct = tol_pct + tcr_pct + life_pct

    min_ohm = nominal_ohm * (1.0 - rss_pct / 100.0)
    max_ohm = nominal_ohm * (1.0 + rss_pct / 100.0)
    worst_min = nominal_ohm * (1.0 - sum_pct / 100.0)
    worst_max = nominal_ohm * (1.0 + sum_pct / 100.0)

    return {
        "nominal_ohm": nominal_ohm,
        "min_ohm": round(min_ohm, 6),
        "max_ohm": round(max_ohm, 6),
        "worst_case_min_ohm": round(worst_min, 6),
        "worst_case_max_ohm": round(worst_max, 6),
        "tolerance_pct": round(tol_pct, 6),
        "tcr_pct": round(tcr_pct, 6),
        "life_drift_pct": round(life_pct, 6),
        "rss_total_pct": round(rss_pct, 6),
        "linear_total_pct": round(sum_pct, 6),
        "dominant_term": max(
            (("tolerance", tol_pct), ("tcr", tcr_pct), ("life_drift", life_pct)),
            key=lambda kv: kv[1],
        )[0],
    }


@dataclass(frozen=True)
class DividerToleranceResult:
    """Output voltage band of a two-resistor divider."""

    v_in: float
    v_out_nominal: float
    r1_ohm: float
    r2_ohm: float
    # Absolute bounds, in volts. These are what a downstream part sees.
    v_out_min: float
    v_out_max: float
    v_out_worst_min: float
    v_out_worst_max: float
    # The same bounds as a percentage of nominal.
    error_rss_pct: float
    error_worst_pct: float
    # Which resistor dominates the error budget.
    dominant_resistor: str
    sensitivity_r1: float
    sensitivity_r2: float
    method: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def divider_tolerance(
    v_in: float,
    r1_ohm: float,
    r2_ohm: float,
    tolerance_pct: float = 1.0,
    tcr_ppm_per_c: float = 0.0,
    delta_temp_c: float = 0.0,
    life_drift_pct: float = 0.0,
    ratio_tolerance_pct: float | None = None,
    v_in_tolerance_pct: float = 0.0,
) -> DividerToleranceResult:
    """Tolerance band of ``V_out = V_in · R2/(R1+R2)``.

    Two methods, both reported:

    * **Worst case** — enumerate the four resistor corners (R1 min/max × R2
      min/max). Exact, because the transfer function is monotonic in each
      resistor. This is the bound the design must survive.
    * **RSS** — first-order sensitivity propagation. The analytic partials are
      ``∂V/∂R1 = −V_in·R2/(R1+R2)²`` and ``∂V/∂R2 = +V_in·R1/(R1+R2)²``; each
      resistor's uncertainty is converted to a *voltage* contribution through its
      sensitivity, and the contributions are RSS'd. This is the method that stays
      valid for a quotient, where RSS-ing the percentage tolerances directly does
      not (TI SNVA112).

    Args:
        ratio_tolerance_pct: When the two resistors are a matched pair in one
            package, their *ratio* tolerance is much tighter than their absolute
            tolerance. Supplying it replaces both absolute tolerances for the
            ratio term — the single biggest accuracy win available, and free.
        v_in_tolerance_pct: Supply tolerance. Included as an independent
            contribution because the output scales with it directly.
    """
    if r1_ohm <= 0 or r2_ohm <= 0:
        raise ToleranceError("r1_ohm and r2_ohm must be positive")
    if v_in <= 0:
        raise ToleranceError("v_in must be positive")

    total = r1_ohm + r2_ohm
    v_out = v_in * r2_ohm / total

    band1 = resistor_value_band(
        r1_ohm,
        tolerance_pct,
        tcr_ppm_per_c,
        delta_temp_c,
        life_drift_pct,
    )
    band2 = resistor_value_band(
        r2_ohm,
        tolerance_pct,
        tcr_ppm_per_c,
        delta_temp_c,
        life_drift_pct,
    )

    # --- Exact worst case: the transfer function is monotonic in each part --- #
    # V_out rises with R2 and falls with R1, so the max is (R1 min, R2 max).
    v_max = v_in * band2["worst_case_max_ohm"] / (band1["worst_case_min_ohm"] + band2["worst_case_max_ohm"])
    v_min = v_in * band2["worst_case_min_ohm"] / (band1["worst_case_max_ohm"] + band2["worst_case_min_ohm"])

    # --- First-order sensitivity propagation (valid for a quotient) --------- #
    # dV/dR1 = -V_in * R2 / (R1+R2)^2 ;  dV/dR2 = +V_in * R1 / (R1+R2)^2
    sens_r1 = -v_in * r2_ohm / (total**2)
    sens_r2 = v_in * r1_ohm / (total**2)

    # Uncertainty in each resistor, in ohms, at the RSS band.
    d_r1 = r1_ohm * band1["rss_total_pct"] / 100.0
    d_r2 = r2_ohm * band2["rss_total_pct"] / 100.0

    contrib_r1 = abs(sens_r1) * d_r1
    contrib_r2 = abs(sens_r2) * d_r2

    if ratio_tolerance_pct is not None:
        # A matched pair: the ratio is specified directly, so the ratio error is
        # ratio_tolerance_pct of the ratio, and the output error follows.
        if ratio_tolerance_pct < 0:
            raise ToleranceError("ratio_tolerance_pct must be non-negative")
        contrib_ratio = v_out * ratio_tolerance_pct / 100.0
        # Replace both resistor contributions with the single ratio term.
        rss_voltage = math.sqrt(contrib_ratio**2 + (v_out * v_in_tolerance_pct / 100.0) ** 2)
        contrib_r1 = contrib_ratio
        contrib_r2 = 0.0
        notes_ratio = [
            (
                f"Matched pair: ratio tolerance ±{ratio_tolerance_pct}% replaces the "
                f"±{tolerance_pct}% absolute tolerances — the ratio is what sets the output"
            )
        ]
    else:
        v_in_contrib = v_out * v_in_tolerance_pct / 100.0
        rss_voltage = math.sqrt(contrib_r1**2 + contrib_r2**2 + v_in_contrib**2)
        notes_ratio = []

    v_rss_min = v_out - rss_voltage
    v_rss_max = v_out + rss_voltage

    notes: list[str] = list(notes_ratio)
    notes.append(
        f"Worst case ±{abs(v_max - v_out) / v_out * 100:.2f}% assumes every part at "
        f"its worst corner simultaneously; RSS ±{rss_voltage / v_out * 100:.2f}% is "
        "what a production population looks like"
    )
    if tcr_ppm_per_c > 0 and delta_temp_c != 0:
        tcr_pct = (tcr_ppm_per_c * 1e-6) * abs(delta_temp_c) * 100.0
        if tcr_pct > tolerance_pct:
            notes.append(
                f"TCR contributes {tcr_pct:.2f}% over {delta_temp_c} °C — more than the "
                f"±{tolerance_pct}% tolerance itself. Buying a tighter tolerance grade "
                "would not help; a lower-TCR technology would"
            )
    if abs(v_max - v_out) / v_out > 0.05:
        notes.append(
            f"Worst-case error {abs(v_max - v_out) / v_out:.1%} exceeds 5% — "
            "consider a matched pair or a lower-TCR grade"
        )

    dominant = "r1" if contrib_r1 >= contrib_r2 else "r2"

    return DividerToleranceResult(
        v_in=round(v_in, 6),
        v_out_nominal=round(v_out, 9),
        r1_ohm=round(r1_ohm, 6),
        r2_ohm=round(r2_ohm, 6),
        v_out_min=round(v_rss_min, 9),
        v_out_max=round(v_rss_max, 9),
        v_out_worst_min=round(v_min, 9),
        v_out_worst_max=round(v_max, 9),
        error_rss_pct=round(rss_voltage / v_out * 100.0, 4),
        error_worst_pct=round(max(abs(v_max - v_out), abs(v_out - v_min)) / v_out * 100.0, 4),
        dominant_resistor=dominant,
        sensitivity_r1=round(sens_r1, 12),
        sensitivity_r2=round(sens_r2, 12),
        method="worst_case_corner_enumeration + first_order_sensitivity_rss",
        notes=notes,
    )


def divider_ratio_for_target(
    v_out: float,
    v_ref: float,
    r_total_ohm: float = 100_000.0,
) -> dict[str, Any]:
    """Exact R1/R2 pair for a feedback divider, and the error the E96 snap adds.

    ``V_out = V_ref·(R1+R2)/R2`` for the usual regulator topology with the
    reference at the midpoint. The ideal pair almost never exists in E96, so the
    snap error is a real, static offset that must be budgeted — TI calls this out
    explicitly, and it is routinely forgotten because it is not a tolerance at
    all, it is a wrongness.
    """
    if v_ref <= 0 or v_out <= v_ref:
        raise ToleranceError("v_out must exceed v_ref, both positive")
    if r_total_ohm <= 0:
        raise ToleranceError("r_total_ohm must be positive")

    ratio = v_out / v_ref  # = (R1+R2)/R2
    r2_ideal = r_total_ohm / ratio
    r1_ideal = r_total_ohm - r2_ideal

    from .parametric_equations import snap_to_e_series

    r2_snap = snap_to_e_series(r2_ideal, "E96")
    r1_snap = snap_to_e_series(r1_ideal, "E96")
    v_out_actual = v_ref * (r1_snap + r2_snap) / r2_snap
    snap_error_pct = (v_out_actual - v_out) / v_out * 100.0

    return {
        "v_out_target": v_out,
        "v_ref": v_ref,
        "r1_ohm": r1_snap,
        "r2_ohm": r2_snap,
        "v_out_actual": round(v_out_actual, 6),
        "snap_error_pct": round(snap_error_pct, 4),
        "note": (
            "Snap error is a static offset, not a tolerance: it is the same on "
            "every board. Budget it separately from the tolerance band."
        ),
    }


def required_tolerance_grade(
    target_error_pct: float,
    contributions_pct: list[float],
) -> dict[str, Any]:
    """Which tolerance grade can meet an error target, given other contributions.

    Solves ``target² = other² + x²`` for the tolerance term ``x``, then picks the
    tightest standard grade that fits. Returns the grade and the headroom left.

    If the other contributions alone already exceed the target, no tolerance
    grade can save the design and this says so instead of returning a grade that
    cannot work.
    """
    if target_error_pct <= 0:
        raise ToleranceError("target_error_pct must be positive")
    if any(c < 0 for c in contributions_pct):
        raise ToleranceError("contributions must be non-negative")

    other_rss = math.sqrt(sum(c**2 for c in contributions_pct))
    if other_rss >= target_error_pct:
        return {
            "feasible": False,
            "other_contributions_rss_pct": round(other_rss, 4),
            "target_pct": target_error_pct,
            "reason": (
                f"Other error sources already contribute {other_rss:.3f}% RSS, at or above "
                f"the {target_error_pct}% target — no tolerance grade can meet it. "
                "Reduce a different term first."
            ),
            "recommended_grade": None,
            "max_allowed_tolerance_pct": 0.0,
        }

    allowed = math.sqrt(target_error_pct**2 - other_rss**2)
    # Pick the tightest grade that is still ≥ allowed, i.e. the cheapest that works.
    fitting = [
        (name, pct) for name, pct in sorted(TOLERANCE_GRADES.items(), key=lambda kv: kv[1]) if pct <= allowed
    ]
    if not fitting:
        return {
            "feasible": False,
            "other_contributions_rss_pct": round(other_rss, 4),
            "target_pct": target_error_pct,
            "reason": (
                f"Only {allowed:.4f}% of the budget is left for tolerance, below the "
                "tightest standard grade (0.01%). Use a matched pair or trim."
            ),
            "recommended_grade": None,
            "max_allowed_tolerance_pct": round(allowed, 4),
        }

    grade, grade_pct = fitting[-1]  # loosest that still fits = cheapest
    total = math.sqrt(other_rss**2 + grade_pct**2)
    return {
        "feasible": True,
        "other_contributions_rss_pct": round(other_rss, 4),
        "target_pct": target_error_pct,
        "max_allowed_tolerance_pct": round(allowed, 4),
        "recommended_grade": grade,
        "recommended_tolerance_pct": grade_pct,
        "resulting_total_rss_pct": round(total, 4),
        "headroom_pct": round(target_error_pct - total, 4),
    }


def tcr_penalty_over_temperature(
    tolerance_pct: float,
    tcr_ppm_per_c: float,
    delta_temp_c: float,
) -> dict[str, Any]:
    """Whether TCR or tolerance dominates a resistor's error, over temperature.

    The practical question behind this function: a designer buys a ±0.1% part to
    fix an accuracy problem, and it does nothing because the 200 ppm/°C thick-film
    TCR already contributes 1.2% over a 60 °C excursion. Answering "which term
    dominates" before spending money is cheaper than a respin.
    """
    tcr_pct = (tcr_ppm_per_c * 1e-6) * abs(delta_temp_c) * 100.0
    if tcr_pct == 0 and tolerance_pct == 0:
        return {
            "tcr_pct": 0.0,
            "tolerance_pct": 0.0,
            "dominant": "none",
            "recommendation": "No error sources specified.",
        }

    if tcr_pct > tolerance_pct * 2:
        dominant = "tcr"
        recommendation = (
            f"TCR contributes {tcr_pct:.2f}% vs {tolerance_pct:.2f}% tolerance. "
            "Buying a tighter tolerance grade would waste money — switch to a "
            "lower-TCR technology (thin film, metal foil)."
        )
    elif tolerance_pct > tcr_pct * 2:
        dominant = "tolerance"
        recommendation = (
            f"Tolerance contributes {tolerance_pct:.2f}% vs {tcr_pct:.2f}% TCR. "
            "A tighter grade will help; TCR is not the limiting term here."
        )
    else:
        dominant = "comparable"
        recommendation = (
            f"TCR ({tcr_pct:.2f}%) and tolerance ({tolerance_pct:.2f}%) are comparable. "
            "Improving only one will not move the total much — RSS says you get "
            "about 30% for halving either."
        )

    return {
        "tcr_pct": round(tcr_pct, 6),
        "tolerance_pct": round(tolerance_pct, 6),
        "dominant": dominant,
        "combined_rss_pct": round(math.sqrt(tcr_pct**2 + tolerance_pct**2), 6),
        "recommendation": recommendation,
    }
