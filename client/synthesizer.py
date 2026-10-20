"""Natural Language Synthesizer Client (Community Edition).

Design contract
---------------
`synthesize_from_prompt` is a **deterministic** keyword-to-block mapper, not a
generative model. The same prompt always produces byte-identical output, which
is what makes the emitted netlist safe to feed into downstream compilation.

Supported intents
-----------------
  * target MCU     : STM32F103C8T6 (default) / ESP32-C3 / ESP32-S3 / RP2040 / STC89C52RC
  * power          : Type-C receptacle + dual 5.1k CC, AMS1117-3.3V LDO
  * buttons        : debounced tactile switches (count parsed from the prompt)
  * status LED     : indicator with current-limiting resistor
  * buzzer         : NPN driver + flyback diode
  * I2C header     : 4-pin bus header with 4.7k pull-ups
  * sensors        : AHT20 temperature/humidity, MPU-6050 6-axis IMU
  * fieldbuses     : RS-485 (SP3485) half-duplex, CAN (SN65HVD230)
  * protection     : USB/RS-485/CAN TVS arrays, reverse-polarity, π filter
  * manufacturing  : ICT test-point matrix, optical fiducials (Mark points)

Two diagnostic lists are returned so callers can tell the two failure modes apart:

  * ``unmatched``     — the user asked for something this DSL cannot build yet
                        (e.g. "以太网", "继电器", "电机驱动"). This is an actionable
                        capability gap and is what an LLM caller should surface.
  * ``not_requested`` — optional blocks the prompt simply did not mention
                        (e.g. no button was asked for). Informational only.

Status: **alpha**. The block set is intentionally small and fully unit-tested.
"""

from __future__ import annotations

import re
from typing import Any

from .chip_rules import (
    ChipPinoutRule,
    apply_chip_pinout,
    detect_chip_from_prompt,
    get_chip_rule,
    register_chip_rule,
)
from .circuit_blocks import (
    block_battery_tp4056,
    block_button,
    block_buzzer,
    block_can_transceiver,
    block_crystal_clock,
    block_esd_can_tvs,
    block_esd_rs485_tvs,
    block_esd_usb_tvs,
    block_ethernet_phy_w5500,
    block_fiducial_marks,
    block_i2c_header,
    block_isolated_adc_ina219,
    block_led,
    block_motor_driver_drv8825,
    block_optocoupler_isolated_io,
    block_power_ldo_3v3,
    block_power_pi_filter,
    block_reverse_polarity_protection,
    block_rs485_transceiver,
    block_screw_terminal_vmot,
    block_sensor_aht20,
    block_sensor_mpu6050,
    block_testpoint_matrix,
    block_usb_c_power,
    block_watchdog_supervisor,
)

KNOWN_CHIPS = ("STM32F103C8T6", "ESP32-C3", "ESP32-S3", "RP2040", "STC89C52RC")

# Ordered longest-match-first so "esp32-c3" wins over a bare "esp32" mention.
_CHIP_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("esp32-c3", "esp32c3", "esp32 c3"), "ESP32-C3"),
    (("esp32-s3", "esp32s3", "esp32 s3"), "ESP32-S3"),
    (("rp2040",), "RP2040"),
    (("stc89c52", "89c52", "51单片机", "51 单片机"), "STC89C52RC"),
    (("stm32", "stm32f103"), "STM32F103C8T6"),
)

_POWER_TOKENS = ("type-c", "type c", "usb-c", "usb c", "typec", "usb", "供电", "取电", "电源")
_LED_TOKENS = ("led", "指示灯", "状态灯", "呼吸灯")
_BUZZER_TOKENS = ("蜂鸣器", "buzzer", "报警")
_I2C_TOKENS = ("i2c", "i²c", "传感器", "sensor", "oled")
_AHT20_TOKENS = ("aht20", "aht-20", "aht", "温湿度", "温度计", "湿度计", "dht", "sht")
_MPU6050_TOKENS = ("mpu6050", "mpu-6050", "mpu", "六轴", "陀螺仪", "加速度计", "imu", "姿态")
_BUTTON_TOKENS = ("按键", "按钮", "button", "key")
_CRYSTAL_TOKENS = ("晶振", "crystal", "外部时钟", "振荡器")
_RS485_TOKENS = ("rs485", "485", "max485", "sp3485", "差分串口", "modbus")
# NOTE: a bare lowercase "can" is deliberately NOT a token — it collides with the
# ordinary English verb ("a board that can drive a relay"). CAN-bus intent is
# detected by _has_can() below, which requires an explicit bus marker or the
# uppercase acronym.
_CAN_BUS_TOKENS = ("can总线", "can 总线", "canbus", "can-bus", "tja1050", "sn65hvd230", "can收发器", "can收发")
_BATTERY_TOKENS = ("battery", "锂电池", "充电", "tp4056", "电池供电", "充放电", "单节锂电")

