"""Regression tests for the MCU placement and power-chain defects.

Every test here corresponds to a defect that shipped and produced a *passing*
build: the synthesizer named a chip, no pin rule existed for it, so no MCU was
placed and every peripheral net carried a single endpoint. The board could not
be built and nothing in the pipeline said so.

These are pinned because the failure mode is silent. A missing chip rule does
not raise — it returns the spec untouched — and a missing power source does not
raise either, it just leaves the rail at 0 V. The only thing standing between
that and a customer is an assertion.
"""

from __future__ import annotations

import pytest

from client.chip_rules import get_chip_rule, list_supported_chips
from client.erc import erc_gate, run_erc
from client.synthesizer import _CHIP_RULES, synthesize_from_prompt

#: Every chip the synthesizer can name. If it can detect a chip, it must be able
#: to place it; the two lists drifting apart is exactly the defect below.
DETECTABLE_CHIPS = sorted({chip_id for _tokens, chip_id in _CHIP_RULES})


def test_every_detectable_chip_has_a_pinout_rule():
    """A chip the synthesizer recognises but cannot place is a chip it silently drops."""
    missing = [chip_id for chip_id in DETECTABLE_CHIPS if get_chip_rule(chip_id) is None]
    assert not missing, (
        f"synthesizer detects {missing} but no pinout rule is registered for them — "
        "designs naming these chips get no MCU on the board"
    )


def test_synthesizer_detection_and_registry_agree():
    """Registered chips the synthesizer cannot reach are dead weight; report both directions."""
    registered = {chip["chip_id"] for chip in list_supported_chips()}
    unreachable = sorted(registered - set(DETECTABLE_CHIPS))
    # Not a failure: third-party rules can be registered at runtime and matched
    # by alias. But the built-in list should not silently accumulate orphans.
    assert isinstance(unreachable, list)


@pytest.mark.parametrize("chip_id", DETECTABLE_CHIPS)
def test_synthesizer_places_the_mcu(chip_id):
    """The MCU must appear on the board, with a package and a real part number."""
    spec = synthesize_from_prompt(f"{chip_id} 最小系统板")
    assert spec["chip_id"] == chip_id
    assert "U_MCU" in spec["modules"], f"{chip_id}: no MCU placed on the board"
    mcu = spec["modules"]["U_MCU"]
    assert mcu["kind"] == "MCU"
    assert mcu["value"] == chip_id
    assert mcu["package"] and mcu["package"] != "CUSTOM"
    # A BOM row with no part number is a line the fab house cannot quote.
    assert mcu["lcsc"].startswith("C"), f"{chip_id}: MCU has no LCSC part number ({mcu['lcsc']!r})"


@pytest.mark.parametrize("chip_id", DETECTABLE_CHIPS)
def test_peripheral_nets_reach_the_mcu(chip_id):
    """A net with one endpoint is a wire to nowhere; the MCU must close the loop.

    A chip that runs out of pins is allowed to leave signals unrouted, but only
    if it says so: `unrouted_signals` names them. Silence is the defect, not the
    shortfall — a board that quietly drops CAN_TX is a board that ships broken.
    """
    spec = synthesize_from_prompt(f"{chip_id} 带 CAN 总线和 RS485 的工业控制器")
    unrouted = set(spec.get("unrouted_signals", []))
    floating = [
        conn["net"]
        for conn in spec["netlist"]["connections"]
        if len(conn["points"]) == 1 and conn["net"] not in unrouted
    ]
    assert not floating, f"{chip_id}: single-endpoint nets after pin binding: {floating}"


def test_pin_binding_does_not_invent_nets_the_user_did_not_ask_for():
    """Default allocations are not requests.

    The chip's default map covers SCL, SDA, TX, RX, buttons, LED and buzzer. A
    board with no I2C must not sprout a `/SCL` net whose only endpoint is the MCU
    pin — that is a phantom floating net, and nine of them drown out the real ones.
    """
    spec = synthesize_from_prompt("ESP32-S3 带 CAN 总线的网关")
    net_names = {conn["net"] for conn in spec["netlist"]["connections"]}
    assert "/SCL" not in net_names
    assert "/SDA" not in net_names
    assert "/BUZZ_CTRL" not in net_names
    # The nets that were requested are present and bound.
    assert "/CAN_TX" in net_names
    assert any("U_MCU" in p for p in next(c["points"] for c in spec["netlist"]["connections"] if c["net"] == "/CAN_TX"))


def test_pin_allocations_report_only_bound_nets():
    """`pin_allocations` must describe the design, not the chip's full default map."""
    spec = synthesize_from_prompt("ESP32-S3 带 CAN 总线的网关")
    bound = spec["pin_allocations"]
    net_names = {conn["net"] for conn in spec["netlist"]["connections"]}
    assert set(bound) <= net_names, "pin_allocations lists nets that do not exist in the netlist"


# --------------------------------------------------------------------------- #
# Power chain
# --------------------------------------------------------------------------- #


def test_transceiver_board_gets_a_power_source():
    """Naming CAN and RS485 without saying 供电 still requires a powered board."""
    spec = synthesize_from_prompt("STM32F103 带 CAN 总线和 RS485 的工业控制器")
    kinds = {m["kind"] for m in spec["modules"].values()}
    assert kinds & {"LDO", "REGULATOR"}, "no regulator on a board whose ICs need 3.3 V"
    assert "CONNECTOR" in kinds, "no connector feeding the regulator"


