"""Comprehensive tests for advanced PCB component placement, targeted decoupling adsorption,
Specctra DSN compliance, and native Python multi-layer autorouting engine.
"""

from __future__ import annotations

import math

from client.mcp_server import handle_tool_call
from client.placement_engine import (
    export_specctra_dsn,
    heuristic_place_components,
)
from client.router_engine import autoroute_circuit
from client.synthesizer import synthesize_from_prompt


def test_heuristic_placement_mcu_centering():
    """Verify MCU is placed at the geometric board center even with multiple peripheral ICs."""
    prompts_to_test = [
        "ESP32-S3 工业 CAN 与 RS485 网关",
        "STM32F103 带电机驱动的控制器",
        "51单片机带 RS485 的工业板",
        "RP2040 带电流采样和看门狗的开发板",
        "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键",
    ]
    for prompt in prompts_to_test:
        spec = synthesize_from_prompt(prompt)
        placements = heuristic_place_components(spec["modules"], 70.0, 50.0)

        # Geometric center is (35.0, 25.0)
        center_comp = [ref for ref, p in placements.items() if p.x_mm == 35.0 and p.y_mm == 25.0]
        assert len(center_comp) == 1, f"Expected 1 component at center for {prompt}, got {center_comp}"
        mcu_ref = center_comp[0]
        assert "MCU" in mcu_ref or "U1" in mcu_ref, f"Center component should be MCU, got {mcu_ref} in {prompt}"


def test_decoupling_capacitor_targeted_adsorption():
    """Verify peripheral decoupling capacitors cluster near their target ICs (<5mm)."""
    spec = synthesize_from_prompt("ESP32-S3 工业 CAN 与 RS485 网关")
    placements = heuristic_place_components(spec["modules"], 70.0, 50.0)

    # C_485 should be placed near U_485
    if "C_485" in placements and "U_485" in placements:
        c_pos = placements["C_485"]
        u_pos = placements["U_485"]
        dist = math.hypot(c_pos.x_mm - u_pos.x_mm, c_pos.y_mm - u_pos.y_mm)
        assert dist <= 5.0, f"C_485 should be within 5mm of U_485, got {dist:.2f}mm"

    # C_CAN should be placed near U_CAN
    if "C_CAN" in placements and "U_CAN" in placements:
        c_pos = placements["C_CAN"]
        u_pos = placements["U_CAN"]
        dist = math.hypot(c_pos.x_mm - u_pos.x_mm, c_pos.y_mm - u_pos.y_mm)
        assert dist <= 5.0, f"C_CAN should be within 5mm of U_CAN, got {dist:.2f}mm"


def test_collision_avoidance_no_overlapping():
    """Verify collision avoidance pass guarantees zero overlapping components."""
    from tests.test_export_content_sanity import PROMPTS

    for prompt in PROMPTS:
        spec = synthesize_from_prompt(prompt)
        placements = heuristic_place_components(spec["modules"], 70.0, 50.0)
        seen_coords: set[tuple[float, float]] = set()
        for ref, p in placements.items():
            coord = (round(p.x_mm, 2), round(p.y_mm, 2))
            assert coord not in seen_coords, f"Collision detected for {ref} at {coord} in {prompt}"
            seen_coords.add(coord)
            assert 0.0 <= p.x_mm <= 70.0, f"Component {ref} placed out of board width: {p.x_mm}"
            assert 0.0 <= p.y_mm <= 50.0, f"Component {ref} placed out of board height: {p.y_mm}"


def test_specctra_dsn_library_and_pins_format():
    """Verify generated Specctra DSN contains valid library section and standard pin references."""
    spec = synthesize_from_prompt("ESP32-C3 环境监测节点")
    dsn = export_specctra_dsn(spec["modules"], spec["netlist"]["connections"])

    assert "(library" in dsn
    assert '(padstack "Pad_SMD"' in dsn
    assert '(padstack "Via[0.6-0.3]"' in dsn
    assert '(image "C0603"' in dsn
    assert '(image "ESP32-C3-WROOM-02"' in dsn
    assert "(structure" in dsn
    assert '(via "Via[0.6-0.3]")' in dsn
    assert "(network" in dsn
    # Standard Specctra pins format: (pins "Comp" - "Pin" ...)
    assert '(pins "J_USB1" - "VBUS"' in dsn or '(pins "U_LDO1" - "3"' in dsn


def test_native_autoroute_esp32c3_node():
    """Verify native Python autorouter completes routing for ESP32-C3 node with 100% completion rate."""
    spec = synthesize_from_prompt("ESP32-C3 环境监测节点")
    res = autoroute_circuit(spec["modules"], spec["netlist"]["connections"])

    assert res["success"] is True
    metrics = res["metrics"]
    assert metrics["completion_rate_pct"] == 100.0
    assert metrics["routed_nets_count"] == 7
    assert metrics["unrouted_nets_count"] == 0
    assert metrics["total_wire_length_mm"] > 50.0
    assert len(metrics["layers_used"]) >= 1
    assert "(session" in res["ses_text"]
    assert "(routes" in res["ses_text"]


def test_native_autoroute_industrial_gateway():
    """Verify multi-layer routing on dense industrial gateway with vias and multi-layer tracks."""
    spec = synthesize_from_prompt("ESP32-S3 工业 CAN 与 RS485 网关")
    res = autoroute_circuit(spec["modules"], spec["netlist"]["connections"])

    assert res["success"] is True
    metrics = res["metrics"]
    assert metrics["completion_rate_pct"] >= 90.0
    assert metrics["routed_nets_count"] >= 20
    assert metrics["via_count"] >= 1, "Dense board should require vias for layer transitions"
    assert "Top" in metrics["layers_used"] and "Bottom" in metrics["layers_used"]
    assert metrics["total_wire_length_mm"] > 200.0


def test_mcp_tool_autoroute_pcb():
    """Verify MCP tool autoroute_pcb executes cleanly and returns structured payload."""
    import json

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
    assert data["success"] is True
    assert "metrics" in data
    assert data["metrics"]["completion_rate_pct"] >= 80.0
    assert "ses_text" in data
    assert "(session" in data["ses_text"]