# Features a user can reasonably ask for that this DSL does not implement yet.
# Surfacing these is the whole point of the `unmatched` field: the caller must be
# able to tell "we didn't understand you" apart from "we simply didn't need it".
_UNSUPPORTED_TOKENS: dict[str, tuple[str, ...]] = {
    "ethernet": ("以太网", "ethernet", "rj45", "网口", "有线网络"),
    "wifi": ("wifi", "wi-fi", "无线网络", "无线通信"),
    "bluetooth": ("蓝牙", "bluetooth", "ble"),
    "relay": ("继电器", "relay"),
    "motor_driver": ("电机驱动", "步进电机", "直流电机", "舵机", "servo", "motor driver"),
    "display": ("屏幕", "显示屏", "lcd", "tft", "数码管"),
    "sd_card": ("sd卡", "tf卡", "sd card"),
    "camera": ("摄像头", "camera", "ov2640", "ov7670"),
    "audio": ("音频", "麦克风", "扬声器", "功放"),
    "rs232": ("rs232", "串口232"),
    "poe": ("poe", "以太网供电"),
    "rfid": ("rfid", "nfc", "读卡器"),
    "gps": ("gps", "北斗", "定位模块"),
    "lora": ("lora", "lora模块"),
}

_INDUSTRIAL_TOKENS = ("工业", "工业级", "industrial", "高可靠", "生产级")
_TVS_TOKENS = ("tvs", "esd", "防静电", "浪涌", "防护", "保护", "防雷")
_WATCHDOG_TOKENS = ("看门狗", "watchdog", "wdt", "复位监控", "supervisor", "防跑飞")
_REV_TOKENS = ("防反接", "反接保护", "polarity", "肖特基防反")
_PI_TOKENS = ("pi滤波", "π滤波", "滤波", "磁珠", "clc", "lc滤波")
_DFT_TOKENS = ("测试点", "testpoint", "ict", "飞针", "测试焊盘")
_DFA_TOKENS = ("mark点", "mark", "fiducial", "光学定位", "对准点")
_ETHERNET_TOKENS = ("ethernet", "以太网", "网口", "rj45", "w5500", "lan")
_INA219_TOKENS = ("电流采样", "功率监测", "ina219", "power monitor", "current monitor", "电量计")
_MOTOR_TOKENS = ("电机", "步进电机", "drv8825", "stepper", "motor", "马达")
_OPTO_TOKENS = ("光耦", "隔离输入", "plc", "optocoupler", "pc817", "24v")

_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "两": 2}


def _detect_chip(prompt_lower: str) -> str:
    for tokens, chip_id in _CHIP_RULES:
        if any(t in prompt_lower for t in tokens):
            return chip_id
    custom = detect_chip_from_prompt(prompt_lower)
    if custom is not None:
        return custom.chip_id
    return "STM32F103C8T6"


def _detect_count(prompt: str, tokens: tuple[str, ...], default: int = 1) -> int:
    """Count devices, e.g. '2个按键' -> 2, '三个按键' -> 3."""
    for i in range(1, 9):
        if (f"{i}个" in prompt or f"{i} 个" in prompt or f"{i}按键" in prompt) and any(t in prompt for t in tokens):
            return i
    for cn, n in _CN_NUM.items():
        if f"{cn}个" in prompt and any(t in prompt for t in tokens):
            return n
    return default


def _has(prompt_lower: str, prompt: str, tokens: tuple[str, ...]) -> bool:
    return any(t in prompt_lower or t in prompt for t in tokens)


def _has_can_bus(prompt_lower: str, prompt: str) -> bool:
    """Detect CAN-bus intent without matching the ordinary English verb 'can'.

    Matches either an explicit bus marker (can总线 / canbus / TJA1050 / ...) or the
    uppercase acronym `CAN` appearing as a standalone word.
    """
    if _has(prompt_lower, prompt, _CAN_BUS_TOKENS):
        return True
    return re.search(r"\bCAN\b", prompt) is not None


