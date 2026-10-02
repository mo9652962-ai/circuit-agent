"""CircuitAgent Public Client & Specification Package."""

from .circuit_blocks import (
    CircuitBlock,
    CircuitComponent,
    block_battery_tp4056,
    block_button,
    block_buzzer,
    block_can_transceiver,
    block_crystal_clock,
    block_i2c_header,
    block_led,
    block_power_ldo_3v3,
    block_rs485_transceiver,
    block_usb_c_power,
    block_sensor_aht20,
    block_sensor_mpu6050,
)
from .chip_rules import (
    ChipPinoutRule,
    apply_chip_pinout,
    get_chip_rule,
    list_supported_chips,
    register_chip_rule,
    validate_pin_allocation,
)
from .lcsc_client import search_lcsc_parts
from .synthesizer import synthesize_from_prompt

__version__ = "0.1.5"

__all__ = [
    "CircuitComponent",
    "CircuitBlock",
    "block_usb_c_power",
    "block_power_ldo_3v3",
    "block_crystal_clock",
    "block_button",
    "block_led",
    "block_buzzer",
    "block_i2c_header",
    "block_rs485_transceiver",
    "block_can_transceiver",
    "block_battery_tp4056",
    "block_sensor_aht20",
    "block_sensor_mpu6050",
    "ChipPinoutRule",
    "register_chip_rule",
    "get_chip_rule",
    "list_supported_chips",
    "apply_chip_pinout",
    "validate_pin_allocation",
    "synthesize_from_prompt",
    "search_lcsc_parts",
    "__version__",
]

