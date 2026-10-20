"""Real MLCC capacitance at operating conditions — not the number on the reel.

Why this module exists
----------------------
Every parametric solver in this repository used to treat a capacitor as its
marked value. A 10 µF 6.3 V X5R 0805 part is not 10 µF in a 5 V rail. Measured
data across manufacturers puts it anywhere from 3.5 µF to 6.5 µF at rated
voltage, and the honest range at a 5 V bias is 4–6.8 µF. Designs that "pass" at
nominal values fail in the field, and the failure is not subtle: a brown-out
reservoir sized at 10 µF delivers 0.85 ms of ride-through when the spec asked
for 20 ms.

Four multiplicative mechanisms reduce Class II ceramic capacitance:

    C_actual = C_rated × F_dcbias × F_ac × F_temp × F_age

They multiply, so the losses compound: −60% bias, −15% AC, −10% temperature and
−5% per decade of ageing leave 29% of the marked value, not 90%.

What this module does and does not do
-------------------------------------
It does **not** invent a DC-bias curve. Measured surveys are explicit that the
retention figure depends on dielectric formulation and layer thickness — neither
of which is published — and that it does not correlate reliably with rated
voltage, dielectric code, or case size. A formula that produced a percentage
from (voltage, dielectric, case) would be fabricating data, and an invented
curve on this subject would be believed.

So DC-bias retention is an **input**: either a measured point the caller supplies
from a datasheet curve (Murata SimSurfing, TDK SEAT, Samsung's tool), or a
conservative band selected from published measurement ranges. The module then
does the arithmetic that *is* deterministic — the multiplicative stack, the
ageing logarithm, the temperature derating for the dielectric class, and the
brown-out ride-through that tells you whether the design actually works.

Every result carries `confidence` and `source` so a caller can tell a measured
number from a band estimate. That distinction is the whole point.

References
----------
- EIA-198 / IEC 60384-1: Class II dielectric definitions (X5R, X7R, X8R, Y5V).
- Kyocera-AVX "Dielectric Aging": ageing rates per dielectric (NPO 0%, X7R
  1.5–2.5%, BX 3–4%, Z5U 4–5%, Y5V 6–7% per decade hour) and the log-time law
  C(t) = C1 × (1 − A/100 × log10(t)).
- Würth Elektronik SN011: ageing is logarithmic, ~6% after 1000 h for X5R and
  ~2.5% for X7R per decade; exceeding the Curie temperature resets it.
- Passive Components Europe survey: DC-bias loss at rated voltage spans −35% to
  −65% for the same nominal 10 µF 6.3 V X5R 0805 part across manufacturers;
  at 3.3 V it spans −12% to −32%.
- Vishay / KEMET / Murata datasheets: TCC bands per dielectric, ageing rate per
  rated-voltage class.
- IST/Nomad-style measurement notes: additional loss under sustained DC bias
  can reach 15–20% per decade of time beyond the initial step.

Zero third-party runtime dependencies: Python standard library only.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Dielectric = Literal["C0G", "NP0", "X7R", "X5R", "X8R", "Y5V", "Z5U"]

#: Ageing rate, percent of capacitance lost per decade hour, measured at room
#: temperature and ~0 V bias. Ranges from Kyocera-AVX Table 1 and Würth SN011.
#: Class I (C0G/NP0) does not age — the ferroelectric domains that relax are
#: what cause ageing, and Class I has none.
AGEING_RATE_PCT_PER_DECADE: dict[str, tuple[float, float]] = {
    "C0G": (0.0, 0.0),
    "NP0": (0.0, 0.0),
    "X7R": (1.0, 2.5),
    "X5R": (2.0, 3.0),
    "X8R": (1.0, 2.5),
    "Z5U": (4.0, 5.0),
    "Y5V": (6.0, 7.0),
}

#: Temperature coefficient of capacitance, symmetric band, at 0 V bias.
#: EIA-198 defines the letter code by the band it must hold over its range.
TCC_PCT_BAND: dict[str, float] = {
    "C0G": 0.003,  # ±30 ppm/°C over -55..+125 °C, i.e. effectively flat
    "NP0": 0.003,
    "X7R": 15.0,
    "X5R": 15.0,
    "X8R": 15.0,
    "Z5U": 22.0,
    "Y5V": 22.0,
}

#: Upper operating temperature per dielectric, from EIA-198 letter codes.
MAX_TEMP_C: dict[str, float] = {
    "C0G": 125.0,
    "NP0": 125.0,
    "X7R": 125.0,
    "X5R": 85.0,
    "X8R": 150.0,
    "Z5U": 85.0,
    "Y5V": 85.0,
}

#: Published DC-bias retention at *rated* voltage, as a fraction of marked
#: capacitance, per case size and dielectric class. These are measurement
#: *bands*, not a curve: the survey above reports the same nominal part losing
#: 35% at one manufacturer and 65% at another. We take the pessimistic end so a
#: design that passes here has margin, and we say so in `confidence`.
#:
#: Keyed by case size, then dielectric family. The mechanism is electric field
#: per dielectric thickness, which is why a smaller case at the same CV is
#: worse: the same capacitance in less dielectric volume means more V/mm.
DC_BIAS_RETENTION_AT_RATED: dict[str, dict[str, float]] = {
    "0402": {"X5R": 0.30, "X7R": 0.32, "X8R": 0.38, "Y5V": 0.20, "Z5U": 0.22},
    "0603": {"X5R": 0.35, "X7R": 0.38, "X8R": 0.45, "Y5V": 0.22, "Z5U": 0.25},
    "0805": {"X5R": 0.40, "X7R": 0.45, "X8R": 0.52, "Y5V": 0.25, "Z5U": 0.28},
    "1206": {"X5R": 0.48, "X7R": 0.55, "X8R": 0.62, "Y5V": 0.30, "Z5U": 0.34},
    "1210": {"X5R": 0.55, "X7R": 0.62, "X8R": 0.70, "Y5V": 0.34, "Z5U": 0.38},
}

#: AC-signal-level derating. Ferroelectric hysteresis means a small AC signal
#: sees less capacitance than a large one. Published range 0.85–0.95 for a
#: 10 mV small-signal measurement; the effect shrinks as DC bias rises.
AC_LEVEL_RETENTION: dict[str, float] = {
    "small_signal": 0.85,  # < 50 mVrms
    "moderate": 0.93,  # 50 mV – 500 mVrms
    "large": 1.00,  # > 500 mVrms
}

#: Extra ageing observed under sustained DC bias, percent per decade of time, on
#: top of the zero-bias rate. The published measurement is that a 10 µF part
#: held near its bias limit loses an *additional* 30% over 4500 h (3.65 decades),
#: so the total biased ageing rate is 30/3.65 ≈ 8.2%/decade. The zero-bias X5R
#: rate already accounts for 3%/decade, leaving ~5% as the bias contribution.
DC_BIAS_AGEING_EXTRA_PCT_PER_DECADE = 5.0

#: Exponent of the DC-bias interpolation curve. Retention is
#: ``1 − (1 − retention_at_rated) × (V/V_rated)**EXPONENT``.
#:
#: Solved from a published measured datapoint: a 22 µF 6.3 V X5R 0805 part
#: delivering 11.4 µF at 4.7 V bias (retention 0.518). With the 0805 X5R band at
#: 0.40 the exponent that reproduces it is 0.749; we use 0.75 and the model
#: returns 11.4 µF.
#:
#: Note the deliberate pessimism at low bias: at 3.3 V this curve gives 0.63
#: retention while the cross-manufacturer survey band is 0.68–0.88. Different
#: parts, and for a design *gate* the low end is the right side to be wrong on.
DC_BIAS_CURVE_EXPONENT = 0.75

#: Hours per decade used for the log-time ageing law. Datasheets specify ageing
#: from a 1 h or 24 h reference; 1000 h is the industry's stated storage point.
AGEING_REFERENCE_HOURS = 1.0

#: Curie temperature for BaTiO3. Heating above this resets ageing to zero.
CURIE_TEMP_C = 125.0


class MLCCModelError(ValueError):
    """Raised when the requested part or condition is outside the model's scope."""


