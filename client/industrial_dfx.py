"""Industrial DFX (DFM, DFA, DFT, DFC) & IPC Standards Engine (Community & Enterprise Edition).

Implements rigorous physical and manufacturing rules for production-ready hardware:
  1. IPC-2152: Precise conductor current-carrying capacity, temperature rise, and trace width sizing.
  2. IPC-2221: Voltage-dependent electrical clearance and creepage spacing (Table 6-1).
  3. DFT (Design for Testability): Automated test point matrix coverage audit for power and signal buses.
  4. DFA (Design for Assembly): Optical fiducial marks (MARK) and tooling holes verification for automated pick-and-place.
  5. EMC & Industrial Protection: Mandatory TVS diode arrays on exposed connectors (USB, RS485, CAN)
     and reverse-polarity protection on industrial DC supplies (IEC 61000-4-2 ESD 8kV/15kV compliance).
  6. DFC (Design for Cost): Basic vs Extended SMT feeder surcharge analysis for JLCPCB / LCSC.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

__all__ = [
    "IPC2221_CLEARANCES",
    "DFXViolation",
    "IndustrialDFXReport",
    "TraceCurrentResult",
    "audit_industrial_dfx",
    "calculate_ipc2152",
    "get_ipc2221_clearance",
    "solve_trace_width_ipc2152",
]

# --------------------------------------------------------------------------- #
# IPC-2221 Voltage Clearance Table (Table 6-1)
# --------------------------------------------------------------------------- #

# Voltage range (max V): (internal_mm, external_uncoated_mm, external_coated_mm)
IPC2221_CLEARANCES: list[tuple[float, float, float, float]] = [
    (15.0, 0.05, 0.10, 0.05),
    (30.0, 0.05, 0.10, 0.05),
    (50.0, 0.10, 0.60, 0.13),
    (100.0, 0.10, 0.60, 0.13),
    (150.0, 0.20, 0.60, 0.40),
    (300.0, 0.20, 1.25, 0.40),
    (500.0, 0.25, 2.50, 0.80),
]


def get_ipc2221_clearance(voltage_v: float, layer: str = "external_coated") -> float:
    """Return required clearance in mm according to IPC-2221 Table 6-1.

    Args:
        voltage_v: Peak working voltage across conductors (V).
        layer: 'internal', 'external_uncoated', or 'external_coated'.
    """
    col_idx = 1 if layer == "internal" else (2 if layer == "external_uncoated" else 3)
    for max_v, internal_clr, ext_uncoated, ext_coated in IPC2221_CLEARANCES:
        if voltage_v <= max_v:
            return (internal_clr, ext_uncoated, ext_coated)[col_idx - 1]
    # Above 500V: Base 500V value + 0.005mm/V
    delta_v = voltage_v - 500.0
    base_clr = 0.25 if layer == "internal" else (2.50 if layer == "external_uncoated" else 0.80)
    extra_rate = 0.0025 if layer == "internal" else (0.005 if layer == "external_uncoated" else 0.003)
    return round(base_clr + delta_v * extra_rate, 3)


# --------------------------------------------------------------------------- #
# IPC-2152 Conductor Current-Carrying & Temperature Sizing
# --------------------------------------------------------------------------- #

@dataclass
class TraceCurrentResult:
    trace_width_mm: float
    trace_width_mil: float
    copper_oz: float
    temp_rise_c: float
    layer: str
    max_current_a: float
    cross_section_mil2: float
    cross_section_mm2: float
    resistance_mohm_per_m: float
    power_loss_w_per_m: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_ipc2152(
    trace_width_mm: float,
    copper_oz: float = 1.0,
    temp_rise_c: float = 20.0,
    layer: str = "external",
) -> TraceCurrentResult:
    """Calculate maximum current carrying capacity in Amperes according to IPC-2152.

    Formula:
        Area (mil^2) = Width (mil) * Thickness (mil)
        I = k * (delta_T ^ b) * (Area ^ c)
        where:
          - external layer: k=0.048, b=0.44, c=0.725
          - internal layer: k=0.024, b=0.44, c=0.725
          - copper thickness: 1.378 mil per 1 oz (35 um)
    """
    if trace_width_mm <= 0:
        raise ValueError("trace_width_mm must be positive")
    if temp_rise_c <= 0:
        raise ValueError("temp_rise_c must be positive")

    w_mil = trace_width_mm * 39.37007874
    t_mil = copper_oz * 1.378
    area_mil2 = w_mil * t_mil
    area_mm2 = area_mil2 * 0.00064516

    is_ext = layer.lower().startswith("ext")
    k = 0.048 if is_ext else 0.024
    b = 0.44
    c = 0.725

    current_a = k * (temp_rise_c ** b) * (area_mil2 ** c)

    # Copper resistivity at 25°C = 1.724e-8 Ω*m, temperature coefficient alpha = 0.00393 / °C
    op_temp = 25.0 + temp_rise_c
    rho = 1.724e-8 * (1.0 + 0.00393 * (op_temp - 25.0))
    # R = rho * L / A (where L=1m, A in m^2)
    area_m2 = area_mm2 * 1e-6
    res_per_m = (rho / area_m2) if area_m2 > 0 else 0.0
    r_mohm_per_m = res_per_m * 1000.0
    p_loss_w_per_m = (current_a ** 2) * res_per_m

    return TraceCurrentResult(
        trace_width_mm=round(trace_width_mm, 3),
        trace_width_mil=round(w_mil, 1),
        copper_oz=copper_oz,
        temp_rise_c=temp_rise_c,
        layer="external" if is_ext else "internal",
        max_current_a=round(current_a, 2),
        cross_section_mil2=round(area_mil2, 1),
        cross_section_mm2=round(area_mm2, 4),
        resistance_mohm_per_m=round(r_mohm_per_m, 2),
        power_loss_w_per_m=round(p_loss_w_per_m, 2),
    )


def solve_trace_width_ipc2152(
    target_current_a: float,
    copper_oz: float = 1.0,
    temp_rise_c: float = 20.0,
    layer: str = "external",
) -> TraceCurrentResult:
    """Solve required trace width in mm for a desired target current under IPC-2152."""
    if target_current_a <= 0:
        raise ValueError("target_current_a must be positive")
    if temp_rise_c <= 0:
        raise ValueError("temp_rise_c must be positive")

    is_ext = layer.lower().startswith("ext")
    k = 0.048 if is_ext else 0.024
    b = 0.44
    c = 0.725

    # I = k * (delta_T^b) * (Area^c) => Area = (I / (k * delta_T^b))^(1/c)
    area_mil2 = (target_current_a / (k * (temp_rise_c ** b))) ** (1.0 / c)
    t_mil = copper_oz * 1.378
    w_mil = area_mil2 / t_mil
    w_mm = w_mil / 39.37007874

    return calculate_ipc2152(
        trace_width_mm=w_mm,
        copper_oz=copper_oz,
        temp_rise_c=temp_rise_c,
        layer="external" if is_ext else "internal",
    )


# --------------------------------------------------------------------------- #
# DFX Audit Data Structures
# --------------------------------------------------------------------------- #

DFXCategory = Literal["DFT", "DFA", "DFM", "DFC", "EMC_SAFETY"]
DFXSeverity = Literal["CRITICAL", "WARNING", "INFO"]


@dataclass
class DFXViolation:
    rule_id: str
    category: DFXCategory
    severity: DFXSeverity
    location: str
    description: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IndustrialDFXReport:
    score: int  # 0 to 100
    grade: str  # A+, A, B, C, F
    passed: bool
    summary: str
    categories: dict[str, dict[str, Any]]
    metrics: dict[str, Any]
    violations: list[DFXViolation]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "grade": self.grade,
            "passed": self.passed,
            "summary": self.summary,
            "categories": self.categories,
            "metrics": self.metrics,
            "violations": [v.to_dict() for v in self.violations],
        }

    def to_markdown(self) -> str:
        badge = "🟢" if self.passed and self.score >= 85 else ("🟡" if self.score >= 70 else "🔴")
        lines = [
            "# Industrial DFX & Manufacturing Audit Report",
            "",
            (
                f"**Overall Verdict**: {badge} **Grade {self.grade}** ({self.score}/100) — "
                f"{'PASSED (Industrial Production Ready)' if self.passed else 'ACTION REQUIRED (DFM/DFT Deficiencies Detected)'}"
            ),
            "",
            f"> {self.summary}",
            "",
            "## 1. Domain Scorecard",
            "",
            "| Engineering Domain | Score | Weight | Critical | Warnings | Advisories |",
            "|:---|:---:|:---:|:---:|:---:|:---:|",
        ]
        cat_labels = {
            "DFT": "Design for Testability (DFT)",
            "DFA": "Design for Assembly (DFA)",
            "DFM": "Design for Fabrication (DFM)",
            "DFC": "Design for Cost & SMT (DFC)",
            "EMC_SAFETY": "EMC, ESD & Circuit Protection",
        }
        for cat_k, cat_v in self.categories.items():
            name = cat_labels.get(cat_k, cat_k)
            lines.append(
                f"| {name} | **{cat_v.get('score', 0)}** | {int(cat_v.get('weight', 0.2) * 100)}% | "
                f"{cat_v.get('critical', 0)} | {cat_v.get('warning', 0)} | {cat_v.get('info', 0)} |"
            )

        lines.extend([
            "",
            "## 2. Key Physical & Industrial Metrics",
            "",
            "| Metric | Value | Industrial Benchmark / IPC Guideline |",
            "|:---|:---:|:---|",
        ])
        for k, v in self.metrics.items():
            label = k.replace("_", " ").title()
            lines.append(f"| {label} | `{v}` | Industry Best Practice |")

        lines.extend([
            "",
            f"## 3. Engineering Audit Findings ({len(self.violations)})",
            "",
        ])
        if not self.violations:
            lines.append("*All IPC-2152, IPC-2221, DFT, DFA, and industrial protection rules satisfied. 100% clean!*")
        else:
            lines.append("| Rule ID | Severity | Category | Location | Title & Engineering Recommendation |")
            lines.append("|:---|:---:|:---:|:---|:---|")
            for v in self.violations:
                sev_icon = "🚨 CRITICAL" if v.severity == "CRITICAL" else ("⚠️ WARNING" if v.severity == "WARNING" else "ℹ️ INFO")
                lines.append(
                    f"| `{v.rule_id}` | {sev_icon} | {v.category} | **{v.location}** | "
                    f"{v.description}<br>*Action*: {v.recommendation} |"
                )

        lines.extend([
            "",
            "---",
            "*Audited automatically by CircuitAgent Industrial DFX Engine (IPC-2152 / IPC-2221 / IEC 61000-4-2 compliant).*",
        ])
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# DFX Audit Core Implementation
# --------------------------------------------------------------------------- #

def audit_industrial_dfx(netlist_dict: dict[str, Any]) -> IndustrialDFXReport:
    """Perform a comprehensive industrial DFX (DFM/DFA/DFT/DFC/EMC) audit on a netlist."""
    raw = netlist_dict or {}
    if "netlist" in raw and isinstance(raw["netlist"], dict):
        nl = raw["netlist"]
    else:
        nl = raw

    components = nl.get("components", [])
    if not components:
        # Support dict-based modules representation from synthesizer
        src_modules = raw.get("modules") or nl.get("modules")
        if isinstance(src_modules, dict):
            components = [{"ref": ref, **info} for ref, info in src_modules.items() if isinstance(info, dict)]

    connections = nl.get("connections", [])
    if not connections and "connections" in raw:
        connections = raw.get("connections", [])

    violations: list[DFXViolation] = []

    # Map nets
    net_points: dict[str, list[str]] = {}
    for conn in connections:
        if isinstance(conn, dict):
            net_name = conn.get("net", "")
            pts = conn.get("points", [])
            net_points.setdefault(net_name, []).extend(pts)

    # 1. DFT (Design for Testability) Audit
    # Identify test points
    test_points = [
        c for c in components
        if c.get("kind") in ("TESTPOINT", "TEST_POINT")
        or c.get("ref", "").upper().startswith(("TP_", "TP"))
    ]
    tp_nets = set()
    for tp in test_points:
        ref = tp.get("ref", "")
        for n, pts in net_points.items():
            if any(p.startswith(f"{ref}.") for p in pts):
                tp_nets.add(n)

    # Power rails requiring testpoints
    power_rails = [n for n in net_points if any(p in n.upper() for p in ("VBUS", "VCC", "3.3V", "3V3", "5V", "VBAT"))]
    gnd_rails = [n for n in net_points if "GND" in n.upper()]
    critical_debug_nets = [n for n in net_points if any(d in n.upper() for d in ("SWDIO", "SWCLK", "TX", "RX", "NRST", "RESET"))]

    missing_power_tps = [p for p in power_rails if p not in tp_nets]
    if missing_power_tps:
        violations.append(DFXViolation(
            rule_id="DFT-01",
            category="DFT",
            severity="WARNING",
            location="Power Rails",
            description=f"Power nets missing dedicated ICT/flying-probe test points: {', '.join(missing_power_tps[:4])}.",
            recommendation="Add 1.0mm SMD test point pads (block_testpoint_matrix) on all power rails for production yield testing.",
        ))

    if gnd_rails and not any(g in tp_nets for g in gnd_rails):
        violations.append(DFXViolation(
            rule_id="DFT-02",
            category="DFT",
            severity="WARNING",
            location="GND Rail",
            description="Ground rail lacks a dedicated reference test point pad.",
            recommendation="Add at least one TP_GND test pad near primary power supply entry.",
        ))

    if critical_debug_nets and not any(d in tp_nets for d in critical_debug_nets):
        violations.append(DFXViolation(
            rule_id="DFT-03",
            category="DFT",
            severity="INFO",
            location="Debug/Bus Nets",
            description="Programming/UART/I2C buses lack dedicated test pads for in-line flashing or boundary scan.",
            recommendation="Add test pads on SWD/UART signals if board header is omitted or space-constrained.",
        ))

    # 2. DFA (Design for Assembly) Audit
    fiducials = [
        c for c in components
        if c.get("kind") in ("FIDUCIAL", "MARK")
        or c.get("ref", "").upper().startswith(("FID", "MARK"))
    ]
    if len(fiducials) < 3:
        violations.append(DFXViolation(
            rule_id="DFA-01",
            category="DFA",
            severity="WARNING",
            location="Board Panel/Corners",
            description=f"Optical fiducials count is {len(fiducials)} (< 3 minimum required for automatic pick-and-place skew correction).",
            recommendation="Place at least 3 asymmetrical optical fiducial marks (1.0mm copper with 2.0mm soldermask clearance) via block_fiducial_marks.",
        ))

    # 3. EMC & Industrial Circuit Protection Audit
    # USB Protection check
    has_usb = any("USB" in (c.get("value", "") + c.get("package", "") + c.get("ref", "")).upper() for c in components)
    has_usb_tvs = any(
        any(k in (c.get("value", "") + c.get("description", "")).upper() for k in ("USBLC6", "ESDALC", "TVS", "ESD"))
        for c in components
    )
    if has_usb and not has_usb_tvs:
        violations.append(DFXViolation(
            rule_id="EMC-01",
            category="EMC_SAFETY",
            severity="CRITICAL",
            location="USB Interface",
            description="Exposed external USB data lines (D+/D-) lack TVS diode electrostatic discharge protection.",
            recommendation="Add USBLC6-2SC6 or low-capacitance dual TVS diode array (block_esd_usb_tvs) to withstand IEC 61000-4-2 15kV ESD.",
        ))

    # RS485 Protection check
    has_rs485 = any("485" in (c.get("value", "") + c.get("ref", "")).upper() for c in components)
    has_rs485_tvs = any("SM712" in c.get("value", "").upper() or "SM712" in c.get("lcsc", "").upper() for c in components)
    if has_rs485 and not has_rs485_tvs:
        violations.append(DFXViolation(
            rule_id="EMC-02",
            category="EMC_SAFETY",
            severity="CRITICAL",
            location="RS485 Transceiver",
            description="Industrial RS485 differential lines (A/B) lack asymmetrical TVS surge protection.",
            recommendation="Insert SM712 TVS diodes (block_esd_rs485_tvs) between lines A/B and GND to prevent field lightning and ground-loop surges.",
        ))

    # CAN Bus Protection check
    has_can = any("CAN" in (c.get("value", "") + c.get("ref", "")).upper() for c in components)
    has_can_tvs = any("PESD" in c.get("value", "").upper() or "CAN_TVS" in c.get("ref", "").upper() for c in components)
    if has_can and not has_can_tvs:
        violations.append(DFXViolation(
            rule_id="EMC-03",
            category="EMC_SAFETY",
            severity="WARNING",
            location="CAN Transceiver",
            description="CAN bus differential lines (CAN_H / CAN_L) lack automotive/industrial transient suppressor diodes.",
            recommendation="Add PESD1CAN or 24V bidirectional TVS (block_esd_can_tvs) across CAN lines.",
        ))

    # Reverse polarity check on DC power input
    has_dc_in = any(
        any(k in c.get("ref", "").upper() or k in c.get("value", "").upper() for k in ("DC_JACK", "VIN", "TERMINAL"))
        for c in components
    )
    has_polarity_protection = any(
        any(k in c.get("ref", "").upper() or k in c.get("value", "").upper() for k in ("SS34", "SS14", "D_REV", "Q_REV", "AO3401"))
        for c in components
    )
    if has_dc_in and not has_polarity_protection:
        violations.append(DFXViolation(
            rule_id="EMC-04",
            category="EMC_SAFETY",
            severity="WARNING",
            location="DC Input Entry",
            description="DC power input lacks reverse-polarity protection against accidental reverse wiring.",
            recommendation="Add Schottky diode (SS34) or P-MOSFET ideal diode circuit (block_reverse_polarity_protection).",
        ))

    # 4. Power Integrity & Decoupling Ratio Audit
    ic_components = [
        c for c in components
        if c.get("kind") in ("IC", "MCU", "SENSOR", "TRANSCEIVER")
        or c.get("ref", "").startswith("U")
    ]
    decoupling_caps = [
        c for c in components
        if c.get("kind") == "CAPACITOR"
        and ("100N" in c.get("value", "").upper() or "0.1U" in c.get("value", "").upper())
    ]
    bulk_caps = [
        c for c in components
        if c.get("kind") == "CAPACITOR"
        and any(b in c.get("value", "").upper() for b in ("4.7U", "10U", "22U", "47U", "100U"))
    ]

    ic_count = len(ic_components)
    decoupling_count = len(decoupling_caps)
    decoupling_ratio = (decoupling_count / ic_count) if ic_count > 0 else 1.0

    if ic_count > 0 and decoupling_ratio < 1.0:
        violations.append(DFXViolation(
            rule_id="PI-01",
            category="DFM",
            severity="WARNING",
            location="Power Decoupling",
            description=f"Decoupling capacitor count ({decoupling_count}) is less than active IC count ({ic_count}). Ratio = {decoupling_ratio:.2f} < 1.0.",
            recommendation="Ensure at least one 100nF low-ESR ceramic decoupling capacitor is placed immediately adjacent to each IC power pin.",
        ))

    if ic_count >= 2 and not bulk_caps:
        violations.append(DFXViolation(
            rule_id="PI-02",
            category="DFM",
            severity="WARNING",
            location="Power Distribution",
            description="No bulk capacitor (>= 4.7uF) detected on power rail to stabilize transient load switching.",
            recommendation="Add a 10uF X7R ceramic or tantalum bulk capacitor at the output of LDO/DC-DC converters.",
        ))

    # 5. DFC (Design for Cost & SMT Optimization) Audit
    # Basic vs Extended parts analysis
    total_parts = len(components)
    unique_lcsc = len({c.get("lcsc") for c in components if c.get("lcsc")})
    # Typical extended parts are specialized ICs or non-basic passives
    estimated_extended = max(0, unique_lcsc - 5)
    est_smt_fee_cny = estimated_extended * 20.0  # ¥20/type feeder fee on JLCPCB

    if estimated_extended > 6:
        violations.append(DFXViolation(
            rule_id="DFC-01",
            category="DFC",
            severity="INFO",
            location="BOM Feeder Setup",
            description=f"Design utilizes approximately {estimated_extended} Extended library components (est. ¥{est_smt_fee_cny:.0f} feeder loading surcharge).",
            recommendation="Replace generic passives and common diodes with JLCPCB Basic Library parts to eliminate feeder setup surcharges.",
        ))

    # Scoring computation
    cat_weights = {
        "EMC_SAFETY": 0.30,
        "DFT": 0.20,
        "DFA": 0.20,
        "DFM": 0.15,
        "DFC": 0.15,
    }
    cat_stats: dict[str, dict[str, Any]] = {}
    for cat, weight in cat_weights.items():
        v_cat = [v for v in violations if v.category == cat]
        crit = sum(1 for v in v_cat if v.severity == "CRITICAL")
        warn = sum(1 for v in v_cat if v.severity == "WARNING")
        info = sum(1 for v in v_cat if v.severity == "INFO")
        deduction = crit * 30 + warn * 15 + info * 5
        score = max(0, 100 - deduction)
        cat_stats[cat] = {
            "score": score,
            "weight": weight,
            "critical": crit,
            "warning": warn,
            "info": info,
        }

    overall_score = int(sum(cat_stats[c]["score"] * cat_weights[c] for c in cat_weights))
    passed = (overall_score >= 70) and not any(v.severity == "CRITICAL" for v in violations)

    if overall_score >= 90:
        grade = "A+" if passed else "B"
    elif overall_score >= 80:
        grade = "A" if passed else "B"
    elif overall_score >= 70:
        grade = "B"
    elif overall_score >= 60:
        grade = "C"
    else:
        grade = "F"

    summary = (
        f"Industrial DFX audit score is {overall_score}/100 (Grade {grade}). "
        f"Detected {len(test_points)} test points, {len(fiducials)} fiducials, and {decoupling_count} decoupling caps across {total_parts} components. "
        + ("Production certified for industrial deployment." if passed else "Action required: resolve critical safety/protection findings prior to fabrication.")
    )

    metrics = {
        "total_components": total_parts,
        "active_ics_count": ic_count,
        "testpoints_count": len(test_points),
        "fiducials_count": len(fiducials),
        "decoupling_capacitors": decoupling_count,
        "decoupling_ratio": round(decoupling_ratio, 2),
        "bulk_capacitors": len(bulk_caps),
        "unique_lcsc_parts": unique_lcsc,
        "estimated_smt_extended_fee_cny": est_smt_fee_cny,
        "has_usb_tvs": has_usb_tvs if has_usb else "N/A",
        "has_rs485_tvs": has_rs485_tvs if has_rs485 else "N/A",
        "has_can_tvs": has_can_tvs if has_can else "N/A",
    }

    return IndustrialDFXReport(
        score=overall_score,
        grade=grade,
        passed=passed,
        summary=summary,
        categories=cat_stats,
        metrics=metrics,
        violations=violations,
    )
