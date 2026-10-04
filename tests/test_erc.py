"""ERC 电气规则门禁测试（工业级升级轮）。

覆盖：5 条规则的正反例 + 门禁语义 + MCP 工具集成（run_erc / synthesize 附带 erc）。
"""
from __future__ import annotations

from client.erc import erc_allowed, erc_gate, run_erc
from client.synthesizer import synthesize_from_prompt


def _mk(modules, connections):
    return run_erc(modules, connections)


def test_pass_on_full_design():
    """完整设计（USB-C + LDO + CAN）：无 blocking/error。"""
    res = synthesize_from_prompt("STM32F103 CAN RS485 USB-C power LDO")
    gate = erc_gate(_mk(res["modules"], res["netlist"]["connections"]))
    assert gate["allowed"] is True, [i for i in gate.items()]
    assert gate["counts"]["blocking"] == 0 and gate["counts"]["error"] == 0


def test_missing_gnd_blocks():
    """无 GND 网络 → blocking。"""
    gate = erc_gate(_mk(
        {"R1": {"kind": "RESISTOR", "value": "10k", "package": "R0603", "lcsc": "C1"}},
        [{"net": "/SIG", "points": ["R1.1"]}]))
    assert gate["allowed"] is False
    assert gate["counts"]["blocking"] == 1


def test_floating_net_warning_reserved_interface():
    """单点网络 → warning（预留外部接口语义），不阻断交付。"""
    issues = _mk(
        {"R1": {"kind": "RESISTOR", "value": "10k", "package": "R0603", "lcsc": ""},
         "R2": {"kind": "RESISTOR", "value": "10k", "package": "R0603", "lcsc": ""}},
        [{"net": "/GND", "points": ["R1.2", "R2.2"]},
         {"net": "/SIG", "points": ["R1.1"]}])
    hit = [i for i in issues if i["code"] == "FLOATING_NET"]
    assert len(hit) == 1 and hit[0]["severity"] == "warning"
    assert hit[0]["object_id"] == "net:/SIG"
    assert erc_allowed(issues) is True


def test_empty_net_error():
    """0 点网络 → error，阻断交付。"""
    issues = _mk(
        {"R1": {"kind": "RESISTOR", "value": "10k", "package": "R0603", "lcsc": ""}},
        [{"net": "/GND", "points": ["R1.2"]},
         {"net": "/DEAD", "points": []}])
    hit = [i for i in issues if i["code"] == "EMPTY_NET"]
    assert len(hit) == 1 and hit[0]["severity"] == "error"
    assert erc_allowed(issues) is False


def test_unknown_component_error():
    """连接点引用不存在的位号 → error。"""
    issues = _mk(
        {"R1": {"kind": "RESISTOR", "value": "10k", "package": "R0603", "lcsc": ""}},
        [{"net": "/GND", "points": ["R1.2", "GHOST.1"]}])
    codes = {i["code"] for i in issues}
    assert "UNKNOWN_COMPONENT" in codes


def test_missing_power_warning():
    """有 IC 无电源网络 → warning（不阻断）。"""
    issues = _mk(
        {"U1": {"kind": "IC", "value": "CAN", "package": "SOIC-8", "lcsc": ""},
         "R1": {"kind": "RESISTOR", "value": "10k", "package": "R0603", "lcsc": ""}},
        [{"net": "/GND", "points": ["U1.GND", "R1.2"]},
         {"net": "/BUS", "points": ["U1.CANH"]}])
    codes = {i["code"]: i["severity"] for i in issues}
    assert codes.get("MISSING_POWER_NET") == "warning"
    assert erc_allowed(issues) is True


def test_missing_decoupling_warning_and_pass():
    """IC + 无 100nF → warning；加 100nF 后消失。"""
    mods = {"U1": {"kind": "IC", "value": "MCU", "package": "QFN", "lcsc": ""},
            "R1": {"kind": "RESISTOR", "value": "10k", "package": "R0603", "lcsc": ""}}
    conns = [{"net": "/GND", "points": ["U1.GND", "R1.2"]},
             {"net": "/+3.3V", "points": ["U1.VDD"]}]
    assert any(i["code"] == "MISSING_DECOUPLING" for i in _mk(mods, conns))
    mods["C1"] = {"kind": "CAPACITOR", "value": "100nF", "package": "C0603", "lcsc": ""}
    conns.append({"net": "/+3.3V", "points": ["C1.1"]})
    conns.append({"net": "/GND", "points": ["C1.2"]})
    assert not any(i["code"] == "MISSING_DECOUPLING" for i in _mk(mods, conns))


def test_gate_shape_matches_drc():
    """erc_gate 与 DRC.gate 同形：allowed/counts/worst/total。"""
    g = erc_gate([])
    assert g == {"allowed": True, "counts": {"info": 0, "warning": 0, "error": 0,
                                             "blocking": 0}, "worst": "info", "total": 0}


# ── MCP 集成 ─────────────────────────────────────────────────────
def test_mcp_synthesize_includes_erc():
    from client.mcp_server import handle_tool_call

    out = handle_tool_call("synthesize_circuit", {"prompt": "ESP32-C3 CAN USB-C power LDO"})
    assert "isError" not in out
    payload = out["content"][0]["text"]
    import json
    res = json.loads(payload)
    assert "erc" in res and "allowed" in res["erc"]


def test_mcp_run_erc_tool():
    from client.mcp_server import handle_tool_call

    out = handle_tool_call("run_erc", {
        "netlist": {"connections": [{"net": "/SIG", "points": ["R1.1"]}]},
        "modules": {"R1": {"kind": "RESISTOR", "value": "10k", "package": "R0603"}},
    })
    import json
    res = json.loads(out["content"][0]["text"])
    assert res["gate"]["allowed"] is False
    codes = {i["code"] for i in res["issues"]}
    assert "FLOATING_NET" in codes and "MISSING_GND" in codes


def test_mcp_run_erc_requires_netlist():
    from client.mcp_server import handle_tool_call

    out = handle_tool_call("run_erc", {})
    assert out.get("isError") is True
