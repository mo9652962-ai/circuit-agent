"""Parametric Hardware Equations & Circuit Design Solver (Community & Enterprise Edition).

Inspired by atopile constraint modeling and JITX parametric circuit synthesis.
Provides closed-form, deterministic mathematical solvers for:
  1. Standard E96 (1%) / E24 (5%) Resistor & Capacitor Series snapping
  2. Optimal Resistor Voltage Divider synthesis with minimum ratio error & target impedance
  3. LDO thermal power dissipation, junction temperature ($T_j$), and efficiency analysis
  4. I2C bus pull-up resistor sizing compliant with NXP UM10204 (100kHz / 400kHz / 1MHz)
  5. RC Low-pass / High-pass filter cut-off frequency calculation

Zero external runtime dependencies: 100% Python standard library.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Literal

# --------------------------------------------------------------------------- #
# Standard Decade Value Series (E24 5% and E96 1%)
# --------------------------------------------------------------------------- #

E24_BASE = [
    1.0,
    1.1,
    1.2,
    1.3,
    1.5,
    1.6,
    1.8,
    2.0,
    2.2,
    2.4,
    2.7,
    3.0,
    3.3,
    3.6,
    3.9,
    4.3,
    4.7,
    5.1,
    5.6,
    6.2,
    6.8,
    7.5,
    8.2,
    9.1,
]

E96_BASE = [
    1.00,
    1.02,
    1.05,
    1.07,
    1.10,
    1.13,
    1.15,
    1.18,
    1.21,
    1.24,
    1.27,
    1.30,
    1.33,
    1.37,
    1.40,
    1.43,
    1.47,
    1.50,
    1.54,
    1.58,
    1.62,
    1.65,
    1.69,
    1.74,
    1.78,
    1.82,
    1.87,
    1.91,
    1.96,
    2.00,
    2.05,
    2.10,
    2.15,
    2.21,
    2.26,
    2.32,
    2.37,
    2.43,
    2.49,
    2.55,
    2.61,
    2.67,
    2.74,
    2.80,
    2.87,
    2.94,
    3.01,
    3.09,
    3.16,
    3.24,
    3.32,
    3.40,
    3.48,
    3.57,
    3.65,
    3.74,
    3.83,
    3.92,
    4.02,
    4.12,
    4.22,
    4.32,
    4.42,
    4.53,
    4.64,
    4.75,
    4.87,
    4.99,
    5.11,
    5.23,
    5.36,
    5.49,
    5.62,
    5.76,
    5.90,
    6.04,
    6.19,
    6.34,
    6.49,
    6.65,
    6.81,
    6.98,
    7.15,
    7.32,
    7.50,
    7.68,
    7.87,
    8.06,
    8.25,
    8.45,
    8.66,
    8.87,
    9.09,
    9.31,
    9.53,
    9.76,
]


def generate_standard_series(
    series: Literal["E24", "E96"] = "E96", min_val: float = 1.0, max_val: float = 10e6
) -> list[float]:
    """Generate all standard resistor values between min_val and max_val."""
    base = E96_BASE if series == "E96" else E24_BASE
    values: list[float] = []
    decade = 1.0
    while decade <= max_val:
        for b in base:
            v = round(b * decade, 4 if decade < 1 else 2)
            if min_val <= v <= max_val:
                values.append(v)
        decade *= 10.0
    return sorted(set(values))


def snap_to_e_series(value: float, series: Literal["E24", "E96"] = "E96") -> float:
    """Find the nearest standard commercial value in E24 or E96 series."""
    if value <= 0:
        raise ValueError("Value must be strictly positive")
    exp = math.floor(math.log10(value))
    norm = value / (10**exp)
    base = (E96_BASE + [10.0]) if series == "E96" else (E24_BASE + [10.0])
    best = min(base, key=lambda b: abs(b - norm))
    return round(best * (10**exp), 2 if exp >= 0 else 6)


# --------------------------------------------------------------------------- #
# 1. Optimal Resistor Voltage Divider
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DividerResult:
    v_in: float
    v_out_target: float
    v_out_actual: float
    r1_ohm: float
    r2_ohm: float
    ratio_error_pct: float
    total_resistance_ohm: float
    quiescent_current_ma: float
    p_r1_mw: float
    p_r2_mw: float
    series: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def solve_resistor_divider(
    v_in: float,
    v_out_target: float,
    max_quiescent_current_ma: float = 1.0,
    min_quiescent_current_ma: float = 0.01,
    series: Literal["E24", "E96"] = "E96",
) -> DividerResult:
    """Synthesize an optimal discrete E96/E24 resistor divider pair (R1 on high side, R2 on low side).

    V_out = V_in * (R2 / (R1 + R2))
    Searches standard commercial values to minimize voltage error while respecting current constraints.
    """
    if v_out_target >= v_in:
        raise ValueError(f"v_out_target ({v_out_target}V) must be less than v_in ({v_in}V)")
    if v_out_target <= 0 or v_in <= 0:
        raise ValueError("Voltages must be positive")

    target_ratio = v_out_target / v_in
    min_r_total = v_in / (max_quiescent_current_ma * 1e-3)
    max_r_total = v_in / (min_quiescent_current_ma * 1e-3)

    candidates = generate_standard_series(series, min_val=100.0, max_val=2.2e6)
    best_error = float("inf")
    best_r1 = 10000.0
    best_r2 = 10000.0
    best_v_out = 0.0

    for r2 in candidates:
        ideal_r1 = r2 * (1.0 - target_ratio) / target_ratio
        if ideal_r1 < 10.0 or ideal_r1 > 5e6:
            continue
        snapped_r1 = snap_to_e_series(ideal_r1, series)
        r_total = snapped_r1 + r2
        if not (min_r_total <= r_total <= max_r_total):
            continue

        actual_ratio = r2 / r_total
        actual_v_out = v_in * actual_ratio
        err = abs(actual_v_out - v_out_target) / v_out_target

        if err < best_error:
            best_error = err
            best_r1 = snapped_r1
            best_r2 = r2
            best_v_out = actual_v_out
            if err < 0.001:  # 0.1% is sufficiently optimal
                break

    r_total = best_r1 + best_r2
    i_q_ma = (v_in / r_total) * 1e3
    p_r1 = ((v_in - best_v_out) ** 2 / best_r1) * 1e3
    p_r2 = (best_v_out**2 / best_r2) * 1e3

    return DividerResult(
        v_in=round(v_in, 3),
        v_out_target=round(v_out_target, 3),
        v_out_actual=round(best_v_out, 4),
        r1_ohm=round(best_r1, 2),
        r2_ohm=round(best_r2, 2),
        ratio_error_pct=round(best_error * 100, 3),
        total_resistance_ohm=round(r_total, 2),
        quiescent_current_ma=round(i_q_ma, 4),
        p_r1_mw=round(p_r1, 2),
        p_r2_mw=round(p_r2, 2),
        series=series,
    )


# --------------------------------------------------------------------------- #
# 2. LDO Thermal & Efficiency Analysis
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LDOThermalResult:
    v_in: float
    v_out: float
    i_load_a: float
    power_loss_w: float
    efficiency_pct: float
    ambient_temp_c: float
    junction_temp_c: float
    package: str
    thermal_resistance_c_per_w: float
    is_safe: bool
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PACKAGE_THERMAL_RESISTANCE = {
    "SOT-23": 250.0,
    "SOT-23-5": 220.0,
    "SOT-89": 100.0,
    "SOT-223": 62.0,
    "TO-252": 45.0,
    "TO-263": 35.0,
    "DFN-6": 120.0,
    "SOIC-8": 90.0,
}


def calculate_ldo_thermal(
    v_in: float,
    v_out: float,
    i_load_a: float,
    package: str = "SOT-223",
    ambient_temp_c: float = 25.0,
    max_junction_temp_c: float = 125.0,
    quiescent_current_ma: float = 5.0,
) -> LDOThermalResult:
    """Analyze LDO thermal dissipation, efficiency, and die temperature rise."""
    if v_in <= v_out:
        raise ValueError(f"v_in ({v_in}V) must be greater than v_out ({v_out}V) for an LDO")
    if i_load_a <= 0:
        raise ValueError("i_load_a must be positive")

    i_q = quiescent_current_ma * 1e-3
    p_loss = (v_in - v_out) * i_load_a + v_in * i_q
    efficiency = (v_out * i_load_a) / (v_in * (i_load_a + i_q)) * 100.0

    r_theta = PACKAGE_THERMAL_RESISTANCE.get(package, 65.0)
    t_junction = ambient_temp_c + p_loss * r_theta
    is_safe = t_junction <= max_junction_temp_c

    if is_safe and efficiency >= 70.0:
        rec = f"Thermal design optimal: Tj={t_junction:.1f}°C is well within safety limits ({max_junction_temp_c}°C)."
    elif is_safe and efficiency < 70.0:
        rec = f"Acceptable for low-cost, but efficiency is low ({efficiency:.1f}%). Loss={p_loss:.2f}W causes Tj={t_junction:.1f}°C."
    else:
        rec = (
            f"CRITICAL OVERHEATING RISK: Junction temp ({t_junction:.1f}°C) exceeds max {max_junction_temp_c}°C! "
            f"Power loss is {p_loss:.2f}W in {package}. Recommendation: Switch to a synchronous DC-DC buck converter "
            f"(e.g. TPS54302 or MP2315) or upgrade to larger package / add thermal copper pour."
        )

    return LDOThermalResult(
        v_in=round(v_in, 2),
        v_out=round(v_out, 2),
        i_load_a=round(i_load_a, 4),
        power_loss_w=round(p_loss, 3),
        efficiency_pct=round(efficiency, 1),
        ambient_temp_c=round(ambient_temp_c, 1),
        junction_temp_c=round(t_junction, 1),
        package=package,
        thermal_resistance_c_per_w=r_theta,
        is_safe=is_safe,
        recommendation=rec,
    )


# --------------------------------------------------------------------------- #
# 3. I2C Bus Pull-Up Resistor Sizing (NXP UM10204)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class I2CPullUpResult:
    v_cc: float
    mode: str
    bus_capacitance_pf: float
    min_resistance_ohm: float
    max_resistance_ohm: float
    recommended_standard_ohm: float
    max_rise_time_ns: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_i2c_pullup(
    v_cc: float = 3.3,
    bus_capacitance_pf: float = 100.0,
    mode: Literal["standard", "fast", "fast_plus"] = "fast",
) -> I2CPullUpResult:
    """Calculate allowable and recommended I2C pull-up resistor values according to NXP UM10204 standard.

    Modes:
      - standard: 100 kHz (max rise time tr = 1000 ns, I_OL = 3mA, Vol = 0.4V)
      - fast: 400 kHz (max rise time tr = 300 ns, I_OL = 3mA, Vol = 0.4V)
      - fast_plus: 1000 kHz (max rise time tr = 120 ns, I_OL = 20mA, Vol = 0.4V)
    """
    if v_cc <= 0:
        raise ValueError("v_cc must be positive")
    if bus_capacitance_pf <= 0:
        raise ValueError("bus_capacitance_pf must be positive")

    # Parameters from NXP UM10204 Table 10
    if mode == "standard":
        tr_max_ns = 1000.0
        i_ol_ma = 3.0
        v_ol_max = 0.4
    elif mode == "fast_plus":
        tr_max_ns = 120.0
        i_ol_ma = 20.0
        v_ol_max = 0.4
    else:  # fast (400kHz default)
        tr_max_ns = 300.0
        i_ol_ma = 3.0
        v_ol_max = 0.4

    # Minimum resistance (limited by driver sink current I_OL)
    r_min = (v_cc - v_ol_max) / (i_ol_ma * 1e-3)

    # Maximum resistance (limited by RC time constant and maximum allowable rise time)
    # tr = 0.8473 * R * C_b (from 0.3 Vdd to 0.7 Vdd)
    c_b_farad = bus_capacitance_pf * 1e-12
    r_max = (tr_max_ns * 1e-9) / (0.8473 * c_b_farad)

    if r_min > r_max:
        rec_ohm = snap_to_e_series(r_min, "E24")
        explanation = (
            f"Bus capacitance ({bus_capacitance_pf}pF) is too high for {mode} mode! "
            f"R_min ({r_min:.0f}Ω) > R_max ({r_max:.0f}Ω). Reduce trace length or bus load."
        )
    else:
        # Standard engineering target: geometric mean of min and max, snapped to standard E24
        target = math.sqrt(r_min * r_max)
        rec_ohm = snap_to_e_series(target, "E24")
        # Clamp to range
        if rec_ohm < r_min:
            rec_ohm = snap_to_e_series(r_min * 1.05, "E24")
        if rec_ohm > r_max:
            rec_ohm = snap_to_e_series(r_max * 0.95, "E24")
        explanation = (
            f"Valid range for {mode} mode ({bus_capacitance_pf}pF bus load): "
            f"{r_min:.0f}Ω ≤ R_pullup ≤ {r_max:.0f}Ω. Optimal standard choice: {rec_ohm:.0f}Ω."
        )

    return I2CPullUpResult(
        v_cc=v_cc,
        mode=mode,
        bus_capacitance_pf=bus_capacitance_pf,
        min_resistance_ohm=round(r_min, 1),
        max_resistance_ohm=round(r_max, 1),
        recommended_standard_ohm=round(rec_ohm, 1),
        max_rise_time_ns=tr_max_ns,
        explanation=explanation,
    )


# --------------------------------------------------------------------------- #
# 4. RC Filter Sizing
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RCFilterResult:
    cutoff_freq_hz: float
    resistance_ohm: float
    capacitance_f: float
    capacitance_nf: float
    time_constant_ms: float
    impedance_at_cutoff_ohm: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_rc_filter(
    cutoff_freq_hz: float | None = None,
    r_ohm: float | None = None,
    c_f: float | None = None,
) -> RCFilterResult:
    """Solve 1st-order RC filter parameter (f_c = 1 / (2 * pi * R * C)).

    Provide any 2 of (cutoff_freq_hz, r_ohm, c_f) to solve for the third.
    """
    provided = sum(1 for p in (cutoff_freq_hz, r_ohm, c_f) if p is not None)
    if provided != 2:
        raise ValueError("Must provide exactly two of (cutoff_freq_hz, r_ohm, c_f)")

    if cutoff_freq_hz is None:
        assert r_ohm is not None and c_f is not None
        fc = 1.0 / (2.0 * math.pi * r_ohm * c_f)
        r = r_ohm
        c = c_f
    elif r_ohm is None:
        assert cutoff_freq_hz is not None and c_f is not None
        r = 1.0 / (2.0 * math.pi * cutoff_freq_hz * c_f)
        fc = cutoff_freq_hz
        c = c_f
    else:
        assert cutoff_freq_hz is not None and r_ohm is not None
        c = 1.0 / (2.0 * math.pi * cutoff_freq_hz * r_ohm)
        fc = cutoff_freq_hz
        r = r_ohm

    tau_ms = (r * c) * 1e3
    return RCFilterResult(
        cutoff_freq_hz=round(fc, 2),
        resistance_ohm=round(r, 2),
        capacitance_f=c,
        capacitance_nf=round(c * 1e9, 3),
        time_constant_ms=round(tau_ms, 4),
        impedance_at_cutoff_ohm=round(r * math.sqrt(2), 2),
    )


def calculate_ipc2221_clearance(
    peak_voltage_v: float,
    conductor_type: Literal["B1", "B2", "B4", "A6"] = "B2",
) -> dict[str, Any]:
    """Calculate minimum electrical clearance according to IPC-2221B Table 6-1.

    Conductor Types:
    - B1: Internal conductors (内层导体)
    - B2: External conductors, uncoated, sea level to 3050m (外层裸露导线)
    - B4: External conductors, with conformal coating (涂覆三防漆外层)
    - A6: External component leads, uncoated (裸露元件引脚)

    Voltage tiers: 0-15V, 16-30V, 31-50V, 51-100V, 101-150V, 151-170V, 171-250V, 251-300V, 301-500V.
    """
    v = abs(float(peak_voltage_v))
    # IPC-2221B Table 6-1 clearances in mm: (max_v, B1, B2, B4, A6)
    table = [
        (15.0, 0.05, 0.10, 0.05, 0.10),
        (30.0, 0.05, 0.10, 0.05, 0.10),
        (50.0, 0.10, 0.60, 0.13, 0.60),
        (100.0, 0.10, 0.60, 0.13, 0.60),
        (150.0, 0.20, 0.60, 0.40, 0.60),
        (170.0, 0.20, 1.25, 0.40, 1.25),
        (250.0, 0.20, 1.25, 0.40, 1.25),
        (300.0, 0.20, 1.25, 0.40, 1.25),
        (500.0, 0.25, 2.50, 0.80, 2.50),
    ]
    type_idx = {"B1": 1, "B2": 2, "B4": 3, "A6": 4}.get(str(conductor_type).upper(), 2)
    clearance_mm = 0.10
    tier_desc = "0-15V"

    for max_v, *cols in table:
        if v <= max_v:
            clearance_mm = cols[type_idx - 1]
            tier_desc = f"≤{max_v:.0f}V"
            break
    else:
        # > 500V: base 500V clearance + 0.005mm per volt over 500V
        base_500 = table[-1][type_idx]
        clearance_mm = base_500 + (v - 500.0) * 0.005
        tier_desc = ">500V (linear scale 0.005mm/V)"

    return {
        "peak_voltage_v": v,
        "conductor_type": str(conductor_type).upper(),
        "conductor_type_desc": {
            "B1": "Internal conductors (内层走线)",
            "B2": "External conductors, uncoated (外层裸露导线)",
            "B4": "External conductors, coated (三防漆涂覆)",
            "A6": "External component leads (裸露引脚)",
        }.get(str(conductor_type).upper(), "External uncoated"),
        "min_clearance_mm": round(clearance_mm, 3),
        "min_clearance_mils": round(clearance_mm / 0.0254, 1),
        "voltage_tier": tier_desc,
        "standard": "IPC-2221B Table 6-1 (Generic Standard on Printed Board Design)",
    }
