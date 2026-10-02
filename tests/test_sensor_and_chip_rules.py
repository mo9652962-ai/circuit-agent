"""Tests for AHT20, MPU6050 sensor blocks and third-party chip pinout rules."""

import pytest
from client import (
    ChipPinoutRule,
    apply_chip_pinout,
    block_sensor_aht20,
    block_sensor_mpu6050,
    get_chip_rule,
    list_supported_chips,
    register_chip_rule,
    synthesize_from_prompt,
    validate_pin_allocation,
)
from client.mcp_server import process_message


class TestSensorBlocks:
    """Test AHT20 and MPU6050 circuit block definitions."""

    def test_aht20_block_structure(self):
        blk = block_sensor_aht20()
        assert blk.name == "Sensor_AHT20"
        assert blk.properties["interface"] == "I2C"
        assert blk.properties["i2c_address"] == "0x38"

        # Check components: AHT20 sensor IC + 100nF decoupling + 2 pull-up resistors
        comp_refs = [c.ref for c in blk.components]
        assert "U_AHT1" in comp_refs
        assert "C_AHT1" in comp_refs
        assert "R_AHT_SCL" in comp_refs
        assert "R_AHT_SDA" in comp_refs

        # Check decoupling capacitor
        c_dec = next(c for c in blk.components if c.ref == "C_AHT1")
        assert c_dec.value == "100nF"
        assert c_dec.kind == "CAPACITOR"

        # Check pullups
        r_scl = next(c for c in blk.components if c.ref == "R_AHT_SCL")
        assert r_scl.value == "4.7k"

        # Check nets
        assert "/SCL" in blk.nets
        assert "/SDA" in blk.nets
        assert "/+3.3V" in blk.nets
        assert "/GND" in blk.nets

    def test_aht20_without_pullups(self):
        blk = block_sensor_aht20(include_pullups=False)
        comp_refs = [c.ref for c in blk.components]
        assert "R_AHT_SCL" not in comp_refs
        assert "R_AHT_SDA" not in comp_refs

    def test_mpu6050_block_structure(self):
        blk = block_sensor_mpu6050()
        assert blk.name == "Sensor_MPU6050"
        assert blk.properties["interface"] == "I2C"
        assert blk.properties["i2c_address"] == "0x68"
        assert blk.properties["sensor_type"] == "6axis_imu"

        comp_refs = [c.ref for c in blk.components]
        assert "U_MPU1" in comp_refs
        assert "C_MPU_VDD" in comp_refs
        assert "C_MPU_VLOG" in comp_refs
        assert "C_MPU_REG" in comp_refs
        assert "C_MPU_CP" in comp_refs
        assert "R_MPU_SCL" in comp_refs
        assert "R_MPU_SDA" in comp_refs

        # Pin connections
        ic = next(c for c in blk.components if c.ref == "U_MPU1")
        assert ic.pins["23"] == "/SCL"
        assert ic.pins["24"] == "/SDA"
        assert ic.pins["12"] == "/MPU_INT"
        assert ic.pins["20"] == "/MPU_CPOUT"
        assert ic.pins["10"] == "/MPU_REGOUT"