def _detect_unsupported(prompt_lower: str, prompt: str) -> list[str]:
    """Return the features the user asked for that this DSL cannot synthesize yet."""
    return [feature for feature, tokens in _UNSUPPORTED_TOKENS.items() if _has(prompt_lower, prompt, tokens)]


def synthesize_from_prompt(
    prompt: str,
    chip_id: str | None = None,
    custom_chip: dict[str, Any] | ChipPinoutRule | None = None,
    pin_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Map a natural-language hardware description to blocks + a netlist."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    prompt_lower = prompt.lower()

    rule = None
    if custom_chip is not None:
        rule = register_chip_rule(custom_chip)
        if chip_id is None:
            chip_id = rule.chip_id

    if chip_id is None:
        chip_id = _detect_chip(prompt_lower)

    if rule is None:
        rule = get_chip_rule(chip_id)

    blocks = []
    not_requested: list[str] = []
    unsupported: list[str] = _detect_unsupported(prompt_lower, prompt)

    # The logic rail every peripheral block pulls up to. Blocks default to
    # /+3.3V, which is right for most parts but wrong for a 5 V MCU: a 51 board
    # ended up with buttons and an LED pulling up to a 3.3 V rail that nothing
    # produced, while the MCU itself sat on /+5V.
    logic_rail = "/+5V" if chip_id == "STC89C52RC" else "/+3.3V"

    # --- power ------------------------------------------------------------
    wants_power_input = _has(prompt_lower, prompt, _POWER_TOKENS)
    if not wants_power_input:
        not_requested.append("power")

    # --- buttons ----------------------------------------------------------
    if _has(prompt_lower, prompt, _BUTTON_TOKENS):
        for i in range(1, _detect_count(prompt, _BUTTON_TOKENS) + 1):
            blocks.append(block_button(f"SW{i}", f"/BTN{i}", vcc_net=logic_rail))
    else:
        not_requested.append("button")

    # --- status LED -------------------------------------------------------
    if _has(prompt_lower, prompt, _LED_TOKENS):
        blocks.append(block_led(vcc_net=logic_rail))
    else:
        not_requested.append("led")

    # --- buzzer -----------------------------------------------------------
    if _has(prompt_lower, prompt, _BUZZER_TOKENS):
        blocks.append(block_buzzer(vcc_net=logic_rail))
    else:
        not_requested.append("buzzer")

    # --- sensors (AHT20 & MPU6050) ----------------------------------------
    has_aht = _has(prompt_lower, prompt, _AHT20_TOKENS)
    has_mpu = _has(prompt_lower, prompt, _MPU6050_TOKENS)

    if has_aht:
        blocks.append(block_sensor_aht20(vcc_net=logic_rail))

    if has_mpu:
        blocks.append(block_sensor_mpu6050(vcc_net=logic_rail))

    # --- I2C header -------------------------------------------------------
    if _has(prompt_lower, prompt, _I2C_TOKENS):
        header_explicit = any(k in prompt for k in ("插座", "排针", "接口", "header", "oled"))
        if not (has_aht or has_mpu) or header_explicit:
            blocks.append(block_i2c_header(vcc_net=logic_rail))
    elif not (has_aht or has_mpu):
        not_requested.append("i2c")

    # --- external crystal -------------------------------------------------
    if _has(prompt_lower, prompt, _CRYSTAL_TOKENS):
        blocks.append(block_crystal_clock())
    else:
        not_requested.append("crystal")

    # --- industrial fieldbuses & battery ----------------------------------
    if _has(prompt_lower, prompt, _RS485_TOKENS):
        blocks.append(block_rs485_transceiver())

    if _has_can_bus(prompt_lower, prompt):
        blocks.append(block_can_transceiver())

    if _has(prompt_lower, prompt, _BATTERY_TOKENS):
        blocks.append(block_battery_tp4056())

    # --- industrial protection & DFX --------------------------------------
    is_industrial = _has(prompt_lower, prompt, _INDUSTRIAL_TOKENS)
    has_tvs = _has(prompt_lower, prompt, _TVS_TOKENS)

    has_rs485 = any(b.name == "RS485_Transceiver" for b in blocks)
    has_can = any(b.name == "CAN_Transceiver" for b in blocks)

    if has_rs485 and (is_industrial or has_tvs):
        blocks.append(block_esd_rs485_tvs())

    if has_can and (is_industrial or has_tvs):
        blocks.append(block_esd_can_tvs())

    if _has(prompt_lower, prompt, _DFT_TOKENS) or is_industrial:
        blocks.append(block_testpoint_matrix())

    if _has(prompt_lower, prompt, _WATCHDOG_TOKENS):
        blocks.append(block_watchdog_supervisor())

    if _has(prompt_lower, prompt, _DFA_TOKENS) or is_industrial:
        blocks.append(block_fiducial_marks())

    if _has(prompt_lower, prompt, _ETHERNET_TOKENS):
        blocks.append(block_ethernet_phy_w5500())

    if _has(prompt_lower, prompt, _INA219_TOKENS):
        blocks.append(block_isolated_adc_ina219())

    if _has(prompt_lower, prompt, _MOTOR_TOKENS):
        blocks.append(block_motor_driver_drv8825())

    if _has(prompt_lower, prompt, _OPTO_TOKENS):
        blocks.append(block_optocoupler_isolated_io())

    # --- power chain ------------------------------------------------------
    #
    # A motor driver runs from its own high-voltage input, not from the logic
    # rail. Without a terminal feeding /VMOT_24V the driver is a chip whose power
    # pins go nowhere, which is what the ERC now reports as
    # POWER_RAIL_WITHOUT_SOURCE — correctly, on a board that was never going to
    # turn a motor.
    #
    # The chain is built here, once, as a series rather than as independent
    # blocks that happen to share net names. Doing it in the order the prompt
    # mentioned things produced parallel branches — `/VBUS` fed both the LDO and
    # the pi-filter, so `/VIN` and `/VCC_CLEAN` dead-ended at the filter and the
    # regulator drew from unfiltered 5 V. Electrically that is two half-circuits,
    # not one supply.
    #
    # Series topology, which is what the blocks were written for:
    #
    #   VBUS (Type-C) -> reverse-polarity diode -> VIN -> pi-filter -> VCC_CLEAN
    #                                                        |
    #                                                        +-> LDO -> +3.3V
    #
    # A stage is added when the design needs it or the prompt asked for it, and
    # never otherwise, so a bare 5 V 51 board does not grow a 3.3 V regulator it
    # has no use for. `power_chain_added` records what was added on the user's
    # behalf so the output stays honest about it.
    power_chain_added: list[str] = []
    block_names = {b.name for b in blocks}
    needs_3v3 = any(
        comp.kind in {"IC", "MCU", "SENSOR", "TRANSCEIVER"} and "/+3.3V" in comp.pins.values()
        for b in blocks
        for comp in b.components
    )
    # The MCU itself is a load on the 3.3 V rail even before its pins are bound:
    # a 3.3 V part needs a 3.3 V supply regardless of what peripherals the prompt
    # mentioned. Checking only block components meant an RP2040 dev board with a
    # Type-C connector got no regulator at all, and the MCU's supply pins were
    # then bound to a rail nothing produced.
    if getattr(rule, "supply_voltage", 3.3) <= 3.6 and chip_id != "STC89C52RC":
        needs_3v3 = True
    is_5v_part = chip_id == "STC89C52RC" or getattr(rule, "supply_voltage", 3.3) > 3.6
    # A 5 V MCU still needs 3.3 V when a peripheral block asks for it: the RS485
    # transceiver on a 51 board sits on /+3.3V, and without a regulator the board
    # shipped with that rail unsourced. The rail's need is decided by what is on
    # it, not by the MCU's own supply voltage.
    needs_ldo = needs_3v3
    needs_protection = (
        _has(prompt_lower, prompt, _REV_TOKENS) or is_industrial or wants_power_input
    )
    needs_filter = (
        _has(prompt_lower, prompt, _PI_TOKENS) or (is_industrial and (has_rs485 or has_can))
    )

    # Any of the downstream stages implies the 5 V input exists to feed it.
    needs_input = wants_power_input or needs_ldo or needs_filter
    if needs_input and "USB_C_Power" not in block_names:
        blocks.insert(0, block_usb_c_power())
        if not wants_power_input:
            power_chain_added.append("USB_C_Power")

    # The LDO input net depends on what sits between it and the connector:
    # the filter's output if a filter is present, otherwise the protection
    # diode's output, otherwise the connector's own rail. Picking the wrong one
    # leaves an orphan net (`/VIN` fed by the diode, read by nothing).
    # Walk the chain from the connector forward and take the last stage that
    # exists before the regulator. Anything else leaves the regulator drawing
    # from a net nothing drives.
    if needs_filter:
        ldo_vin = "/VCC_CLEAN"
    elif needs_protection:
        # Protection is present but no filter: the diode drives /VBUS when a
        # regulator follows it (see prot_out below), so that is the LDO input.
        ldo_vin = "/VBUS"
    else:
        ldo_vin = "/VBUS"
    if needs_filter and "Power_Pi_Filter" not in block_names:
        # The filter's input is the protection diode's output when protection is
        # present, otherwise the connector rail directly. Defaulting to /VBUS
        # while the diode drove /VIN left the filter fed by the wrong net and
        # /VIN with a single endpoint.
        blocks.append(block_power_pi_filter(vin_net="/VIN" if needs_protection else "/VBUS"))
        power_chain_added.append("Power_Pi_Filter")
    if needs_protection and "Reverse_Polarity_Protection" not in block_names:
        # Protection sits between the connector and everything else. Its output
        # net is whatever consumes it next: the filter's input if a filter
        # follows, otherwise the rail the parts actually use — a diode feeding a
        # net with no load is an orphan net, which the ERC correctly flags.
        if needs_filter:
            prot_out = "/VIN"
        elif needs_ldo:
            # The regulator's input is /VBUS, so the diode drives that rail.
            prot_out = "/VBUS"
        elif is_5v_part:
            # A 5 V part with no regulator: the diode output *is* the rail.
            prot_out = "/+5V"
        else:
            prot_out = "/VBUS"
        blocks.append(block_reverse_polarity_protection(vin_net=prot_out))
        power_chain_added.append("Reverse_Polarity_Protection")
    if needs_ldo and "LDO_3V3" not in block_names:
        blocks.append(block_power_ldo_3v3(vin_net=ldo_vin))
        power_chain_added.append("LDO_3V3")

    # A high-voltage load needs its own supply terminal. The motor driver's
    # /VMOT_24V is fed by a screw terminal, not by the 5 V USB input — a board
    # that drives a stepper from a Type-C port would draw 2.5 A through a
    # connector rated for far less.
    has_hv_load = any(b.name == "Motor_Driver_DRV8825" for b in blocks)
    if has_hv_load and "Screw_Terminal_VMOT" not in {b.name for b in blocks}:
        blocks.append(block_screw_terminal_vmot())
        power_chain_added.append("Screw_Terminal_VMOT")

    # --- USB ESD protection, after the power chain -------------------------
    #
    # This check has to run after the connector exists. `USB_C_Power` can be
    # added by the power-chain step above (a design that needs 3.3 V gets a
    # Type-C input whether or not the prompt said "供电"), so asking earlier
    # missed exactly the boards that have a USB port. The result was a Type-C
    # receptacle with bare D+/D- and a CRITICAL EMC finding in the DFX audit —
    # the audit was right, the synthesizer had simply never looked.
    has_usb = any(b.name == "USB_C_Power" for b in blocks)
    if has_usb and (is_industrial or has_tvs) and "ESD_TVS_USB" not in {b.name for b in blocks}:
        blocks.append(block_esd_usb_tvs())


    # --- flatten (insertion order is deterministic) ------------------------
    modules: dict[str, Any] = {}
    net_merge: dict[str, list[str]] = {}

    for blk in blocks:
        for comp in blk.components:
            if comp.ref in modules:
                raise ValueError(f"duplicate designator across blocks: {comp.ref}")
            modules[comp.ref] = {
                "kind": comp.kind,
                "value": comp.value,
                "package": comp.package,
                "lcsc": comp.lcsc,
            }
        for net, endpoints in blk.nets.items():
            bucket = net_merge.setdefault(net, [])
            for ep in endpoints:
                if ep not in bucket:
                    bucket.append(ep)

    connections = [{"net": net, "points": pts} for net, pts in net_merge.items()]

    result = {
        "chip_id": chip_id,
        "prompt": prompt,
        "modules": modules,
        "netlist": {"connections": connections, "modules": modules},
        "block_names": [b.name for b in blocks],
        # `unmatched` = what the user asked for that this DSL cannot build yet.
        # `not_requested` = optional blocks the prompt did not mention (informational).
        "unmatched": unsupported,
        "not_requested": not_requested,
    }

    if rule is not None or pin_mapping is not None:
        apply_chip_pinout(result, chip_rule=rule, custom_overrides=pin_mapping)

    return result


if __name__ == "__main__":
    import json
    import sys

    p = (
        sys.argv[1]
        if len(sys.argv) > 1
        else ("基于 ESP32-C3 的环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键")
    )
    print(json.dumps(synthesize_from_prompt(p), ensure_ascii=False, indent=2))
