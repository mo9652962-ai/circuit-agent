"""ERC rules for the two failure modes that pass a netlist but fail a board.

Both rules here exist because the previous check was too coarse to catch them:

* decoupling was "does the board have a 100 nF?", which one capacitor satisfies
  for any number of ICs;
* derating did not exist at all, so a 6.3 V capacitor could sit on a 24 V rail
  and nothing in the pipeline noticed.
"""

import pytest

from client.erc import run_erc
from client.synthesizer import synthesize_from_prompt


def _codes(modules, connections):
    return [i["code"] for i in run_erc(modules, connections)]


# --------------------------------------------------------------------------- #
# Per-IC decoupling
# --------------------------------------------------------------------------- #


def test_three_ics_sharing_one_capacitor_is_flagged():
    """One 100 nF does not decouple three parts.

    The original rule asked only whether any decoupling capacitor existed, so a
    single part satisfied it for the whole board.
    """
    modules = {
        "U1": {"kind": "IC", "value": "SN65HVD230"},
        "U2": {"kind": "IC", "value": "SP3485EN"},
        "U3": {"kind": "IC", "value": "W5500"},
        "C1": {"kind": "CAPACITOR", "value": "100nF"},
        "LDO": {"kind": "LDO", "value": "AMS1117"},
    }
    connections = [
        {"net": "/GND", "points": ["U1.2", "U2.5", "U3.1", "C1.2", "LDO.1"]},
        {"net": "/+3.3V", "points": ["U1.3", "U2.8", "U3.2", "C1.1", "LDO.2"]},
        {"net": "/VBUS", "points": ["LDO.3"]},
    ]
    assert "DECOUPLING_PER_IC_DEFICIT" in _codes(modules, connections)


def test_one_capacitor_per_ic_is_not_flagged():
    modules = {
        "U1": {"kind": "IC", "value": "SN65HVD230"},
        "U2": {"kind": "IC", "value": "SP3485EN"},
        "C1": {"kind": "CAPACITOR", "value": "100nF"},
        "C2": {"kind": "CAPACITOR", "value": "100nF"},
        "LDO": {"kind": "LDO", "value": "AMS1117"},
    }
    connections = [
        {"net": "/GND", "points": ["U1.2", "U2.5", "C1.2", "C2.2", "LDO.1"]},
        {"net": "/+3.3V", "points": ["U1.3", "U2.8", "C1.1", "C2.1", "LDO.2"]},
        {"net": "/VBUS", "points": ["LDO.3"]},
    ]
    assert "DECOUPLING_PER_IC_DEFICIT" not in _codes(modules, connections)


# --------------------------------------------------------------------------- #
# Derating
# --------------------------------------------------------------------------- #


def test_capacitor_rated_below_its_rail_is_an_error():
    """A 6.3 V part on a 24 V rail is not marginal, it is broken."""
    modules = {
        "C1": {"kind": "CAPACITOR", "value": "10uF/6.3V", "rated_v": 6.3, "pins": {"1": "/VMOT_24V", "2": "/GND"}},
        "LDO": {"kind": "LDO", "value": "AMS1117", "pins": {"1": "/GND", "2": "/+3.3V", "3": "/VBUS"}},
    }
    connections = [
        {"net": "/GND", "points": ["C1.2", "LDO.1"]},
        {"net": "/VMOT_24V", "points": ["C1.1"]},
        {"net": "/+3.3V", "points": ["LDO.2"]},
        {"net": "/VBUS", "points": ["LDO.3"]},
    ]
    issues = run_erc(modules, connections)
    derating = [i for i in issues if i["code"] == "COMPONENT_RATING_INSUFFICIENT"]
    assert derating, "6.3 V capacitor on a 24 V rail was not flagged"
    assert derating[0]["severity"] == "error"
    assert "24" in derating[0]["detail"]


def test_adequately_rated_capacitor_passes():
    modules = {
        "C1": {"kind": "CAPACITOR", "value": "10uF/50V", "rated_v": 50.0, "pins": {"1": "/VMOT_24V", "2": "/GND"}},
        "LDO": {"kind": "LDO", "value": "AMS1117", "pins": {"1": "/GND", "2": "/+3.3V", "3": "/VBUS"}},
    }
    connections = [
        {"net": "/GND", "points": ["C1.2", "LDO.1"]},
        {"net": "/VMOT_24V", "points": ["C1.1"]},
        {"net": "/+3.3V", "points": ["LDO.2"]},
        {"net": "/VBUS", "points": ["LDO.3"]},
    ]
    assert "COMPONENT_RATING_INSUFFICIENT" not in _codes(modules, connections)


def test_part_without_declared_rating_is_skipped_not_assumed():
    """Inventing a rating is worse than staying silent.

    A part that declares no voltage rating cannot be checked, and guessing one
    would either hide a real violation or manufacture a false one.
    """
    modules = {
        "C1": {"kind": "CAPACITOR", "value": "10uF", "pins": {"1": "/VMOT_24V", "2": "/GND"}},
        "LDO": {"kind": "LDO", "value": "AMS1117", "pins": {"1": "/GND", "2": "/+3.3V", "3": "/VBUS"}},
    }
    connections = [
        {"net": "/GND", "points": ["C1.2", "LDO.1"]},
        {"net": "/VMOT_24V", "points": ["C1.1"]},
        {"net": "/+3.3V", "points": ["LDO.2"]},
        {"net": "/VBUS", "points": ["LDO.3"]},
    ]
    assert "COMPONENT_RATING_INSUFFICIENT" not in _codes(modules, connections)


@pytest.mark.parametrize(
    "prompt",
    [
        "ESP32-S3 带以太网口的工业网关",
        "RP2040 带电流采样和看门狗的开发板",
        "RP2040 带 CAN 总线的机器人控制板",
        "ESP32-S3 带 INA219 的电源监测板",
        "STM32F103 带电机驱动的控制器",
    ],
    ids=lambda p: p[:22],
)
def test_synthesis_completes_decoupling_for_every_active_part(prompt):
    """Synthesis must not emit a board that its own ERC rejects.

    These prompts each add an IC whose block defines no decoupling capacitor.
    The completion pass runs after all blocks are assembled, so it sees the
    final part list.
    """
    spec = synthesize_from_prompt(prompt)
    assert "DECOUPLING_PER_IC_DEFICIT" not in _codes(spec["modules"], spec["netlist"]["connections"])

    caps = [v for v in spec["modules"].values() if v["kind"] == "CAPACITOR" and str(v["value"]).startswith(("100n", "0.1u"))]
    actives = [
        v for v in spec["modules"].values() if v["kind"] in {"IC", "MCU", "TRANSCEIVER", "SENSOR", "CHARGER"}
    ]
    assert len(caps) >= len(actives), f"{len(caps)} capacitors for {len(actives)} active parts"
