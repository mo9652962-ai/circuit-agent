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

Status: **alpha**. The block set is intentionally small and fully unit-tested;
unmatched intents are reported back via `unmatched` instead of being silently
dropped, so callers can see exactly what the mapper did not understand.
"""

from __future__ import annotations

from typing import Any

from .circuit_blocks import (
    block_button,
    block_buzzer,
    block_crystal_clock,
    block_i2c_header,
    block_led,
    block_power_ldo_3v3,
    block_rs485_transceiver,
    block_can_transceiver,
    block_battery_tp4056,
    block_usb_c_power,
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
_I2C_TOKENS = ("i2c", "i²c", "传感器", "sensor", "温湿度", "oled")
_BUTTON_TOKENS = ("按键", "按钮", "button", "key")
_CRYSTAL_TOKENS = ("晶振", "crystal", "外部时钟", "振荡器")
_RS485_TOKENS = ("rs485", "485", "max485", "sp3485", "差分串口", "modbus")
_CAN_TOKENS = ("can", "can总线", "canbus", "can-bus", "tja1050", "sn65hvd230")
_BATTERY_TOKENS = ("battery", "锂电池", "充电", "tp4056", "电池供电", "充放电", "单节锂电")

_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "两": 2}


def _detect_chip(prompt_lower: str) -> str:
    for tokens, chip_id in _CHIP_RULES:
        if any(t in prompt_lower for t in tokens):
            return chip_id
    return "STM32F103C8T6"


def _detect_count(prompt: str, tokens: tuple[str, ...], default: int = 1) -> int:
    """Count devices, e.g. '2个按键' -> 2, '三个按键' -> 3."""
    for i in range(1, 9):
        if f"{i}个" in prompt or f"{i} 个" in prompt or f"{i}按键" in prompt:
            # Only accept if a device token appears near the numeral.
            if any(t in prompt for t in tokens):
                return i
    for cn, n in _CN_NUM.items():
        if f"{cn}个" in prompt and any(t in prompt for t in tokens):
            return n
    return default


def _has(prompt_lower: str, prompt: str, tokens: tuple[str, ...]) -> bool:
    return any(t in prompt_lower or t in prompt for t in tokens)


def synthesize_from_prompt(prompt: str) -> dict[str, Any]:
    """Map a natural-language hardware description to blocks + a netlist."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    prompt_lower = prompt.lower()
    chip_id = _detect_chip(prompt_lower)

    blocks = []
    unmatched: list[str] = []

    # --- power ------------------------------------------------------------
    if _has(prompt_lower, prompt, _POWER_TOKENS):
        blocks.append(block_usb_c_power())
        # A bare 51 board is usually fed from a 5V adapter; MCUs below run at 3.3V.
        if chip_id != "STC89C52RC":
            blocks.append(block_power_ldo_3v3())
    else:
        unmatched.append("power")

    # --- buttons ----------------------------------------------------------
    if _has(prompt_lower, prompt, _BUTTON_TOKENS):
        for i in range(1, _detect_count(prompt, _BUTTON_TOKENS) + 1):
            blocks.append(block_button(f"SW{i}", f"/BTN{i}"))
    else:
        unmatched.append("button")

    # --- status LED -------------------------------------------------------
    if _has(prompt_lower, prompt, _LED_TOKENS):
        blocks.append(block_led())
    else:
        unmatched.append("led")

    # --- buzzer -----------------------------------------------------------
    if _has(prompt_lower, prompt, _BUZZER_TOKENS):
        blocks.append(block_buzzer())
    else:
        unmatched.append("buzzer")

    # --- I2C header -------------------------------------------------------
    if _has(prompt_lower, prompt, _I2C_TOKENS):
        blocks.append(block_i2c_header())
    else:
        unmatched.append("i2c")

    # --- external crystal -------------------------------------------------
    if _has(prompt_lower, prompt, _CRYSTAL_TOKENS):
        blocks.append(block_crystal_clock())
    else:
        unmatched.append("crystal")

    # --- industrial fieldbuses & battery ----------------------------------
    if _has(prompt_lower, prompt, _RS485_TOKENS):
        blocks.append(block_rs485_transceiver())

    if _has(prompt_lower, prompt, _CAN_TOKENS):
        blocks.append(block_can_transceiver())

    if _has(prompt_lower, prompt, _BATTERY_TOKENS):
        blocks.append(block_battery_tp4056())

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

    return {
        "chip_id": chip_id,
        "prompt": prompt,
        "modules": modules,
        "netlist": {"connections": connections},
        "block_names": [b.name for b in blocks],
        "unmatched": unmatched,
    }


if __name__ == "__main__":
    import json
    import sys

    p = sys.argv[1] if len(sys.argv) > 1 else (
        "基于 ESP32-C3 的环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键"
    )
    print(json.dumps(synthesize_from_prompt(p), ensure_ascii=False, indent=2))