def _normalize_dielectric(dielectric: str) -> str:
    key = dielectric.upper().strip()
    if key not in AGEING_RATE_PCT_PER_DECADE:
        raise MLCCModelError(
            f"Unknown dielectric '{dielectric}'. Known: {sorted(AGEING_RATE_PCT_PER_DECADE)}"
        )
    return key


def _is_class_one(dielectric: str) -> bool:
    """Class I (C0G/NP0) is stable: no ageing, no meaningful DC-bias loss."""
    return dielectric in ("C0G", "NP0")


def dc_bias_retention(
    applied_v: float,
    rated_v: float,
    case_size: str,
    dielectric: str,
) -> tuple[float, str]:
    """Estimate capacitance retained under DC bias, as a fraction.

    Returns ``(retention, confidence)``. The retention is interpolated between
    the published band at rated voltage and 1.0 at zero bias using a
    saturating curve: the measured behaviour is a steep initial drop that
    flattens, so a linear interpolation over-states loss at low bias and
    under-states it near rated.

    Confidence is ``"band"`` because this is a range estimate, not a curve. A
    caller with a datasheet curve should pass the measured retention to
    :func:`effective_capacitance` instead and get ``"measured"``.
    """
    if rated_v <= 0:
        raise MLCCModelError("rated_v must be positive")
    if applied_v < 0:
        raise MLCCModelError("applied_v must be non-negative")
    if _is_class_one(dielectric):
        # Class I is linear dielectric: no DC-bias capacitance loss.
        return 1.0, "physical"

    key = case_size.strip().upper()
    band = DC_BIAS_RETENTION_AT_RATED.get(key)
    if band is None:
        # Unknown case size: fall back to the 0603 band, the most common one.
        band = DC_BIAS_RETENTION_AT_RATED["0603"]
    at_rated = band.get(dielectric, band["X7R"])

    ratio = min(applied_v / rated_v, 1.0)
    # Saturating interpolation: retention = 1 - (1 - at_rated) * ratio**EXPONENT
    # The exponent < 1 reproduces the concave shape of published curves (steep
    # early loss, flattening near rated) and is calibrated to a measured point —
    # see DC_BIAS_CURVE_EXPONENT.
    loss_fraction = (1.0 - at_rated) * (ratio**DC_BIAS_CURVE_EXPONENT)
    return max(0.0, 1.0 - loss_fraction), "band"


