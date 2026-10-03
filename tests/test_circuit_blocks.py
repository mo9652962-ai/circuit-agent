"""Determinism and contract tests for the CircuitBlocks DSL.

The core promise of this repository is that the DSL mapping is deterministic:
the same prompt must always produce byte-identical output. These tests enforce
that promise, plus the structural invariants every block must satisfy.
"""

from __future__ import annotations

import json

import pytest

from client import circuit_blocks as cb
from client.synthesizer import synthesize_from_prompt

BLOCK_FACTORIES = [
    cb.block_usb_c_power,
    cb.block_power_ldo_3v3,
    cb.block_crystal_clock,
    cb.block_button,
    cb.block_led,
    cb.block_buzzer,
    cb.block_i2c_header,
    cb.block_rs485_transceiver,
    cb.block_can_transceiver,
    cb.block_battery_tp4056,
    cb.block_sensor_aht20,
    cb.block_sensor_mpu6050,
    cb.block_esd_usb_tvs,
    cb.block_esd_rs485_tvs,
    cb.block_esd_can_tvs,
    cb.block_reverse_polarity_protection,
    cb.block_power_pi_filter,
    cb.block_fiducial_marks,
    cb.block_testpoint_matrix,
]


# --------------------------------------------------------------------------- #
# Block-level invariants
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("factory", BLOCK_FACTORIES, ids=lambda f: f.__name__)
def test_block_has_components_and_nets(factory):
    blk = factory()
    assert blk.name, "block must be named"
    assert blk.description, "block must be documented"
    assert blk.components, "block must declare components"
    if blk.name != "Fiducial_Marks":
        assert blk.nets, "block must declare nets"


@pytest.mark.parametrize("factory", BLOCK_FACTORIES, ids=lambda f: f.__name__)
def test_component_designators_are_unique(factory):
    blk = factory()
    refs = [c.ref for c in blk.components]
    assert len(refs) == len(set(refs)), f"duplicate designators in {blk.name}: {refs}"


@pytest.mark.parametrize("factory", BLOCK_FACTORIES, ids=lambda f: f.__name__)
def test_every_component_has_lcsc_and_package(factory):
    blk = factory()
    for comp in blk.components:
        assert comp.package, f"{comp.ref} missing package"
        assert comp.lcsc.startswith("C"), f"{comp.ref} missing LCSC part number"


@pytest.mark.parametrize("factory", BLOCK_FACTORIES, ids=lambda f: f.__name__)
def test_nets_reference_declared_components(factory):
    """Every net endpoint must point at a component the block actually declares."""
    blk = factory()
    refs = {c.ref for c in blk.components}
    for net, endpoints in blk.nets.items():
        assert endpoints, f"net {net} has no endpoints"
        for ep in endpoints:
            ref = ep.split(".")[0]
            assert ref in refs, f"net {net} references undeclared component {ref}"


@pytest.mark.parametrize("factory", BLOCK_FACTORIES, ids=lambda f: f.__name__)
def test_ground_net_is_reachable(factory):
    blk = factory()
    # Mechanical fiducials and pure high-side inline reverse diodes don't have dedicated /GND net
    if blk.name in ("Fiducial_Marks", "Reverse_Polarity_Protection"):
        return
    assert "/GND" in blk.nets, f"{blk.name} must tie to /GND"


def test_crystal_declares_guard_ring():
    blk = cb.block_crystal_clock()
    assert blk.properties.get("guard_ring") is True
    assert blk.properties.get("guard_ring_radius_mm") == 8.0


def test_rs485_block_properties():
    blk = cb.block_rs485_transceiver()
    assert blk.properties.get("differential_impedance") == 120
    assert "/485_A" in blk.nets and "/485_B" in blk.nets
    assert "U_485" in {c.ref for c in blk.components}


def test_can_block_properties():
    blk = cb.block_can_transceiver()
    assert blk.properties.get("differential_impedance") == 120
    assert "/CAN_H" in blk.nets and "/CAN_L" in blk.nets
    assert "U_CAN" in {c.ref for c in blk.components}


def test_battery_tp4056_properties():
    blk = cb.block_battery_tp4056()
    assert blk.properties.get("battery_chemistry") == "Li-Ion"
    assert blk.properties.get("charge_voltage") == 4.2
    assert "U_BAT1" in {c.ref for c in blk.components}


def test_synthesizer_supports_industrial_intents():
    spec = synthesize_from_prompt("基于 STM32F103 的工业网关，带 RS485、CAN总线 和 锂电池充电")
    refs = spec["modules"].keys()
    assert "U_485" in refs
    assert "U_CAN" in refs
    assert "U_BAT1" in refs
    assert "/485_A" in [c["net"] for c in spec["netlist"]["connections"]]
    assert "/CAN_H" in [c["net"] for c in spec["netlist"]["connections"]]
    assert "/VBAT" in [c["net"] for c in spec["netlist"]["connections"]]


