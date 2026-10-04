"""Tests for Power Tree analysis, IPC-2221B clearance calculation, and Differential Bus Termination ERC.

Benchmark authorities:
- JITX / atopile / Altium Power Analyzer power architecture methodology
- IPC-2221B Table 6-1 conductor spacing rules
- ISO 11898-2 CAN / TIA/EIA-485-A 120R differential termination
"""

import pytest

from client.erc import erc_allowed, run_erc
from client.parametric_equations import calculate_ipc2221_clearance
from client.power_tree import analyze_power_tree
from client.synthesizer import synthesize_from_prompt


def test_power_tree_stm32_full_system():
    """Synthesize STM32 + LDO + CAN + RS485 and verify power tree nodes & thermals."""
    res = synthesize_from_prompt("STM32F103 CAN RS485 USB-C LDO")
    pt = analyze_power_tree(res["modules"], res["netlist"]["connections"])
    assert len(pt.rails) >= 2
    assert "/VBUS" in pt.root_sources or "/+3.3V" in [r.net for r in pt.rails]
    assert len(pt.converters) >= 1

    ldo = next(c for c in pt.converters if c.ref == "U_LDO1")
    assert ldo.vin_v == 5.0 and ldo.vout_v == 3.3
    assert ldo.dropout_margin_v == pytest.approx(0.6, abs=0.1)  # 5 - 3.3 - 1.1 = 0.6V margin
    assert ldo.power_loss_typ_mw > 0
    assert ldo.thermal_status in ("OK", "WARN")
    assert pt.total_system_power_typ_mw > 0


def test_power_tree_overload_alert():
    """Exceeding 800mA AMS1117 rating flags overload alert."""
    fake_modules = {
        "U_LDO1": {"kind": "IC", "value": "AMS1117-3.3"},
        "MCU1": {"kind": "MCU", "value": "ESP32-S3"},  # 380mA
        "MCU2": {"kind": "MCU", "value": "ESP32-S3"},  # 380mA
        "MCU3": {"kind": "MCU", "value": "ESP32-S3"},  # 380mA -> >1000mA peak
    }
    fake_connections = [
        {"net": "/VBUS", "points": ["U_LDO1.3"]},
        {"net": "/+3.3V", "points": ["U_LDO1.2", "MCU1.VDD", "MCU2.VDD", "MCU3.VDD"]},
    ]
    pt = analyze_power_tree(fake_modules, fake_connections)
    assert pt.has_overload_risk is True
    assert "Overload alert" in pt.summary


def test_ipc2221_clearance_calculation():
    """Verify IPC-2221B Table 6-1 conductor spacing tiers across B1, B2, B4, A6."""
    # 5V (<=15V tier)
    c5 = calculate_ipc2221_clearance(5.0, "B2")
    assert c5["min_clearance_mm"] == 0.10
    assert c5["voltage_tier"] == "≤15V"

    # 48V (<=50V tier, external uncoated B2 requires 0.60mm)
    c48 = calculate_ipc2221_clearance(48.0, "B2")
    assert c48["min_clearance_mm"] == 0.60

    # 48V coated B4 requires only 0.13mm
    c48_coated = calculate_ipc2221_clearance(48.0, "B4")
    assert c48_coated["min_clearance_mm"] == 0.13

    # High voltage 230V mains (<=250V tier, B2 requires 1.25mm)
    c230 = calculate_ipc2221_clearance(230.0, "B2")
    assert c230["min_clearance_mm"] == 1.25

    # Ultra high voltage 600V (>500V tier, linear extrapolation 2.50 + 100 * 0.005 = 3.00mm)
    c600 = calculate_ipc2221_clearance(600.0, "B2")
    assert c600["min_clearance_mm"] == pytest.approx(3.00, abs=0.01)


def test_erc_differential_bus_termination():
    """Detect missing 120R termination across CAN or RS-485 bus."""
    # Block CAN transceiver without termination resistor
    modules_no_term = {
        "U_CAN": {"kind": "IC", "value": "SN65HVD230"},
        "R_GND": {"kind": "RESISTOR", "value": "10k"},
        "J1": {"kind": "CONNECTOR", "value": "HDR-3P"},
        "C_PWR": {"kind": "CAPACITOR", "value": "100nF"},
    }
    conns_no_term = [
        {"net": "/GND", "points": ["U_CAN.2", "R_GND.1", "J1.3", "C_PWR.2"]},
        {"net": "/CAN_H", "points": ["U_CAN.7", "J1.1"]},
        {"net": "/CAN_L", "points": ["U_CAN.6", "J1.2"]},
        {"net": "/+3.3V", "points": ["U_CAN.3", "C_PWR.1"]},
    ]
    issues = run_erc(modules_no_term, conns_no_term)
    codes = {i["code"] for i in issues}
    assert "MISSING_BUS_TERMINATION" in codes
    assert erc_allowed(issues) is True  # Warning level does not block

    # Add 120R termination bridging CAN_H and CAN_L -> Warning eliminated
    modules_with_term = dict(modules_no_term)
    modules_with_term["R_TERM"] = {"kind": "RESISTOR", "value": "120R"}
    conns_with_term = [
        {"net": "/GND", "points": ["U_CAN.2", "R_GND.1", "J1.3", "C_PWR.2"]},
        {"net": "/CAN_H", "points": ["U_CAN.7", "J1.1", "R_TERM.1"]},
        {"net": "/CAN_L", "points": ["U_CAN.6", "J1.2", "R_TERM.2"]},
        {"net": "/+3.3V", "points": ["U_CAN.3", "C_PWR.1"]},
    ]

    issues2 = run_erc(modules_with_term, conns_with_term)
    codes2 = {i["code"] for i in issues2}
    assert "MISSING_BUS_TERMINATION" not in codes2


def test_mcp_tool_analyze_power_tree():
    """MCP tool execution test for analyze_power_tree."""
    from client.mcp_server import handle_tool_call

    res = synthesize_from_prompt("ESP32-C3 USB-C LDO")
    out = handle_tool_call(
        "analyze_power_tree",
        {
            "modules": res["modules"],
            "netlist": res["netlist"],
            "ambient_temp_c": 30.0,
        },
    )
    assert "isError" not in out
    import json

    data = json.loads(out["content"][0]["text"])
    assert "rails" in data and "converters" in data
    assert "total_system_power_typ_mw" in data


def test_mcp_tool_calculate_ipc2221_clearance():
    """MCP tool execution test for calculate_ipc2221_clearance."""
    from client.mcp_server import handle_tool_call

    out = handle_tool_call(
        "calculate_ipc2221_clearance",
        {
            "peak_voltage_v": 24.0,
            "conductor_type": "B2",
        },
    )
    assert "isError" not in out
    import json

    data = json.loads(out["content"][0]["text"])
    assert data["min_clearance_mm"] == 0.10
    assert "IPC-2221B" in data["standard"]