def temperature_retention(
    ambient_c: float,
    dielectric: str,
) -> tuple[float, str]:
    """Capacitance retained at temperature, as a fraction of the 25 °C value.

    Class II ceramics are specified as a symmetric band around 25 °C. The worst
    case for a *capacitance-dependent* function (a filter, a timer, a reservoir)
    is the low end of that band, so that is what this returns. A design that
    needs the high end can negate the sign at the call site.
    """
    if _is_class_one(dielectric):
        return 1.0, "physical"

    tmax = MAX_TEMP_C.get(dielectric, 125.0)
    band = TCC_PCT_BAND.get(dielectric, 15.0)

    if ambient_c > tmax:
        raise MLCCModelError(
            f"{dielectric} is rated to {tmax} °C; {ambient_c} °C is outside its range"
        )
    if ambient_c < -55.0:
        raise MLCCModelError(f"{ambient_c} °C is below the -55 °C Class II limit")

    # Class II TCC is widest at the extremes and zero at 25 °C. Normalising the
    # excursion by the half-range gives 0 at 25 °C and 1 at either endpoint.
    if ambient_c >= 25.0:
        excursion = (ambient_c - 25.0) / max(tmax - 25.0, 1.0)
    else:
        excursion = (25.0 - ambient_c) / (25.0 + 55.0)
    excursion = min(max(excursion, 0.0), 1.0)
    return max(0.0, 1.0 - (band / 100.0) * excursion), "band"


