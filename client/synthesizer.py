"""Natural Language Synthesizer Client (Public Community Edition)."""

from __future__ import annotations

from typing import Any
from .circuit_blocks import block_usb_c_power, block_power_ldo_3v3, block_button


def synthesize_from_prompt(prompt: str) -> dict[str, Any]:
    """Translate natural language hardware prompt into structured modules & netlists."""
    prompt_lower = prompt.lower()

    # Detect target MCU
    chip_id = "STM32F103C8T6"
    if "esp32-c3" in prompt_lower or "esp32c3" in prompt_lower:
        chip_id = "ESP32-C3"
    elif "rp2040" in prompt_lower:
        chip_id = "RP2040"
    elif "esp32-s3" in prompt_lower or "esp32s3" in prompt_lower:
        chip_id = "ESP32-S3"
    elif "51" in prompt_lower or "89c52" in prompt_lower:
        chip_id = "STC89C52RC"

    blocks = []
    # Power detection
    if any(k in prompt_lower for k in ("type-c", "type c", "usb-c", "usb c", "供电", "usb")):
        blocks.append(block_usb_c_power())
        if chip_id in ("STM32F103C8T6", "ESP32-C3", "RP2040", "ESP32-S3"):
            blocks.append(block_power_ldo_3v3())

    # Buttons detection
    if "按键" in prompt or "button" in prompt_lower:
        btn_count = 2 if ("2个" in prompt or "两个" in prompt or "2按键" in prompt) else 1
        for i in range(1, btn_count + 1):
            blocks.append(block_button(f"SW{i}", f"/BTN{i}"))

    # Synthesize module mapping
    modules: dict[str, Any] = {}
    netlist_conns: list[dict[str, Any]] = []

    for blk in blocks:
        for comp in blk.components:
            modules[comp.ref] = {
                "kind": comp.kind,
                "value": comp.value,
                "package": comp.package,
                "lcsc": comp.lcsc,
            }
        for net, endpoints in blk.nets.items():
            netlist_conns.append({"net": net, "points": endpoints})

    return {
        "chip_id": chip_id,
        "prompt": prompt,
        "modules": modules,
        "netlist": {
            "connections": netlist_conns,
        },
    }
