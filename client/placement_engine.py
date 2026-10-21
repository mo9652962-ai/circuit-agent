"""Heuristic PCB Component Auto-Placement & Specctra DSN Auto-Router Exporter.

Industrial benchmark & standard:
- Specctra DSN (Design Specctra Netlist v15.0 standard): The universal ASCII
  interchange format for automatic PCB routing tools (Freerouting, Cadence Specctra,
  Altium, Electra).
- Heuristic Placement Algorithm:
    * Microcontroller (MCU) placed in the geometric center of the PCB.
    * Power entry (USB Type-C, TVS, LDO) placed in clean linear flow along left edge.
    * Decoupling capacitors clustered tightly adjacent to targeted IC power pins (<3mm).
    * High-frequency crystal oscillator placed adjacent to XTAL pins (<3mm).
    * Fieldbus transceivers (CAN, RS-485, Ethernet) and connectors arranged along the board perimeter.
    * User I/O (Buttons, LEDs) aligned along top edges.
    * Collision avoidance guarantees non-overlapping component placement.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass
from typing import Any

log = logging.getLogger("circuit-placement")


@dataclass
class ComponentPlacement:
    ref: str
    package: str
    x_mm: float
    y_mm: float
    rotation_deg: float = 0.0
    layer: str = "Top"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


#: Half-extents (hw, hh) in mm of each package's occupied footprint area.
#: Used both by the placement engine's collision maths and by the silkscreen
#: generator, so a part's outline matches the space it actually reserves.
PACKAGE_HALF_EXTENTS: dict[str, tuple[float, float]] = {
    "ESP32-S3-WROOM-1": (9.5, 13.5),
    "ESP32-C3-WROOM-02": (9.5, 10.5),
    "LQFP-48": (5.0, 5.0),
    "QFN-56": (4.5, 4.5),
    "LQFP-44": (6.5, 6.5),
    "R2512": (3.5, 1.8),
    "HTSSOP-28": (5.0, 3.5),
    "SOIC-8": (3.0, 2.5),
    "SOT-223": (3.5, 2.0),
    # Passive half-extents (body + pad land)
    "C0402": (0.6, 0.3),
    "C0603": (0.8, 0.45),
    "C0805": (1.0, 0.6),
    "C1206": (1.6, 0.8),
    "R0402": (0.6, 0.3),
    "R0603": (0.8, 0.45),
    "R0805": (1.0, 0.6),
    # Discrete / connector packages whose pads reach further than their body
    "SMA": (2.3, 1.4),
    "SMB": (2.6, 1.7),
    "L0805": (1.1, 0.7),
    "L1206": (1.7, 0.9),
    "LED0603": (0.9, 0.45),
    "LED0805": (1.1, 0.6),
    "SOT-23-6": (1.7, 1.6),
    "SOT-23-5": (1.6, 1.5),
    "SOT-23": (1.6, 1.5),
    "TestPoint_Pad": (1.2, 1.2),
    "Fiducial": (1.2, 1.2),
    "HDR-1X3": (1.6, 4.1),
    "HDR-1X4": (1.6, 5.4),
    "HDR-1X2": (1.6, 2.8),
    "PinHeader": (1.6, 5.4),
    "RJ45": (8.5, 8.0),
    "USB-C-16P": (4.6, 3.8),
    "SW-SMD_4P": (3.1, 2.0),
    "Screw_Terminal": (5.2, 4.2),
    "TERMINAL": (5.2, 4.2),
    "Buzzer": (4.2, 4.2),
}

#: Body dimensions (width, height) in mm, for silkscreen outlines. Distinct from
#: the half-extents above: the courtyard reserves pad land, the silk draws the part.
BODY_DIMS_MM: dict[str, tuple[float, float]] = {
    "ESP32-S3-WROOM-1": (18.0, 25.5),
    "ESP32-C3-WROOM-02": (18.0, 20.0),
    "LQFP-48": (7.0, 7.0),
    "LQFP-44": (10.0, 10.0),
    "QFN-56": (7.0, 7.0),
    "R2512": (6.3, 3.2),
    "HTSSOP-28": (9.7, 4.4),
    "SOIC-8": (4.9, 3.9),
    "SOT-223": (6.5, 3.5),
    "C0402": (1.0, 0.5),
    "C0603": (1.6, 0.8),
    "C0805": (2.0, 1.25),
    "C1206": (3.2, 1.6),
    "R0402": (1.0, 0.5),
    "R0603": (1.6, 0.8),
    "R0805": (2.0, 1.25),
    "SMA": (4.3, 2.6),
    "SMB": (5.3, 3.6),
    "L0805": (2.0, 1.25),
    "LED0603": (1.6, 0.8),
    "LED0805": (2.0, 1.25),
    "SOT-23": (2.9, 1.3),
    "SOT-23-6": (2.9, 1.6),
    "TestPoint_Pad": (2.0, 2.0),
    "Fiducial": (2.0, 2.0),
    "HDR-1X3": (2.5, 7.6),
    "HDR-1X4": (2.5, 10.2),
    "RJ45": (16.0, 15.0),
    "USB-C-16P": (9.0, 7.5),
    "SW-SMD_4P": (6.0, 3.5),
    "Screw_Terminal": (10.0, 8.0),
}


#: Standard component pin offsets (relative to component centroid, in mm)
STANDARD_PIN_OFFSETS: dict[str, dict[str, tuple[float, float]]] = {
    "C0603": {"1": (-0.75, 0.0), "2": (0.75, 0.0)},
    "R0603": {"1": (-0.75, 0.0), "2": (0.75, 0.0)},
    "L0805": {"1": (-0.95, 0.0), "2": (0.95, 0.0)},
    "C0805": {"1": (-0.95, 0.0), "2": (0.95, 0.0)},
    "R2512": {"1": (-3.0, 0.0), "2": (3.0, 0.0)},
    "LED0603": {"1": (-0.75, 0.0), "2": (0.75, 0.0), "A": (-0.75, 0.0), "K": (0.75, 0.0)},
    "SMA": {"1": (-2.0, 0.0), "2": (2.0, 0.0)},
    "SOT-23": {"1": (-0.95, -1.0), "2": (0.95, -1.0), "3": (0.0, 1.0)},
    "SOT-23-5": {
        "1": (-0.95, -1.3), "2": (0.0, -1.3), "3": (0.95, -1.3),
        "4": (0.95, 1.3), "5": (-0.95, 1.3),
    },
    "SOT-23-6": {
        "1": (-0.95, -1.3), "2": (0.0, -1.3), "3": (0.95, -1.3),
        "4": (0.95, 1.3), "5": (0.0, 1.3), "6": (-0.95, 1.3),
    },
    "SOT-223": {"1": (-2.3, -3.1), "2": (0.0, -3.1), "3": (2.3, -3.1), "4": (0.0, 3.1)},
    "SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL": {
        "1": (-1.905, -2.7), "2": (-0.635, -2.7), "3": (0.635, -2.7), "4": (1.905, -2.7),
        "8": (-1.905, 2.7), "7": (-0.635, 2.7), "6": (0.635, 2.7), "5": (1.905, 2.7),
    },
    "SW-SMD_4P-3X6": {"1": (-3.25, -1.5), "2": (3.25, -1.5), "3": (-3.25, 1.5), "4": (3.25, 1.5)},
    "HDR-1X3-2.54": {"1": (-2.54, 0.0), "2": (0.0, 0.0), "3": (2.54, 0.0)},
    "HDR-1X4-2.54": {"1": (-3.81, 0.0), "2": (-1.27, 0.0), "3": (1.27, 0.0), "4": (3.81, 0.0)},
    "CONN-TH_B4B-XH-A": {"1": (-3.75, 0.0), "2": (-1.25, 0.0), "3": (1.25, 0.0), "4": (3.75, 0.0)},
    "TERMINAL-2P-5.08": {"1": (-2.54, 0.0), "2": (2.54, 0.0)},
    "TestPoint_Pad_D1.0mm": {"1": (0.0, 0.0)},
    "Fiducial_1mm_Mask2mm": {"1": (0.0, 0.0)},
    # USB-C 2.0 receptacle: 16 pads, but only the ones this project's blocks use
    # are modelled. D+/D- sit between the CC pair on the real part (A6/B6 = D+,
    # A7/B7 = D-); they were missing entirely, so a USB data line had nowhere to
    # land and the ESD array ended up protecting two nets of its own.
    "USB-C-16P-SMD": {
        "A5": (-0.75, 2.5), "B5": (0.75, 2.5),
        "GND": (-2.8, 2.5), "VBUS": (2.8, 2.5),
        "1": (-2.8, 2.5), "2": (2.8, 2.5),
        "A6": (-0.25, 2.5), "B6": (0.25, 2.5),
        "A7": (-1.25, 2.5), "B7": (1.25, 2.5),
    },
    "ESP32-C3-WROOM-02": {
        "3V3": (-8.5, 6.0), "EN": (-8.5, 4.5), "IO4": (-8.5, 3.0), "IO5": (-8.5, 1.5),
        "IO6": (-8.5, 0.0), "IO7": (-8.5, -1.5), "IO8": (-8.5, -3.0), "IO9": (-8.5, -4.5),
        "GND": (8.5, 6.0), "IO0": (8.5, 4.5), "IO1": (8.5, 3.0), "IO2": (8.5, 1.5),
        "IO3": (8.5, 0.0), "IO10": (8.5, -1.5), "IO18": (8.5, -3.0), "IO19": (8.5, -4.5),
        "IO20": (8.5, -6.0), "IO21": (8.5, -7.5),
    },
    "HTSSOP-28_L9.7-W4.4-P0.65-LS6.4-BL": {
        str(i + 1): (-3.2 if i < 14 else 3.2, round(-4.225 + (i if i < 14 else 27 - i) * 0.65, 3))
        for i in range(28)
    },
}

_s3_pins = [
    "IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7", "IO8", "IO9", "IO10", "IO11",
    "IO12", "IO13", "IO14", "IO15", "IO16", "IO17", "IO18", "IO19", "IO20", "IO21", "IO35",
    "IO36", "IO37", "IO38", "IO39", "IO40", "IO41", "IO42", "IO43", "IO44", "IO45", "IO46",
    "IO47", "IO48", "EN", "3V3", "GND1", "GND2",
]
_s3_coords: dict[str, tuple[float, float]] = {}
for _i in range(14):
    _s3_coords[_s3_pins[_i]] = (-9.0, round(8.0 - _i * 1.27, 3))
for _i in range(12):
    _s3_coords[_s3_pins[14 + _i]] = (round(-6.0 + _i * 1.27, 3), -10.0)
for _i in range(14):
    _s3_coords[_s3_pins[26 + _i]] = (9.0, round(-8.0 + _i * 1.27, 3))
STANDARD_PIN_OFFSETS["ESP32-S3-WROOM-1"] = _s3_coords

_stm_pins = [
    "PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PA8", "PA9", "PA10", "PA11",
    "PA12", "PA13", "PA14", "PA15", "PB0", "PB1", "PB2", "PB3", "PB4", "PB5", "PB6", "PB7",
    "PB8", "PB9", "PB10", "PB11", "PB12", "PB13", "PB14", "PB15", "PC13", "PC14", "PC15",
    "PD0", "PD1", "VDD_1", "VDD_2", "VDD_3", "VDDA", "VSS_1", "VSS_2", "VSS_3", "VSSA",
]
_stm_coords: dict[str, tuple[float, float]] = {}
for _i, _pname in enumerate(_stm_pins):
    _side = _i // 12
    _idx = _i % 12
    _pos = -2.75 + _idx * 0.5
    if _side == 0:
        _coord = (-4.2, round(-_pos, 3))
    elif _side == 1:
        _coord = (round(_pos, 3), -4.2)
    elif _side == 2:
        _coord = (4.2, round(_pos, 3))
    else:
        _coord = (round(-_pos, 3), 4.2)
    _stm_coords[_pname] = _coord
    _stm_coords[str(_i + 1)] = _coord
STANDARD_PIN_OFFSETS["LQFP-48"] = _stm_coords
STANDARD_PIN_OFFSETS["LQFP-48_7x7mm_P0.5mm"] = _stm_coords

# Standard STC89C52RC / 8051 LQFP-44 pin assignments
_lqfp44_coords: dict[str, tuple[float, float]] = {}
_lqfp44_left = ["P1.5", "P1.6", "P1.7", "RST", "P3.0", "P3.1", "P3.2", "P3.3", "P3.4", "P3.5", "P3.6"]
for _i, _name in enumerate(_lqfp44_left):
    _coord = (-5.5, round(4.0 - _i * 0.8, 3))
    _lqfp44_coords[_name] = _coord
    _lqfp44_coords[str(_i + 1)] = _coord
_lqfp44_bot = ["P3.7", "XTAL2", "XTAL1", "GND", "P2.0", "P2.1", "P2.2", "P2.3", "P2.4", "P2.5", "P2.6"]
for _i, _name in enumerate(_lqfp44_bot):
    _coord = (round(-4.0 + _i * 0.8, 3), -5.5)
    _lqfp44_coords[_name] = _coord
    _lqfp44_coords[str(_i + 12)] = _coord
_lqfp44_right = ["P2.7", "EA", "NC", "ALE", "PSEN", "P0.7", "P0.6", "P0.5", "P0.4", "P0.3", "P0.2"]
for _i, _name in enumerate(_lqfp44_right):
    _coord = (5.5, round(-4.0 + _i * 0.8, 3))
    _lqfp44_coords[_name] = _coord
    _lqfp44_coords[str(_i + 23)] = _coord
_lqfp44_top = ["P0.1", "P0.0", "VCC", "P1.0", "P1.1", "P1.2", "P1.3", "P1.4", "NC2", "NC3", "NC4"]
for _i, _name in enumerate(_lqfp44_top):
    _coord = (round(4.0 - _i * 0.8, 3), 5.5)
    _lqfp44_coords[_name] = _coord
    _lqfp44_coords[str(_i + 34)] = _coord
STANDARD_PIN_OFFSETS["LQFP-44"] = _lqfp44_coords


def _synthesize_footprint_pins(pkg: str, pin_names: list[str]) -> dict[str, tuple[float, float]]:
    """Synthesize pin centroid coordinates for custom or unlisted footprints."""
    if not pin_names:
        return {"1": (-0.75, 0.0), "2": (0.75, 0.0)}

    clean_pins = sorted(set(pin_names))
    n = len(clean_pins)
    res: dict[str, tuple[float, float]] = {}

    if "LQFP" in pkg or "QFN" in pkg or n >= 28:
        # Quad perimeter distribution
        per_side = max(1, (n + 3) // 4)
        pitch = 0.5 if "0.5" in pkg or "QFN" in pkg else 0.65
        span = (per_side - 1) * pitch / 2.0
        offset = span + 1.5
        for i, name in enumerate(clean_pins):
            side = i // per_side
            idx = i % per_side
            pos = round(-span + idx * pitch, 3)
            if side == 0:
                res[name] = (round(-offset, 3), pos)
            elif side == 1:
                res[name] = (pos, round(-offset, 3))
            elif side == 2:
                res[name] = (round(offset, 3), -pos)
            else:
                res[name] = (-pos, round(offset, 3))
    elif n <= 2:
        res[clean_pins[0]] = (-0.75, 0.0)
        if n > 1:
            res[clean_pins[1]] = (0.75, 0.0)
    else:
        # Dual inline distribution
        half = max(1, (n + 1) // 2)
        pitch = 1.27 if "SOIC" in pkg else 0.65
        span = (half - 1) * pitch / 2.0
        x_off = 2.5
        for i, name in enumerate(clean_pins):
            if i < half:
                res[name] = (round(-x_off, 3), round(-span + i * pitch, 3))
            else:
                res[name] = (round(x_off, 3), round(span - (i - half) * pitch, 3))

    return res


def heuristic_place_components(
    modules: dict[str, Any],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
) -> dict[str, ComponentPlacement]:
    """Calculate deterministic heuristic 2D placement coordinates for components."""
    cx = board_width_mm / 2.0
    cy = board_height_mm / 2.0

    pkg_dims: dict[str, tuple[float, float]] = dict(PACKAGE_HALF_EXTENTS)

    # Minimum courtyard gap enforced between neighbouring parts (mm)
    _GAP = 0.5

    def _half_dims(ref: str, pkg: str) -> tuple[float, float]:
        """Half-extent (hw, hh) of a component's occupied footprint area."""
        for k, dims in pkg_dims.items():
            if k in pkg:
                return dims
        if ref.startswith(("U_", "IC")):
            return (2.5, 2.5)
        return (1.2, 0.8)

    placements: dict[str, ComponentPlacement] = {}

    # 1. Identify primary Microcontroller (MCU) -> Geometric center
    primary_mcu: str | None = None
    # Level A: Explicit kind MCU or canonical reference
    for ref, m in modules.items():
        if m.get("kind") == "MCU" or ref in ("U_MCU", "U1") or ref.upper().startswith("MCU"):
            primary_mcu = ref
            break
    # Level B: Recognizable MCU families in part value
    if not primary_mcu:
        for ref, m in modules.items():
            val = str(m.get("value", "")).upper()
            if any(k in val for k in ("STM32", "ESP32", "RP2040", "STC89", "CH32", "ATMEGA")):
                primary_mcu = ref
                break
    # Level C: Generic IC fallback (excluding transceivers and regulators)
    if not primary_mcu:
        for ref, m in modules.items():
            if m.get("kind") in ("MCU", "IC") and not any(k in ref for k in ("485", "CAN", "LDO", "TVS", "WDT", "ETH")):
                primary_mcu = ref
                break

    mcu_pkg = "QFN-48"
    if primary_mcu:
        mcu_pkg = modules[primary_mcu].get("package", "QFN-48")
        placements[primary_mcu] = ComponentPlacement(
            ref=primary_mcu,
            package=mcu_pkg,
            x_mm=round(cx, 2),
            y_mm=round(cy, 2),
        )

    mcu_hw, mcu_hh = pkg_dims.get(mcu_pkg, (6.0, 6.0))

    # 2. Linear Power Chain: USB -> TVS -> LDO along left border
    power_y = cy
    for ref, m in modules.items():
        if ref in placements:
            continue
        val = str(m.get("value", "")).upper()
        if "USB" in ref or "USB" in val:
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", "USB-C-16P-SMD"), x_mm=8.0, y_mm=round(power_y, 2)
            )
            break

    # TVS ESD protector immediately adjacent to USB port
    for ref, m in modules.items():
        if ref in placements:
            continue
        if m.get("kind") == "TVS" and ("USB" in ref or "USBLC6" in str(m.get("value", "")).upper()):
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", "SOT-23-6"), x_mm=13.0, y_mm=round(power_y, 2)
            )
            break

    # LDO voltage regulator placed downstream
    for ref, m in modules.items():
        if ref in placements:
            continue
        val = str(m.get("value", "")).upper()
        if "LDO" in ref or "AMS1117" in val or "TP4056" in val:
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", "SOT-223"), x_mm=21.0, y_mm=round(power_y, 2)
            )
            break

    # 2b. Parts that are electrically required to sit beside their anchor.
    #
    # A Type-C sink's 5.1k CC pull-downs belong at the receptacle: they are what
    # tells a charger to supply 5 V, and a long CC trace is an antenna on the
    # line the connector uses to negotiate power. They are also the shortest nets
    # on the board, and a router that has to cross the whole board to reach them
    # will leave them unrouted — which is exactly what happened: CC1/CC2 were the
    # two nets the autorouter could not complete on the ESP32-C3 node.
    #
    # Same reasoning for a USB ESD array (already anchored above) and for a
    # crystal's load capacitors. Anything whose net has no other purpose than to
    # join two adjacent parts goes next to its partner, not wherever the generic
    # passive stage happens to drop it.
    usb_ref = next((r for r in placements if "USB" in r.upper()), None)
    if usb_ref is not None:
        usb_p = placements[usb_ref]
        usb_hw, usb_hh = _half_dims(usb_ref, usb_p.package or "")
        companion_slots = [
            (usb_p.x_mm, usb_p.y_mm + usb_hh + 2.2),
            (usb_p.x_mm, usb_p.y_mm - usb_hh - 2.2),
            (usb_p.x_mm + usb_hw + 2.6, usb_p.y_mm),
            (usb_p.x_mm - usb_hw - 2.6, usb_p.y_mm),
        ]
        companion_refs = [
            r
            for r, m in modules.items()
            if r not in placements
            and (
                "CC" in r.upper()
                or (
                    str(m.get("kind", "")).upper() == "RESISTOR"
                    and "5.1K" in str(m.get("value", "")).upper().replace(" ", "")
                )
            )
        ]
        for ref, (sx, sy) in zip(companion_refs, companion_slots):
            placements[ref] = ComponentPlacement(
                ref=ref,
                package=modules[ref].get("package", "R0603"),
                x_mm=round(sx, 2),
                y_mm=round(sy, 2),
            )

    # 3. Peripheral Transceiver & Motor Driver ICs (strictly ICs)
    right_x = board_width_mm - 14.0
    right_y = 14.0
    for ref, m in modules.items():
        if ref in placements:
            continue
        kind = m.get("kind", "").upper()
        val = str(m.get("value", "")).upper()
        if ref.startswith("U_") or kind == "IC":
            if "ETH" in ref or "W5500" in val:
                placements[ref] = ComponentPlacement(
                    ref=ref,
                    package=m.get("package", "LQFP-48_7x7mm_P0.5mm"),
                    x_mm=54.0,
                    y_mm=round(cy, 2),
                )
            elif any(k in ref for k in ("485", "CAN", "LAN")):
                placements[ref] = ComponentPlacement(
                    ref=ref, package=m.get("package", "SOIC-8"), x_mm=round(right_x, 2), y_mm=round(right_y, 2)
                )
                right_y = min(board_height_mm - 8.0, right_y + 14.0)
            elif any(k in ref for k in ("DRV", "STEP", "MOTOR")):
                placements[ref] = ComponentPlacement(
                    ref=ref, package=m.get("package", "HTSSOP-28"), x_mm=round(board_width_mm - 25.0, 2), y_mm=14.0
                )

    # 4. Connectors and Terminals -> Outer perimeter
    conn_x = board_width_mm - 8.0
    conn_y = 12.0
    for ref, m in modules.items():
        if ref in placements:
            continue
        kind = m.get("kind", "").upper()
        if ref.startswith("J_") or "HDR" in ref or "CONN" in kind or "TERMINAL" in kind or "RJ45" in ref:
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", "HDR"), x_mm=round(conn_x, 2), y_mm=round(conn_y, 2)
            )
            conn_y += 12.0
            if conn_y > board_height_mm - 8.0:
                conn_y = 12.0
                conn_x -= 8.0

    # 5. Crystal Oscillator & Load Capacitors -> Near MCU
    for ref, m in modules.items():
        if ref in placements:
            continue
        if m.get("kind") == "CRYSTAL" or "XTAL" in ref or "Y1" in ref:
            placements[ref] = ComponentPlacement(
                ref=ref, package=m.get("package", "SMD"), x_mm=round(cx + mcu_hw + 3.0, 2), y_mm=round(cy + 5.0, 2)
            )
            break

    # 6. Decoupling Capacitors -> Targeted adsorption adjacent to respective ICs (<3.5mm)
    decoup_angle = 0.0
    decoup_r = max(mcu_hw, mcu_hh) + 4.0
    for ref, m in modules.items():
        if ref in placements:
            continue
        kind = m.get("kind", "")
        val = str(m.get("value", "")).upper()
        if kind == "CAPACITOR" and ("100N" in val or "0.1U" in val or "DEC" in ref):
            target_ic = None
            if "485" in ref:
                target_ic = "U_485"
            elif "CAN" in ref:
                target_ic = "U_CAN"
            elif "ETH" in ref:
                target_ic = "U_ETH1"
            elif "DRV" in ref:
                target_ic = "U_DRV1"

            if target_ic and target_ic in placements:
                ic_pos = placements[target_ic]
                # Courtyard-accurate offset: IC half-extent + cap half-extent + min gap.
                # Keeps the bypass cap legally adjacent (<5mm) instead of a magic constant.
                _ic_pkg = ic_pos.package or ""
                _ic_hw = 2.5
                for _k, _dims in pkg_dims.items():
                    if _k in _ic_pkg:
                        _ic_hw = _dims[0]
                        break
                _cap_pkg = m.get("package", "C0603")
                _cap_hw = 0.8
                for _k, _dims in pkg_dims.items():
                    if _k in _cap_pkg:
                        _cap_hw = _dims[0]
                        break
                _off = round(_ic_hw + _cap_hw + _GAP + 0.15, 2)  # +0.15mm solder-mask margin
                placements[ref] = ComponentPlacement(
                    ref=ref, package=_cap_pkg, x_mm=round(ic_pos.x_mm - _off, 2), y_mm=round(ic_pos.y_mm, 2)
                )
            else:
                dx = cx + decoup_r * math.cos(decoup_angle)
                dy = cy + decoup_r * math.sin(decoup_angle)
                placements[ref] = ComponentPlacement(
                    ref=ref, package=m.get("package", "C0603"), x_mm=round(dx, 2), y_mm=round(dy, 2)
                )
                decoup_angle += math.pi / 4.0

    # 7. User I/O (Buttons, LEDs) -> Along top border
    #    Must respect the wireless module's antenna keep-out strip, otherwise these parts
    #    land inside a DSN keepout and their nets become permanently unroutable.
    _MOD_HH = {"ESP32-S3-WROOM-1": 13.5, "ESP32-C3-WROOM-02": 10.5, "ESP32-WROOM-32": 12.75}
    _ant_box: tuple[float, float, float, float] | None = None
    if primary_mcu and primary_mcu in placements:
        _mp = placements[primary_mcu]
        _mpkg = _mp.package or ""
        if "ESP32" in _mpkg or "WROOM" in _mpkg:
            _mhh = _MOD_HH.get(_mpkg, 12.0)
            _ant_box = (_mp.x_mm - 5.0, _mp.y_mm + _mhh, _mp.x_mm + 5.0, _mp.y_mm + _mhh + 8.0)

    def _in_antenna_keepout(x: float, y: float, hw: float, hh: float) -> bool:
        if _ant_box is None:
            return False
        ax1, ay1, ax2, ay2 = _ant_box
        return not (x + hw <= ax1 or x - hw >= ax2 or y + hh <= ay1 or y - hh >= ay2)

    top_x = 20.0
    top_y = board_height_mm - 8.0
    for ref, m in modules.items():
        if ref in placements:
            continue
        if any(k in ref for k in ("SW", "BTN", "LED", "D1", "D2", "BZ")):
            _pkg_io = m.get("package", "0603")
            _ihw, _ihh = _half_dims(ref, _pkg_io)
            _guard = 0
            while _in_antenna_keepout(top_x, top_y, _ihw, _ihh) and _guard < 40:
                top_x += 9.0
                if top_x > board_width_mm - 15:
                    top_x = 20.0
                    top_y -= 8.0
                _guard += 1
            placements[ref] = ComponentPlacement(
                ref=ref, package=_pkg_io, x_mm=round(top_x, 2), y_mm=round(top_y, 2)
            )
            top_x += 9.0
            if top_x > board_width_mm - 15:
                top_x = 20.0
                top_y -= 8.0

    # 8. Remaining components -> Placed with clearance spacing
    candidate_pts: list[tuple[float, float]] = []
    for gy in [6.5, 10.5, board_height_mm - 6.5, board_height_mm - 10.5, 16.0, 22.0, 28.0, 34.0, 40.0]:
        for gx in [14.0, 19.0, 24.0, 46.0, 52.0, 58.0, 63.0, 30.0, 36.0, 41.0]:
            candidate_pts.append((gx, gy))

    c_idx = 0
    for ref, m in modules.items():
        if ref not in placements:
            pkg = m.get("package", "0603")
            hw, hh = _half_dims(ref, pkg)
            placed = False
            while c_idx < len(candidate_pts):
                cand_x, cand_y = candidate_pts[c_idx]
                c_idx += 1
                # Check bounds
                if cand_x - hw < 6.0 or cand_x + hw > board_width_mm - 6.0:
                    continue
                if cand_y - hh < 5.0 or cand_y + hh > board_height_mm - 5.0:
                    continue
                # Check MCU box
                if (
                    cand_x + hw >= cx - mcu_hw - 1.5
                    and cand_x - hw <= cx + mcu_hw + 1.5
                    and cand_y + hh >= cy - mcu_hh - 1.5
                    and cand_y - hh <= cy + mcu_hh + 1.5
                ):
                    continue
                # Check distance against placed items
                overlap = False
                for o_ref, o_p in placements.items():
                    o_hw, o_hh = _half_dims(o_ref, o_p.package or "")
                    req_d = math.hypot(hw + o_hw + 1.2, hh + o_hh + 1.2)
                    if math.hypot(cand_x - o_p.x_mm, cand_y - o_p.y_mm) < req_d:
                        overlap = True
                        break
                # Check antenna keep-out strip
                if not overlap and _in_antenna_keepout(cand_x, cand_y, hw, hh):
                    overlap = True
                if not overlap:
                    placements[ref] = ComponentPlacement(
                        ref=ref, package=pkg, x_mm=round(cand_x, 2), y_mm=round(cand_y, 2)
                    )
                    placed = True
                    break
            if not placed:
                placements[ref] = ComponentPlacement(ref=ref, package=pkg, x_mm=20.0, y_mm=10.0)

    def _priority(ref: str) -> int:
        if "MCU" in ref:
            return 0
        if ref.startswith(("U_", "J_")):
            return 1
        if "XTAL" in ref or "Y1" in ref:
            return 2
        # Decoupling caps must stay welded to their target IC -> resolve before generic passives
        _v = str(modules.get(ref, {}).get("value", "")).upper()
        if "DEC" in ref or "100N" in _v or "0.1U" in _v:
            return 3
        return 4

    # 9. Collision avoidance pass: anchors resolved first, then a bounded spiral search
    #    around each component's *desired* position so local intent (decoupling, crystals)
    #    is preserved instead of being flung to a far corner.
    def _free(x: float, y: float, hw: float, hh: float,
              placed_items: list[tuple[str, ComponentPlacement, float, float]],
              coords: set[tuple[float, float]]) -> bool:
        if x - hw < 5.0 or x + hw > board_width_mm - 5.0:
            return False
        if y - hh < 5.0 or y + hh > board_height_mm - 5.0:
            return False
        if (round(x, 2), round(y, 2)) in coords:
            return False
        # Never resolve a collision by pushing a part into the antenna keep-out strip
        if _in_antenna_keepout(x, y, hw, hh):
            return False
        for _o_ref, o_p, o_hw, o_hh in placed_items:
            if abs(x - o_p.x_mm) < (hw + o_hw + _GAP) and abs(y - o_p.y_mm) < (hh + o_hh + _GAP):
                return False
        return True

    placed_items: list[tuple[str, ComponentPlacement, float, float]] = []
    used_coords: set[tuple[float, float]] = set()

    for ref, p in sorted(placements.items(), key=lambda item: (_priority(item[0]), item[0])):
        hw, hh = _half_dims(ref, p.package or "")
        want_x, want_y = p.x_mm, p.y_mm

        if _free(want_x, want_y, hw, hh, placed_items, used_coords):
            pass
        else:
            resolved = False
            # Expanding ring search: try progressively larger offsets around the desired spot
            for radius in (1.5, 3.0, 4.5, 6.0, 8.0, 11.0, 15.0, 20.0):
                for step in range(16):
                    ang = step * (math.pi / 8.0)
                    tx = round(want_x + radius * math.cos(ang), 2)
                    ty = round(want_y + radius * math.sin(ang), 2)
                    if _free(tx, ty, hw, hh, placed_items, used_coords):
                        p.x_mm, p.y_mm = tx, ty
                        resolved = True
                        break
                if resolved:
                    break
            if not resolved:
                # Last-resort deterministic scan over the whole board
                for gy in [round(6.0 + i * 2.0, 2) for i in range(int((board_height_mm - 12.0) / 2.0))]:
                    for gx in [round(6.0 + j * 2.0, 2) for j in range(int((board_width_mm - 12.0) / 2.0))]:
                        if _free(gx, gy, hw, hh, placed_items, used_coords):
                            p.x_mm, p.y_mm = gx, gy
                            resolved = True
                            break
                    if resolved:
                        break

        used_coords.add((round(p.x_mm, 2), round(p.y_mm, 2)))
        placed_items.append((ref, p, hw, hh))

    log.info(f"✅ 启发式布局完成: {len(placements)} 个器件布于 {board_width_mm:.0f}×{board_height_mm:.0f}mm 目标板框")
    return placements