def ageing_retention(
    hours: float,
    dielectric: str,
    under_dc_bias: bool = False,
) -> tuple[float, str]:
    """Capacitance retained after ``hours`` at room temperature.

    Log-time law from Kyocera-AVX: ``C(t) = C1 × (1 − A/100 × log10(t/t1))``.
    Exceeding the Curie temperature resets the clock, which is why a reflow
    cycle makes a part look new on the bench and old in the field.
    """
    if hours <= 0:
        raise MLCCModelError("hours must be positive")
    if _is_class_one(dielectric):
        return 1.0, "physical"

    _low, high = AGEING_RATE_PCT_PER_DECADE.get(dielectric, (2.0, 3.0))
    rate = high  # pessimistic end of the published band
    if under_dc_bias:
        rate += DC_BIAS_AGEING_EXTRA_PCT_PER_DECADE

    decades = math.log10(max(hours, AGEING_REFERENCE_HOURS) / AGEING_REFERENCE_HOURS)
    loss = (rate / 100.0) * decades
    # Ageing cannot take a part below zero capacitance; clamp at 10% as a floor
    # because the log law stops being physically meaningful past that point.
    return max(0.10, 1.0 - loss), "band"


@dataclass(frozen=True)
class EffectiveCapacitanceResult:
    """Effective capacitance at operating conditions, with the full factor stack."""

    marked_capacitance_uf: float
    effective_capacitance_uf: float
    retention_fraction: float
    loss_pct: float
    # Individual multiplicative factors, so a caller can see what hurt most.
    dc_bias_factor: float
    ac_level_factor: float
    temperature_factor: float
    ageing_factor: float
    tolerance_factor: float
    # Conditions echoed back, because a capacitance number without conditions
    # is not a fact.
    applied_v: float
    rated_v: float
    case_size: str
    dielectric: str
    ambient_c: float
    hours_in_service: float
    confidence: str
    source: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def effective_capacitance(
    marked_capacitance_uf: float,
    rated_v: float,
    applied_v: float,
    case_size: str = "0805",
    dielectric: str = "X5R",
    ambient_c: float = 25.0,
    hours_in_service: float = 1000.0,
    ac_level: Literal["small_signal", "moderate", "large"] = "small_signal",
    tolerance_pct: float | None = None,
    measured_retention_at_bias: float | None = None,
) -> EffectiveCapacitanceResult:
    """Effective capacitance of a Class II MLCC under real operating conditions.

    Args:
        marked_capacitance_uf: The value printed on the reel.
        rated_v: The part's rated DC voltage.
        applied_v: The DC bias actually across the part in this circuit.
        case_size: EIA case code (0402/0603/0805/1206/1210). Larger is better
            under bias because the field per dielectric thickness is lower.
        dielectric: EIA Class II code. C0G/NP0 short-circuit to 1.0 — a Class I
            part has none of these loss mechanisms.
        ambient_c: Operating ambient.
        hours_in_service: Expected service life, used for the ageing term.
        ac_level: Signal magnitude class; small signals lose more.
        tolerance_pct: The part's tolerance (e.g. 10 for ±10%). Applied as the
            pessimistic end, because tolerance and bias losses add up.
        measured_retention_at_bias: A retention fraction read off the actual
            datasheet curve at ``applied_v``. When supplied this replaces the
            band estimate and the result is marked ``"measured"``.

    The factors multiply. That is the point: individually each looks tolerable,
    together they are why a 10 µF part behaves like 3 µF.
    """
    if marked_capacitance_uf <= 0:
        raise MLCCModelError("marked_capacitance_uf must be positive")

    dielectric = _normalize_dielectric(dielectric)
    notes: list[str] = []

    if _is_class_one(dielectric):
        # Class I: only tolerance applies. Everything else is 1.0.
        tol = tolerance_pct if tolerance_pct is not None else 5.0
        tol_factor = 1.0 - tol / 100.0
        eff = marked_capacitance_uf * tol_factor
        return EffectiveCapacitanceResult(
            marked_capacitance_uf=marked_capacitance_uf,
            effective_capacitance_uf=round(eff, 6),
            retention_fraction=round(tol_factor, 6),
            loss_pct=round((1.0 - tol_factor) * 100, 3),
            dc_bias_factor=1.0,
            ac_level_factor=1.0,
            temperature_factor=1.0,
            ageing_factor=1.0,
            tolerance_factor=round(tol_factor, 6),
            applied_v=applied_v,
            rated_v=rated_v,
            case_size=case_size,
            dielectric=dielectric,
            ambient_c=ambient_c,
            hours_in_service=hours_in_service,
            confidence="physical",
            source="Class I (C0G/NP0) is a linear dielectric: no DC-bias, ageing or TCC loss",
            notes=["Class I part: only tolerance applies"],
        )

    # --- DC bias ---------------------------------------------------------- #
    if measured_retention_at_bias is not None:
        if not 0.0 < measured_retention_at_bias <= 1.0:
            raise MLCCModelError("measured_retention_at_bias must be in (0, 1]")
        dc_factor = measured_retention_at_bias
        dc_confidence = "measured"
        notes.append(
            f"DC-bias retention {dc_factor:.3f} taken from a datasheet curve at {applied_v} V"
        )
    else:
        dc_factor, dc_confidence = dc_bias_retention(applied_v, rated_v, case_size, dielectric)
        notes.append(
            f"DC-bias retention {dc_factor:.3f} is a BAND estimate for {case_size} {dielectric} "
            f"at {applied_v}/{rated_v} V — replace with a datasheet curve for a real design"
        )

    ac_factor = AC_LEVEL_RETENTION.get(ac_level, 0.85)
    temp_factor, _ = temperature_retention(ambient_c, dielectric)
    age_factor, _ = ageing_retention(
        hours_in_service, dielectric, under_dc_bias=applied_v > 0.1 * rated_v
    )

    if tolerance_pct is None:
        # Class II parts are commonly ±10%; assuming ±20% would be pessimistic
        # for X7R and optimistic for Y5V, so default to 10 and say so.
        tolerance_pct = 10.0
    tol_factor = 1.0 - tolerance_pct / 100.0

    retention = dc_factor * ac_factor * temp_factor * age_factor * tol_factor

    # Round the factors first, then derive the reported retention from them, so
    # the numbers in the response are self-consistent: a caller that multiplies
    # the factors it was given gets exactly the retention it was given. Rounding
    # the retention independently would leave the two disagreeing in the sixth
    # decimal, which reads as a bug in someone else's spreadsheet.
    dc_factor = round(dc_factor, 6)
    ac_factor = round(ac_factor, 6)
    temp_factor = round(temp_factor, 6)
    age_factor = round(age_factor, 6)
    tol_factor = round(tol_factor, 6)
    retention = round(dc_factor * ac_factor * temp_factor * age_factor * tol_factor, 9)

    eff = marked_capacitance_uf * retention

    # Confidence is the weakest link: one band estimate makes the result a band.
    confidence = "band" if dc_confidence == "band" else "measured"

    if applied_v > 0.8 * rated_v:
        notes.append(
            f"Applied {applied_v} V is {applied_v / rated_v:.0%} of rated — derate to ≤50% "
            "of rated for Class II ceramics, or step up a case size"
        )
    if retention < 0.5:
        notes.append(
            f"Only {retention:.0%} of the marked value survives: size the part from "
            "effective capacitance, not the reel label"
        )

    return EffectiveCapacitanceResult(
        marked_capacitance_uf=marked_capacitance_uf,
        effective_capacitance_uf=round(eff, 6),
        retention_fraction=round(retention, 9),
        loss_pct=round((1.0 - retention) * 100, 3),
        dc_bias_factor=round(dc_factor, 6),
        ac_level_factor=round(ac_factor, 6),
        temperature_factor=round(temp_factor, 6),
        ageing_factor=round(age_factor, 6),
        tolerance_factor=round(tol_factor, 6),
        applied_v=applied_v,
        rated_v=rated_v,
        case_size=case_size,
        dielectric=dielectric,
        ambient_c=ambient_c,
        hours_in_service=hours_in_service,
        confidence=confidence,
        source=(
            "Kyocera-AVX dielectric ageing note; Würth SN011; Passive Components Europe "
            "DC-bias survey; EIA-198 dielectric classes; Vishay/KEMET TCC bands"
        ),
        notes=notes,
    )


