"""CircuitBlocks DSL & Parameterized Hardware Modules Specification (Public Edition)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CircuitComponent:
    ref: str
    kind: str  # RESISTOR, CAPACITOR, IC, DIODE, CONNECTOR, SWITCH, etc.
    value: str
    package: str
    lcsc: str = ""
    pins: dict[str, str] = field(default_factory=dict)


@dataclass
class CircuitBlock:
    name: str
    description: str
    components: list[CircuitComponent] = field(default_factory=list)
    nets: dict[str, list[str]] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)


def block_usb_c_power(vbus_net: str = "/VBUS", gnd_net: str = "/GND") -> CircuitBlock:
    """Type-C receptacle with dual 5.1k CC pull-down resistors."""
    return CircuitBlock(
        name="USB_C_Power",
        description="USB Type-C power input with dual 5.1k CC pull-downs",
        components=[
            CircuitComponent("J_USB1", "CONNECTOR", "USB-C-16P", "USB-C-16P-SMD", "C7204555",
                             {"A5": "/CC1", "B5": "/CC2", "VBUS": vbus_net, "GND": gnd_net}),
            CircuitComponent("R_CC1", "RESISTOR", "5.1k", "R0603", "C23186", {"1": "/CC1", "2": gnd_net}),
            CircuitComponent("R_CC2", "RESISTOR", "5.1k", "R0603", "C23186", {"1": "/CC2", "2": gnd_net}),
        ],
        nets={
            vbus_net: ["J_USB1.VBUS"],
            gnd_net: ["J_USB1.GND", "R_CC1.2", "R_CC2.2"],
            "/CC1": ["J_USB1.A5", "R_CC1.1"],
            "/CC2": ["J_USB1.B5", "R_CC2.1"],
        },
    )


def block_power_ldo_3v3(vin_net: str = "/VBUS", vout_net: str = "/+3.3V", gnd_net: str = "/GND") -> CircuitBlock:
    """AMS1117-3.3V power regulator sub-circuit with input/output bulk capacitors."""
    return CircuitBlock(
        name="LDO_3V3",
        description="AMS1117-3.3 LDO Regulator with 10uF input/output filter capacitors",
        components=[
            CircuitComponent("U_LDO1", "IC", "AMS1117-3.3", "SOT-223", "C6186",
                             {"1": gnd_net, "2": vout_net, "3": vin_net}),
            CircuitComponent("C_IN1", "CAPACITOR", "10uF", "C0805", "C15849",
                             {"1": vin_net, "2": gnd_net}),
            CircuitComponent("C_OUT1", "CAPACITOR", "10uF", "C0805", "C15849",
                             {"1": vout_net, "2": gnd_net}),
        ],
        nets={
            vin_net: ["U_LDO1.3", "C_IN1.1"],
            vout_net: ["U_LDO1.2", "C_OUT1.1"],
            gnd_net: ["U_LDO1.1", "C_IN1.2", "C_OUT1.2"],
        },
    )


def block_button(btn_ref: str = "SW1", pin_net: str = "/BTN1", gnd_net: str = "/GND", vcc_net: str = "/+3.3V") -> CircuitBlock:
    """Tactile button with pull-up resistor and 100nF debounce capacitor."""
    return CircuitBlock(
        name=f"Button_{btn_ref}",
        description=f"Debounced tactile switch {btn_ref}",
        components=[
            CircuitComponent(btn_ref, "SWITCH", "TactSwitch", "SW-SMD_4P-3X6", "C26638", {"1": pin_net, "2": gnd_net}),
            CircuitComponent(f"R_{btn_ref}", "RESISTOR", "10k", "R0603", "C25804", {"1": pin_net, "2": vcc_net}),
            CircuitComponent(f"C_{btn_ref}", "CAPACITOR", "100nF", "C0603", "C14663", {"1": pin_net, "2": gnd_net}),
        ],
        nets={
            pin_net: [f"{btn_ref}.1", f"R_{btn_ref}.1", f"C_{btn_ref}.1"],
            vcc_net: [f"R_{btn_ref}.2"],
            gnd_net: [f"{btn_ref}.2", f"C_{btn_ref}.2"],
        },
    )
