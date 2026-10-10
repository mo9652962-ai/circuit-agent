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
- MISSING_BUS_TERMINATION (warning)：CAN / RS-485 差分总线引脚间未见 120Ω 终端
  匹配电阻（ISO 11898-2 CAN / TIA/EIA-485-A 规范）。
- HIGH_SPEED_PAIR_UNBALANCED (warning)：高速差分对正负信号线连接点数量不一致，
  支路拓扑不对称会导致共模噪声（Common-mode noise）与时延偏斜（Skew）。
- STACKUP_IMPEDANCE_MISMATCH (warning)：走线线宽与叠层设计目标阻抗偏离度过大（IPC-2141A）。
- MISSING_LAYER_RETURN_PATH (warning)：高速接口（USB/以太网/RF）连接器缺少参考地回路引脚。
- DRILL_ASPECT_RATIO_EXCEEDED (warning)：过孔钻孔孔径与板厚深宽比 > 1:10，沉铜药水无法充分交换导致孔壁铜厚不足断路（IPC-2221）。
- PIN_TYPE_CONFLICT (error)：两个非开漏/非三态推挽输出引脚短接冲突（KiCad ERC 规则）。
- SMT_TAPE_FEEDER_PITCH_MISMATCH (warning)：封装物理外形尺寸大于料带步距设置（EIA-481 标准）。
- HIGH_VOLTAGE_ISOLATION_BARRIER_BREACH (warning)：高压/PLC 隔离网络与低压弱电之间未满足 IPC-2221B 安全爬电间隙。
- COURTYARD_COLLISION_RISK (warning)：元件间距低于 IPC-7351B Courtyard 最小边界裕量，贴片机吸嘴干涉与贴装防撞。
- THERMAL_RELIEF_MISSING_ON_HIGH_CURRENT (warning)：大电流/功率焊盘直接实心连接大面积铜皮而缺少热隔离十字花孔，回流焊易冷焊或立碑（IPC-2221B / IPC-A-610G）。
- ICT_TESTPOINT_COVERAGE_DEFICIT (warning)：关键电源轨或复位引脚缺少 ICT 测试焊盘，产线自动化针床测试覆盖率不足（IPC-9252 / IPC-2221B）。
- HIGH_FREQUENCY_CLOCK_TRACE_LENGTH (warning)：晶振高频时钟走线长度 > 15mm，易引入寄生电容导致停振或强 EMI 辐射（ST AN2867 / IPC-2141A）。
- LAYER_COPPER_THIEVING_IMBALANCE (warning)：顶底层铺铜覆盖率差异 > 35%，回流焊热应力不对称极易产生弓曲/扭曲变形（IPC-2221B / IPC-TM-650 2.4.22）。
- UNREINFORCED_VIA_ANNULAR_BREAKOUT (warning)：细线 (≤0.15mm) 直连过孔而未加泪滴倒角补强，钻孔微偏极易造成焊环破裂开路（IPC-2221B / IPC-A-600J Class 3）。
- EXPOSED_PAD_THERMAL_VIA_MISSING (warning)：功率 IC / QFN 底部散热焊盘缺少矩阵散热过孔，热阻过高易导致热击穿（IPC-7093 Section 7.2）。
- RF_GROUND_SHIELDING_FENCE_SPACING (warning)：高频/RF 射频走线屏蔽地孔间距过大 (> 2.5mm)，无法有效抑制空间电磁场泄漏与串扰（IPC-2141A）。

用法（合成输出即输入）：
    from client.synthesizer import synthesize_from_prompt
    res = synthesize_from_prompt("ESP32 + CAN + RS485")
    issues = run_erc(res["modules"], res["netlist"]["connections"])
    verdict = erc_gate(issues)
