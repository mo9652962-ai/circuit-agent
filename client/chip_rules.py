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
    lcsc: str = ""
    supply_voltage: float = 3.3
    pins: list[str] = field(default_factory=list)
    pin_numbers: dict[str, str] = field(default_factory=dict)
    reserved_pins: dict[str, str] = field(default_factory=dict)
    #: Pins that are held back from the default allocation but may be used when a
    #: design asks for the signal they carry (an MCU's native USB pair). A pin
    #: here is not an error to allocate; a pin in ``reserved_pins`` is.
    conditional_pins: dict[str, str] = field(default_factory=dict)
    peripheral_routes: dict[str, dict[str, str]] = field(default_factory=dict)
    default_gpio_assignments: dict[str, str] = field(default_factory=dict)
    #: Supply pins, keyed by the rail they belong to (``"+3.3V"``, ``"VBUS"``).
    #: An MCU with no supply pins bound is an unpowered part: the netlist looks
    #: complete, the BOM looks complete, and the board does nothing when powered.
    supply_pins: dict[str, list[str]] = field(default_factory=dict)
    #: Ground pins.
    ground_pins: list[str] = field(default_factory=list)
    #: Signals this part cannot provide at all — not "no free pin", but "no such
    #: peripheral". An ESP32-C3 has no SWD (it debugs over JTAG or the built-in
    #: USB-JTAG); an 8051 has no CAN controller. Listing them here keeps the
    #: synthesizer from allocating a pin to a feature the silicon lacks, which
    #: produced netlist nets that could never be driven.
    unsupported_signals: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chip_id": self.chip_id,
            "aliases": list(self.aliases),
            "mcu_family": self.mcu_family,
            "package": self.package,
            "lcsc": self.lcsc,
            "supply_voltage": self.supply_voltage,
            "pins": self.pins,
            "pin_numbers": self.pin_numbers,
            "reserved_pins": self.reserved_pins,
            "conditional_pins": self.conditional_pins,
            "peripheral_routes": self.peripheral_routes,
            "default_gpio_assignments": self.default_gpio_assignments,
            "supply_pins": self.supply_pins,
            "ground_pins": self.ground_pins,
            "unsupported_signals": self.unsupported_signals,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChipPinoutRule:
        return cls(
            chip_id=data["chip_id"],
            aliases=tuple(data.get("aliases", ())),
            mcu_family=data.get("mcu_family", "custom"),
            package=data.get("package", "CUSTOM"),
            lcsc=data.get("lcsc", ""),
            supply_voltage=float(data.get("supply_voltage", 3.3)),
            pins=list(data.get("pins", [])),
            pin_numbers=dict(data.get("pin_numbers", {})),
            reserved_pins=dict(data.get("reserved_pins", {})),
            conditional_pins=dict(data.get("conditional_pins", {})),
            peripheral_routes=dict(data.get("peripheral_routes", {})),
            default_gpio_assignments=dict(data.get("default_gpio_assignments", {})),
            supply_pins=dict(data.get("supply_pins", {})),
            ground_pins=list(data.get("ground_pins", [])),
            unsupported_signals=list(data.get("unsupported_signals", [])),
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
    # ----------------------------------------------------------------- #
    # The five families `synthesizer._CHIP_RULES` can detect.
    #
    # These were missing, and the failure was silent in the worst way: the
    # synthesizer would name the chip, `apply_chip_pinout` would look up a rule,
    # get None, and return the spec untouched — so no MCU was ever placed on the
    # board and every peripheral net (CAN_TX, RS485_A, SDA, ...) ended up with a
    # single endpoint. The ERC caught it as FLOATING_NET, which is exactly what
    # a gate is for, but the design was never buildable in the first place.
    #
    # Pin data below is from vendor documentation, not invented:
    #   * ESP32-S3-WROOM-1 pin numbers: Espressif ESP32-S3-WROOM-1 datasheet
    #     and ESP32-S3-DevKitC-1 schematic; I2C defaults GPIO8/GPIO9 and UART0
    #     GPIO43/GPIO44 from the ESP Hardware Design Guidelines schematic
    #     checklist ("U0TXD and U0RXD are GPIO43 and GPIO44 by default").
    #     Strapping pins GPIO0/3/45/46 are reserved per that same checklist.
    #   * ESP32-C3-WROOM-02: Espressif datasheet; I2C GPIO8/GPIO9, UART0
    #     GPIO20/GPIO21, native USB GPIO18/GPIO19, strapping GPIO2/8/9.
    #   * STM32F103C8T6 LQFP48: ST datasheet DS5319 Figure 8 pinout —
    #     USART1 TX=PA9(30)/RX=PA10(31), I2C1 SCL=PB6(42)/SDA=PB7(43),
    #     SWDIO=PA13(34)/SWCLK=PA14(37), CAN_RX=PA11(32)/CAN_TX=PA12(33),
    #     CAN remap RX=PB8(45)/TX=PB9(46).
    #   * RP2040: Raspberry Pi datasheet — I2C0 SDA=GPIO4/SCL=GPIO5,
    #     UART0 TX=GPIO0/RX=GPIO1, SWD, native USB.
    #   * STC89C52RC: STC datasheet — UART RXD=P3.0/TXD=P3.1, 5 V part,
    #     no hardware I2C (bit-banged on P1.0/P1.1).
    # ----------------------------------------------------------------- #
    ChipPinoutRule(
        chip_id="ESP32-S3",
        aliases=("esp32-s3", "esp32s3", "esp32 s3", "esp32s3wroom", "esp32-s3-wroom-1"),
        mcu_family="Xtensa LX7",
        package="ESP32-S3-WROOM-1",
        lcsc="C2913202",
        supply_voltage=3.3,
        pins=[
            "IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7", "IO8", "IO9",
            "IO10", "IO11", "IO12", "IO13", "IO14", "IO15", "IO16", "IO17", "IO18",
            "IO19", "IO20", "IO21", "IO35", "IO36", "IO37", "IO38", "IO39", "IO40",
            "IO41", "IO42", "IO43", "IO44", "IO45", "IO46", "IO47", "IO48", "EN",
            "3V3", "GND1", "GND2",
        ],
        pin_numbers={
            "IO0": "27", "IO1": "39", "IO2": "38", "IO3": "15", "IO4": "4",
            "IO5": "5", "IO6": "6", "IO7": "7", "IO8": "12", "IO9": "17",
            "IO10": "18", "IO11": "19", "IO12": "20", "IO13": "21", "IO14": "22",
            "IO15": "8", "IO16": "9", "IO17": "10", "IO18": "11", "IO19": "13",
            "IO20": "14", "IO21": "23", "IO35": "28", "IO36": "29", "IO37": "30",
            "IO38": "31", "IO39": "32", "IO40": "33", "IO41": "34", "IO42": "35",
            "IO43": "37", "IO44": "36", "IO45": "26", "IO46": "16", "IO47": "24",
            "IO48": "25", "EN": "3",
        },
        # Strapping pins are sampled at reset: a pull-down on IO0 or a load on
        # IO46 stops the board booting. Reserving them keeps the allocator from
        # quietly building a board that only works when a programmer is attached.
        reserved_pins={
            "IO0": "strapping (boot mode)",
            "IO3": "strapping (JTAG source)",
            "IO45": "strapping (VDD_SPI voltage)",
            "IO46": "strapping / input-only",
        },
        #: Native USB pair (IO19 = D-, IO20 = D+). Held out of the default
        #: allocation, usable by the USB signals that need them.
        conditional_pins={
            "IO19": "native USB D-",
            "IO20": "native USB D+",
        },
        peripheral_routes={
            "I2C0": {"I2C_SCL": "IO9", "I2C_SDA": "IO8"},
            "UART0": {"UART_TX": "IO43", "UART_RX": "IO44"},
            "TWAI": {"CAN_TX": "IO4", "CAN_RX": "IO5"},
            "UART1": {"UART_TX": "IO17", "UART_RX": "IO18"},
        },
        default_gpio_assignments={
            "/SCL": "IO9",
            "/SDA": "IO8",
            "/TX": "IO43",
            "/RX": "IO44",
            "/CAN_TX": "IO4",
            "/CAN_RX": "IO5",
            "/485_DI": "IO6",
            "/485_RO": "IO7",
            "/485_RE_DE": "IO15",
            "/BTN1": "IO10",
            "/BTN2": "IO11",
            "/LED_DRV": "IO12",
            "/BUZZ_CTRL": "IO13",
            "/SWDIO": "IO39",
            "/SWCLK": "IO42",
            "/NRST": "EN",
            "/USB_DP": "IO20",
            "/USB_DM": "IO19",
            "/MOSI": "IO11", "/MISO": "IO13", "/SCLK": "IO12", "/CS_ETH": "IO10",
            "/INT_ETH": "IO14", "/RST_ETH": "IO21",
        },
                supply_pins={"+3.3V": ["3V3"]},
        ground_pins=["GND1", "GND2"],
        description="Espressif ESP32-S3 dual-core Xtensa LX7 with Wi-Fi/BLE (ESP32-S3-WROOM-1 module)",
    ),
    ChipPinoutRule(
        chip_id="ESP32-C3",
        aliases=("esp32-c3", "esp32c3", "esp32 c3", "esp32-c3-wroom-02"),
        mcu_family="RISC-V",
        package="ESP32-C3-WROOM-02",
        lcsc="C2934560",
        supply_voltage=3.3,
        pins=[
            "IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7", "IO8", "IO9",
            "IO10", "IO18", "IO19", "IO20", "IO21", "EN", "3V3", "GND",
        ],
        pin_numbers={
            "IO0": "17", "IO1": "16", "IO2": "15", "IO3": "14", "IO4": "3",
            "IO5": "4", "IO6": "5", "IO7": "6", "IO8": "7", "IO9": "8",
            "IO10": "9", "IO18": "12", "IO19": "13", "IO20": "10", "IO21": "11",
            "EN": "2",
        },
        # IO2 is the only strapping pin that is not also the standard I2C pair
        # (IO8/IO9). IO8/IO9 are strapping too, but their I2C pull-ups satisfy
        # the reset requirement, so reserving them would break the documented
        # default bus for no benefit.
        #
        # IO18/IO19 are the native USB pair. They stay out of
        # `default_gpio_assignments` so a design that does not use USB never
        # spends them, but a design that *does* route D+/D- must land there —
        # the signal is the reason the pins exist. Listing them as hard
        # `reserved_pins` rejected exactly that binding, which is why the
        # receptacle and the ESD array ended up on nets of their own.
        reserved_pins={
            "IO2": "strapping (boot mode)",
        },
        #: Pins usable only when a matching signal asks for them.
        conditional_pins={
            "IO18": "native USB D-",
            "IO19": "native USB D+",
        },
        peripheral_routes={
            "I2C0": {"I2C_SCL": "IO9", "I2C_SDA": "IO8"},
            "UART0": {"UART_TX": "IO21", "UART_RX": "IO20"},
            "TWAI": {"CAN_TX": "IO4", "CAN_RX": "IO5"},
        },
        default_gpio_assignments={
            "/SCL": "IO9",
            "/SDA": "IO8",
            "/TX": "IO21",
            "/RX": "IO20",
            # ESP32-C3-WROOM-02 exposes 11 usable GPIOs after strapping and USB.
            # CAN, RS485, SPI-Ethernet and two buttons cannot all fit; the
            # allocation below keeps the buses and drops the peripheral
            # conveniences, and `validate_pin_allocation` reports the collision
            # if a design asks for more than the package has. Silently sharing a
            # pin would produce a board that works until two features are used
            # at once, which is the worst kind of working.
            "/CAN_TX": "IO4",
            "/CAN_RX": "IO5",
            "/485_DI": "IO6",
            "/485_RO": "IO7",
            "/485_RE_DE": "IO10",
            "/BTN1": "IO3",
            "/LED_DRV": "IO1",
            "/NRST": "EN",
            # Native USB lands on the pair the part reserves for it. These only
            # bind when the design already carries the nets (see apply_chip_pinout's
            # "bind only what exists" gate), so a board without USB spends nothing.
            "/USB_DP": "IO19",
            "/USB_DM": "IO18",
            # Ethernet shares the SPI bus the part does not have enough pins
            # for; a design that requests both CAN/RS485 and Ethernet on this
            # package is over-subscribed and the allocator says so.
            "/MOSI": "IO6", "/MISO": "IO7", "/SCLK": "IO10", "/CS_ETH": "IO1",
            "/INT_ETH": "IO3", "/RST_ETH": "IO4",
        },
        # ESP32-C3 has no SWD peripheral: it debugs over JTAG (MTDI/MTCK/MTMS/
        # MTDO) or the built-in USB-JTAG. Allocating pins to /SWDIO and /SWCLK
        # created two nets whose only endpoint was the MCU pin.
        unsupported_signals=["/SWDIO", "/SWCLK"],
        supply_pins={"+3.3V": ["3V3"]},
        ground_pins=["GND"],
        description="Espressif ESP32-C3 single-core RISC-V with Wi-Fi/BLE (ESP32-C3-WROOM-02 module)",
    ),
    ChipPinoutRule(
        chip_id="STM32F103C8T6",
        aliases=("stm32f103", "stm32f103c8", "stm32f103c8t6", "stm32", "bluepill", "blue pill"),
        mcu_family="ARM Cortex-M3",
        package="LQFP-48",
        lcsc="C8734",
        supply_voltage=3.3,
        pins=[
            "PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7",
            "PA8", "PA9", "PA10", "PA11", "PA12", "PA13", "PA14", "PA15",
            "PB0", "PB1", "PB2", "PB3", "PB4", "PB5", "PB6", "PB7",
            "PB8", "PB9", "PB10", "PB11", "PB12", "PB13", "PB14", "PB15",
            "PC13", "PC14", "PC15", "PD0", "PD1",
            "VDD_1", "VDD_2", "VDD_3", "VDDA", "VSS_1", "VSS_2", "VSS_3", "VSSA",
        ],
        pin_numbers={
            "PA0": "10", "PA1": "11", "PA2": "12", "PA3": "13", "PA4": "14",
            "PA5": "15", "PA6": "16", "PA7": "17", "PA8": "29", "PA9": "30",
            "PA10": "31", "PA11": "32", "PA12": "33", "PA13": "34", "PA14": "37",
            "PA15": "38", "PB0": "18", "PB1": "19", "PB2": "20", "PB3": "39",
            "PB4": "40", "PB5": "41", "PB6": "42", "PB7": "43", "PB8": "45",
            "PB9": "46", "PB10": "21", "PB11": "22", "PB12": "25", "PB13": "26",
            "PB14": "27", "PB15": "28", "PC13": "2", "PC14": "3", "PC15": "4",
            "PD0": "5", "PD1": "6",
        },
        # PA13/PA14 carry SWD. They are *reserved* in the sense that a design
        # must not repurpose them for ordinary GPIO, but the SWD nets themselves
        # legitimately land there — so they are not listed in `reserved_pins`,
        # which would make the allocator reject its own debug assignment.
        reserved_pins={
            "PB2": "BOOT1",
        },
        peripheral_routes={
            "I2C1": {"I2C_SCL": "PB6", "I2C_SDA": "PB7"},
            "USART1": {"UART_TX": "PA9", "UART_RX": "PA10"},
            # CAN is routed to the remap pins so PA11/PA12 stay free for USB.
            # On this part CAN_RX/CAN_TX and USB_DM/DP share PA11/PA12, so a
            # board that wants both must remap CAN — this is the standard Blue
            # Pill arrangement, and silently taking PA11/PA12 would produce a
            # board where USB enumeration and CAN cannot coexist.
            "CAN": {"CAN_TX": "PB9", "CAN_RX": "PB8"},
        },
        default_gpio_assignments={
            "/SCL": "PB6",
            "/SDA": "PB7",
            "/TX": "PA9",
            "/RX": "PA10",
            "/CAN_TX": "PB9",
            "/CAN_RX": "PB8",
            "/CAN_RS": "PB5",
            "/485_DI": "PA2",
            "/485_RO": "PA3",
            "/485_RE_DE": "PA1",
            "/BTN1": "PA0",
            "/BTN2": "PB12",
            "/LED_DRV": "PC13",
            "/BUZZ_CTRL": "PB13",
            "/SWDIO": "PA13",
            "/SWCLK": "PA14",
            "/NRST": "PC14",
            "/USB_DP": "PA12",
            "/USB_DM": "PA11",
            "/XTAL_IN": "PD0",
            "/XTAL_OUT": "PD1",
            "/MOSI": "PA7", "/MISO": "PA6", "/SCLK": "PA5", "/CS_ETH": "PA4",
            "/INT_ETH": "PB0", "/RST_ETH": "PB1",
        },
                supply_pins={"+3.3V": ["VDD_1", "VDD_2", "VDD_3", "VDDA"]},
        ground_pins=["VSS_1", "VSS_2", "VSS_3", "VSSA"],
        description="ST STM32F103C8T6 ARM Cortex-M3 72MHz, 64KB flash, USB + CAN (LQFP-48)",
    ),
    ChipPinoutRule(
        chip_id="RP2040",
        aliases=("rp2040", "raspberry pi pico", "pico"),
        mcu_family="ARM Cortex-M0+",
        package="QFN-56",
        lcsc="C2040",
        supply_voltage=3.3,
        pins=[f"GPIO{i}" for i in range(30)] + ["SWCLK", "SWDIO", "RUN", "IOVDD", "DVDD", "GND"],
        pin_numbers={f"GPIO{i}": str(i + 1) for i in range(29)},
        reserved_pins={
            "GPIO26": "ADC0 / shared with internal temperature sensor path",
            "GPIO27": "ADC1",
            "GPIO28": "ADC2",
            "GPIO29": "ADC3",
        },
        # RP2040's USB pair is hard-wired to GPIO4/GPIO5 in silicon — it cannot be
        # remapped. I2C0 therefore moves to GPIO6/GPIO7 (a legal I2C0 mapping on
        # this part) so a board with a Type-C receptacle does not end up with its
        # data lines and its sensor bus fighting over the same two pads.
        peripheral_routes={
            "I2C0": {"I2C_SCL": "GPIO7", "I2C_SDA": "GPIO6"},
            "UART0": {"UART_TX": "GPIO0", "UART_RX": "GPIO1"},
        },
        default_gpio_assignments={
            "/SCL": "GPIO7",
            "/SDA": "GPIO6",
            "/TX": "GPIO0",
            "/RX": "GPIO1",
            "/CAN_TX": "GPIO16",
            "/CAN_RX": "GPIO17",
            "/485_DI": "GPIO8",
            "/485_RO": "GPIO9",
            "/485_RE_DE": "GPIO10",
            "/BTN1": "GPIO2",
            "/BTN2": "GPIO3",
            "/LED_DRV": "GPIO25",
            "/SWDIO": "SWDIO",
            "/SWCLK": "SWCLK",
            "/NRST": "RUN",
            "/USB_DP": "GPIO4",
            "/USB_DM": "GPIO5",
            "/MOSI": "GPIO11", "/MISO": "GPIO12", "/SCLK": "GPIO13", "/CS_ETH": "GPIO14",
            "/INT_ETH": "GPIO15", "/RST_ETH": "GPIO18",
        },
                supply_pins={"+3.3V": ["IOVDD", "DVDD"]},
        ground_pins=["GND"],
        description="Raspberry Pi RP2040 dual-core Cortex-M0+ 133MHz, 264KB SRAM (QFN-56)",
    ),
    ChipPinoutRule(
        chip_id="STC89C52RC",
        aliases=("stc89c52", "89c52", "stc89", "51单片机", "51 单片机"),
        mcu_family="8051",
        package="LQFP-44",
        lcsc="C8769",
        supply_voltage=5.0,
        pins=[
            "P0.0", "P0.1", "P0.2", "P0.3", "P0.4", "P0.5", "P0.6", "P0.7",
            "P1.0", "P1.1", "P1.2", "P1.3", "P1.4", "P1.5", "P1.6", "P1.7",
            "P2.0", "P2.1", "P2.2", "P2.3", "P2.4", "P2.5", "P2.6", "P2.7",
            "P3.0", "P3.1", "P3.2", "P3.3", "P3.4", "P3.5", "P3.6", "P3.7",
            "RST", "XTAL1", "XTAL2", "EA", "VCC", "GND",
        ],
        pin_numbers={
            "P0.0": "39", "P0.1": "38", "P0.2": "37", "P0.3": "36",
            "P0.4": "35", "P0.5": "34", "P0.6": "33", "P0.7": "32",
            "P1.0": "1", "P1.1": "2", "P1.2": "3", "P1.3": "4",
            "P1.4": "5", "P1.5": "6", "P1.6": "7", "P1.7": "8",
            "P2.0": "24", "P2.1": "23", "P2.2": "22", "P2.3": "21",
            "P2.4": "20", "P2.5": "19", "P2.6": "18", "P2.7": "17",
            "P3.0": "10", "P3.1": "11", "P3.2": "12", "P3.3": "13",
            "P3.4": "14", "P3.5": "15", "P3.6": "16", "P3.7": "17",
            "RST": "9", "XTAL1": "19", "XTAL2": "18", "EA": "31",
        },
        # P0 is open-drain and needs external pull-ups; P3.0/P3.1 are the UART.
        # No hardware I2C exists on this part, so the I2C nets are bit-banged.
        reserved_pins={
            "P0.0": "open-drain, needs external pull-up",
            "P0.1": "open-drain, needs external pull-up",
            "P0.2": "open-drain, needs external pull-up",
            "P0.3": "open-drain, needs external pull-up",
            "P0.4": "open-drain, needs external pull-up",
            "P0.5": "open-drain, needs external pull-up",
            "P0.6": "open-drain, needs external pull-up",
            "P0.7": "open-drain, needs external pull-up",
            "EA": "tied high for internal flash",
        },
        peripheral_routes={
            "UART1": {"UART_TX": "P3.1", "UART_RX": "P3.0"},
            "I2C_SOFT": {"I2C_SCL": "P1.0", "I2C_SDA": "P1.1"},
        },
        default_gpio_assignments={
            "/SCL": "P1.0",
            "/SDA": "P1.1",
            "/TX": "P3.1",
            "/RX": "P3.0",
            "/485_DI": "P1.2",
            "/485_RO": "P1.3",
            "/485_RE_DE": "P1.4",
            "/BTN1": "P3.2",
            "/BTN2": "P3.3",
            "/LED_DRV": "P1.5",
            "/BUZZ_CTRL": "P1.6",
            "/XTAL_IN": "XTAL1",
            "/XTAL_OUT": "XTAL2",
            "/NRST": "RST",
            "/MOSI": "P2.0", "/MISO": "P2.1", "/SCLK": "P2.2", "/CS_ETH": "P2.3",
            "/INT_ETH": "P2.4", "/RST_ETH": "P2.5",
        },
        # No CAN controller and no USB peripheral on this part. Allocating pins
        # to them would create nets that nothing can ever drive.
        unsupported_signals=["/CAN_TX", "/CAN_RX", "/CAN_RS", "/USB_DP", "/USB_DM"],
        supply_pins={"+5V": ["VCC"]},
        ground_pins=["GND"],
        description="STC STC89C52RC 8051-compatible 8-bit MCU, 5V, 8KB flash (LQFP-44)",
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
        # A conditional pin is usable by the signal it names, and by nothing else:
        # allocating IO18 to a button would take the D- line away from the USB
        # pair the part provides it for.
        elif pin in chip_rule.conditional_pins:
            allowed = chip_rule.conditional_pins[pin]
            if signal.upper() not in allowed.upper():
                errors.append(
                    f"Signal '{signal}' assigned to pin '{pin}' which is held for {allowed} "
                    f"on {chip_rule.chip_id}"
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

    # 4. Drop signals the silicon cannot provide.
    #
    # "No free pin" and "no such peripheral" are different failures. A part with
    # no CAN controller should not receive a CAN_TX assignment that then becomes
    # a net nothing can drive; the honest outcome is that the signal is absent
    # and the caller is told so. Without this, an 8051 board came out with
    # /CAN_TX and /CAN_RX nets whose only endpoint was the MCU pin.
    unsupported = set(getattr(chip_rule, "unsupported_signals", ()) or ())
    dropped_unsupported = [sig for sig in effective_map if sig in unsupported]
    for sig in dropped_unsupported:
        effective_map.pop(sig)

    # Validate allocations.
    #
    # A collision means the design asks for more signals than the package has
    # pins. Raising was the old behaviour, and it was wrong for a synthesizer:
    # the caller gets a stack trace instead of a board, and nothing says which
    # feature to drop. The honest output is the largest self-consistent subset
    # plus an explicit record of what did not fit, so the caller can decide
    # instead of the exception deciding for them.
    unrouted: list[str] = []
    while True:
        errs = validate_pin_allocation(chip_rule, effective_map)
        if not errs:
            break
        conflict_signals: list[str] = []
        for err in errs:
            if "Pin collision on" in err:
                # "Pin collision on 'IO6': requested by both '/485_DI' and '/MOSI'"
                parts = err.split("requested by both '")
                if len(parts) == 2:
                    conflict_signals.append(parts[1].split("'")[0])
            elif "assigned to unknown pin" in err or "assigned to reserved pin" in err:
                conflict_signals.append(err.split("Signal '")[1].split("'")[0])
        if not conflict_signals:
            break
        victim = conflict_signals[0]
        if victim not in effective_map:
            break
        effective_map.pop(victim)
        unrouted.append(victim)

    # Add MCU component designator to modules
    modules = spec.setdefault("modules", {})
    mcu_ref = "U_MCU"
    if mcu_ref not in modules:
        modules[mcu_ref] = {
            "kind": "MCU",
            "value": chip_rule.chip_id,
            "package": chip_rule.package,
            # The MCU needs a real LCSC number: an empty string fails the
            # published output schema (`^C[0-9]+$`) and, more practically, a BOM
            # row with no part number is a line a fab house cannot quote.
            "lcsc": chip_rule.lcsc,
        }

    # Bind MCU pins to net connections
    connections = spec.get("netlist", {}).get("connections", [])
    conn_by_net = {c["net"]: c for c in connections}

    # Only bind signals that the design actually contains.
    #
    # `effective_map` is the chip's full default allocation — SCL, SDA, TX, RX,
    # every button, the LED, the buzzer. Most designs use a handful of them. The
    # previous loop created a connection for every entry in the map, so a board
    # with no I2C still got a `/SCL` net carrying exactly one endpoint (the MCU
    # pin) — which the ERC then correctly reported as FLOATING_NET. The gate was
    # right and the design was wrong: those nets were invented by the pinout
    # step, not asked for by the user. On an ESP32-S3 CAN gateway that produced
    # nine phantom floating nets, and a gate that cries wolf nine times is a
    # gate nobody reads.
    #
    # A signal the user did not request has no business becoming a net. Binding
    # is therefore conditional on the net already existing.
    bound: dict[str, str] = {}
    for net_name, pin in effective_map.items():
        if net_name not in conn_by_net:
            continue
        endpoint = f"{mcu_ref}.{pin}"
        pts = conn_by_net[net_name]["points"]
        if endpoint not in pts:
            pts.append(endpoint)
        bound[net_name] = pin

    # Supply and ground are not optional signals: an MCU with no VDD and no VSS
    # is a part sitting on a board doing nothing. The pinout step used to bind
    # only peripheral signals, so a synthesized board had a CAN transceiver on
    # `/+3.3V` and an MCU that was not on `/+3.3V` at all — the rail existed, the
    # regulator existed, and the processor was not connected to either.
    for rail, rail_pins in chip_rule.supply_pins.items():
        # `supply_pins` keys are bare rail names ("+5V"); netlist nets carry the
        # leading slash. Normalising here rather than in every rule keeps the
        # data readable while the binding stays consistent.
        net_name = rail if rail.startswith("/") else f"/{rail}"
        if net_name not in conn_by_net:
            # The rail may legitimately not exist yet (a 5 V part on a 3.3 V
            # design); create it only when this chip needs it.
            connections.append({"net": net_name, "points": []})
            conn_by_net[net_name] = connections[-1]
        for pin in rail_pins:
            endpoint = f"{mcu_ref}.{pin}"
            if endpoint not in conn_by_net[net_name]["points"]:
                conn_by_net[net_name]["points"].append(endpoint)

    for gnd_net_name in ("/GND",):
        if gnd_net_name not in conn_by_net:
            connections.append({"net": gnd_net_name, "points": []})
            conn_by_net[gnd_net_name] = connections[-1]
        for pin in chip_rule.ground_pins:
            endpoint = f"{mcu_ref}.{pin}"
            if endpoint not in conn_by_net[gnd_net_name]["points"]:
                conn_by_net[gnd_net_name]["points"].append(endpoint)

    spec["pin_allocations"] = bound
    # Signals the part cannot drive are removed from the netlist outright.
    #
    # Blocks create their nets before pin binding runs, so a CAN transceiver on
    # an 8051 board has already produced `/CAN_TX` and `/CAN_RX` by the time we
    # know the MCU has no CAN controller. Leaving them in place yields nets whose
    # only endpoint is the transceiver — a bus that cannot be driven and that the
    # ERC reports as floating on every build. The transceiver itself stays (it is
    # in the BOM, and removing parts is not this function's job); what goes away
    # is the claim that the MCU is wired to it.
    if dropped_unsupported:
        removed = set(dropped_unsupported)
        kept: list[dict[str, Any]] = []
        for conn in connections:
            if conn.get("net") in removed:
                # Drop only the MCU endpoints; if other parts still share the
                # net it stays, because the net is still real between them.
                remaining = [p for p in conn.get("points", []) if not str(p).startswith(f"{mcu_ref}.")]
                if remaining:
                    conn["points"] = remaining
                    kept.append(conn)
            else:
                kept.append(conn)
        connections[:] = kept

    # Remove nets that are left with a single endpoint after signal removal.
    #
    # A net carrying one pin is not a connection, it is a stub. Before binding,
    # `/SWDIO` held the test point; after the unsupported-signal drop it holds
    # only the test point, and `/CAN_TX` holds only the transceiver. Both are
    # leftovers of a feature this part cannot support, and leaving them makes the
    # ERC report FLOATING_NET on every build of a design that is as complete as
    # the silicon allows. The parts stay; the dead nets go.
    surviving: list[dict[str, Any]] = []
    removed_nets: list[str] = []
    for conn in connections:
        points = conn.get("points") or []
        if len(points) < 2 and conn.get("net") not in ("/GND",):
            removed_nets.append(str(conn.get("net")))
            continue
        surviving.append(conn)
    connections[:] = surviving

    if unrouted or dropped_unsupported or removed_nets:
        # Named, not silently dropped: "we could not route /MOSI" is actionable,
        # an empty net is not. `unsupported_signals` entries are reported the
        # same way — the part cannot do it, and the caller needs to know.
        spec["unrouted_signals"] = sorted(set(unrouted) | set(dropped_unsupported) | set(removed_nets))
    spec["mcu_family"] = chip_rule.mcu_family
    spec["supply_voltage"] = chip_rule.supply_voltage

    return spec
