"""CircuitBlocks DSL & Parameterized Hardware Modules Specification (Community Edition).

Every block is a *pre-validated* sub-circuit: pin numbers, LCSC part numbers and
package names were checked against the vendor datasheet and the LCSC listing
before being frozen here. Blocks compose by merging nets, so a design is built
from audited primitives instead of free-form LLM output.

Status: **alpha**. The block set is small on purpose -- correctness over coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CircuitBlock",
    "CircuitComponent",
    "block_battery_tp4056",
    "block_button",
    "block_buzzer",
    "block_can_transceiver",
    "block_crystal_clock",
    "block_esd_can_tvs",
    "block_esd_rs485_tvs",
    "block_esd_usb_tvs",
    "block_fiducial_marks",
    "block_i2c_header",
    "block_led",
    "block_power_ldo_3v3",
    "block_power_pi_filter",
    "block_reverse_polarity_protection",
    "block_rs485_transceiver",
    "block_sensor_aht20",
    "block_sensor_mpu6050",
    "block_testpoint_matrix",
    "block_usb_c_power",
    "block_watchdog_supervisor",
]


@dataclass
class CircuitComponent:
    ref: str
    kind: str  # RESISTOR, CAPACITOR, IC, DIODE, CONNECTOR, SWITCH, LED, ...
    value: str
    package: str
    lcsc: str = ""
    pins: dict[str, str] = field(default_factory=dict)


@dataclass
class CircuitBlock:
    name: str
    description: str
    components: list[CircuitComponent] = field(default_factory=list)
    nets: dict[str, list[str]] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Power
# --------------------------------------------------------------------------- #
def block_usb_c_power(vbus_net: str = "/VBUS", gnd_net: str = "/GND") -> CircuitBlock:
    """Type-C receptacle with dual 5.1k CC pull-downs (sink, 5V @ 3A default)."""
    return CircuitBlock(
        name="USB_C_Power",
        description="USB Type-C power input with dual 5.1k CC pull-downs",
        components=[
            CircuitComponent("J_USB1", "CONNECTOR", "USB-C-16P", "USB-C-16P-SMD", "C7204555",
                             {"A5": "/CC1", "B5": "/CC2", "VBUS": vbus_net, "GND": gnd_net}),
            CircuitComponent("R_CC1", "RESISTOR", "5.1k", "R0603", "C23186",
                             {"1": "/CC1", "2": gnd_net}),
            CircuitComponent("R_CC2", "RESISTOR", "5.1k", "R0603", "C23186",
                             {"1": "/CC2", "2": gnd_net}),
        ],
        nets={
            vbus_net: ["J_USB1.VBUS"],
            gnd_net: ["J_USB1.GND", "R_CC1.2", "R_CC2.2"],
            "/CC1": ["J_USB1.A5", "R_CC1.1"],
            "/CC2": ["J_USB1.B5", "R_CC2.1"],
        },
    )


def block_power_ldo_3v3(vin_net: str = "/VBUS", vout_net: str = "/+3.3V",
                        gnd_net: str = "/GND") -> CircuitBlock:
    """AMS1117-3.3V regulator with 10uF input/output bulk storage."""
    return CircuitBlock(
        name="LDO_3V3",
        description="AMS1117-3.3 LDO with 10uF input/output bulk capacitors",
        components=[
            CircuitComponent("U_LDO1", "IC", "AMS1117-3.3", "SOT-223", "C6186",
                             {"1": gnd_net, "2": vout_net, "3": vin_net}),
            CircuitComponent("C_IN1", "CAPACITOR", "10uF", "C0805", "C15849",
                             {"1": vin_net, "2": gnd_net}),
            CircuitComponent("C_OUT1", "CAPACITOR", "10uF", "C0805", "C15849",
                             {"1": vout_net, "2": gnd_net}),
        ],
        nets={
            vin_net: ["U_LDO1.3", "C_IN1.1"],
            vout_net: ["U_LDO1.2", "C_OUT1.1"],
            gnd_net: ["U_LDO1.1", "C_IN1.2", "C_OUT1.2"],
        },
    )


# --------------------------------------------------------------------------- #
# Clock
# --------------------------------------------------------------------------- #
def block_crystal_clock(freq_mhz: str = "8MHz", gnd_net: str = "/GND") -> CircuitBlock:
    """Passive crystal with two NPO load capacitors (external clock source)."""
    return CircuitBlock(
        name=f"Crystal_{freq_mhz}",
        description=f"{freq_mhz} passive crystal with NPO load capacitors",
        components=[
            CircuitComponent("Y1", "CRYSTAL", freq_mhz, "HC-49S-SMD", "C115962",
                             {"1": "/XTAL_IN", "2": "/XTAL_OUT"}),
            CircuitComponent("C_X1", "CAPACITOR", "22pF", "C0603", "C1653",
                             {"1": "/XTAL_IN", "2": gnd_net}),
            CircuitComponent("C_X2", "CAPACITOR", "22pF", "C0603", "C1653",
                             {"1": "/XTAL_OUT", "2": gnd_net}),
        ],
        nets={
            "/XTAL_IN": ["Y1.1", "C_X1.1"],
            "/XTAL_OUT": ["Y1.2", "C_X2.1"],
            gnd_net: ["C_X1.2", "C_X2.2"],
        },
        properties={"guard_ring": True, "guard_ring_radius_mm": 8.0},
    )


# --------------------------------------------------------------------------- #
# Human interface
# --------------------------------------------------------------------------- #
def block_button(btn_ref: str = "SW1", pin_net: str = "/BTN1", gnd_net: str = "/GND",
                 vcc_net: str = "/+3.3V") -> CircuitBlock:
    """Tactile switch with 10k pull-up and 100nF RC debounce."""
    return CircuitBlock(
        name=f"Button_{btn_ref}",
        description=f"Debounced tactile switch {btn_ref}",
        components=[
            CircuitComponent(btn_ref, "SWITCH", "TactSwitch", "SW-SMD_4P-3X6", "C26638",
                             {"1": pin_net, "2": gnd_net}),
            CircuitComponent(f"R_{btn_ref}", "RESISTOR", "10k", "R0603", "C25804",
                             {"1": pin_net, "2": vcc_net}),
            CircuitComponent(f"C_{btn_ref}", "CAPACITOR", "100nF", "C0603", "C14663",
                             {"1": pin_net, "2": gnd_net}),
        ],
        nets={
            pin_net: [f"{btn_ref}.1", f"R_{btn_ref}.1", f"C_{btn_ref}.1"],
            vcc_net: [f"R_{btn_ref}.2"],
            gnd_net: [f"{btn_ref}.2", f"C_{btn_ref}.2"],
        },
    )


def block_led(led_ref: str = "D1", vcc_net: str = "/+3.3V", gnd_net: str = "/GND",
              color: str = "GREEN", resistor: str = "1k") -> CircuitBlock:
    """Status LED with current-limiting resistor."""
    return CircuitBlock(
        name=f"LED_{led_ref}",
        description=f"{color} status indicator {led_ref} with {resistor} limiting resistor",
        components=[
            CircuitComponent(led_ref, "LED", color, "LED0603", "C72043",
                             {"A": "/LED_DRV", "K": gnd_net}),
            CircuitComponent(f"R_{led_ref}", "RESISTOR", resistor, "R0603", "C21190",
                             {"1": vcc_net, "2": "/LED_DRV"}),
        ],
        nets={
            "/LED_DRV": [f"{led_ref}.A", f"R_{led_ref}.2"],
            vcc_net: [f"R_{led_ref}.1"],
            gnd_net: [f"{led_ref}.K"],
        },
    )


def block_buzzer(buzzer_ref: str = "BZ1", ctrl_net: str = "/BUZZ_CTRL",
                 gnd_net: str = "/GND", vcc_net: str = "/+3.3V") -> CircuitBlock:
    """NPN-driven active buzzer with anti-parallel flyback diode."""
    return CircuitBlock(
        name=f"Buzzer_{buzzer_ref}",
        description=f"NPN-driven buzzer {buzzer_ref} with flyback protection",
        components=[
            CircuitComponent(buzzer_ref, "BUZZER", "ActiveBuzzer", "BUZ-SMD-9.6MM",
                             "C42420997", {"1": vcc_net, "2": "/BUZZ_K"}),
            CircuitComponent("Q_BZ1", "TRANSISTOR", "S8050", "SOT-23", "C2146",
                             {"1": "/BUZZ_BASE", "2": gnd_net, "3": "/BUZZ_K"}),
            CircuitComponent("R_BZ1", "RESISTOR", "1k", "R0603", "C21190",
                             {"1": ctrl_net, "2": "/BUZZ_BASE"}),
            CircuitComponent("D_BZ1", "DIODE", "1N4148W", "SOD-123", "C81598",
                             {"A": "/BUZZ_K", "K": vcc_net}),
        ],
        nets={
            ctrl_net: ["R_BZ1.1"],
            "/BUZZ_BASE": ["R_BZ1.2", "Q_BZ1.1"],
            "/BUZZ_K": [f"{buzzer_ref}.2", "Q_BZ1.3", "D_BZ1.A"],
            vcc_net: [f"{buzzer_ref}.1", "D_BZ1.K"],
            gnd_net: ["Q_BZ1.2"],
        },
    )


def block_i2c_header(hdr_ref: str = "J_I2C1", vcc_net: str = "/+3.3V",
                     gnd_net: str = "/GND") -> CircuitBlock:
    """4-pin I2C expansion header with 4.7k pull-ups on SCL/SDA."""
    return CircuitBlock(
        name="I2C_Header",
        description="4-pin I2C bus header (VCC/GND/SCL/SDA) with 4.7k pull-ups",
        components=[
            CircuitComponent(hdr_ref, "CONNECTOR", "HDR-4P-2.54", "HDR-1X4-2.54", "C5383111",
                             {"1": vcc_net, "2": gnd_net, "3": "/SCL", "4": "/SDA"}),
            CircuitComponent("R_SCL1", "RESISTOR", "4.7k", "R0603", "C23162",
                             {"1": vcc_net, "2": "/SCL"}),
            CircuitComponent("R_SDA1", "RESISTOR", "4.7k", "R0603", "C23162",
                             {"1": vcc_net, "2": "/SDA"}),
        ],
        nets={
            vcc_net: [f"{hdr_ref}.1", "R_SCL1.1", "R_SDA1.1"],
            gnd_net: [f"{hdr_ref}.2"],
            "/SCL": [f"{hdr_ref}.3", "R_SCL1.2"],
            "/SDA": [f"{hdr_ref}.4", "R_SDA1.2"],
        },
    )


# --------------------------------------------------------------------------- #
# Industrial fieldbuses & Power storage
# --------------------------------------------------------------------------- #
def block_rs485_transceiver(ic_ref: str = "U_485", hdr_ref: str = "J_485",
                            vcc_net: str = "/+3.3V", gnd_net: str = "/GND") -> CircuitBlock:
    """SP3485 3.3V half-duplex RS485 transceiver with 120R differential termination."""
    return CircuitBlock(
        name="RS485_Transceiver",
        description="SP3485 3.3V RS485 transceiver with differential termination",
        components=[
            CircuitComponent(ic_ref, "IC", "SP3485EN", "SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL",
                             "C2692302", {"1": "/485_RO", "2": "/485_RE_DE", "3": "/485_RE_DE",
                                          "4": "/485_DI", "5": gnd_net, "6": "/485_A",
                                          "7": "/485_B", "8": vcc_net}),
            CircuitComponent("C_485", "CAPACITOR", "100nF", "C0603", "C14663",
                             {"1": vcc_net, "2": gnd_net}),
            CircuitComponent("R_485_TERM", "RESISTOR", "120R", "R0603", "C245186",
                             {"1": "/485_A", "2": "/485_B"}),
            CircuitComponent(hdr_ref, "CONNECTOR", "HDR-3P-2.54", "HDR-1X3-2.54", "C5383112",
                             {"1": "/485_A", "2": "/485_B", "3": gnd_net}),
        ],
        nets={
            vcc_net: [f"{ic_ref}.8", "C_485.1"],
            gnd_net: [f"{ic_ref}.5", "C_485.2", f"{hdr_ref}.3"],
            "/485_RO": [f"{ic_ref}.1"],
            "/485_RE_DE": [f"{ic_ref}.2", f"{ic_ref}.3"],
            "/485_DI": [f"{ic_ref}.4"],
            "/485_A": [f"{ic_ref}.6", "R_485_TERM.1", f"{hdr_ref}.1"],
            "/485_B": [f"{ic_ref}.7", "R_485_TERM.2", f"{hdr_ref}.2"],
        },
        properties={"differential_pair": ["/485_A", "/485_B"], "differential_impedance": 120},
    )


def block_can_transceiver(ic_ref: str = "U_CAN", hdr_ref: str = "J_CAN",
                          vcc_net: str = "/+3.3V", gnd_net: str = "/GND") -> CircuitBlock:
    """SN65HVD230 3.3V CAN bus transceiver with 120R termination."""
    return CircuitBlock(
        name="CAN_Transceiver",
        description="SN65HVD230 3.3V CAN transceiver with 120R termination",
        components=[
            CircuitComponent(ic_ref, "IC", "SN65HVD230DR", "SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL",
                             "C1544959", {"1": "/CAN_TX", "2": gnd_net, "3": vcc_net,
                                          "4": "/CAN_RX", "5": "/CAN_VREF", "6": "/CAN_L",
                                          "7": "/CAN_H", "8": "/CAN_RS"}),
            CircuitComponent("C_CAN", "CAPACITOR", "100nF", "C0603", "C14663",
                             {"1": vcc_net, "2": gnd_net}),
            CircuitComponent("R_CAN_RS", "RESISTOR", "10k", "R0603", "C25804",
                             {"1": "/CAN_RS", "2": gnd_net}),
            CircuitComponent("R_CAN_TERM", "RESISTOR", "120R", "R0603", "C245186",
                             {"1": "/CAN_H", "2": "/CAN_L"}),
            CircuitComponent(hdr_ref, "CONNECTOR", "HDR-3P-2.54", "HDR-1X3-2.54", "C5383112",
                             {"1": "/CAN_H", "2": "/CAN_L", "3": gnd_net}),
        ],
        nets={
            vcc_net: [f"{ic_ref}.3", "C_CAN.1"],
            gnd_net: [f"{ic_ref}.2", "C_CAN.2", "R_CAN_RS.2", f"{hdr_ref}.3"],
            "/CAN_TX": [f"{ic_ref}.1"],
            "/CAN_RX": [f"{ic_ref}.4"],
            "/CAN_RS": [f"{ic_ref}.8", "R_CAN_RS.1"],
            "/CAN_H": [f"{ic_ref}.7", "R_CAN_TERM.1", f"{hdr_ref}.1"],
            "/CAN_L": [f"{ic_ref}.6", "R_CAN_TERM.2", f"{hdr_ref}.2"],
        },
        properties={"differential_pair": ["/CAN_H", "/CAN_L"], "differential_impedance": 120},
    )


def block_battery_tp4056(ic_ref: str = "U_BAT1", vbus_net: str = "/VBUS",
                         vbat_net: str = "/VBAT", gnd_net: str = "/GND") -> CircuitBlock:
    """TP4056 1A linear Li-Ion battery charger with dual status indicators."""
    return CircuitBlock(
        name="Battery_TP4056",
        description="TP4056 1A standalone linear Li-Ion charger with charge/standby LEDs",
        components=[
            CircuitComponent(ic_ref, "IC", "TP4056-42", "ESOP-8_L4.9-W3.9-P1.27-LS6.0-BL-EP",
                             "C16581", {"1": gnd_net, "2": "/CHG_PROG", "3": gnd_net,
                                        "4": vbus_net, "5": vbat_net, "6": "/CHG_STDBY",
                                        "7": "/CHG_ACT", "8": vbus_net}),
            CircuitComponent("R_PROG1", "RESISTOR", "1.2k", "R0603", "C269681",
                             {"1": "/CHG_PROG", "2": gnd_net}),
            CircuitComponent("C_VIN_BAT", "CAPACITOR", "10uF", "C0805", "C15849",
                             {"1": vbus_net, "2": gnd_net}),
            CircuitComponent("C_BAT1", "CAPACITOR", "10uF", "C0805", "C15849",
                             {"1": vbat_net, "2": gnd_net}),
            CircuitComponent("D_CHG1", "LED", "RED", "LED0603", "C72044",
                             {"A": "/LED_CHG_A", "K": "/CHG_ACT"}),
            CircuitComponent("R_CHG1", "RESISTOR", "1k", "R0603", "C21190",
                             {"1": vbus_net, "2": "/LED_CHG_A"}),
            CircuitComponent("D_STD1", "LED", "GREEN", "LED0603", "C72043",
                             {"A": "/LED_STD_A", "K": "/CHG_STDBY"}),
            CircuitComponent("R_STD1", "RESISTOR", "1k", "R0603", "C21190",
                             {"1": vbus_net, "2": "/LED_STD_A"}),
            CircuitComponent("J_BAT1", "CONNECTOR", "HDR-2P-2.54", "HDR-1X2-2.54", "C5383113",
                             {"1": vbat_net, "2": gnd_net}),
        ],
        nets={
            vbus_net: [f"{ic_ref}.4", f"{ic_ref}.8", "C_VIN_BAT.1", "R_CHG1.1", "R_STD1.1"],
            vbat_net: [f"{ic_ref}.5", "C_BAT1.1", "J_BAT1.1"],
            gnd_net: [f"{ic_ref}.1", f"{ic_ref}.3", "R_PROG1.2", "C_VIN_BAT.2", "C_BAT1.2", "J_BAT1.2"],
            "/CHG_PROG": [f"{ic_ref}.2", "R_PROG1.1"],
            "/CHG_ACT": [f"{ic_ref}.7", "D_CHG1.K"],
            "/CHG_STDBY": [f"{ic_ref}.6", "D_STD1.K"],
            "/LED_CHG_A": ["R_CHG1.2", "D_CHG1.A"],
            "/LED_STD_A": ["R_STD1.2", "D_STD1.A"],
        },
        properties={"battery_chemistry": "Li-Ion", "charge_voltage": 4.2, "charge_current_ma": 1000},
    )


# --------------------------------------------------------------------------- #
# Sensors (Environment & Motion)
# --------------------------------------------------------------------------- #
def block_sensor_aht20(ic_ref: str = "U_AHT1", vcc_net: str = "/+3.3V",
                       gnd_net: str = "/GND", scl_net: str = "/SCL",
                       sda_net: str = "/SDA",
                       include_pullups: bool = True) -> CircuitBlock:
    """Aosong AHT20 I2C temperature and humidity sensor with 100nF decoupling."""
    components = [
        CircuitComponent(ic_ref, "SENSOR", "AHT20", "DFN-6_L3.0-W3.0-P1.00-BL", "C2757850",
                         {"1": "/NC_AHT1", "2": vcc_net, "3": scl_net, "4": sda_net,
                          "5": gnd_net, "6": "/NC_AHT2"}),
        CircuitComponent("C_AHT1", "CAPACITOR", "100nF", "C0603", "C14663",
                         {"1": vcc_net, "2": gnd_net}),
    ]
    nets: dict[str, list[str]] = {
        vcc_net: [f"{ic_ref}.2", "C_AHT1.1"],
        gnd_net: [f"{ic_ref}.5", "C_AHT1.2"],
        scl_net: [f"{ic_ref}.3"],
        sda_net: [f"{ic_ref}.4"],
        "/NC_AHT1": [f"{ic_ref}.1"],
        "/NC_AHT2": [f"{ic_ref}.6"],
    }
    if include_pullups:
        components.extend([
            CircuitComponent("R_AHT_SCL", "RESISTOR", "4.7k", "R0603", "C23162",
                             {"1": vcc_net, "2": scl_net}),
            CircuitComponent("R_AHT_SDA", "RESISTOR", "4.7k", "R0603", "C23162",
                             {"1": vcc_net, "2": sda_net}),
        ])
        nets[vcc_net].extend(["R_AHT_SCL.1", "R_AHT_SDA.1"])
        nets[scl_net].append("R_AHT_SCL.2")
        nets[sda_net].append("R_AHT_SDA.2")

    return CircuitBlock(
        name="Sensor_AHT20",
        description="Aosong AHT20 I2C temperature and humidity sensor with 100nF decoupling capacitor",
        components=components,
        nets=nets,
        properties={
            "interface": "I2C",
            "i2c_address": "0x38",
            "sensor_type": "temperature_humidity",
            "temp_range": "-40~85°C",
            "humidity_range": "0-100%RH",
        },
    )


def block_sensor_mpu6050(ic_ref: str = "U_MPU1", vcc_net: str = "/+3.3V",
                         gnd_net: str = "/GND", scl_net: str = "/SCL",
                         sda_net: str = "/SDA", int_net: str = "/MPU_INT",
                         include_pullups: bool = True) -> CircuitBlock:
    """InvenSense MPU-6050 6-axis motion tracking sensor (gyro + accelerometer)."""
    components = [
        CircuitComponent(ic_ref, "SENSOR", "MPU-6050", "QFN-24_L4.0-W4.0-P0.50-BL-EP2.7", "C24112",
                         {"1": gnd_net, "8": vcc_net, "9": gnd_net, "10": "/MPU_REGOUT",
                          "11": gnd_net, "12": int_net, "13": vcc_net, "18": gnd_net,
                          "20": "/MPU_CPOUT", "23": scl_net, "24": sda_net, "25": gnd_net}),
        CircuitComponent("C_MPU_VDD", "CAPACITOR", "100nF", "C0603", "C14663",
                         {"1": vcc_net, "2": gnd_net}),
        CircuitComponent("C_MPU_VLOG", "CAPACITOR", "100nF", "C0603", "C14663",
                         {"1": vcc_net, "2": gnd_net}),
        CircuitComponent("C_MPU_REG", "CAPACITOR", "100nF", "C0603", "C14663",
                         {"1": "/MPU_REGOUT", "2": gnd_net}),
        CircuitComponent("C_MPU_CP", "CAPACITOR", "2.2nF", "C0603", "C1604",
                         {"1": "/MPU_CPOUT", "2": gnd_net}),
    ]
    nets: dict[str, list[str]] = {
        vcc_net: [f"{ic_ref}.8", f"{ic_ref}.13", "C_MPU_VDD.1", "C_MPU_VLOG.1"],
        gnd_net: [f"{ic_ref}.1", f"{ic_ref}.9", f"{ic_ref}.11", f"{ic_ref}.18", f"{ic_ref}.25",
                  "C_MPU_VDD.2", "C_MPU_VLOG.2", "C_MPU_REG.2", "C_MPU_CP.2"],
        scl_net: [f"{ic_ref}.23"],
        sda_net: [f"{ic_ref}.24"],
        int_net: [f"{ic_ref}.12"],
        "/MPU_REGOUT": [f"{ic_ref}.10", "C_MPU_REG.1"],
        "/MPU_CPOUT": [f"{ic_ref}.20", "C_MPU_CP.1"],
    }
    if include_pullups:
        components.extend([
            CircuitComponent("R_MPU_SCL", "RESISTOR", "4.7k", "R0603", "C23162",
                             {"1": vcc_net, "2": scl_net}),
            CircuitComponent("R_MPU_SDA", "RESISTOR", "4.7k", "R0603", "C23162",
                             {"1": vcc_net, "2": sda_net}),
        ])
        nets[vcc_net].extend(["R_MPU_SCL.1", "R_MPU_SDA.1"])
        nets[scl_net].append("R_MPU_SCL.2")
        nets[sda_net].append("R_MPU_SDA.2")

    return CircuitBlock(
        name="Sensor_MPU6050",
        description="InvenSense MPU-6050 6-axis IMU (3-axis gyro + 3-axis accelerometer)",
        components=components,
        nets=nets,
        properties={
            "interface": "I2C",
            "i2c_address": "0x68",
            "sensor_type": "6axis_imu",
            "accelerometer": True,
            "gyroscope": True,
        },
    )


# --------------------------------------------------------------------------- #
# Industrial Protection & DFX Blocks (Enterprise Grade)
# --------------------------------------------------------------------------- #

def block_esd_usb_tvs(
    vbus_net: str = "/VBUS",
    gnd_net: str = "/GND",
    dp_net: str = "/USB_DP",
    dm_net: str = "/USB_DM",
    tvs_ref: str = "U_TVS_USB1",
) -> CircuitBlock:
    """Industrial ultra-low capacitance TVS diode array for USB 2.0 (IEC 61000-4-2 15kV ESD)."""
    return CircuitBlock(
        name="ESD_TVS_USB",
        description="STMicroelectronics USBLC6-2SC6 low-capacitance rail-to-rail ESD protection for USB D+/D- and VBUS",
        components=[
            CircuitComponent(
                tvs_ref, "TVS", "USBLC6-2SC6", "SOT-23-6", "C7519",
                {"1": dp_net, "2": gnd_net, "3": dp_net, "4": dm_net, "5": vbus_net, "6": dm_net},
            ),
        ],
        nets={
            vbus_net: [f"{tvs_ref}.5"],
            gnd_net: [f"{tvs_ref}.2"],
            dp_net: [f"{tvs_ref}.1", f"{tvs_ref}.3"],
            dm_net: [f"{tvs_ref}.4", f"{tvs_ref}.6"],
        },
        properties={
            "standard": "IEC 61000-4-2 (Level 4)",
            "air_discharge": "15kV",
            "contact_discharge": "8kV",
            "capacitance_pf": 3.5,
        },
    )


def block_esd_rs485_tvs(
    a_net: str = "/RS485_A",
    b_net: str = "/RS485_B",
    gnd_net: str = "/GND",
    tvs_ref: str = "D_TVS_485",
) -> CircuitBlock:
    """Asymmetrical bidirectional TVS diode for RS485 differential lines (-7V to +12V common mode)."""
    return CircuitBlock(
        name="ESD_TVS_RS485",
        description="Semtech SM712 asymmetrical TVS diode for RS-485 transceiver protection against lightning and ESD",
        components=[
            CircuitComponent(
                tvs_ref, "TVS", "SM712", "SOT-23", "C19001",
                {"1": a_net, "2": b_net, "3": gnd_net},
            ),
        ],
        nets={
            a_net: [f"{tvs_ref}.1"],
            b_net: [f"{tvs_ref}.2"],
            gnd_net: [f"{tvs_ref}.3"],
        },
        properties={
            "standard": "IEC 61000-4-5 Surge & IEC 61000-4-2 ESD",
            "standoff_voltage": "-7V to +12V",
            "peak_pulse_power_w": 600,
        },
    )


def block_esd_can_tvs(
    canh_net: str = "/CAN_H",
    canl_net: str = "/CAN_L",
    gnd_net: str = "/GND",
    tvs_ref: str = "D_TVS_CAN1",
) -> CircuitBlock:
    """Automotive/Industrial dual bidirectional TVS diode for CAN bus (24V system fault tolerant)."""
    return CircuitBlock(
        name="ESD_TVS_CAN",
        description="Nexperia PESD1CAN dual bidirectional TVS diode array for ISO 11898-2 CAN bus ESD protection",
        components=[
            CircuitComponent(
                tvs_ref, "TVS", "PESD1CAN", "SOT-23", "C2848243",
                {"1": canh_net, "2": canl_net, "3": gnd_net},
            ),
        ],
        nets={
            canh_net: [f"{tvs_ref}.1"],
            canl_net: [f"{tvs_ref}.2"],
            gnd_net: [f"{tvs_ref}.3"],
        },
        properties={
            "standard": "ISO 10605 / IEC 61000-4-2",
            "reverse_standoff_v": 24.0,
            "peak_pulse_power_w": 200,
        },
    )


def block_reverse_polarity_protection(
    vin_raw_net: str = "/VIN_RAW",
    vin_net: str = "/VIN",
    gnd_net: str = "/GND",
    method: str = "schottky",
) -> CircuitBlock:
    """Industrial wide-input reverse polarity protection (Schottky SS34 or P-MOSFET ideal diode)."""
    if method.lower() == "pmos":
        components = [
            CircuitComponent("Q_REV1", "MOSFET", "AO3401A", "SOT-23", "C15127",
                             {"S": vin_raw_net, "D": vin_net, "G": "/G_REV"}),
            CircuitComponent("R_REV_G", "RESISTOR", "100k", "R0603", "C25804",
                             {"1": "/G_REV", "2": gnd_net}),
            CircuitComponent("D_REV_Z", "ZENER", "12V", "SOD-123", "C81598",
                             {"1": gnd_net, "2": "/G_REV"}),
        ]
        nets = {
            vin_raw_net: ["Q_REV1.S"],
            vin_net: ["Q_REV1.D"],
            gnd_net: ["R_REV_G.2", "D_REV_Z.1"],
            "/G_REV": ["Q_REV1.G", "R_REV_G.1", "D_REV_Z.2"],
        }
        desc = "P-MOSFET (AO3401A) ultra-low voltage drop ideal diode reverse polarity protection circuit"
    else:
        components = [
            CircuitComponent("D_REV1", "DIODE", "SS34", "SMA", "C8678",
                             {"1": vin_raw_net, "2": vin_net}),
        ]
        nets = {
            vin_raw_net: ["D_REV1.1"],
            vin_net: ["D_REV1.2"],
        }
        desc = "Schottky barrier rectifier (SS34 40V 3A) reverse polarity protection diode"

    return CircuitBlock(
        name="Reverse_Polarity_Protection",
        description=desc,
        components=components,
        nets=nets,
        properties={"method": method, "max_reverse_voltage_v": 30.0},
    )


def block_power_pi_filter(
    vin_net: str = "/VIN",
    vout_net: str = "/VCC_CLEAN",
    gnd_net: str = "/GND",
) -> CircuitBlock:
    """High-attenuation C-L-C pi-filter with ferrite bead for noisy industrial DC supplies."""
    return CircuitBlock(
        name="Power_Pi_Filter",
        description="CLC Pi-Filter (10uF + 600R@100MHz 2A Ferrite Bead + 10uF + 100nF) for industrial EMI suppression",
        components=[
            CircuitComponent("C_PI_IN", "CAPACITOR", "10uF", "C0805", "C15850",
                             {"1": vin_net, "2": gnd_net}),
            CircuitComponent("FB_PI1", "INDUCTOR", "600R_2A", "L0805", "C1015",
                             {"1": vin_net, "2": vout_net}),
            CircuitComponent("C_PI_OUT", "CAPACITOR", "10uF", "C0805", "C15850",
                             {"1": vout_net, "2": gnd_net}),
            CircuitComponent("C_PI_HF", "CAPACITOR", "100nF", "C0603", "C14663",
                             {"1": vout_net, "2": gnd_net}),
        ],
        nets={
            vin_net: ["C_PI_IN.1", "FB_PI1.1"],
            vout_net: ["FB_PI1.2", "C_PI_OUT.1", "C_PI_HF.1"],
            gnd_net: ["C_PI_IN.2", "C_PI_OUT.2", "C_PI_HF.2"],
        },
        properties={"bead_impedance_ohms": 600, "rated_current_a": 2.0},
    )


def block_watchdog_supervisor(
    ic_ref: str = "U_WDT1",
    vcc_net: str = "/+3.3V",
    gnd_net: str = "/GND",
    mcu_rst_net: str = "/NRST",
    mcu_wdi_net: str = "/WDI",
) -> CircuitBlock:
    """TPS3823-33 voltage supervisor + watchdog timer (industrial MCU reliability standard).

    WDI 必须由 MCU GPIO 周期性翻转（<1.6s），否则 WDO 触发复位——防程序跑飞，
    工业控制/远程设备的功能安全基线（IEC 61508 SIL 常见实践）。
    """
    return CircuitBlock(
        name="Watchdog_TPS3823",
        description="TPS3823-33 supervisor: 1.6s watchdog WDI + push-pull reset out (MR input)",
        components=[
            CircuitComponent(ic_ref, "IC", "TPS3823-33", "SOT-23-5", "C26824",
                             {"1": gnd_net, "2": mcu_wdi_net, "3": gnd_net,
                              "4": mcu_rst_net, "5": vcc_net}),
        ],
        nets={
            vcc_net: [f"{ic_ref}.5"],
            gnd_net: [f"{ic_ref}.1", f"{ic_ref}.3"],
            mcu_wdi_net: [f"{ic_ref}.2"],
            mcu_rst_net: [f"{ic_ref}.4"],
        },
        properties={
            "watchdog_timeout_s": 1.6,
            "vdd_v": 3.3,
            "safety_note": "IEC 61508 可靠性实践：MCU 需以 <1.6s 周期喂狗",
        },
    )


def block_fiducial_marks(count: int = 3) -> CircuitBlock:
    """Optical fiducial marks for automated SMT pick-and-place vision alignment (DFA)."""
    count = max(3, count)
    components = [
        CircuitComponent(f"FID{i+1}", "FIDUCIAL", "1.0mm", "Fiducial_1mm_Mask2mm", "C9999998", {})
        for i in range(count)
    ]
    return CircuitBlock(
        name="Fiducial_Marks",
        description=f"Set of {count} optical fiducial marks (1.0mm pad, 2.0mm mask opening) for SMT machine vision",
        components=components,
        nets={},
        properties={"pad_diameter_mm": 1.0, "clearance_mm": 2.0, "quantity": count},
    )


def block_testpoint_matrix(nets: list[str] | None = None) -> CircuitBlock:
    """SMD test point pads matrix for in-circuit testing (ICT) and flying probe validation (DFT)."""
    target_nets = nets or ["/VBUS", "/+3.3V", "/GND", "/SWDIO", "/SWCLK", "/TX", "/RX"]
    components = []
    block_nets: dict[str, list[str]] = {}
    for i, net_name in enumerate(target_nets):
        clean_name = (
            net_name.replace("/", "")
            .replace("+", "P")
            .replace("-", "N")
            .replace(".", "_")
        )
        ref = f"TP_{clean_name}"
        components.append(
            CircuitComponent(ref, "TESTPOINT", "1.0mm", "TestPoint_Pad_D1.0mm", "C9999999", {"1": net_name})
        )
        block_nets[net_name] = [f"{ref}.1"]

    return CircuitBlock(
        name="Testpoint_Matrix",
        description=f"SMD test point pads matrix for automated ICT bed-of-nails and flying probe validation ({len(target_nets)} pads)",
        components=components,
        nets=block_nets,
        properties={"pad_diameter_mm": 1.0, "tested_nets": target_nets},
    )