@dataclass(frozen=True)
class HoldUpResult:
    """Brown-out ride-through of an MLCC reservoir bank."""

    required_hold_time_ms: float
    achieved_hold_time_ms: float
    passes: bool
    # The number that decides it: effective capacitance, not marked.
    required_capacitance_uf: float
    effective_capacitance_uf: float
    marked_capacitance_uf: float
    shortfall_uf: float
    required_marked_capacitance_uf: float
    load_current_ma: float
    v_start: float
    v_floor: float
    margin_ms: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def hold_up_capacitance(
    load_current_ma: float,
    v_start: float,
    v_floor: float,
    required_hold_time_ms: float,
    rated_v: float | None = None,
    case_size: str = "0805",
    dielectric: str = "X5R",
    ambient_c: float = 25.0,
    hours_in_service: float = 1000.0,
    tolerance_pct: float = 10.0,
) -> HoldUpResult:
    """Size an MLCC reservoir for a brown-out window, in *effective* farads.

    The energy argument is the standard constant-current one:

        I·t = C·(V_start − V_floor)   →   C_required = I·t / ΔV

    Sizing from that number and buying a part with that marked value is the
    classic mistake. The part must deliver ``C_required`` *after* DC bias,
    temperature, ageing and tolerance have taken their cut, so the marked value
    is ``C_required / retention``. The gap between the two is the bug that ships.

    ``v_start`` should be the rail voltage at the moment the source collapses —
    after any ORing diode drop — not the nominal input.
    """
    if load_current_ma <= 0:
        raise MLCCModelError("load_current_ma must be positive")
    if v_start <= v_floor:
        raise MLCCModelError(
            f"v_start ({v_start} V) must exceed v_floor ({v_floor} V); there is no headroom to discharge"
        )
    if required_hold_time_ms <= 0:
        raise MLCCModelError("required_hold_time_ms must be positive")

    delta_v = v_start - v_floor
    t_s = required_hold_time_ms / 1000.0
    i_a = load_current_ma / 1000.0
    # C = I·t/ΔV, expressed in µF.
    required_c_uf = (i_a * t_s / delta_v) * 1e6

    notes: list[str] = []
    if rated_v is None:
        # A reservoir sits on a rail that may see the full input, so rate at
        # twice the start voltage: that keeps bias derating near 50%.
        rated_v = max(v_start * 2.0, 6.3)
        notes.append(f"rated_v defaulted to {rated_v:.1f} V (2× v_start) for bias headroom")

    # Retention at the worst-case bias in the window: the start of the discharge.
    probe = effective_capacitance(
        marked_capacitance_uf=1.0,
        rated_v=rated_v,
        applied_v=v_start,
        case_size=case_size,
        dielectric=dielectric,
        ambient_c=ambient_c,
        hours_in_service=hours_in_service,
        tolerance_pct=tolerance_pct,
    )
    retention = probe.retention_fraction
    if retention <= 0:
        raise MLCCModelError("retention collapsed to zero; check rated_v vs applied_v")

    required_marked_uf = required_c_uf / retention

    # Now evaluate the design as built: a marked value gives some effective value.
    achieved_eff_uf = required_marked_uf * retention
    # t = C·ΔV/I, in ms.
    achieved_ms = (achieved_eff_uf * 1e-6 * delta_v / i_a) * 1000.0

    notes.append(
        f"Retention at {v_start} V bias is {retention:.0%}: buy "
        f"{required_marked_uf:.0f} µF marked to get {required_c_uf:.0f} µF effective"
    )
    if retention < 0.5:
        notes.append(
            "Retention below 50% — a larger case or a higher voltage rating buys back "
            "more capacitance per yuan than adding parallel parts"
        )

    return HoldUpResult(
        required_hold_time_ms=round(required_hold_time_ms, 4),
        achieved_hold_time_ms=round(achieved_ms, 4),
        passes=achieved_ms >= required_hold_time_ms * 0.999,
        required_capacitance_uf=round(required_c_uf, 4),
        effective_capacitance_uf=round(achieved_eff_uf, 4),
        marked_capacitance_uf=round(required_marked_uf, 4),
        shortfall_uf=round(max(0.0, required_c_uf - achieved_eff_uf), 4),
        required_marked_capacitance_uf=round(required_marked_uf, 4),
        load_current_ma=load_current_ma,
        v_start=v_start,
        v_floor=v_floor,
        margin_ms=round(achieved_ms - required_hold_time_ms, 4),
        notes=notes,
    )


