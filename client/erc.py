"""ERC (Electrical Rules Check) —— 网表级电气规则门禁。

工业定位：与 wave-fixture-ai 的 DRC 生产门禁同一套治理模式——设计产物必须过
确定性规则检查才能交付。ERC 在网表契约（SSOT）上运行，每条发现带 severity
与出处，blocking/error 阻止交付。

规则集（每条带出处）：
- MISSING_GND (blocking)：无 GND 网络——任何电路都必须有参考地（IPC J-STD-001
  组件接地前提；无地网=网表不可成立）。
- EMPTY_NET (error)：0 个连接点的网络——空网络意味着断线或生成缺陷。
- FLOATING_NET (warning)：只有 1 个连接点的网络——预留外部接口（CANH 待接总线、
  测试点）是合法设计（KiCad ERC 语义），但需人工豁免确认。
- UNKNOWN_COMPONENT (error)：连接点引用了 modules 中不存在的位号——引脚归属
  错位（对齐 KiCad ERC "pin not driven/unknown symbol"）。
- MISSING_POWER_NET (warning)：无任何电源网络（VBUS/VCC/VDD/5V/3V3/VIN/VOUT）——
  有 IC 无电源域通常意味着电源块缺失（数据手册供电前提）。
- MISSING_DECOUPLING (warning)：存在 IC 但无 100nF/0.1u 去耦电容——行业惯例
  每个 IC 电源引脚配 100nF 陶瓷去耦（Murata/Generic layout guide; IPC-2221
  电源完整性推荐实践）。

用法（合成输出即输入）：
    from client.synthesizer import synthesize_from_prompt
    res = synthesize_from_prompt("ESP32 + CAN + RS485")
    issues = run_erc(res["modules"], res["netlist"]["connections"])
    verdict = erc_gate(issues)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2, "blocking": 3}

GND_RE = re.compile(r"(^|/)(GND|AGND|DGND|PGND)$", re.IGNORECASE)
POWER_RE = re.compile(r"(VBUS|VCC|VDD|VIN|VOUT|VBAT|\+?3V3|\+?5V|\+12V|\+?1V8|\+?2V8)", re.IGNORECASE)
DECOUP_RE = re.compile(r"^(100n|0\.1u)", re.IGNORECASE)


@dataclass
class ERCIssue:
    code: str
    title: str
    detail: str
    severity: str  # blocking / error / warning / info
    object_id: str | None = None
    source: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _issue(code: str, title: str, detail: str, severity: str,
           source: str, **kw) -> dict:
    return ERCIssue(code=code, title=title, detail=detail,
                    severity=severity, source=source, **kw).to_dict()


def run_erc(modules: dict[str, dict], connections: list[dict]) -> list[dict]:
    """在合成产物（modules + netlist.connections）上运行全部 ERC 规则。"""
    issues: list[dict] = []
    SRC = "CircuitAgent ERC（规则出处见模块头注）"

    nets = {c.get("net", ""): (c.get("points") or []) for c in connections or []}
    net_names = list(nets.keys())
    all_points = [p for pts in nets.values() for p in pts]

    # 1. MISSING_GND (blocking)
    if not any(GND_RE.search(str(n)) for n in net_names):
        issues.append(_issue(
            "MISSING_GND", "缺少 GND 网络",
            "网表中没有任何接地网络——无参考地的网表不可成立。",
            "blocking", SRC))

    # 2. 悬空网络分级（KiCad ERC 语义）：0 点=error（空网络）；
    #    1 点=warning——预留外部接口（CANH 待接总线、测试点）是合法设计，需人工确认
    for net, pts in nets.items():
        if len(pts) == 0:
            issues.append(_issue(
                "EMPTY_NET", "空网络",
                f"网络 {net} 没有任何连接点。",
                "error", SRC, object_id=f"net:{net}"))
        elif len(pts) == 1:
            issues.append(_issue(
                "FLOATING_NET", "单点网络",
                f"网络 {net} 只有 1 个连接点——若是预留外部接口（总线/测试点）"
                "请豁免确认，否则为断线或引脚拼写错误。",
                "warning", SRC, object_id=f"net:{net}"))

    # 3. UNKNOWN_COMPONENT (error)
    known = set(modules.keys())
    for p in all_points:
        ref = str(p).split(".", 1)[0]
        if known and ref not in known:
            issues.append(_issue(
                "UNKNOWN_COMPONENT", "连接点引用未知位号",
                f"连接点 {p} 引用的位号不在元件清单中。",
                "error", SRC, object_id=f"point:{p}"))

    # 4. MISSING_POWER_NET (warning)
    kinds = {str(v.get("kind", "")).upper() for v in modules.values()}
    has_ic = any(k in ("IC", "MCU", "REGULATOR", "TRANSCEIVER", "CHARGER") for k in kinds)
    has_power = any(POWER_RE.search(str(n)) for n in net_names)
    if modules and has_ic and not has_power:
        issues.append(_issue(
            "MISSING_POWER_NET", "有 IC 但无电源网络",
            "设计包含 IC，但没有任何电源网络（VBUS/VCC/3V3/5V…）——电源块缺失。",
            "warning", SRC))

    # 5. MISSING_DECOUPLING (warning)
    if has_ic:
        decouplers = [ref for ref, v in modules.items()
                      if str(v.get("kind", "")).upper() == "CAPACITOR"
                      and DECOUP_RE.match(str(v.get("value", "")))]
        if not decouplers:
            issues.append(_issue(
                "MISSING_DECOUPLING", "IC 缺少去耦电容",
                "设计包含 IC 但没有 100nF/0.1u 去耦电容——每个 IC 电源引脚"
                "应配 100nF 陶瓷电容（IPC-2221 电源完整性推荐）。",
                "warning", SRC))

    return issues


def counts(issues: list[dict]) -> dict:
    out = {s: 0 for s in SEVERITY_ORDER}
    for i in issues:
        out[i["severity"]] = out.get(i["severity"], 0) + 1
    return out


def erc_allowed(issues: list[dict]) -> bool:
    """无 blocking 且无 error 才允许进入 BOM/CPL 交付。"""
    return all(i["severity"] not in ("blocking", "error") for i in issues)


def erc_gate(issues: list[dict]) -> dict:
    """门禁汇总：allowed + 分级计数 + 最高严重度（与 DRC.gate 同形）。"""
    c = counts(issues)
    worst = "info"
    for i in issues:
        if SEVERITY_ORDER[i["severity"]] > SEVERITY_ORDER[worst]:
            worst = i["severity"]
    return {"allowed": erc_allowed(issues), "counts": c, "worst": worst,
            "total": len(issues)}


if __name__ == "__main__":
    from client.synthesizer import synthesize_from_prompt

    res = synthesize_from_prompt("ESP32 CAN RS485")
    gate = erc_gate(run_erc(res["modules"], res["netlist"]["connections"]))
    print(gate)