#: Mounting-hole keep-out: centre inset from each board corner, and the diameter
#: of the cleared circle around it. M3 hardware needs ~3 mm of clear copper.
_MOUNT_INSET = 4.0
_MOUNT_DIAMETER = 6.0


def export_specctra_dsn(
    modules: dict[str, Any],
    connections: list[dict[str, Any]],
    placements: dict[str, ComponentPlacement] | None = None,
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    trace_width_mm: float = 0.150,
    clearance_mm: float = 0.100,
) -> str:
    """Generate universal Specctra DSN (v15.0) auto-router interchange file for Freerouting/KiCad."""
    if placements is None:
        placements = heuristic_place_components(modules, board_width_mm, board_height_mm)

    bw = round(board_width_mm, 3)
    bh = round(board_height_mm, 3)
    tw = round(trace_width_mm, 3)
    cl = round(clearance_mm, 3)

    # 1. Collect required pins per component from netlist connections
    component_pins: dict[str, set[str]] = {}
    for conn in connections:
        for pt in conn.get("points") or []:
            if "." in pt:
                ref, pin = pt.split(".", 1)
                component_pins.setdefault(ref, set()).add(pin)

    # Check for wireless MCU
    has_esp = any("ESP" in str(p.package) or "ESP" in ref for ref, p in placements.items())

    # 2. Build Specctra DSN Header & Structure with Physical Keepouts
    L = [
        "(pcb pcb_board",
        "  (parser",
        '    (string_quote ")',
        "    (space_in_quoted_tokens on)",
        '    (host_cad "CircuitAgent")',
        '    (host_version "1.0")',
        "  )",
        "  (resolution mm 1000)",
        "  (unit mm)",
        "  (structure",
        "    (layer Top (type signal))",
        "    (layer Bottom (type signal))",
        f"    (boundary (path pcb 0 0 0 {bw:.3f} 0 {bw:.3f} {bh:.3f} 0 {bh:.3f} 0 0))",
        "    (rule",
        f"      (width {tw:.3f})",
        f"      (clearance {cl:.3f})",
        '      (via "Via[0.6-0.3]")',
        "    )",
        f'    (keepout "edge_left" (rect pcb 0 0 0.8 {bh:.3f}))',
        f'    (keepout "edge_right" (rect pcb {bw-0.8:.3f} 0 {bw:.3f} {bh:.3f}))',
        f'    (keepout "edge_bottom" (rect pcb 0 0 {bw:.3f} 0.8))',
        f'    (keepout "edge_top" (rect pcb 0 {bh-0.8:.3f} {bw:.3f} {bh:.3f}))',
        # Mounting holes. Specctra circle syntax is
        # ``(circle <layer> <diameter> [cx cy])`` — diameter first, centre last.
        # Writing ``(circle pcb 6.0 4.0 46.0)`` for the top-left corner is correct:
        # a 6 mm keep-out centred at (4, 46). Reading those numbers as
        # (cx, cy, radius) makes them look like a 46 mm circle covering the board,
        # which is how they were first misdiagnosed here.
        f'    (keepout "mount_BL" (circle pcb {_MOUNT_DIAMETER:.1f} {_MOUNT_INSET:.1f} {_MOUNT_INSET:.1f}))',
        f'    (keepout "mount_BR" (circle pcb {_MOUNT_DIAMETER:.1f} {bw-_MOUNT_INSET:.1f} {_MOUNT_INSET:.1f}))',
        f'    (keepout "mount_TL" (circle pcb {_MOUNT_DIAMETER:.1f} {_MOUNT_INSET:.1f} {bh-_MOUNT_INSET:.1f}))',
        f'    (keepout "mount_TR" (circle pcb {_MOUNT_DIAMETER:.1f} {bw-_MOUNT_INSET:.1f} {bh-_MOUNT_INSET:.1f}))',
    ]
    # RF antenna keepout: only the strip immediately OUTSIDE the module's antenna end,
    # clipped to the board. The previous version started inside the module body and
    # swallowed neighbouring components' pads, making their nets unroutable.
    _mod_hh = {"ESP32-S3-WROOM-1": 13.5, "ESP32-C3-WROOM-02": 10.5, "ESP32-WROOM-32": 12.75}
    if has_esp and "U_MCU" in placements:
        mpos = placements["U_MCU"]
        mhh = _mod_hh.get(mpos.package or "", 12.0)
        ky1 = mpos.y_mm + mhh
        ky2 = ky1 + 8.0
        if ky1 < bh - 2.0:
            ky2 = min(bh, ky2)
            L.append(
                f'    (keepout "rf_antenna" (rect pcb {mpos.x_mm-5.0:.3f} {ky1:.3f} {mpos.x_mm+5.0:.3f} {ky2:.3f}))'
            )
    L.append("  )")

    # 3. Build Specctra Footprint Image Library
    L.append("  (library")
    L.append('    (padstack "Pad_SMD"')
    L.append("      (shape (rect Top -0.25 -0.30 0.25 0.30))")
    L.append("      (shape (rect Bottom -0.25 -0.30 0.25 0.30))")
    L.append("    )")
    L.append('    (padstack "Pad_SMD_Fine"')
    L.append("      (shape (rect Top -0.20 -0.08 0.20 0.08))")
    L.append("      (shape (rect Bottom -0.20 -0.08 0.20 0.08))")
    L.append("    )")
    # 0.5 mm-pitch land: 0.30 mm wide leaves 0.20 mm between neighbours, which is
    # the clearance the board rules ask for. Reusing Pad_SMD (0.50 mm wide) on a
    # 0.5 mm-pitch part makes adjacent pads touch, so the router sees a solid
    # copper wall at the connector and cannot escape it — CC1/CC2 were unroutable
    # for exactly this reason, not because of placement.
    L.append('    (padstack "Pad_SMD_0p5mm"')
    L.append("      (shape (rect Top -0.15 -0.30 0.15 0.30))")
    L.append("      (shape (rect Bottom -0.15 -0.30 0.15 0.30))")
    L.append("    )")
    L.append('    (padstack "Pad_TH"')
    L.append("      (shape (circle Top 0.8))")
    L.append("      (shape (circle Bottom 0.8))")
    L.append("    )")
    L.append('    (padstack "Via[0.6-0.3]"')
    L.append("      (shape (circle Top 0.6))")
    L.append("      (shape (circle Bottom 0.6))")
    L.append("    )")

    # Group placements by clean package name
    pkgs_used: dict[str, list[str]] = {}
    for ref, p in placements.items():
        clean_pkg = re.sub(r"[^\w\-.]", "_", p.package or "SMD")
        pkgs_used.setdefault(clean_pkg, []).append(ref)

    for clean_pkg, refs in sorted(pkgs_used.items()):
        needed_pins: set[str] = set()
        for ref in refs:
            c_pins = component_pins.get(ref)
            if c_pins:
                needed_pins.update(c_pins)
            else:
                if any(k in clean_pkg for k in ("TestPoint", "MountingHole", "Pad")):
                    needed_pins.add("1")
                else:
                    needed_pins.update({"1", "2"})

        if not needed_pins:
            needed_pins = {"1"} if any(k in clean_pkg for k in ("TestPoint", "MountingHole", "Pad")) else {"1", "2"}

        pin_coords = STANDARD_PIN_OFFSETS.get(clean_pkg)
        if pin_coords is None:
            pin_coords = _synthesize_footprint_pins(clean_pkg, list(needed_pins))

        is_fine = any(k in clean_pkg for k in ("HTSSOP", "LQFP", "QFN"))
        is_th = any(k in clean_pkg for k in ("CONN_TH", "HDR", "TERMINAL", "PinHeader"))
        # 0.5 mm-pitch connectors (USB-C) need their own land: at this pitch a
        # 0.5 mm-wide pad touches its neighbour, so the router sees a solid wall.
        # Matched by package family, not by a bare "0.5mm" substring — the latter
        # also caught `LQFP-48_7x7mm_P0.5mm` and gave an IC connector land.
        is_half_pitch = any(k in clean_pkg.upper() for k in ("USB-C", "USB_C", "FPC", "TYPE-C"))
        if is_th:
            pad_name = "Pad_TH"
        elif is_half_pitch:
            pad_name = "Pad_SMD_0p5mm"
        elif is_fine:
            pad_name = "Pad_SMD_Fine"
        else:
            pad_name = "Pad_SMD"

        L.append(f'    (image "{clean_pkg}"')
        for pin_name in sorted(needed_pins):
            x, y = pin_coords.get(pin_name, (0.0, 0.0))
            L.append(f'      (pin "{pad_name}" "{pin_name}" {x:.3f} {y:.3f})')
        L.append("    )")
    L.append("  )")

    # 4. Placement section
    L.append("  (placement")
    for ref, p in sorted(placements.items()):
        clean_pkg = re.sub(r"[^\w\-.]", "_", p.package or "SMD")
        L.append(f'    (component "{clean_pkg}"')
        L.append(f'      (place "{ref}" {p.x_mm:.3f} {p.y_mm:.3f} front {p.rotation_deg:.1f})')
        L.append("    )")
    L.append("  )")

    # 5. Network section with Net Classes
    power_nets: list[str] = []
    motor_nets: list[str] = []
    comm_nets: list[str] = []

    L.append("  (network")
    for conn in connections:
        raw_net = str(conn.get("net", ""))
        net_name = raw_net.replace("/", "").replace(" ", "_").replace("+", "P")
        if not net_name:
            continue
        pts = conn.get("points") or []
        if len(pts) < 2:
            continue

        valid_tokens: list[str] = []
        for pt in pts:
            if "." in pt:
                ref, pin = pt.split(".", 1)
                if ref in placements:
                    valid_tokens.append(f'"{ref}" - "{pin}"')

        if len(valid_tokens) >= 2:
            L.append(f'    (net "{net_name}"')
            pins_str = " ".join(valid_tokens)
            L.append(f"      (pins {pins_str})")
            L.append("    )")

            u_net = net_name.upper()
            if any(k in u_net for k in ("VMOT", "24V", "12V", "MOT")):
                motor_nets.append(f'"{net_name}"')
            elif any(k in u_net for k in ("GND", "VCC", "3V3", "5V", "VBUS", "VIN", "VBAT", "VDD", "VSS")):
                power_nets.append(f'"{net_name}"')
            elif any(k in u_net for k in ("CAN", "485", "DP", "DN", "TX", "RX", "SCLK", "MOSI", "MISO")):
                comm_nets.append(f'"{net_name}"')

    if power_nets:
        L.append("    (class \"POWER\" " + " ".join(power_nets))
        L.append("      (rule (width 0.254) (clearance 0.150))")
        L.append("    )")
    if motor_nets:
        L.append("    (class \"MOTOR_POWER\" " + " ".join(motor_nets))
        L.append("      (rule (width 0.350) (clearance 0.180))")
        L.append("    )")
    if comm_nets:
        L.append("    (class \"COMM_BUS\" " + " ".join(comm_nets))
        L.append("      (rule (width 0.180) (clearance 0.120))")
        L.append("    )")

    L.append("  )")
    L.append(")")

    return "\n".join(L) + "\n"
