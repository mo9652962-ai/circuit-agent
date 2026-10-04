"""Tests for 2D heuristic auto-placement, Specctra DSN export, and new industrial blocks.

Industrial blocks tested:
- W5500 SPI Ethernet
- INA219 I2C current monitor
- DRV8825 45V stepper driver
- PC817 isolated PLC input
"""

from client.circuit_blocks import (
    block_ethernet_phy_w5500,
    block_isolated_adc_ina219,
    block_motor_driver_drv8825,
    block_optocoupler_isolated_io,
)
from client.placement_engine import export_specctra_dsn, heuristic_place_components
from client.synthesizer import synthesize_from_prompt


def test_new_industrial_blocks_properties():
    """Verify component and net integrity of the 4 new industrial blocks."""
    # 1. W5500
    eth = block_ethernet_phy_w5500()
    assert eth.name == "Ethernet_W5500"
    assert any(c.ref == "U_ETH1" and c.value == "W5500" for c in eth.components)
    assert any(c.ref == "J_RJ45" and c.kind == "CONNECTOR" for c in eth.components)
    assert "/MOSI" in eth.nets and "/MISO" in eth.nets

    # 2. INA219
    ina = block_isolated_adc_ina219()
    assert ina.name == "Current_Monitor_INA219"
    assert any("R_SHUNT" in c.ref and "0.1R" in c.value for c in ina.components)
    assert "/VIN_SENSE_P" in ina.nets

    # 3. DRV8825
    drv = block_motor_driver_drv8825()
    assert drv.name == "Motor_Driver_DRV8825"
    assert any("DRV8825" in c.value for c in drv.components)
    assert any("100uF" in c.value for c in drv.components)  # VMOT bulk cap
    assert "/MOT_A1" in drv.nets and "/STEP" in drv.nets

    # 4. Optocoupler
    opto = block_optocoupler_isolated_io()
    assert opto.name == "Optocoupler_Isolated_IO"
    assert any("PC817" in c.value for c in opto.components)
    assert any("1N4148" in c.value for c in opto.components)  # Reverse diode
    assert "/PLC_IN_24V" in opto.nets


def test_synthesizer_triggers_new_industrial_blocks():
    """Verify natural language synthesis triggers new industrial blocks."""
    res = synthesize_from_prompt("STM32F103 以太网网口 电流采样 步进电机 光耦隔离24V")
    names = set(res["block_names"])
    assert "Ethernet_W5500" in names
    assert "Current_Monitor_INA219" in names
    assert "Motor_Driver_DRV8825" in names
    assert "Optocoupler_Isolated_IO" in names


def test_heuristic_placement_layout():
    """Verify MCU/primary chip is placed in center, USB on left, transceivers on border."""
    res = synthesize_from_prompt("STM32F103 USB-C LDO CAN 步进电机")
    placements = heuristic_place_components(res["modules"], board_width_mm=80.0, board_height_mm=60.0)

    # Primary chip in center (40.0, 30.0)
    center_comp = next((p for ref, p in placements.items() if p.x_mm == 40.0 and p.y_mm == 30.0), None)
    assert center_comp is not None

    # Power on left (x <= 16)
    usb = next((p for ref, p in placements.items() if "USB" in ref), None)
    assert usb is not None
    assert usb.x_mm <= 16.0


def test_export_specctra_dsn_format():
    """Verify Specctra DSN output conforms to Specctra 15.0 format."""
    res = synthesize_from_prompt("ESP32-C3 USB-C LDO 以太网")
    dsn = export_specctra_dsn(
        res["modules"],
        res["netlist"]["connections"],
        board_width_mm=75.0,
        board_height_mm=55.0,
        trace_width_mm=0.254,
        clearance_mm=0.200,
    )
    assert dsn.startswith("(pcb pcb_board")
    assert "(parser" in dsn and "(unit mm)" in dsn
    assert "(structure" in dsn and "(boundary (path pcb 0 0 0 75.0 0 75.0 55.0 0 55.0 0 0))" in dsn
    assert "(rule" in dsn and "(width 0.254)" in dsn and "(clearance 0.2)" in dsn
    assert "(placement" in dsn
    assert "(network" in dsn
    assert dsn.rstrip().endswith(")")


def test_mcp_tool_export_specctra_dsn():
    """Verify MCP tool export_specctra_dsn executes cleanly."""
    from client.mcp_server import handle_tool_call

    res = synthesize_from_prompt("STM32F103 CAN RS485")
    out = handle_tool_call(
        "export_specctra_dsn",
        {
            "modules": res["modules"],
            "netlist": res["netlist"],
            "board_width_mm": 80.0,
            "board_height_mm": 60.0,
        },
    )
    assert "isError" not in out
    dsn_text = out["content"][0]["text"]
    assert "(pcb pcb_board" in dsn_text
    assert "(boundary (path pcb 0 0 0 80.0 0 80.0 60.0 0 60.0 0 0))" in dsn_text
