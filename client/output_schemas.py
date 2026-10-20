"""Output schemas for the electrical-analysis tools.

Only tools whose response shape is a *contract* get an ``outputSchema``. An
output schema is a promise: the server MUST return ``structuredContent``
conforming to it, so declaring one for a free-form tool would be a lie that a
client's validator would catch at the worst possible moment.

So this module is deliberately partial. The six electrical tools below return
fixed-shape numeric reports that downstream code reads field by field; those get
schemas. File-export tools (KiCad netlist, Gerber, IPC-2581, BOM CSV) return
document text, not a data object — a schema for them would describe a string
container and add nothing.

:data:`OUTPUT_SCHEMAS` is keyed by tool name and merged into
``AVAILABLE_TOOLS`` at import time by :func:`client.mcp_schema.apply_output_schemas`.
"""

from __future__ import annotations

from typing import Any

#: Reusable node for the human-readable findings list every analysis returns.
NOTES_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Human-readable findings: which term dominates, what to change, and any caveat.",
}


def _num(description: str) -> dict[str, Any]:
    return {"type": "number", "description": description}


def _str(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _bool(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


EFFECTIVE_CAPACITANCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "marked_capacitance_uf",
        "effective_capacitance_uf",
        "retention_fraction",
        "loss_pct",
        "dc_bias_factor",
        "ac_level_factor",
        "temperature_factor",
        "ageing_factor",
        "tolerance_factor",
        "applied_v",
        "rated_v",
        "case_size",
        "dielectric",
        "ambient_c",
        "hours_in_service",
        "confidence",
        "source",
        "notes",
    ],
    "properties": {
        "marked_capacitance_uf": _num("The value printed on the reel."),
        "effective_capacitance_uf": _num("The capacitance the circuit actually gets."),
        "retention_fraction": _num("effective / marked, after every loss mechanism."),
        "loss_pct": _num("Percentage of the marked value that is lost."),
        "dc_bias_factor": _num("Retention from DC bias alone — usually the dominant term."),
        "ac_level_factor": _num("Retention from AC signal magnitude (ferroelectric hysteresis)."),
        "temperature_factor": _num("Retention at the operating temperature, worst-case end of the TCC band."),
        "ageing_factor": _num("Retention after the service life, log-time law."),
        "tolerance_factor": _num("Retention at the pessimistic end of the part tolerance."),
        "applied_v": _num("DC bias across the part that was analysed."),
        "rated_v": _num("The part's rated DC voltage."),
        "case_size": _str("EIA case code analysed."),
        "dielectric": _str("EIA dielectric class analysed."),
        "ambient_c": _num("Operating ambient used."),
        "hours_in_service": _num("Service life used for the ageing term."),
        "confidence": {
            "type": "string",
            "enum": ["measured", "band", "physical"],
            "description": (
                "How trustworthy the number is: 'measured' from a datasheet curve, 'band' from a "
                "published retention range, 'physical' for Class I parts where the loss is zero by physics."
            ),
        },
        "source": _str("The measurements and standards the model is calibrated against."),
        "notes": NOTES_SCHEMA,
    },
}


HOLD_UP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "required_hold_time_ms",
        "achieved_hold_time_ms",
        "passes",
        "required_capacitance_uf",
        "effective_capacitance_uf",
        "marked_capacitance_uf",
        "shortfall_uf",
        "required_marked_capacitance_uf",
        "load_current_ma",
        "v_start",
        "v_floor",
        "margin_ms",
        "notes",
    ],
    "properties": {
        "required_hold_time_ms": _num("The spec: how long the rail must survive."),
        "achieved_hold_time_ms": _num("What the sized bank actually delivers."),
        "passes": _bool("True when achieved meets or exceeds required."),
        "required_capacitance_uf": _num("Effective capacitance the physics demands (I·t/ΔV)."),
        "effective_capacitance_uf": _num("Effective capacitance the sized part delivers."),
        "marked_capacitance_uf": _num("The reel value you must buy to get that effective value."),
        "shortfall_uf": _num("Effective capacitance still missing; zero when the design passes."),
        "required_marked_capacitance_uf": _num("Alias of marked_capacitance_uf, kept for clarity."),
        "load_current_ma": _num("Load current used."),
        "v_start": _num("Rail voltage at the start of the outage, after any diode drop."),
        "v_floor": _num("Brown-out floor the rail must stay above."),
        "margin_ms": _num("Achieved minus required; negative means the design fails."),
        "notes": NOTES_SCHEMA,
    },
}


RC_FILTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "nominal_cutoff_hz",
        "actual_cutoff_hz",
        "drift_pct",
        "marked_capacitance_uf",
        "effective_capacitance_uf",
        "retention_fraction",
        "resistance_ohm",
        "tolerance_included",
        "confidence",
        "notes",
    ],
    "properties": {
        "nominal_cutoff_hz": _num("Cutoff computed from the marked capacitance."),
        "actual_cutoff_hz": _num("Cutoff computed from the capacitance the part really has."),
        "drift_pct": _num("Percentage the cutoff moved; positive means it went higher."),
        "marked_capacitance_uf": _num("Marked capacitance used."),
        "effective_capacitance_uf": _num("Effective capacitance at operating conditions."),
        "retention_fraction": _num("effective / marked."),
        "resistance_ohm": _num("Series resistance used."),
        "tolerance_included": _bool("Whether part tolerance was folded in (default: no, to isolate bias drift)."),
        "confidence": {
            "type": "string",
            "enum": ["measured", "band", "physical"],
            "description": "Trust level of the underlying capacitance figure.",
        },
        "notes": NOTES_SCHEMA,
    },
}