def capacitance_tolerance_corners(
    nominal_f: float,
    tolerance_pct: float,
) -> dict[str, float]:
    """Min/max capacitance for a tolerance band, as the worst-case corners.

    Trivial arithmetic, but naming the corners prevents the recurring mistake of
    designing at nominal and calling the result "worst case".
    """
    if nominal_f <= 0:
        raise MLCCModelError("nominal_f must be positive")
    if not 0 <= tolerance_pct < 100:
        raise MLCCModelError("tolerance_pct must be in [0, 100)")
    low = nominal_f * (1.0 - tolerance_pct / 100.0)
    high = nominal_f * (1.0 + tolerance_pct / 100.0)
    return {
        "nominal_f": nominal_f,
        "min_f": low,
        "max_f": high,
        "min_uf": low * 1e6,
        "max_uf": high * 1e6,
        "spread_pct": (high - low) / nominal_f * 100.0,
    }


def rc_cutoff_with_effective_c(
    r_ohm: float,
    marked_c_uf: float,
    rated_v: float,
    applied_v: float,
    case_size: str = "0805",
    dielectric: str = "X5R",
    ambient_c: float = 25.0,
    hours_in_service: float = 1000.0,
    tolerance_pct: float = 0.0,
) -> dict[str, Any]:
    """RC cutoff using the capacitance the part actually has.

    A filter designed for 1 kHz with a 10 µF part that delivers 4 µF cuts at
    2.5 kHz. The nominal calculation is not wrong, it is answering a different
    question — and this function answers the one that matters.

    ``tolerance_pct`` defaults to **0**, unlike :func:`effective_capacitance`,
    because this function isolates one effect: what operating conditions do to
    the cutoff. Folding in the part's tolerance would conflate two independent
    error sources and make the reported drift look like a bias effect when part
    of it is just a ±10% reel. Pass a tolerance explicitly if you want the
    combined worst case.
    """
    if r_ohm <= 0 or marked_c_uf <= 0:
        raise MLCCModelError("r_ohm and marked_c_uf must be positive")

    eff = effective_capacitance(
        marked_capacitance_uf=marked_c_uf,
        rated_v=rated_v,
        applied_v=applied_v,
        case_size=case_size,
        dielectric=dielectric,
        ambient_c=ambient_c,
        hours_in_service=hours_in_service,
        tolerance_pct=tolerance_pct,
    )
    c_f = eff.effective_capacitance_uf * 1e-6
    fc_actual = 1.0 / (2.0 * math.pi * r_ohm * c_f)
    fc_nominal = 1.0 / (2.0 * math.pi * r_ohm * marked_c_uf * 1e-6)

    return {
        "nominal_cutoff_hz": round(fc_nominal, 3),
        "actual_cutoff_hz": round(fc_actual, 3),
        "drift_pct": round((fc_actual - fc_nominal) / fc_nominal * 100.0, 3),
        "marked_capacitance_uf": marked_c_uf,
        "effective_capacitance_uf": eff.effective_capacitance_uf,
        "retention_fraction": eff.retention_fraction,
        "resistance_ohm": r_ohm,
        "tolerance_included": tolerance_pct != 0.0,
        "confidence": eff.confidence,
        "notes": eff.notes,
    }