class TestThirdPartyChipRules:
    """Test registration, query, and pinout allocation rules."""

    def test_builtin_chips_registered(self):
        chips = list_supported_chips()
        chip_ids = [c["chip_id"] for c in chips]
        assert "CH32V003F4P6" in chip_ids
        assert "STM32G030F6P6" in chip_ids
        assert "ATmega328P" in chip_ids

    def test_ch32v003_defaults_and_pins(self):
        rule = get_chip_rule("CH32V003F4P6")
        assert rule is not None
        assert rule.mcu_family == "QingKe-RISC-V"
        assert rule.package == "TSSOP-20"
        assert rule.peripheral_routes["I2C1"]["I2C_SCL"] == "PC2"
        assert rule.peripheral_routes["I2C1"]["I2C_SDA"] == "PC1"
        assert "PD1" in rule.reserved_pins

    def test_custom_chip_registration(self):
        custom = {
            "chip_id": "TEST_MCU_01",
            "mcu_family": "Custom-RISC-V",
            "package": "QFN-16",
            "supply_voltage": 3.3,
            "pins": ["P0", "P1", "P2", "P3", "P4"],
            "reserved_pins": {"P0": "DEBUG"},
            "peripheral_routes": {
                "I2C1": {"I2C_SCL": "P2", "I2C_SDA": "P3"},
            },
            "default_gpio_assignments": {
                "/LED1": "P1",
            },
        }
        rule = register_chip_rule(custom)
        assert rule.chip_id == "TEST_MCU_01"
        assert get_chip_rule("TEST_MCU_01") is not None

    def test_validate_pin_allocation_reserved(self):
        rule = get_chip_rule("CH32V003F4P6")
        errs = validate_pin_allocation(rule, {"/MY_SIG": "PD1"})  # PD1 is SWDIO
        assert len(errs) > 0
        assert "reserved pin 'PD1'" in errs[0]

    def test_validate_pin_allocation_collision(self):
        rule = get_chip_rule("CH32V003F4P6")
        errs = validate_pin_allocation(rule, {"/SIG1": "PC4", "/SIG2": "PC4"})
        assert len(errs) > 0
        assert "Pin collision on 'PC4'" in errs[0]


class TestSynthesizerIntegration:
    """Test synthesis with new sensor blocks and chip pin mappings."""

    def test_synthesize_with_sensors_and_ch32v003(self):
        prompt = "基于沁恒 CH32V003 的 AHT20 温湿度与 MPU6050 六轴传感器，包含 Type-C 供电与按键"
        res = synthesize_from_prompt(prompt)

        assert res["chip_id"] == "CH32V003F4P6"
        assert "Sensor_AHT20" in res["block_names"]
        assert "Sensor_MPU6050" in res["block_names"]
        assert "USB_C_Power" in res["block_names"]

        # Check MCU module added
        assert "U_MCU" in res["modules"]
        assert res["modules"]["U_MCU"]["value"] == "CH32V003F4P6"

        # Check pin allocations applied
        assert "/SCL" in res["pin_allocations"]
        assert res["pin_allocations"]["/SCL"] == "PC2"
        assert res["pin_allocations"]["/SDA"] == "PC1"

        # Check net connection includes U_MCU endpoint
        scl_conn = next(c for c in res["netlist"]["connections"] if c["net"] == "/SCL")
        assert "U_MCU.PC2" in scl_conn["points"]
        assert "U_AHT1.3" in scl_conn["points"]
        assert "U_MPU1.23" in scl_conn["points"]

    def test_synthesize_custom_pin_override(self):
        prompt = "CH32V003 温湿度传感器"
        custom_mapping = {"/SCL": "PC5", "/SDA": "PC6"}
        res = synthesize_from_prompt(prompt, pin_mapping=custom_mapping)

        assert res["pin_allocations"]["/SCL"] == "PC5"
        assert res["pin_allocations"]["/SDA"] == "PC6"
        scl_conn = next(c for c in res["netlist"]["connections"] if c["net"] == "/SCL")
        assert "U_MCU.PC5" in scl_conn["points"]


class TestMCPExtensions:
    """Test newly added MCP tools and capabilities."""

    def test_mcp_list_supported_chips(self):
        req = {
            "jsonrpc": "2.0",
            "id": 101,
            "method": "tools/call",
            "params": {"name": "list_supported_chips", "arguments": {}},
        }
        resp = process_message(req)
        assert "result" in resp
        import json
        chips = json.loads(resp["result"]["content"][0]["text"])
        assert any(c["chip_id"] == "CH32V003F4P6" for c in chips)

    def test_mcp_register_custom_chip(self):
        req = {
            "jsonrpc": "2.0",
            "id": 102,
            "method": "tools/call",
            "params": {
                "name": "register_custom_chip",
                "arguments": {
                    "chip_id": "TEST_MCP_MCU",
                    "pins": ["PA0", "PA1", "PA2"],
                },
            },
        }
        resp = process_message(req)
        assert "result" in resp
        assert get_chip_rule("TEST_MCP_MCU") is not None