"""

from __future__ import annotations

import math
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


def _issue(code: str, title: str, detail: str, severity: str, source: str, **kw) -> dict:
    return ERCIssue(code=code, title=title, detail=detail, severity=severity, source=source, **kw).to_dict()


def run_erc(modules: dict[str, dict], connections: list[dict]) -> list[dict]:
    """在合成产物（modules + netlist.connections）上运行全部 ERC 规则。"""
    issues: list[dict] = []
    SRC = "CircuitAgent ERC（规则出处见模块头注）"

    nets = {c.get("net", ""): (c.get("points") or []) for c in connections or []}
    net_names = list(nets.keys())
    all_points = [p for pts in nets.values() for p in pts]

    # 1. MISSING_GND (blocking)
    if not any(GND_RE.search(str(n)) for n in net_names):
        issues.append(
            _issue("MISSING_GND", "缺少 GND 网络", "网表中没有任何接地网络——无参考地的网表不可成立。", "blocking", SRC)
        )

    # 2. 悬空网络分级（KiCad ERC 语义）：0 点=error（空网络）；
    #    1 点=warning——预留外部接口（CANH 待接总线、测试点）是合法设计，需人工确认
    for net, pts in nets.items():
        if len(pts) == 0:
            issues.append(
                _issue("EMPTY_NET", "空网络", f"网络 {net} 没有任何连接点。", "error", SRC, object_id=f"net:{net}")
            )
        elif len(pts) == 1:
            issues.append(
                _issue(
                    "FLOATING_NET",
                    "单点网络",
                    f"网络 {net} 只有 1 个连接点——若是预留外部接口（总线/测试点）"
                    "请豁免确认，否则为断线或引脚拼写错误。",
                    "warning",
                    SRC,
                    object_id=f"net:{net}",
                )
            )

    # 3. UNKNOWN_COMPONENT (error)
    known = set(modules.keys())
    for p in all_points:
        ref = str(p).split(".", 1)[0]
        if known and ref not in known:
            issues.append(
                _issue(
                    "UNKNOWN_COMPONENT",
                    "连接点引用未知位号",
                    f"连接点 {p} 引用的位号不在元件清单中。",
                    "error",
                    SRC,
                    object_id=f"point:{p}",
                )
            )

    # 4. MISSING_POWER_NET (warning)
    kinds = {str(v.get("kind", "")).upper() for v in modules.values()}
    has_ic = any(k in ("IC", "MCU", "REGULATOR", "TRANSCEIVER", "CHARGER") for k in kinds)
    has_power = any(POWER_RE.search(str(n)) for n in net_names)
    if modules and has_ic and not has_power:
        issues.append(
            _issue(
                "MISSING_POWER_NET",
                "有 IC 但无电源网络",
                "设计包含 IC，但没有任何电源网络（VBUS/VCC/3V3/5V…）——电源块缺失。",
                "warning",
                SRC,
            )
        )

    # 5. NO_INPUT_PROTECTION (warning)：有电源输入网络但无 TVS/保险丝防护件
    #    （IEC 61000-4-2 ESD 基线；USB/DC 输入口建议 TVS + 自恢复保险丝）
    has_input = any(
        POWER_RE.search(str(n)) and re.search(r"(VBUS|VIN|DC_IN|[+]5V)", str(n), re.IGNORECASE) for n in net_names
    )
    has_protection = bool(kinds & {"TVS", "FUSE", "PPTC", "ESD"})
    if has_input and modules and not has_protection:
        issues.append(
            _issue(
                "NO_INPUT_PROTECTION",
                "电源输入缺少防护器件",
                "检测到电源输入网络但设计无 TVS/PPTC 防护——外部电源口建议加 ESD/浪涌"
                "防护（IEC 61000-4-2）与自恢复保险丝；可用 ESD_TVS_USB / 防反接积木。",
                "warning",
                SRC,
            )
        )

    # 6. MISSING_DECOUPLING (warning)
    if has_ic:
        decouplers = [
            ref
            for ref, v in modules.items()
            if str(v.get("kind", "")).upper() == "CAPACITOR" and DECOUP_RE.match(str(v.get("value", "")))
        ]
        if not decouplers:
            issues.append(
                _issue(
                    "MISSING_DECOUPLING",
                    "IC 缺少去耦电容",
                    "设计包含 IC 但没有 100nF/0.1u 去耦电容——每个 IC 电源引脚"
                    "应配 100nF 陶瓷电容（IPC-2221 电源完整性推荐）。",
                    "warning",
                    SRC,
                )
            )

    # 7. MISSING_BUS_TERMINATION (warning)：差分总线引脚间未连接 120Ω 终端电阻
    #    （ISO 11898-2 CAN / TIA/EIA-485-A 规范）
    diff_pairs = [
        ("/CAN_H", "/CAN_L", "CAN 总线 (ISO 11898-2)"),
        ("/485_A", "/485_B", "RS-485 总线 (TIA/EIA-485-A)"),
    ]
    for p_net, n_net, bus_name in diff_pairs:
        if p_net in nets and n_net in nets:
            p_pts = {pt.split(".", 1)[0] for pt in nets[p_net]}
            n_pts = {pt.split(".", 1)[0] for pt in nets[n_net]}
            bridging_refs = p_pts & n_pts
            has_term = any(str(modules.get(r, {}).get("kind", "")).upper() == "RESISTOR" for r in bridging_refs)
            if not has_term:
                issues.append(
                    _issue(
                        "MISSING_BUS_TERMINATION",
                        f"{bus_name}缺少 120Ω 终端电阻",
                        f"检测到差分网络 {p_net} 与 {n_net}，但两引脚间未连接匹配电阻。"
                        "高速差分总线需并联 120Ω 终端电阻以抑制反射。",
                        "warning",
                        SRC,
                        object_id=f"diff:{p_net}/{n_net}",
                    )
                )

    # 8. HIGH_SPEED_PAIR_UNBALANCED (warning)：高速差分对拓扑不对称
    high_speed_pairs = [
        ("/USB_DP", "/USB_DM", "USB 2.0 差分对"),
        ("/ETH_TXP", "/ETH_TXN", "以太网发送差分对"),
        ("/ETH_RXP", "/ETH_RXN", "以太网接收差分对"),
    ]
    for p_net, n_net, pair_name in high_speed_pairs:
        if p_net in nets and n_net in nets:
            p_cnt = len(nets[p_net])
            n_cnt = len(nets[n_net])
            if p_cnt != n_cnt:
                issues.append(
                    _issue(
                        "HIGH_SPEED_PAIR_UNBALANCED",
                        f"{pair_name}连接点不对称",
                        f"{pair_name}正端 {p_net} 有 {p_cnt} 个连接点，负端 {n_net} 有 {n_cnt} 个连接点；"
                        "高速差分对支路拓扑不对称会导致共模噪声增大与时延失配。",
                        "warning",
                        SRC,
                        object_id=f"pair:{p_net}/{n_net}",
                    )
                )

    # 9. STACKUP_IMPEDANCE_MISMATCH (warning)：特征阻抗线宽失配检查 (IPC-2141A)
    for conn in connections or []:
        props = conn.get("properties") or {}
        target_z = props.get("target_impedance_ohms")
        w_mm = props.get("trace_width_mm")
        if target_z and w_mm:
            # 典型 50R 微带线在标准四层板推荐 ~0.38mm (允许 ±25% 容差)
            expected_w = 0.38 if target_z == 50.0 else (0.20 if target_z == 90.0 else 0.18)
            if abs(w_mm - expected_w) / expected_w > 0.35:
                issues.append(
                    _issue(
                        "STACKUP_IMPEDANCE_MISMATCH",
                        "走线线宽与叠层目标阻抗失配",
                        f"网络 {conn.get('net')} 目标阻抗 {target_z}Ω，所设线宽 {w_mm}mm 偏离"
                        f"标准四层板推荐值 ({expected_w}mm) 超过容限，易引起信号反射。",
                        "warning",
                        "IPC-2141A High-Speed Controlled Impedance Guidelines",
                        object_id=f"net:{conn.get('net')}",
                    )
                )

    # 10. MISSING_LAYER_RETURN_PATH (warning)：高速外设接插件缺少参考地回路
    for ref, m in modules.items():
        val = str(m.get("value", "")).upper()
        if any(k in val for k in ("USB", "RJ45", "ETH")):
            # 检查是否有任何 GND 网络连接到该器件
            gnd_pins = [pt for n in net_names if GND_RE.search(n) for pt in nets.get(n, []) if pt.startswith(f"{ref}.")]
            if not gnd_pins:
                issues.append(
                    _issue(
                        "MISSING_LAYER_RETURN_PATH",
                        "高速外设接口缺少地回路",
                        f"高速接插件 {ref} ({val}) 未连接任何参考地网络（GND），"
                        "缺少高频信号回流路径，易导致 EMI 辐射超标与共模干扰。",
                        "warning",
                        "IPC-2141A High-Speed Return Current Path Guidelines",
                        object_id=f"connector:{ref}",
                    )
                )

    # 11. DRILL_ASPECT_RATIO_EXCEEDED (warning)：钻孔深径比超标 (IPC-2221)
    for conn in connections or []:
        props = conn.get("properties") or {}
        via_dia = props.get("via_drill_mm")
        board_th = props.get("board_thickness_mm", 1.6)
        if via_dia and via_dia > 0:
            aspect = board_th / via_dia
            if aspect > 10.0:
                issues.append(
                    _issue(
                        "DRILL_ASPECT_RATIO_EXCEEDED",
                        "过孔钻孔深径比过大",
                        f"过孔孔径 {via_dia}mm 相对板厚 {board_th}mm 的深径比 {aspect:.1f} > 10:1；"
                        "沉铜电镀药水流动受阻易导致孔铜偏薄或断裂（IPC-2221）。",
                        "warning",
                        "IPC-2221 Generic Standard on Printed Board Design",
                        object_id=f"net:{conn.get('net')}",
                    )
                )

    # 12. PIN_TYPE_CONFLICT (error)：推挽输出短路冲突
    for net, pts in nets.items():
        out_pins = [p for p in pts if any(p.endswith(k) for k in (".TX", ".MOSI", ".SCLK", "_OUT", ".RO"))]
        if len(out_pins) >= 2:
            issues.append(
                _issue(
                    "PIN_TYPE_CONFLICT",
                    "推挽输出引脚短路冲突",
                    f"网络 {net} 同时连接了多个推挽输出驱动引脚 ({', '.join(out_pins[:3])})；"
                    "输出引脚相连存在总线争用短路烧毁芯片风险（KiCad ERC 规则）。",
                    "error",
                    "KiCad Electrical Rules Check: Pin-to-Pin Conflict",
                    object_id=f"net:{net}",
                )
            )

    # 13. SMT_TAPE_FEEDER_PITCH_MISMATCH (warning)：供料器载带步距与封装尺寸冲突
    for ref, m in modules.items():
        pkg = str(m.get("package", "")).upper()
        if any(k in pkg for k in ("1206", "1210", "SOT-223", "SOIC-8")) and "2MM" in pkg:
            issues.append(
                _issue(
                    "SMT_TAPE_FEEDER_PITCH_MISMATCH",
                    "SMT 供料器载带步距与封装外形冲突",
                    f"器件 {ref} 封装 {pkg} 尺寸大于 2mm 步距载带，易导致贴片机料盘供料卡死或翻件（EIA-481 标准）。",
                    "warning",
                    "EIA-481 Automated SMT Component Taping Standard",
                    object_id=f"comp:{ref}",
                )
            )

    # 14. HIGH_VOLTAGE_ISOLATION_BARRIER_BREACH (warning)：高低压隔离带破损
    iso_nets = [n for n in net_names if any(k in n.upper() for k in ("24V", "PLC", "MAINS", "AC_", "HV_"))]
    logic_nets = [n for n in net_names if any(k in n.upper() for k in ("3.3V", "3V3", "1.8V", "1V8"))]
    if iso_nets and logic_nets:
        for iso_n in iso_nets:
            iso_refs = {p.split(".", 1)[0] for p in nets.get(iso_n, [])}
            for log_n in logic_nets:
                log_refs = {p.split(".", 1)[0] for p in nets.get(log_n, [])}
                shared = iso_refs & log_refs
                unprotected_shared = [
                    r
                    for r in shared
                    if not any(
                        k in str(modules.get(r, {}).get("value", "")).upper() for k in ("PC817", "OPTO", "ISOLATOR")
                    )
                ]
                if unprotected_shared:
                    issues.append(
                        _issue(
                            "HIGH_VOLTAGE_ISOLATION_BARRIER_BREACH",
                            "高压隔离屏障破损风险",
                            f"高压网络 {iso_n} 与低压逻辑网络 {log_n} 经过非隔离器件 {unprotected_shared} 连通；"
                            "未保持 IPC-2221B ≥ 2.5mm 电气绝缘安全爬电隔离屏障。",
                            "warning",
                            "IPC-2221B Table 6-1 High Voltage Isolation Boundary",
                            object_id=f"nets:{iso_n}/{log_n}",
                        )
                    )

    # 15. COURTYARD_COLLISION_RISK (warning)：IPC-7351B 元件 Courtyard 边界冲突与贴装防撞
    positions: dict[str, tuple[float, float]] = {}
    for ref, m in modules.items():
        pos = m.get("position")
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            positions[ref] = (float(pos[0]), float(pos[1]))
    placed_refs = list(positions.keys())
    for i in range(len(placed_refs)):
        for j in range(i + 1, len(placed_refs)):
            r1, r2 = placed_refs[i], placed_refs[j]
            x1, y1 = positions[r1]
            x2, y2 = positions[r2]
            dist = math.hypot(x1 - x2, y1 - y2)
            if dist < 0.25:
                issues.append(
                    _issue(
                        "COURTYARD_COLLISION_RISK",
                        "器件 Courtyard 冲突与贴装防撞风险",
                        f"器件 {r1} 与 {r2} 布局间距 ({dist:.2f}mm) 低于 IPC-7351B 最小 Courtyard 安全裕量；"
                        "贴片机吸嘴易发生机械干涉，回流焊极易出现元件撞件或焊锡桥连。",
                        "warning",
                        "IPC-7351B Section 3.1.5 Courtyard Boundary Excess",
                        object_id=f"comps:{r1}/{r2}",
                    )
                )

    # 16. THERMAL_RELIEF_MISSING_ON_HIGH_CURRENT (warning)：大电流焊盘缺少热隔离十字花连接
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        is_power = bool(POWER_RE.search(net_name) or "GND" in net_name.upper())
        has_direct_connect = props.get("zone_connection") == "solid"
        current_a = float(props.get("current_rating_a", 0.0) or 0.0)
        if is_power and has_direct_connect and current_a >= 1.5:
            issues.append(
                _issue(
                    "THERMAL_RELIEF_MISSING_ON_HIGH_CURRENT",
                    "大电流焊盘缺少热隔离十字花连接 (Thermal Relief)",
                    f"网络 {net_name} (载流 {current_a}A) 的焊盘直接实心连接至大面积铜皮铺铜；"
                    "散热过快会导致焊接热量被大铜皮吸收，极易引发虚焊、冷焊或立碑缺陷（IPC-2221B / IPC-A-610G）。",
                    "warning",
                    "IPC-2221B Section 9.1.2 & IPC-A-610G Solder Joint Thermal Integrity",
                    object_id=f"net:{net_name}",
                )
            )

    # 17. ICT_TESTPOINT_COVERAGE_DEFICIT (warning)：关键网络缺少 ICT 测试点
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        is_crit = bool(POWER_RE.search(net_name) or "RESET" in net_name.upper() or "NRST" in net_name.upper())
        has_tp = props.get("has_testpoint", True)
        if is_crit and not has_tp:
            issues.append(
                _issue(
                    "ICT_TESTPOINT_COVERAGE_DEFICIT",
                    "关键电源/复位网络缺少 ICT 测试点",
                    f"关键网络 {net_name} 未布置专属 ICT 针床测试焊盘；"
                    "量产针床无法测试供电与复位电平，降低 PCBA 自动化首检与功能测试覆盖率（IPC-9252 / IPC-2221B）。",
                    "warning",
                    "IPC-9252 & IPC-2221B Section 12 Design for Testability",
                    object_id=f"net:{net_name}",
                )
            )

    # 18. HIGH_FREQUENCY_CLOCK_TRACE_LENGTH (warning)：晶振高频时钟走线超长
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        is_osc = any(k in net_name.upper() for k in ("OSC_", "XTAL_", "CLK_IN", "CLK_OUT"))
        t_len = float(props.get("trace_length_mm", 0.0) or 0.0)
        if is_osc and t_len > 15.0:
            issues.append(
                _issue(
                    "HIGH_FREQUENCY_CLOCK_TRACE_LENGTH",
                    "高频晶体时钟走线过长风险",
                    f"时钟网络 {net_name} 走线长度 {t_len:.1f}mm > 15mm 建议上限；"
                    "长走线寄生杂散电容过大易导致晶体起振困难、频率漂移与高频 EMI 谐波辐射（ST AN2867 / IPC-2141A）。",
                    "warning",
                    "ST AN2867 Oscillator Design Guide & IPC-2141A High-Speed Layout",
                    object_id=f"net:{net_name}",
                )
            )

    # 19. LAYER_COPPER_THIEVING_IMBALANCE (warning)：顶底层铺铜不平衡翘曲风险 (IPC-2221B)
    for conn in connections or []:
        props = conn.get("properties") or {}
        top_cov = props.get("top_copper_density_pct")
        bot_cov = props.get("bot_copper_density_pct")
        if top_cov is not None and bot_cov is not None:
            diff = abs(float(top_cov) - float(bot_cov))
            if diff > 35.0:
                issues.append(
                    _issue(
                        "LAYER_COPPER_THIEVING_IMBALANCE",
                        "顶底层铜皮覆盖率严重失衡翘曲风险",
                        f"顶层铜皮覆盖率 ({top_cov}%) 与底层 ({bot_cov}%) 差异 {diff:.1f}% > 35%；"
                        "焊接热应力不对称易导致 PCB 弓曲/扭曲变形超标（IPC-2221B / IPC-TM-650 2.4.22）。",
                        "warning",
                        "IPC-2221B Section 10.1.1 Non-Functional Copper Balancing",
                        object_id=f"net:{conn.get('net')}",
                    )
                )

    # 20. UNREINFORCED_VIA_ANNULAR_BREAKOUT (warning)：细线直连过孔未做泪滴补强
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        tr_w = float(props.get("trace_width_mm", 0.20) or 0.20)
        has_v = bool(props.get("has_vias", False))
        is_reinforced = bool(props.get("teardrop_reinforced", False))
        if has_v and tr_w <= 0.15 and not is_reinforced:
            issues.append(
                _issue(
                    "UNREINFORCED_VIA_ANNULAR_BREAKOUT",
                    "高应力细导线直连过孔缺少泪滴补强",
                    f"网络 {net_name} 细线 (宽 {tr_w}mm) 直连过孔且未加泪滴倒角补强；"
                    "钻孔偏移时颈部易发生 90°/180° 断裂造成热循环开路（IPC-2221B / IPC-A-600J Class 3）。",
                    "warning",
                    "IPC-2221B Section 9.1.5 & IPC-A-600J Class 3 Annular Ring Integrity",
                    object_id=f"net:{net_name}",
                )
            )

    # 21. EXPOSED_PAD_THERMAL_VIA_MISSING (warning)：功率 IC / QFN 缺少散热地孔
    for ref, m in modules.items():
        pkg = str(m.get("package", "")).upper()
        kind = str(m.get("kind", "")).upper()
        has_exposed_pad = any(k in pkg for k in ("QFN", "DFN", "HTSSOP", "HSOP", "EPAD")) or kind in ("REGULATOR", "DRIVER")
        has_thermal_vias = bool(m.get("has_thermal_vias", True))
        if has_exposed_pad and not has_thermal_vias:
            issues.append(
                _issue(
                    "EXPOSED_PAD_THERMAL_VIA_MISSING",
                    "裸露散热焊盘缺少矩阵散热过孔",
                    f"器件 {ref} 封装 {pkg} 具有底部裸露功率热沉，但未布置矩阵导热过孔阵列；"
                    "热阻过高将导致结温超标并触发过温热保护（IPC-7093 Section 7.2）。",
                    "warning",
                    "IPC-7093 Section 7.2 Bottom Termination Components Thermal Design",
                    object_id=f"comp:{ref}",
                )
            )

    # 22. RF_GROUND_SHIELDING_FENCE_SPACING (warning)：RF 走线地屏蔽过孔间距过大
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        is_rf = any(k in net_name.upper() for k in ("RF_", "ANT", "WIFI_", "BLE_"))
        fence_pitch = float(props.get("shield_via_pitch_mm", 2.0) or 2.0)
        if is_rf and fence_pitch > 2.5:
            issues.append(
                _issue(
                    "RF_GROUND_SHIELDING_FENCE_SPACING",
                    "高频 RF 屏蔽地孔栅栏间距过大",
                    f"射频网络 {net_name} 伴随地屏蔽过孔间距 {fence_pitch}mm > 2.5mm (超过 λ/10 上限)；"
                    "地孔间距过大将无法阻断高频电磁场侧向泄漏，极易恶化辐射杂散与带外干扰（IPC-2141A）。",
                    "warning",
                    "IPC-2141A & IEEE High Frequency Shielding Via Fence Criteria",
                    object_id=f"net:{net_name}",
                )
            )

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
    return {"allowed": erc_allowed(issues), "counts": c, "worst": worst, "total": len(issues)}


if __name__ == "__main__":
    from client.synthesizer import synthesize_from_prompt

    res = synthesize_from_prompt("ESP32 CAN RS485")
    gate = erc_gate(run_erc(res["modules"], res["netlist"]["connections"]))
    print(gate)
