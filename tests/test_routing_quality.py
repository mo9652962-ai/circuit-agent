"""Routing-quality regressions.

Each test here pins down a defect that made a board look routed while it was not,
or made the router unable to reach a net at all. They are written against the
observable property a customer cares about — "does this board come out complete"
— rather than against the internal step that happened to be wrong.
"""

from __future__ import annotations

import re

import pytest

from client.placement_engine import (
    export_specctra_dsn,
    heuristic_place_components,
)
from client.synthesizer import synthesize_from_prompt

pytest.importorskip("freeroute", reason="freeroute is an optional routing dependency")

from client.router_engine import autoroute_circuit

BOARDS = [
    "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键",
    "ESP32-S3 带以太网口的工业网关",
    "工业级 STM32F103 RS485 采集卡，带 Type-C、AHT20 和 TVS 防护",
    "RP2040 带电流采样和看门狗的开发板",
]


@pytest.mark.parametrize("prompt", BOARDS)
def test_reference_boards_route_completely(prompt: str):
    """Every reference board must route 100% of its nets.

    A board that is 83% routed is not 83% done: an unrouted net is an open
    circuit. The ESP32-C3 node sat at 83.3% because its CC pull-downs could not
    be reached — the USB-C pads were 0.5 mm wide on a 0.5 mm pitch, so adjacent
    pads touched and formed a copper wall at the connector.
    """
    spec = synthesize_from_prompt(prompt)
    res = autoroute_circuit(spec["modules"], spec["netlist"]["connections"])
    metrics = res["metrics"]
    missing = [
        c["net"]
        for c in spec["netlist"]["connections"]
        if c["net"].lstrip("/") not in metrics["routed_nets"]
    ]
    assert metrics["completion_rate_pct"] == 100.0, (
        f"{prompt}: {metrics['routed_nets_count']}/{metrics['total_nets']} routed, "
        f"unrouted: {missing}"
    )


def test_fine_pitch_land_leaves_a_channel():
    """A 0.5 mm-pitch package must not use 0.5 mm-wide pads.

    Adjacent pads then touch, and the grid router (step = width + clearance)
    finds no channel between them. This checks the DSN the exporter actually
    emits, not the constant it was built from.
    """
    spec = synthesize_from_prompt(BOARDS[0])
    placements = heuristic_place_components(spec["modules"], 70.0, 50.0)
    dsn = export_specctra_dsn(
        spec["modules"], spec["netlist"]["connections"], placements, 70.0, 50.0
    )

    # The USB-C image must reference the half-pitch padstack.
    usb_img = re.search(r'\(image "USB-C[^"]*"(.*?)\n    \)', dsn, re.DOTALL)
    assert usb_img, "USB-C footprint image missing from DSN"
    assert "Pad_SMD_0p5mm" in usb_img.group(1), (
        "USB-C uses a pad wider than its pitch; adjacent pads will touch"
    )

    # And that padstack must be narrower than the 0.5 mm pitch.
    stack = re.search(r'\(padstack "Pad_SMD_0p5mm"(.*?)\n    \)', dsn, re.DOTALL)
    assert stack, "Pad_SMD_0p5mm padstack not declared"
    rect = re.search(r"\(rect Top (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\)", stack.group(1))
    assert rect, "half-pitch padstack has no rectangle shape"
    width = float(rect.group(3)) - float(rect.group(1))
    assert width < 0.5, f"half-pitch pad is {width} mm wide on a 0.5 mm pitch"


def test_coarse_pitch_parts_keep_their_wider_land():
    """An IC must not inherit the connector's land.

    Matching the half-pitch rule on a bare "0.5mm" substring also caught
    ``LQFP-48_7x7mm_P0.5mm``, giving an IC 0.3 mm-wide pads and stranding every
    SPI net on the Ethernet gateway.
    """
    spec = synthesize_from_prompt(BOARDS[1])
    placements = heuristic_place_components(spec["modules"], 70.0, 50.0)
    dsn = export_specctra_dsn(
        spec["modules"], spec["netlist"]["connections"], placements, 70.0, 50.0
    )
    lqfp = re.search(r'\(image "LQFP-48[^"]*"(.*?)\n    \)', dsn, re.DOTALL)
    assert lqfp, "LQFP footprint image missing from DSN"
    assert "Pad_SMD_0p5mm" not in lqfp.group(1), (
        "an LQFP was given connector land; the pitch rule over-matched"
    )


def test_cc_pulldowns_sit_beside_the_receptacle():
    """Type-C CC resistors belong at the connector, not across the board.

    They were dropped by the generic passive stage at a default coordinate and
    left 19 mm from the receptacle, which both violates the Type-C layout
    requirement and made the nets hard to route.
    """
    spec = synthesize_from_prompt(BOARDS[0])
    placements = heuristic_place_components(spec["modules"], 70.0, 50.0)
    usb = next((p for r, p in placements.items() if "USB" in r.upper()), None)
    assert usb is not None, "no USB receptacle placed"

    cc = [p for r, p in placements.items() if "CC" in r.upper()]
    assert cc, "no CC pull-down resistors found"
    for p in cc:
        dist = ((p.x_mm - usb.x_mm) ** 2 + (p.y_mm - usb.y_mm) ** 2) ** 0.5
        assert dist < 10.0, (
            f"{p.ref} is {dist:.1f} mm from the receptacle; "
            "CC resistors must sit beside the connector"
        )