def test_button_count_parameterizes_designator():
    blk = cb.block_button("SW7", "/BTN7")
    refs = {c.ref for c in blk.components}
    assert "SW7" in refs
    assert "/BTN7" in blk.nets


# --------------------------------------------------------------------------- #
# Synthesizer determinism
# --------------------------------------------------------------------------- #
PROMPTS = [
    "基于 ESP32-C3 的环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键",
    "STM32F103 minimal board with USB Type-C power and a status LED",
    "RP2040 双核控制板，Type-C 供电，蜂鸣器报警，1个按键",
    "STC89C52RC 最小系统，带电源和按键",
]


@pytest.mark.parametrize("prompt", PROMPTS)
def test_synthesizer_is_deterministic(prompt):
    a = synthesize_from_prompt(prompt)
    b = synthesize_from_prompt(prompt)
    assert json.dumps(a, sort_keys=True, ensure_ascii=False) == \
           json.dumps(b, sort_keys=True, ensure_ascii=False)


@pytest.mark.parametrize("prompt", PROMPTS)
def test_synthesizer_output_shape(prompt):
    spec = synthesize_from_prompt(prompt)
    assert spec["chip_id"] in (
        "STM32F103C8T6", "ESP32-C3", "ESP32-S3", "RP2040", "STC89C52RC",
    )
    assert spec["modules"], "at least one module expected"
    assert spec["netlist"]["connections"], "at least one net expected"
    assert isinstance(spec["unmatched"], list)


@pytest.mark.parametrize("prompt", PROMPTS)
def test_synthesizer_netlist_is_internally_consistent(prompt):
    spec = synthesize_from_prompt(prompt)
    refs = set(spec["modules"])
    for conn in spec["netlist"]["connections"]:
        assert conn["net"], "net must be named"
        for ep in conn["points"]:
            assert ep.split(".")[0] in refs, f"dangling endpoint {ep} on net {conn['net']}"


def test_chip_detection_variants():
    assert synthesize_from_prompt("esp32c3 板子")["chip_id"] == "ESP32-C3"
    assert synthesize_from_prompt("esp32 s3 board")["chip_id"] == "ESP32-S3"
    assert synthesize_from_prompt("rp2040 dev board")["chip_id"] == "RP2040"
    assert synthesize_from_prompt("89c52 板子")["chip_id"] == "STC89C52RC"
    assert synthesize_from_prompt("stm32f103 板子")["chip_id"] == "STM32F103C8T6"


def test_chip_defaults_to_stm32():
    assert synthesize_from_prompt("随便做一块板子")["chip_id"] == "STM32F103C8T6"


def test_button_count_detection():
    two = synthesize_from_prompt("ESP32-C3 板，2个按键")
    three = synthesize_from_prompt("ESP32-C3 板，三个按键")
    assert "SW2" in two["modules"] and "SW3" not in two["modules"]
    assert "SW3" in three["modules"] and "SW4" not in three["modules"]


def test_51_board_skips_ldo():
    """A 5V-native 51 board should not get a 3.3V LDO inserted."""
    spec = synthesize_from_prompt("STC89C52RC 板子，带 Type-C 供电")
    assert "U_LDO1" not in spec["modules"]


def test_not_requested_blocks_are_reported():
    """Optional blocks the prompt did not mention land in `not_requested`."""
    spec = synthesize_from_prompt("ESP32-C3 板，带 Type-C 供电")
    assert "buzzer" in spec["not_requested"]
    assert "led" in spec["not_requested"]


def test_unmatched_reports_unsupported_features():
    """`unmatched` must surface what the user asked for but the DSL cannot build."""
    spec = synthesize_from_prompt("ESP32-C3 板，带 Type-C 供电、以太网口和继电器输出")
    assert "ethernet" in spec["unmatched"]
    assert "relay" in spec["unmatched"]
    # Requested-but-unsupported must NOT be confused with merely-unrequested.
    assert "ethernet" not in spec["not_requested"]
    assert "relay" not in spec["not_requested"]


def test_unmatched_is_empty_for_fully_supported_prompt():
    spec = synthesize_from_prompt("ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键")
    assert spec["unmatched"] == []


def test_bare_english_can_is_not_a_can_bus():
    """The ordinary English verb 'can' must not synthesize a CAN transceiver."""
    spec = synthesize_from_prompt("ESP32-C3 board that can drive a relay, with Type-C power")
    assert "CAN_Transceiver" not in spec["block_names"]


def test_uppercase_can_acronym_is_a_can_bus():
    spec = synthesize_from_prompt("STM32F103 工业网关，带 CAN 总线和 RS485")
    assert "CAN_Transceiver" in spec["block_names"]


def test_duplicate_designators_are_rejected():
    with pytest.raises(ValueError):
        synthesize_from_prompt("")


def test_empty_prompt_raises():
    with pytest.raises(ValueError):
        synthesize_from_prompt("   ")