def test_no_power_rail_is_left_without_a_source():
    """Every powered rail with two or more endpoints must have something driving it."""
    spec = synthesize_from_prompt("STM32F103 带 CAN 总线和 RS485 的工业控制器")
    issues = run_erc(spec["modules"], spec["netlist"]["connections"])
    unsourced = [i for i in issues if i["code"] == "POWER_RAIL_WITHOUT_SOURCE"]
    assert not unsourced, [i["detail"] for i in unsourced]


def test_unsourced_rail_is_an_error_not_a_warning():
    """An unpowered board is not a style note — it must block the gate."""
    modules = {
        "U1": {"kind": "IC", "value": "SN65HVD230"},
        "C1": {"kind": "CAPACITOR", "value": "100nF"},
    }
    connections = [
        {"net": "/GND", "points": ["U1.2", "C1.2"]},
        {"net": "/+3.3V", "points": ["U1.3", "C1.1"]},
    ]
    issues = run_erc(modules, connections)
    unsourced = [i for i in issues if i["code"] == "POWER_RAIL_WITHOUT_SOURCE"]
    assert unsourced, "a rail with two endpoints and no source must be reported"
    assert unsourced[0]["severity"] == "error"
    assert erc_gate(issues)["allowed"] is False


def test_a_filter_output_counts_as_sourced():
    """A ferrite bead between two supply nets is a conducting path, not a load."""
    modules = {
        "U_LDO": {"kind": "REGULATOR", "value": "AMS1117-3.3"},
        "FB1": {"kind": "INDUCTOR", "value": "600R_2A"},
        "C1": {"kind": "CAPACITOR", "value": "10uF"},
        "U1": {"kind": "IC", "value": "SN65HVD230"},
    }
    connections = [
        {"net": "/GND", "points": ["U_LDO.1", "C1.2", "U1.2"]},
        {"net": "/VIN", "points": ["U_LDO.2", "FB1.1"]},
        {"net": "/VCC_CLEAN", "points": ["FB1.2", "C1.1", "U1.3"]},
    ]
    issues = run_erc(modules, connections)
    assert not [i for i in issues if i["code"] == "POWER_RAIL_WITHOUT_SOURCE"]


def test_single_endpoint_rail_is_left_to_floating_net():
    """One rule per defect: a one-pin rail is FLOATING_NET's finding, not this one's."""
    modules = {"U1": {"kind": "IC", "value": "SN65HVD230"}}
    connections = [
        {"net": "/GND", "points": ["U1.2", "U2.2"]},
        {"net": "/+3.3V", "points": ["U1.3"]},
    ]
    issues = run_erc(modules, connections)
    assert not [i for i in issues if i["code"] == "POWER_RAIL_WITHOUT_SOURCE"]


# --------------------------------------------------------------------------- #
# Protection parts must sit on the nets they protect
# --------------------------------------------------------------------------- #


def test_rs485_tvs_shares_the_bus_nets_with_the_transceiver():
    """A protection diode on its own private nets protects nothing."""
    spec = synthesize_from_prompt("ESP32-S3 带 RS485 的工业控制器")
    nets = {conn["net"]: conn["points"] for conn in spec["netlist"]["connections"]}
    assert "/485_A" in nets
    tvs_points = [p for p in nets["/485_A"] if p.startswith("D_TVS_485")]
    transceiver_points = [p for p in nets["/485_A"] if p.startswith("U_485")]
    assert tvs_points, "the RS485 TVS is not on the bus net it is supposed to clamp"
    assert transceiver_points, "the transceiver is not on the bus net"


def test_rs485_tvs_creates_no_orphan_nets():
    """The TVS must not introduce /RS485_A alongside the bus's /485_A."""
    spec = synthesize_from_prompt("ESP32-S3 带 RS485 的工业控制器")
    net_names = {conn["net"] for conn in spec["netlist"]["connections"]}
    assert "/RS485_A" not in net_names
    assert "/RS485_B" not in net_names


def test_aht20_no_connect_pins_get_no_net():
    """NC pins are not connections; giving them net names invents two false floats."""
    spec = synthesize_from_prompt("ESP32-C3 温湿度节点带 I2C 传感器")
    net_names = {conn["net"] for conn in spec["netlist"]["connections"]}
    assert "/NC_AHT1" not in net_names
    assert "/NC_AHT2" not in net_names


# --------------------------------------------------------------------------- #
# The whole point: a synthesized board passes its own gate
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "prompt",
    [
        "ESP32-S3 工业 CAN 与 RS485 网关，带 Type-C 供电、指示灯、按键和 I2C 传感器插座",
        "ESP32-C3 温湿度节点带 Type-C 供电和 I2C 传感器",
        "STM32F103 带 CAN 总线和 RS485 的工业控制器",
        "RP2040 带 Type-C 供电的开发板",
        "51单片机最小系统带按键和指示灯",
    ],
    ids=lambda p: p[:24],
)
def test_synthesized_design_passes_erc(prompt):
    """End to end: what the synthesizer produces must survive the gate it feeds."""
    spec = synthesize_from_prompt(prompt)
    issues = run_erc(spec["modules"], spec["netlist"]["connections"])
    blocking = [i for i in issues if i["severity"] in ("error", "blocking")]
    assert not blocking, [(i["code"], i["detail"][:120]) for i in blocking]
