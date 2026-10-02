"""Third-party MCU & Chip Pinout Allocation and Mapping Rules.

Provides a formal, extensible specification for arbitrary microcontroller pinouts,
allowing third-party chips (e.g. WCH CH32V003, ST STM32G0, Atmel ATmega328P,
Espressif, Nordic, or custom ASICs) to declare their physical pin constraints,
peripheral multiplexing routes, and default signal allocations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChipPinoutRule:
    """Formal specification for a third-party microcontroller or SoC."""

    chip_id: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    mcu_family: str = "custom"
    package: str = "CUSTOM"
    supply_voltage: float = 3.3
    pins: list[str] = field(default_factory=list)
    pin_numbers: dict[str, str] = field(default_factory=dict)
    reserved_pins: dict[str, str] = field(default_factory=dict)
    peripheral_routes: dict[str, dict[str, str]] = field(default_factory=dict)
    default_gpio_assignments: dict[str, str] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chip_id": self.chip_id,
            "aliases": list(self.aliases),
            "mcu_family": self.mcu_family,
            "package": self.package,
            "supply_voltage": self.supply_voltage,
            "pins": self.pins,
            "pin_numbers": self.pin_numbers,
            "reserved_pins": self.reserved_pins,
            "peripheral_routes": self.peripheral_routes,
            "default_gpio_assignments": self.default_gpio_assignments,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChipPinoutRule:
        return cls(
            chip_id=data["chip_id"],
            aliases=tuple(data.get("aliases", ())),
            mcu_family=data.get("mcu_family", "custom"),
            package=data.get("package", "CUSTOM"),
            supply_voltage=float(data.get("supply_voltage", 3.3)),
            pins=list(data.get("pins", [])),
            pin_numbers=dict(data.get("pin_numbers", {})),
            reserved_pins=dict(data.get("reserved_pins", {})),
            peripheral_routes=dict(data.get("peripheral_routes", {})),
            default_gpio_assignments=dict(data.get("default_gpio_assignments", {})),
            description=data.get("description", ""),
        )


# --------------------------------------------------------------------------- #
# Standard Built-in Third-Party Chip Registry
# --------------------------------------------------------------------------- #

_BUILTIN_CHIPS: list[ChipPinoutRule] = [
    ChipPinoutRule(
        chip_id="CH32V003F4P6",
        aliases=("ch32v003", "ch32v003f4p6", "ch32v", "ch32", "003", "沁恒"),
        mcu_family="QingKe-RISC-V",
        package="TSSOP-20",
        supply_voltage=3.3,
        pins=[
            "PD1", "PD2", "PD3", "PD4", "PD5", "PD6",
            "PA1", "PA2",
            "PC0", "PC1", "PC2", "PC3", "PC4", "PC5", "PC6", "PC7",
        ],
        pin_numbers={
            "PD1": "8", "PD2": "9", "PD3": "10", "PD4": "11", "PD5": "12", "PD6": "13",
            "PA1": "5", "PA2": "6",
            "PC0": "14", "PC1": "15", "PC2": "16", "PC3": "17", "PC4": "18", "PC5": "19", "PC6": "20", "PC7": "1",
        },
        reserved_pins={"PD1": "SWDIO", "NRST": "RESET"},
        peripheral_routes={
            "I2C1": {"I2C_SCL": "PC2", "I2C_SDA": "PC1"},
            "USART1": {"UART_TX": "PD5", "UART_RX": "PD6"},
        },
        default_gpio_assignments={
            "/BTN1": "PA1",
            "/BTN2": "PA2",
            "/LED1": "PD4",
            "/BUZZ_CTRL": "PC4",
        },
        description="WCH CH32V003F4P6 ultra-low-cost 32-bit RISC-V microcontroller (TSSOP-20)",
    ),
    ChipPinoutRule(
        chip_id="STM32G030F6P6",
        aliases=("stm32g030", "stm32g030f6p6", "stm32g0", "g030"),
        mcu_family="ARM-Cortex-M0+",
        package="TSSOP-20",
        supply_voltage=3.3,
        pins=[
            "PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7",
            "PA8", "PA9", "PA10", "PA11", "PA12", "PA13", "PA14", "PA15",
            "PB0", "PB1", "PB6", "PB7", "PB8",
        ],
        pin_numbers={
            "PA0": "6", "PA1": "7", "PA2": "8", "PA3": "9",
            "PA4": "10", "PA5": "11", "PA6": "12", "PA7": "13",
            "PA8": "14", "PA9": "17", "PA10": "18", "PA11": "19", "PA12": "20",
            "PA13": "1", "PA14": "2", "PA15": "3",
            "PB0": "15", "PB1": "16", "PB6": "4", "PB7": "5",
        },
        reserved_pins={"PA13": "SWDIO", "PA14": "SWCLK", "NRST": "RESET"},
        peripheral_routes={
            "I2C1": {"I2C_SCL": "PA9", "I2C_SDA": "PA10"},
            "USART1": {"UART_TX": "PA2", "UART_RX": "PA3"},
        },
        default_gpio_assignments={
            "/BTN1": "PA0",
            "/BTN2": "PB0",
            "/LED1": "PA1",
            "/BUZZ_CTRL": "PA4",
        },
        description="STMicroelectronics STM32G030F6P6 mainstream ARM Cortex-M0+ MCU (TSSOP-20)",
    ),
    ChipPinoutRule(
        chip_id="ATmega328P",
        aliases=("atmega328p", "atmega328", "arduino", "uno", "nano", "avr"),
        mcu_family="AVR-8bit",
        package="TQFP-32",
        supply_voltage=5.0,
        pins=[
            "PB0", "PB1", "PB2", "PB3", "PB4", "PB5", "PB6", "PB7",
            "PC0", "PC1", "PC2", "PC3", "PC4", "PC5", "PC6",
            "PD0", "PD1", "PD2", "PD3", "PD4", "PD5", "PD6", "PD7",
        ],
        pin_numbers={
            "PD0": "30", "PD1": "31", "PD2": "32", "PD3": "1", "PD4": "2",
            "PD5": "9", "PD6": "10", "PD7": "11",
            "PB0": "12", "PB1": "13", "PB2": "14", "PB3": "15", "PB4": "16", "PB5": "17",
            "PB6": "7", "PB7": "8",
            "PC0": "23", "PC1": "24", "PC2": "25", "PC3": "26", "PC4": "27", "PC5": "28", "PC6": "29",
        },
        reserved_pins={"PC6": "RESET", "PB6": "XTAL1", "PB7": "XTAL2"},
        peripheral_routes={
            "I2C1": {"I2C_SCL": "PC5", "I2C_SDA": "PC4"},
            "USART1": {"UART_TX": "PD1", "UART_RX": "PD0"},
        },
        default_gpio_assignments={
            "/BTN1": "PD2",
            "/BTN2": "PD3",
            "/LED1": "PB5",
            "/BUZZ_CTRL": "PD4",
        },
        description="Microchip ATmega328P 8-bit AVR microcontroller (TQFP-32, Arduino reference)",
    ),
]

_REGISTRY: dict[str, ChipPinoutRule] = {chip.chip_id: chip for chip in _BUILTIN_CHIPS}


def register_chip_rule(rule: ChipPinoutRule | dict[str, Any]) -> ChipPinoutRule:
    """Register or dynamically override a third-party chip pinout rule."""
    if isinstance(rule, dict):
        rule = ChipPinoutRule.from_dict(rule)
    elif not isinstance(rule, ChipPinoutRule):
        raise TypeError(f"rule must be a ChipPinoutRule or dict, got {type(rule)}")

    if not rule.chip_id:
        raise ValueError("chip_id cannot be empty")
    _REGISTRY[rule.chip_id] = rule
    return rule


def get_chip_rule(chip_id: str) -> ChipPinoutRule | None:
    """Retrieve registered chip rule by identifier."""
    return _REGISTRY.get(chip_id)


def list_supported_chips() -> list[dict[str, Any]]:
    """List all registered third-party chip pinout rules."""
    return [rule.to_dict() for rule in _REGISTRY.values()]


def detect_chip_from_prompt(prompt_lower: str) -> ChipPinoutRule | None:
    """Match third-party chips against prompt aliases."""
    for rule in _REGISTRY.values():
        for alias in rule.aliases:
            if alias in prompt_lower:
                return rule
    return None


def validate_pin_allocation(
    chip_rule: ChipPinoutRule,
    allocation: dict[str, str],
) -> list[str]:
    """Validate that allocated pin assignments satisfy physical constraints.

    Returns a list of error strings; an empty list indicates full compliance.
    """
    errors: list[str] = []
    used_pins: dict[str, str] = {}

    for signal, pin in allocation.items():
        if pin not in chip_rule.pins:
            errors.append(
                f"Signal '{signal}' assigned to unknown pin '{pin}' on {chip_rule.chip_id}"
            )
        if pin in chip_rule.reserved_pins:
            reason = chip_rule.reserved_pins[pin]
            errors.append(
                f"Signal '{signal}' assigned to reserved pin '{pin}' ({reason}) on {chip_rule.chip_id}"
            )
        if pin in used_pins and used_pins[pin] != signal:
            errors.append(
                f"Pin collision on '{pin}': requested by both '{used_pins[pin]}' and '{signal}'"
            )
        used_pins[pin] = signal

    return errors


def apply_chip_pinout(
    spec: dict[str, Any],
    chip_rule: ChipPinoutRule | None = None,
    custom_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Apply physical MCU pin bindings to synthesized netlist connections."""
    if chip_rule is None:
        cid = spec.get("chip_id", "")
        chip_rule = get_chip_rule(cid)

    if chip_rule is None:
        return spec

    # Build effective signal mapping
    effective_map: dict[str, str] = {}

    # 1. Defaults from peripheral routes
    i2c_route = chip_rule.peripheral_routes.get("I2C1", {})
    if "I2C_SCL" in i2c_route:
        effective_map["/SCL"] = i2c_route["I2C_SCL"]
    if "I2C_SDA" in i2c_route:
        effective_map["/SDA"] = i2c_route["I2C_SDA"]

    uart_route = chip_rule.peripheral_routes.get("USART1", {})
    if "UART_TX" in uart_route:
        effective_map["/TX"] = uart_route["UART_TX"]
    if "UART_RX" in uart_route:
        effective_map["/RX"] = uart_route["UART_RX"]

    # 2. Defaults from GPIO assignments
    for sig, pin in chip_rule.default_gpio_assignments.items():
        effective_map[sig] = pin

    # 3. Apply custom user overrides
    if custom_overrides:
        for sig, pin in custom_overrides.items():
            norm_sig = sig if sig.startswith("/") else f"/{sig}"
            effective_map[norm_sig] = pin

    # Validate allocations
    errs = validate_pin_allocation(chip_rule, effective_map)
    if errs:
        raise ValueError(f"Pin allocation error for {chip_rule.chip_id}: " + "; ".join(errs))

    # Add MCU component designator to modules
    modules = spec.setdefault("modules", {})
    mcu_ref = "U_MCU"
    if mcu_ref not in modules:
        modules[mcu_ref] = {
            "kind": "MCU",
            "value": chip_rule.chip_id,
            "package": chip_rule.package,
            "lcsc": "",
        }

    # Bind MCU pins to net connections
    connections = spec.get("netlist", {}).get("connections", [])
    conn_by_net = {c["net"]: c for c in connections}

    for net_name, pin in effective_map.items():
        endpoint = f"{mcu_ref}.{pin}"
        if net_name in conn_by_net:
            pts = conn_by_net[net_name]["points"]
            if endpoint not in pts:
                pts.append(endpoint)
        else:
            connections.append({"net": net_name, "points": [endpoint]})

    spec["pin_allocations"] = effective_map
    spec["mcu_family"] = chip_rule.mcu_family
    spec["supply_voltage"] = chip_rule.supply_voltage

    return spec