DIVIDER_TOLERANCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "v_in",
        "v_out_nominal",
        "r1_ohm",
        "r2_ohm",
        "v_out_min",
        "v_out_max",
        "v_out_worst_min",
        "v_out_worst_max",
        "error_rss_pct",
        "error_worst_pct",
        "dominant_resistor",
        "sensitivity_r1",
        "sensitivity_r2",
        "method",
        "notes",
    ],
    "properties": {
        "v_in": _num("Input voltage to the divider."),
        "v_out_nominal": _num("Output at nominal resistor values."),
        "r1_ohm": _num("High-side resistor."),
        "r2_ohm": _num("Low-side resistor."),
        "v_out_min": _num("Statistical lower bound (sensitivity RSS)."),
        "v_out_max": _num("Statistical upper bound (sensitivity RSS)."),
        "v_out_worst_min": _num("Exact worst-case lower bound (corner enumeration)."),
        "v_out_worst_max": _num("Exact worst-case upper bound (corner enumeration)."),
        "error_rss_pct": _num("Statistical error band as a percentage of nominal."),
        "error_worst_pct": _num("Worst-case error as a percentage of nominal."),
        "dominant_resistor": {
            "type": "string",
            "enum": ["r1", "r2"],
            "description": "Which resistor contributes more error — fix this one first.",
        },
        "sensitivity_r1": _num("∂V_out/∂R1, in volts per ohm."),
        "sensitivity_r2": _num("∂V_out/∂R2, in volts per ohm."),
        "method": _str("Which methods were used, so the numbers are auditable."),
        "notes": NOTES_SCHEMA,
    },
}


RESISTOR_BUDGET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["value_band", "dominance"],
    "properties": {
        "value_band": {
            "type": "object",
            "required": [
                "nominal_ohm",
                "min_ohm",
                "max_ohm",
                "worst_case_min_ohm",
                "worst_case_max_ohm",
                "tolerance_pct",
                "tcr_pct",
                "life_drift_pct",
                "rss_total_pct",
                "linear_total_pct",
                "dominant_term",
            ],
            "properties": {
                "nominal_ohm": _num("Marked resistance."),
                "min_ohm": _num("RSS lower bound at end of life."),
                "max_ohm": _num("RSS upper bound at end of life."),
                "worst_case_min_ohm": _num("Linear-sum lower bound (everything at its worst)."),
                "worst_case_max_ohm": _num("Linear-sum upper bound."),
                "tolerance_pct": _num("Value tolerance contribution."),
                "tcr_pct": _num("Temperature coefficient contribution over the stated excursion."),
                "life_drift_pct": _num("Life drift contribution, scaled by sqrt of the time ratio."),
                "rss_total_pct": _num("Combined RSS total."),
                "linear_total_pct": _num("Combined linear total."),
                "dominant_term": {
                    "type": "string",
                    "enum": ["tolerance", "tcr", "life_drift"],
                    "description": "Which term to attack first.",
                },
            },
        },
        "dominance": {
            "type": "object",
            "required": ["tcr_pct", "tolerance_pct", "dominant", "combined_rss_pct", "recommendation"],
            "properties": {
                "tcr_pct": _num("TCR contribution as a percentage."),
                "tolerance_pct": _num("Tolerance contribution as a percentage."),
                "dominant": {
                    "type": "string",
                    "enum": ["tcr", "tolerance", "comparable", "none"],
                    "description": "The limiting error source.",
                },
                "combined_rss_pct": _num("Combined RSS of the two."),
                "recommendation": _str("What to change, in plain language."),
            },
        },
    },
}


FEEDBACK_DIVIDER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["v_out_target", "v_ref", "r1_ohm", "r2_ohm", "v_out_actual", "snap_error_pct", "note"],
    "properties": {
        "v_out_target": _num("Requested output voltage."),
        "v_ref": _num("Reference voltage at the feedback midpoint."),
        "r1_ohm": _num("Snapped E96 high-side resistor."),
        "r2_ohm": _num("Snapped E96 low-side resistor."),
        "v_out_actual": _num("Output the snapped pair actually produces."),
        "snap_error_pct": _num("Static offset from E96 quantisation — a wrongness, not a tolerance."),
        "note": _str("Why the snap error must be budgeted separately from the tolerance band."),
    },
}


#: Tool name → output schema. Merged into ``AVAILABLE_TOOLS`` at import time.
OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "calculate_effective_capacitance": EFFECTIVE_CAPACITANCE_SCHEMA,
    "size_hold_up_capacitor": HOLD_UP_SCHEMA,
    "analyze_rc_filter_effective": RC_FILTER_SCHEMA,
    "analyze_divider_tolerance": DIVIDER_TOLERANCE_SCHEMA,
    "analyze_resistor_error_budget": RESISTOR_BUDGET_SCHEMA,
    "solve_feedback_divider": FEEDBACK_DIVIDER_SCHEMA,
}