def test_mounting_hole_keepouts_are_hole_sized():
    """Keep-outs must be hole-sized circles at the four corners.

    Specctra writes ``(circle <layer> <diameter> [cx cy])`` — diameter first,
    centre last. Reading those numbers in the other order makes a correct 6 mm
    corner keep-out look like a board-covering circle, so this test pins the
    parsed geometry rather than the text.
    """
    from freeroute.dsn import parse_dsn

    spec = synthesize_from_prompt(BOARDS[0])
    placements = heuristic_place_components(spec["modules"], 70.0, 50.0)
    dsn = export_specctra_dsn(
        spec["modules"], spec["netlist"]["connections"], placements, 70.0, 50.0
    )
    board = parse_dsn(dsn)

    mounts = [k for k in board.keepouts if k.area.name and k.area.name.startswith("mount_")]
    assert len(mounts) == 4, f"expected 4 mounting keep-outs, got {len(mounts)}"
    for k in mounts:
        border = k.area.border
        assert type(border).__name__ == "Circle", f"{k.area.name} is not a circle"
        assert border.diameter <= 8.0, (
            f"{k.area.name} has diameter {border.diameter}; a mounting keep-out is hole-sized"
        )
        # Each must sit at a distinct corner, well inside the board.
        assert 0.0 < border.center_x < 70.0 and 0.0 < border.center_y < 50.0


def test_mcp_autoroute_defaults_match_the_library():
    """The MCP tool must not silently route with coarser rules than the library.

    `autoroute_pcb` defaulted to 0.254 mm width and 0.200 mm clearance while
    `autoroute_circuit` defaults to 0.150/0.100. The grid router steps by
    (width + clearance), so the tool's 0.454 mm grid was wider than a USB-C
    land's 0.5 mm pitch and it could not route boards the library handled fine.
    """
    import json

    from client.mcp_server import handle_tool_call

    spec = synthesize_from_prompt("STM32F103 带电机驱动的控制器")
    out = handle_tool_call(
        "autoroute_pcb",
        {
            "modules": spec["modules"],
            "netlist": spec["netlist"],
            "board_width_mm": 80.0,
            "board_height_mm": 60.0,
        },
    )
    assert "isError" not in out
    data = json.loads(out["content"][0]["text"])

    direct = autoroute_circuit(
        spec["modules"],
        spec["netlist"]["connections"],
        board_width_mm=80.0,
        board_height_mm=60.0,
    )
    assert data["metrics"]["routed_nets_count"] == direct["metrics"]["routed_nets_count"], (
        "the MCP tool routed fewer nets than the library function it wraps: "
        f"{data['metrics']['routed_nets_count']} vs {direct['metrics']['routed_nets_count']}"
    )


def test_usb_data_pair_reaches_the_controller():
    """D+/D- must connect receptacle, protector and MCU — not the protector alone.

    The receptacle had no data pins modelled and the ESD array sat on two nets of
    its own, so each line had exactly two endpoints (both on the TVS) and the
    ERC's per-net point count could not see the break.
    """
    spec = synthesize_from_prompt(BOARDS[0])
    nets = {c["net"]: c["points"] for c in spec["netlist"]["connections"]}

    for net in ("/USB_DP", "/USB_DM"):
        assert net in nets, f"{net} missing from the netlist"
        refs = {p.split(".", 1)[0] for p in nets[net]}
        # Match the receptacle by reference, not by substring: `U_TVS_USB1` also
        # contains "USB", so a loose check passes even when the connector's data
        # pads were never wired — which is exactly the defect being guarded.
        assert "J_USB1" in refs, f"{net} does not reach the receptacle ({sorted(refs)})"
        assert any("MCU" in r.upper() for r in refs), (
            f"{net} does not reach the controller ({sorted(refs)})"
        )
        assert any("TVS" in r.upper() for r in refs), f"{net} has no ESD protection"


def test_differential_pair_shares_one_net_class():
    """Both halves of a differential pair must get the same width rule.

    The class filter matched ``"DN"`` while the net is called ``USB_DM``, so only
    D+ landed in ``COMM_BUS``. Two lines of a pair routed at different widths is
    a skew and impedance mismatch, and CC1/CC2 were left on the default rule too.
    """
    spec = synthesize_from_prompt(BOARDS[0])
    placements = heuristic_place_components(spec["modules"], 70.0, 50.0)
    dsn = export_specctra_dsn(
        spec["modules"], spec["netlist"]["connections"], placements, 70.0, 50.0
    )

    comm = re.search(r'\(class "COMM_BUS"([^)]*)\)', dsn)
    assert comm, "no COMM_BUS net class emitted"
    members = set(re.findall(r'"([\w+\-.]+)"', comm.group(1)))
    for net in ("USB_DP", "USB_DM", "CC1", "CC2"):
        assert net in members, f"{net} missing from COMM_BUS (class has {sorted(members)})"


def test_power_only_receptacle_has_no_data_nets():
    """A controller without USB must not get dangling D+/D- nets.

    The 51 MCU has no USB peripheral, so the receptacle is a 5 V inlet. Wiring
    its data pads to nets nothing else touches creates a differential pair with a
    single endpoint — a defect the ERC correctly reports.
    """
    spec = synthesize_from_prompt("51单片机带 RS485 的工业板")
    nets = {c["net"] for c in spec["netlist"]["connections"]}
    assert "/USB_DP" not in nets and "/USB_DM" not in nets, (
        "a power-only receptacle must not introduce USB data nets"
    )
