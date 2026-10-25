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
- MLCC_EFFECTIVE_CAPACITANCE_DEFICIT (warning)：电容在真实工作偏置下的有效容值
  跌破标称 60%——标签值不是电路里的值。直流偏置、温度系数、对数老化与容差连乘，
  10µF 的 X5R 在 5V 下常只剩 3~6µF。规则只在器件带有 rated_v/applied_v 时才复算，
  没有偏置数据就保持沉默（编造偏置比沉默更糟）。
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
- STENCIL_APERTURE_RATIO_DEFICIENT (warning)：钢网开孔面积比 < 0.66，锡膏释放不足导致立碑/虚焊/BGA 枕头效应（IPC-7525）。
- FIDUCIAL_LAYOUT_AMBIGUOUS (warning)：全局光学定位点少于 3 处或布局对称，贴片机视觉对位存在 180° 歧义风险（IPC-2221B / J-STD-020）。
- VIA_IN_PAD_SOLDER_WICKING_RISK (warning)：BGA 焊盘内过孔未做 Type VII 填孔+电镀盖帽 (VIPPO)，回流焊锡膏毛细渗流导致焊料饥饿（IPC-4761）。
- POLARIZED_MARKING_MISSING (warning)：极性器件 (LED/二极管/电解电容) 未标记丝印极性标识，人工检验与返修时易反向贴装（IPC-A-610G）。
- BGA_ESCAPE_ROUTING_UNPLANNED (warning)：BGA 封装器件未提供逃逸扇出规划，量产布线将无通道可用（IPC-7095 Section 5.2）。
- NPTH_PLATING_CONFLICT (warning)：非金属化孔 (NPTH) 标记为电镀，钻孔文件与成品孔径歧义将导致定位孔超差（IPC-2221B / IPC-NC-349）。
- FINE_PITCH_MASK_DAM_UNDEFINED (warning)：≤0.5mm 细间距封装未定义阻焊坝 (Mask Dam)，相邻焊盘间阻焊桥无法制作将连锡短路（IPC-2221B / IPC-SM-782）。
- MOUNTING_HOLES_MISSING (warning)：多器件板卡无任何机械安装孔，整机装配无固定锚点将依赖连接器悬臂受力（IPC-2221B Section 8.2）。
- THT_WAVE_SOLDERING_UNSUITABLE (warning)：通孔器件标记为不宜波峰焊（热敏感/大体积），需转选择焊或手工焊工序（IPC-A-610G Section 7）。
- MOUNTING_HOLE_KEEPOUT_MISSING (warning)：机械安装孔未定义隔离环/电气禁布区，紧固件与孔壁铜箔短路（IPC-2221B Section 8.2）。
- PANEL_PROCESS_FEATURES_MISSING (warning)：拼版板未定义工艺边/光学定位点/定位孔，SMT 传送与视觉对位无法执行（IPC-SMEMA-9851 / IPC-2221B Section 8.4）。
- TALL_COMPONENT_SMT_COLLISION_RISK (warning)：高低元件高差 ≥3.0mm 且水平间距 <2.0mm，贴片机吸嘴下压存在机械碰撞撞件风险（IPC-SM-782 / OpenPnP）。
- CREEPAGE_DISTANCE_VIOLATION_WITHOUT_SLOT (warning)：高压网络导体间距不足安规爬电要求且未开空气隔离铣槽（IPC-2221B Table 6-1 / IEC 62368-1）。
- IMPEDANCE_TOLERANCE_WINDOW_EXCEEDED (warning)：特征阻抗在板厂压合/蚀刻公差叠加下极差超出 ±10% 目标容限窗口（IPC-2141A）。
- POLLUTION_DEGREE_CREEPAGE_DEFICIT (warning)：在工业污染等级 2/3 环境下基板材料 CTI 偏低导致爬电安全裕度不足（IEC 62368-1 / GB 4943.1）。
- BOTTOM_SMD_WAVE_ORIENTATION_MISALIGNED (warning)：底面 SMD 阻容平行于波峰流向或 SOIC 垂直于流向，极易发生立碑与桥连（IPC-7351B / SMTA）。
- PRESS_FIT_PTH_TOLERANCE_VIOLATION (warning)：无焊压接鱼眼针过孔成品孔径偏离 0.94~1.09mm 或孔铜 < 25μm，机械开裂或微动磨损断路（IPC-9797 / IEC 60352-5）。
- FAB_CAPABILITY_LIMIT_EXCEEDED (warning)：走线线宽、线距或过孔钻孔低于板厂基础制程能力下限，工程 CAM 预审驳回（IPC-6012）。
- SILKSCREEN_OVER_EXPOSED_COPPER (warning)：丝印层文字/图形覆盖到裸露焊盘铜皮上，阻焊与润湿不良引发焊接虚焊缺陷（IPC-A-600J / IPC-7351B）。

用法（合成输出即输入）：
    from client.synthesizer import synthesize_from_prompt
    res = synthesize_from_prompt("ESP32 + CAN + RS485")
    issues = run_erc(res["modules"], res["netlist"]["connections"])
    verdict = erc_gate(issues)
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass

logger = logging.getLogger("circuit_agent_erc")

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2, "blocking": 3}

GND_RE = re.compile(r"(^|/)(GND|AGND|DGND|PGND)$", re.IGNORECASE)
POWER_RE = re.compile(
    # Rails appear in the wild as `+3.3V`, `3V3`, `+3V3`, `+5V`, `5V0`, `VCC_3V3`
    # and `VDDA`. The pattern must cover the decimal form: a netlist that names
    # its rail `/+3.3V` — which is what every KiCad design does — previously
    # matched nothing, so `POWER_RAIL_WITHOUT_SOURCE` never fired on it and
    # `MISSING_POWER_NET` reported "no power nets" on a board full of them.
    r"(VBUS|VCC|VDD|VDDA|VIN|VOUT|VBAT|"
    r"\+?\d+(\.\d+)?V\d*|"  # +3.3V, 3V3, +5V, 5V0, 12V
    r"\+?\d+V\d+)"  # 1V8, 2V8
    ,
    re.IGNORECASE,
)
DECOUP_RE = re.compile(r"^(100n|0\.1u)", re.IGNORECASE)

#: Suffix → multiplier for a capacitance string. Order matters: the bare-letter
#: shorthands that BOMs actually use (``100n``, ``0.1u``) come first, then the
#: explicit two-letter forms, then a lone ``F``. A single ``n`` means nanofarads
#: by universal BOM convention, and refusing to read it would skip the very
#: parts most likely to be derated (decoupling caps).
_CAP_UNITS: tuple[tuple[str, float], ...] = (
    ("µF", 1.0),
    ("uF", 1.0),
    ("μF", 1.0),  # U+03BC GREEK SMALL LETTER MU, which some datasheets use
    ("µ", 1.0),
    ("u", 1.0),
    ("μ", 1.0),
    ("nF", 1e-3),
    ("n", 1e-3),
    ("pF", 1e-6),
    ("p", 1e-6),
    ("F", 1e3),
)


def _rail_voltages(connections: list[dict]) -> dict[str, float]:
    """Infer a voltage for each rail from its name and any declared properties.

    A netlist does not carry voltages, but rail *names* do: ``/+3.3V``, ``/5V0``,
    ``/VMOT_24V``, ``/VBUS``. This parses the name and lets an explicit
    ``properties.voltage_v`` override it, which is what hand-authored netlists
    supply. A rail with no parseable voltage is simply absent from the result —
    callers must treat "unknown" as "cannot check", never as "safe".
    """
    rails: dict[str, float] = {}
    for conn in connections or []:
        net = str(conn.get("net", ""))
        props = conn.get("properties") or {}
        explicit = props.get("voltage_v")
        if explicit is not None:
            try:
                rails[net] = float(explicit)
                continue
            except (TypeError, ValueError):
                pass
        # VBUS is 5 V on USB and 5 V on Type-C; treat it as such rather than
        # leaving the most common rail uncheckable.
        if re.search(r"VBUS|VCC_?5|5V0|(^|[/+])5V$", net, re.IGNORECASE):
            rails[net] = 5.0
            continue
        m = re.search(r"(\d+(?:\.\d+)?)\s*V", net, re.IGNORECASE)
        if m:
            try:
                rails[net] = float(m.group(1))
            except ValueError:
                continue
    return rails


def _parse_capacitance_uf(raw: str) -> float | None:
    """Parse a capacitor value string into µF, or ``None`` if it is not a capacitance.

    Handles the notations that actually appear in BOMs and block definitions:
    ``100n``, ``0.1u``, ``10uF``, ``4.7µF``, ``22pF``, ``100nF``. Returns
    ``None`` rather than raising, because ERC runs over arbitrary user netlists
    and one unparseable value must not abort the whole check.
    """
    if not raw:
        return None
    text = raw.strip().replace(" ", "")
    match = re.match(r"^([0-9]*\.?[0-9]+)\s*(.*)$", text)
    if not match:
        return None
    try:
        magnitude = float(match.group(1))
    except ValueError:
        return None
    suffix = match.group(2)
    if suffix == "":
        # A bare number carries no unit. Treating it as µF is the convention in
        # every BOM this project emits, but it is a guess — and a wrong guess
        # here would fabricate a derating warning, so return None instead.
        return None
    for token, multiplier in _CAP_UNITS:
        if suffix.upper() == token.upper():
            return magnitude * multiplier
    return None


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
    # Active parts that draw switching current and therefore need their own
    # local decoupling. Regulators are excluded: they *supply* the transient,
    # and their bulk capacitors are counted by the power-chain rules.
    active_ic_refs = {
        ref
        for ref, v in modules.items()
        if str(v.get("kind", "")).upper() in {"IC", "MCU", "TRANSCEIVER", "SENSOR", "CHARGER"}
    }
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

    # 5b. POWER_RAIL_WITHOUT_SOURCE (error)：电源轨上有负载却没有任何源器件
    #
    # MISSING_POWER_NET above asks "is there a net named like a supply?" — which
    # is satisfied by a rail that nothing drives. That gap is not theoretical: a
    # prompt mentioning CAN and RS485 but not "供电" synthesised a board where
    # `/+3.3V` carried both transceivers and no regulator, no LDO, no connector
    # fed it. Every IC was unpowered and the gate passed the design, because a
    # net with the right name existed.
    #
    # So this rule asks the question that matters: does each powered rail have a
    # component whose job is to produce it? Sources are regulators, LDOs,
    # chargers, power modules, connectors (an external supply arrives through
    # one) and batteries.
    source_kinds = {"REGULATOR", "LDO", "CHARGER", "POWER", "CONNECTOR", "MODULE", "BATTERY", "DC_DC"}
    source_refs = {ref for ref, m in modules.items() if str(m.get("kind", "")).upper() in source_kinds}
    # A passive filter element also feeds the rail downstream of it: a ferrite
    # bead or series inductor between two supply nets is a conducting path, not
    # a load. Treating it as a load made `/VCC_CLEAN` — the output of the π
    # filter — look unsourced, which is a false positive on a correctly built
    # power chain.
    pass_through_refs = {
        ref
        for ref, m in modules.items()
        if str(m.get("kind", "")).upper()
        in {"INDUCTOR", "FERRITE", "FERRITE_BEAD", "RESISTOR", "DIODE", "MOSFET", "FUSE"}
    }
    feeding_refs = source_refs | pass_through_refs
    gnd_nets = {str(n) for n in net_names if GND_RE.search(str(n))}

    for conn in connections or []:
        net_name = str(conn.get("net", ""))
        if net_name in gnd_nets or not POWER_RE.search(net_name):
            continue
        points = [str(p) for p in (conn.get("points") or [])]
        if len(points) < 2:
            # A single-endpoint rail is FLOATING_NET's business, not this rule's.
            continue
        if any(p.split(".")[0] in feeding_refs for p in points):
            continue
        loads = sorted({p.split(".")[0] for p in points})
        issues.append(
            _issue(
                "POWER_RAIL_WITHOUT_SOURCE",
                "电源轨无供电源器件",
                f"电源网络 {net_name} 挂了 {len(points)} 个端点（{', '.join(loads[:6])}"
                f"{'…' if len(loads) > 6 else ''}）但没有任何稳压器/LDO/连接器为它供电——"
                "这些器件实际处于未供电状态，上电即不工作。需补电源块（LDO 或 USB 供电）。",
                "error",
                "IEEE 315 Graphic Symbols / 器件数据手册供电前提",
                object_id=f"net:{net_name}",
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
        elif len(decouplers) < len(active_ic_refs):
            # One 100nF somewhere does not decouple three ICs. The rule above
            # only asked "does any decoupling capacitor exist?", which a single
            # part satisfies for the whole board — three transceivers sharing one
            # capacitor passed the gate. Decoupling is per power pin because its
            # job is to supply the transient current the trace inductance cannot.
            issues.append(
                _issue(
                    "DECOUPLING_PER_IC_DEFICIT",
                    "去耦电容数量少于 IC 数量",
                    f"{len(active_ic_refs)} 个有源器件（{', '.join(sorted(active_ic_refs)[:6])}）"
                    f"但只有 {len(decouplers)} 颗 100nF 去耦电容。每个 IC 的电源引脚需要独立的"
                    "就近去耦——共用一颗意味着远端器件的瞬态电流要穿过走线电感，"
                    "在高速开关时表现为电源跌落与误触发（IPC-2221 / Murata 去耦指南）。",
                    "warning",
                    "IPC-2221 §6.3 Power Distribution / Murata MLCC Decoupling Guide",
                    object_id="decoupling:count",
                )
            )

    # 6a. COMPONENT_RATING_INSUFFICIENT (error)：器件额定值低于它所在电源轨电压
    #
    # A 6.3 V capacitor on a 12 V rail is not a margin question — it is a part
    # that fails. The netlist carries rail names, and rail names carry voltage,
    # so this is checkable without a datasheet: parse the rail, compare against
    # the part's declared rating. Parts that declare no rating are skipped
    # rather than assumed, because inventing a rating is worse than silence.
    rail_voltages = _rail_voltages(connections or [])
    for ref, v in modules.items():
        kind = str(v.get("kind", "")).upper()
        if kind not in {"CAPACITOR", "DIODE", "TVS", "ZENER", "MOSFET"}:
            continue
        rated = v.get("rated_v", v.get("voltage_rating_v"))
        pins = v.get("pins") or {}
        if rated is None or not isinstance(pins, dict):
            continue
        try:
            rated_v = float(rated)
        except (TypeError, ValueError):
            continue
        for pin_net in pins.values():
            rail_v = rail_voltages.get(str(pin_net))
            if rail_v is None or rated_v >= rail_v:
                continue
            issues.append(
                _issue(
                    "COMPONENT_RATING_INSUFFICIENT",
                    "器件额定电压低于所在电源轨",
                    f"{ref}（{v.get('value', '')}）额定 {rated_v} V，却接在 {pin_net} 上，"
                    f"该轨为 {rail_v} V——器件工作在额定值以上，击穿、漏电流上升与寿命衰减"
                    "都会发生。换用额定电压 ≥ 轨压 1.5~2 倍的器件（陶瓷电容常用 2 倍降额）。",
                    "error",
                    "IPC-9592B §3.4 Derating / 器件数据手册绝对最大额定值",
                    object_id=f"ref:{ref}",
                )
            )
            break

    # 6b. MLCC_EFFECTIVE_CAPACITANCE_DEFICIT (warning)：去耦/储能电容在真实工作
    #     偏置下有效容值不足。标签值不是电路里的值：直流偏置、温度系数、老化与
    #     容差连乘后，10µF 的 X5R 在 5V 下常只剩 4~6µF。这里用 client.mlcc_model
    #     复算每颗电容的实际容值，跌破标称 60% 即告警——因为去耦失效与储能不足
    #     不会在标称计算里暴露，只在现场暴露。
    try:
        from .mlcc_model import effective_capacitance

        for ref, v in modules.items():
            if str(v.get("kind", "")).upper() != "CAPACITOR":
                continue
            raw_value = str(v.get("value", "")).strip()
            cap_uf = _parse_capacitance_uf(raw_value)
            if cap_uf is None or cap_uf <= 0:
                continue
            rated_v = float(v.get("rated_v", 0.0) or 0.0)
            applied_v = float(v.get("applied_v", 0.0) or 0.0)
            if rated_v <= 0 or applied_v <= 0:
                # No bias data on the part: nothing to recompute honestly. Skipping
                # is correct here — inventing a bias would be worse than silence.
                continue
            eff = effective_capacitance(
                marked_capacitance_uf=cap_uf,
                rated_v=rated_v,
                applied_v=applied_v,
                case_size=str(v.get("case_size", "0805")),
                dielectric=str(v.get("dielectric", "X5R")),
                ambient_c=float(v.get("ambient_c", 25.0) or 25.0),
            )
            if eff.retention_fraction < 0.60:
                issues.append(
                    _issue(
                        "MLCC_EFFECTIVE_CAPACITANCE_DEFICIT",
                        "贴片陶瓷电容有效容值不足",
                        f"器件 {ref} 标称 {cap_uf}µF ({eff.case_size} {eff.dielectric}, "
                        f"额定 {rated_v}V) 在 {applied_v}V 直流偏置下实际仅 "
                        f"{eff.effective_capacitance_uf:.2f}µF（保留 {eff.retention_fraction:.0%}）。"
                        f"去耦/储能按标签值设计会在现场失效：偏置 {eff.dc_bias_factor:.2f} × "
                        f"温度 {eff.temperature_factor:.2f} × 老化 {eff.ageing_factor:.2f} × "
                        f"容差 {eff.tolerance_factor:.2f}。建议换大封装或提高额定电压。",
                        "warning",
                        "Passive Components Europe DC-bias survey; EIA-198; Kyocera-AVX ageing note",
                        object_id=f"comp:{ref}",
                    )
                )
    except Exception as e:
        logger.debug("MLCC effective-capacitance check skipped: %s", e)

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
    # 8b. DIFF_PAIR_PROTECTION_ONLY (error)：差分对没有形成「连接器 → 主控」通路
    #
    # A TVS array is a shunt: it appears on D+ and D- but does not *carry* the pair
    # anywhere. When the connector and the controller were never wired to those
    # nets, the protection part is the only thing on them — each net still has 2
    # points, so the imbalance rule below is satisfied while nothing is connected.
    # The USBLC6 on the ESP32-C3 board sat on two nets of its own: the receptacle
    # had no data pins and the ESD part protected two stubs.
    #
    # A differential pair needs two distinct non-passive devices on it — a driver
    # and a receiver. One device (connector alone, or protector alone) is not a link.
    for p_net, n_net, pair_name in high_speed_pairs:
        if p_net not in nets or n_net not in nets:
            continue

        def _signal_parts(net: str) -> set[str]:
            parts = {pt.split(".", 1)[0] for pt in nets[net]}
            return {
                r
                for r in parts
                if str(modules.get(r, {}).get("kind", "")).upper()
                not in ("TVS", "ESD", "FERRITE", "RESISTOR", "CAPACITOR")
            }

        signal_parts = _signal_parts(p_net) | _signal_parts(n_net)
        if len(signal_parts) < 2:
            issues.append(
                _issue(
                    "DIFF_PAIR_PROTECTION_ONLY",
                    f"{pair_name}未形成收发通路",
                    f"{p_net} 与 {n_net} 上只有 {sorted(signal_parts) or '无'} 一个信号器件，"
                    "差分对缺少发送端或接收端：连接器的数据引脚与主控的差分引脚至少有一侧没接上。"
                    "保护器件是并联旁路，不能承担信号通路。",
                    "error",
                    SRC,
                    object_id=f"pair:{p_net}/{n_net}",
                )
            )

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

    # 23. STENCIL_APERTURE_RATIO_DEFICIENT (warning)：钢网开孔面积比不足 (IPC-7525)
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        st_ar = props.get("stencil_area_ratio")
        if st_ar is not None and float(st_ar) < 0.66:
            issues.append(
                _issue(
                    "STENCIL_APERTURE_RATIO_DEFICIENT",
                    "钢网开孔面积比不足锡膏释放缺陷",
                    f"网络 {net_name} 钢网开孔面积比 {float(st_ar):.2f} < 0.66 (IPC-7525 激光切割钢网下限)；"
                    "锡膏释放不足将引发立碑、开路虚焊与 BGA 枕头效应 (HiP) 缺陷。",
                    "warning",
                    "IPC-7525 Stencil Design Guidelines Area Ratio Criteria",
                    object_id=f"net:{net_name}",
                )
            )

    # 24. FIDUCIAL_LAYOUT_AMBIGUOUS (warning)：全局光学定位点不足或对称歧义 (IPC-2221B / J-STD-020)
    global_fid = int(modules.get("__meta__", {}).get("global_fiducial_count", 3) if isinstance(modules, dict) else 3)
    if modules and global_fid < 3:
        issues.append(
            _issue(
                "FIDUCIAL_LAYOUT_AMBIGUOUS",
                "全局光学定位点不足视觉对位歧义",
                f"PCB 全局光学定位点数量 ({global_fid}) < 3 处，且未采用非对称 L 形布局；"
                "贴片机视觉对位存在 180° 旋转歧义，极易发生整板贴装镜像报废（IPC-2221B / J-STD-020）。",
                "warning",
                "IPC-2221B Section 12 & JEDEC J-STD-020 Optical Alignment Fiducial Criteria",
            )
        )

    # 25. VIA_IN_PAD_SOLDER_WICKING_RISK (warning)：盘中孔未做 IPC-4761 Type VII 填孔盖帽
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        vip = bool(props.get("has_vias_in_pad", False))
        vippo_ok = bool(props.get("vippo_filled_capped", False))
        if vip and not vippo_ok:
            issues.append(
                _issue(
                    "VIA_IN_PAD_SOLDER_WICKING_RISK",
                    "盘中孔缺少填孔电镀盖帽渗锡风险",
                    f"网络 {net_name} 存在焊盘内过孔 (VIPPO) 且未做 IPC-4761 Type VII 填孔+电镀盖帽；"
                    "回流焊时锡膏沿孔壁毛细渗流导致焊料饥饿、枕头效应 (HiP) 与开路缺陷。",
                    "warning",
                    "IPC-4761 Type VII Filled and Capped Via-in-Pad Requirement",
                    object_id=f"net:{net_name}",
                )
            )

    # 26. POLARIZED_MARKING_MISSING (warning)：极性器件缺少丝印极性标识 (IPC-A-610G)
    for ref, m in modules.items():
        if ref == "__meta__":
            continue
        kind = str(m.get("kind", "")).upper()
        is_polar = kind in ("LED", "DIODE", "TVS") or bool(m.get("polarized", False))
        silk_marked = bool(m.get("silk_marked", True))
        if is_polar and not silk_marked:
            issues.append(
                _issue(
                    "POLARIZED_MARKING_MISSING",
                    "极性器件缺少丝印极性标识",
                    f"极性器件 {ref} ({kind}) 未在丝印层标注极性/第一脚标识；"
                    "人工目检、返修与售后维修时极易反向贴装，反向通电将直接损坏器件（IPC-A-610G 极性标识要求）。",
                    "warning",
                    "IPC-A-610G Section 5.2 Component Orientation & Polarity Marking",
                    object_id=f"comp:{ref}",
                )
            )

    # 27. BGA_ESCAPE_ROUTING_UNPLANNED (warning)：BGA 器件逃逸扇出未规划 (IPC-7095)
    for ref, m in modules.items():
        if ref == "__meta__":
            continue
        pkg = str(m.get("package", "")).upper()
        is_bga = "BGA" in pkg
        escape_planned = bool(m.get("escape_planned", True))
        if is_bga and not escape_planned:
            issues.append(
                _issue(
                    "BGA_ESCAPE_ROUTING_UNPLANNED",
                    "BGA 器件逃逸扇出布线未规划",
                    f"器件 {ref} 封装 {pkg} 未提供逃逸扇出规划 (dogbone/通道布线/层数需求)；"
                    "量产布线阶段将无通道可用，焊球环层深挖需要额外内层，成本与交期不可控（IPC-7095 Section 5.2）。",
                    "warning",
                    "IPC-7095 Section 5.2 BGA Escape Routing & Fanout Planning",
                    object_id=f"comp:{ref}",
                )
            )

    # 28. NPTH_PLATING_CONFLICT (warning)：非金属化孔与电镀属性冲突 (IPC-2221B / IPC-NC-349)
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        hole_type = str(props.get("hole_type", "")).lower()
        plated = bool(props.get("plated", False))
        if hole_type == "npth" and plated:
            issues.append(
                _issue(
                    "NPTH_PLATING_CONFLICT",
                    "非金属化孔标记为电镀钻孔歧义",
                    f"网络 {net_name} 孔属性 hole_type=npth 但 plated=true；"
                    "钻孔文件与成品孔径存在歧义，定位孔/安装孔电镀后将超差无法装配（IPC-2221B & IPC-NC-349 钻孔规范）。",
                    "warning",
                    "IPC-2221B & IPC-NC-349 Non-Plated Hole Fabrication Requirements",
                    object_id=f"net:{net_name}",
                )
            )

    # 29. FINE_PITCH_MASK_DAM_UNDEFINED (warning)：细间距封装阻焊坝未定义 (IPC-2221B / IPC-SM-782)
    for ref, m in modules.items():
        if ref == "__meta__":
            continue
        pkg = str(m.get("package", "")).upper()
        fine_pitch_pkgs = ("QFN", "DFN", "LQFP", "TSSOP", "BGA")
        is_fine = any(k in pkg for k in fine_pitch_pkgs) or float(m.get("pitch_mm", 1.0) or 1.0) <= 0.5
        mask_dam_defined = bool(m.get("mask_dam_defined", True))
        if is_fine and not mask_dam_defined:
            issues.append(
                _issue(
                    "FINE_PITCH_MASK_DAM_UNDEFINED",
                    "细间距封装阻焊坝未定义连锡短路风险",
                    f"器件 {ref} 封装 {pkg} 为细间距，但未定义阻焊坝 (Solder Mask Dam ≥0.1mm)；"
                    "相邻焊盘间阻焊桥无法制作，回流焊锡膏互连将造成引脚桥连短路（IPC-2221B & IPC-SM-782）。",
                    "warning",
                    "IPC-2221B & IPC-SM-782 Solder Mask Dam Design Requirements",
                    object_id=f"comp:{ref}",
                )
            )

    # 30. MOUNTING_HOLES_MISSING (warning)：多器件板卡缺少机械安装孔 (IPC-2221B Section 8.2)
    real_refs = [r for r in modules if r != "__meta__"]
    has_mount = any(
        str(m.get("kind", "")).upper() in ("MOUNT_HOLE", "HOLE", "STANDOFF")
        or "MOUNT" in str(m.get("value", "")).upper()
        for m in modules.values()
        if isinstance(m, dict)
    )
    if len(real_refs) >= 8 and not has_mount:
        issues.append(
            _issue(
                "MOUNTING_HOLES_MISSING",
                "板卡缺少机械安装孔固定锚点",
                f"板卡含 {len(real_refs)} 个器件但无任何机械安装孔 (Mounting Hole/Standoff)；"
                "整机装配将依赖连接器悬臂受力，振动/插拔应力易导致焊点开裂（IPC-2221B Section 8.2 机械固定要求）。",
                "warning",
                "IPC-2221B Section 8.2 Mechanical Mounting & Stress Relief",
            )
        )

    # 31. THT_WAVE_SOLDERING_UNSUITABLE (warning)：通孔器件不宜波峰焊 (IPC-A-610G Section 7)
    for ref, m in modules.items():
        if ref == "__meta__":
            continue
        pkg = str(m.get("package", "")).upper()
        is_tht = any(k in pkg for k in ("DIP", "TO-220", "TO-247", "RADIAL", "PINHEADER", "TERMINAL", "RELAY"))
        wave_ok = bool(m.get("wave_solderable", True))
        if is_tht and not wave_ok:
            issues.append(
                _issue(
                    "THT_WAVE_SOLDERING_UNSUITABLE",
                    "通孔器件不宜波峰焊需转工序",
                    f"通孔器件 {ref} (封装 {pkg}) 标记为不宜波峰焊（热敏感/大体积/遮蔽效应）；"
                    "应转选择性焊接或手工补焊工序，并在工艺路线中单独排程（IPC-A-610G Section 7 焊接工艺选择）。",
                    "warning",
                    "IPC-A-610G Section 7 Soldering Process Selection for THT Components",
                    object_id=f"comp:{ref}",
                )
            )

    # 32. MOUNTING_HOLE_KEEPOUT_MISSING (warning)：机械安装孔隔离环缺失 (IPC-2221B Section 8.2)
    for ref, m in modules.items():
        if ref == "__meta__":
            continue
        kind = str(m.get("kind", "")).upper()
        is_mount = kind in ("MOUNT_HOLE", "HOLE", "STANDOFF") or "MOUNT" in str(m.get("value", "")).upper()
        has_keepout = bool(m.get("has_keepout_ring", True))
        if is_mount and not has_keepout:
            issues.append(
                _issue(
                    "MOUNTING_HOLE_KEEPOUT_MISSING",
                    "机械安装孔隔离环未定义",
                    f"机械安装孔 {ref} 未定义电气隔离环/禁布区 (Keepout Ring)；"
                    "紧固件压入后与孔周铜箔/走线短路，或屏蔽地环与机壳地设计意图不明（IPC-2221B Section 8.2）。",
                    "warning",
                    "IPC-2221B Section 8.2 Mounting Hole Keepout & Chassis Ground Ring",
                    object_id=f"comp:{ref}",
                )
            )

    # 33. PANEL_PROCESS_FEATURES_MISSING (warning)：拼版工艺特征缺失 (IPC-SMEMA-9851 / IPC-2221B 8.4)
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        if not props.get("panelized", False):
            continue
        missing = [
            name
            for name, flag in (
                ("工艺边 Process Rails", props.get("has_process_rails", False)),
                ("光学定位点 Fiducials", props.get("has_fiducials", False)),
                ("定位孔 Tooling Holes", props.get("has_tooling_holes", False)),
            )
            if not flag
        ]
        if missing:
            issues.append(
                _issue(
                    "PANEL_PROCESS_FEATURES_MISSING",
                    "拼版板工艺特征缺失",
                    f"网络 {net_name} 标记为拼版 (panelized) 但缺少: {', '.join(missing)}；"
                    "SMT 传送夹持与贴片机视觉对位将无法执行（IPC-SMEMA-9851 导轨接口 & IPC-2221B Section 8.4）。",
                    "warning",
                    "IPC-SMEMA-9851 Conveyor Interface & IPC-2221B Section 8.4 Panelization",
                    object_id=f"net:{net_name}",
                )
            )

    # 34. TALL_COMPONENT_SMT_COLLISION_RISK (warning)：SMT 吸嘴高低元件碰撞干涉风险
    if modules and len(modules) >= 2:
        from .smt_placement_clearance import calculate_smt_placement_clearance

        rep_clr = calculate_smt_placement_clearance(modules)
        for cp in rep_clr.collision_pairs:
            if cp.is_collision_risk:
                issues.append(
                    _issue(
                        "TALL_COMPONENT_SMT_COLLISION_RISK",
                        "高低元件间距不足贴片吸嘴碰撞风险",
                        f"矮件 {cp.low_ref} (高 {cp.low_height_mm}mm) 与高件 {cp.high_ref} (高 {cp.high_height_mm}mm) "
                        f"高差达 {cp.height_delta_mm}mm 但间距仅 {cp.center_dist_mm}mm < 2.0mm；"
                        "贴片机吸嘴下压时易发生机械干涉击碎元件，需按由矮到高分层贴装并拉大间距（IPC-SM-782 / OpenPnP）。",
                        "warning",
                        "IPC-SM-782 Component Height Envelope & SMT Nozzle Z-Clearance Guidelines",
                        object_id=f"pair:{cp.low_ref}/{cp.high_ref}",
                    )
                )
        # Collision distance needs coordinates. Without them the pair is neither
        # safe nor unsafe — it is unexamined, and saying so is the whole point of
        # a gate. One issue, not one per pair: 144 identical warnings is
        # indistinguishable from silence, so the count carries the information.
        if rep_clr.unverified_pairs_count:
            issues.append(
                _issue(
                    "SMT_CLEARANCE_UNVERIFIED_NO_PLACEMENT",
                    "SMT 吸嘴碰撞未校验（缺少器件坐标）",
                    f"{rep_clr.unverified_pairs_count} 组高差元件对因缺少 position 坐标无法计算间距，"
                    "碰撞风险既未证实也未排除。补齐布局坐标后重跑本规则，或直接运行 "
                    "calculate_smt_placement_clearance 获取分层贴装序列（IPC-SM-782 / OpenPnP）。",
                    "info",
                    "IPC-SM-782 Component Height Envelope & SMT Nozzle Z-Clearance Guidelines",
                    object_id="smt_clearance:unplaced",
                )
            )

    # 35. CREEPAGE_DISTANCE_VIOLATION_WITHOUT_SLOT (warning)：高压爬电间隙不足且未开防爬电铣槽
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        v = float(props.get("voltage_v", 0.0) or 0.0)
        direct_dist = props.get("clearance_mm")
        has_slot = bool(props.get("has_isolation_slot", False))
        if v >= 100.0 and direct_dist is not None:
            from .creepage_slot import get_required_creepage

            req_c = get_required_creepage(v)
            if float(direct_dist) < req_c and not has_slot:
                issues.append(
                    _issue(
                        "CREEPAGE_DISTANCE_VIOLATION_WITHOUT_SLOT",
                        "高压爬电距离不足且未开防爬电隔离槽",
                        f"高压网络 {net_name} ({v:g}V) 间距 {float(direct_dist):.2f}mm < 要求的 {req_c:.2f}mm，"
                        "且未规划贯通空气隔离铣槽；潮湿粉尘环境下表面漏电起痕将引发介质击穿（IPC-2221B Table 6-1 / IEC 62368-1）。",
                        "warning",
                        "IPC-2221B Table 6-1 & IEC 62368-1 High Voltage Creepage Requirements",
                        object_id=f"net:{net_name}",
                    )
                )

    # 36. IMPEDANCE_TOLERANCE_WINDOW_EXCEEDED (warning)：特征阻抗公差波动超出 ±10%
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        target_z = props.get("target_impedance_ohms")
        w_mm = props.get("trace_width_mm")
        h_mm = props.get("dielectric_height_mm")
        if target_z is not None and w_mm is not None and h_mm is not None:
            from .impedance_tolerance_analyzer import analyze_impedance_tolerance

            rep_tol = analyze_impedance_tolerance(
                target_z0_ohms=float(target_z),
                trace_width_mm=float(w_mm),
                dielectric_height_mm=float(h_mm),
                copper_thickness_mm=float(props.get("copper_thickness_mm", 0.035)),
                dielectric_er=float(props.get("dielectric_er", 4.2)),
            )
            if not rep_tol.within_10pct_window:
                issues.append(
                    _issue(
                        "IMPEDANCE_TOLERANCE_WINDOW_EXCEEDED",
                        "特征阻抗制造公差波动超标",
                        f"网络 {net_name} 目标阻抗 {target_z:g}Ω，在板厂公差叠加下波动范围 "
                        f"[{rep_tol.min_z0_ohms:g}Ω ~ {rep_tol.max_z0_ohms:g}Ω] 超出 ±10% 目标容限窗口；"
                        "高频信号易出现眼图闭合与阻抗不连续反射（IPC-2141A 阻抗公差模型）。",
                        "warning",
                        "IPC-2141A Controlled Impedance Manufacturing Tolerance Window",
                        object_id=f"net:{net_name}",
                    )
                )

    # 37. POLLUTION_DEGREE_CREEPAGE_DEFICIT (warning)：基材 CTI 偏低导致爬电安全裕度不足
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        v = float(props.get("voltage_v", 0.0) or 0.0)
        cti = float(props.get("substrate_cti_v", 175.0))
        clr = props.get("actual_clearance_mm") or props.get("clearance_mm")
        pd = int(props.get("pollution_degree", 2))
        if v >= 100.0 and clr is not None:
            from .material_cti_evaluator import evaluate_material_cti_creepage

            rep_cti = evaluate_material_cti_creepage(
                working_voltage_v=v,
                actual_clearance_mm=float(clr),
                substrate_cti_v=cti,
                pollution_degree=pd,
                insulation_type=str(props.get("insulation_type", "Basic")),
            )
            if not rep_cti.is_compliant:
                issues.append(
                    _issue(
                        "POLLUTION_DEGREE_CREEPAGE_DEFICIT",
                        "污染等级下基材 CTI 爬电安全裕度不足",
                        f"网络 {net_name} ({v:g}V) 在污染等级 {pd} 下要求爬电 {rep_cti.required_creepage_mm:.2f}mm，"
                        f"当前基材 ({rep_cti.material_group}, CTI {cti:g}V) 间距 {float(clr):.2f}mm 不足；"
                        "建议升级选用 CTI ≥ 600V 高 CTI 覆铜板或增大间距（IEC 62368-1 / GB 4943.1）。",
                        "warning",
                        "IEC 62368-1 Table 25 Material Group & Comparative Tracking Index Criteria",
                        object_id=f"net:{net_name}",
                    )
                )

    # 38. BOTTOM_SMD_WAVE_ORIENTATION_MISALIGNED (warning)：底面 SMD 阻容/SOIC 焊接朝向角失配
    if modules:
        flow_dir = str(modules.get("__meta__", {}).get("wave_flow_direction", "X+"))
        bottom_smds = {
            r: m for r, m in modules.items() if r != "__meta__" and bool(m.get("bottom_side", False))
        }
        if bottom_smds:
            from .wave_solder_orientation import calculate_wave_solder_orientation_audit

            rep_ori = calculate_wave_solder_orientation_audit(bottom_smds, flow_direction=flow_dir)
            for iss in rep_ori.issues:
                issues.append(
                    _issue(
                        "BOTTOM_SMD_WAVE_ORIENTATION_MISALIGNED",
                        "底面贴片器件波峰焊几何朝向角失配",
                        iss.detail,
                        "warning",
                        "IPC-7351B Section 3.1.4 & SMTA Wave Soldering Guidelines",
                        object_id=f"comp:{iss.ref}",
                    )
                )

    # 39. PRESS_FIT_PTH_TOLERANCE_VIOLATION (warning)：鱼眼压接针孔径公差或孔壁铜厚违规
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        if bool(props.get("is_press_fit", False)):
            from .press_fit_analyzer import calculate_press_fit_hole_compliance

            pin_item = [{
                "pin_id": net_name,
                "connector_ref": str(props.get("connector_ref", "CONN")),
                "drill_dia_mm": float(props.get("drill_dia_mm", 1.15)),
                "copper_thickness_um": float(props.get("copper_thickness_um", 25.0)),
                "finished_dia_mm": float(props["finished_dia_mm"]) if "finished_dia_mm" in props else None,
            }]
            # filter out None
            pin_item = [{k: v for k, v in pin_item[0].items() if v is not None}]
            rep_pf = calculate_press_fit_hole_compliance(pin_item)
            for chk in rep_pf.checks:
                if not chk.is_compliant:
                    issues.append(
                        _issue(
                            "PRESS_FIT_PTH_TOLERANCE_VIOLATION",
                            "无焊压接孔径公差或孔壁铜厚违规",
                            f"压接引脚 {chk.pin_id} ({chk.connector_ref}) 违规: {chk.violation_reason}；"
                            "超出 IPC-9797 汽车级公差要求，存在压溃 PCB 内部走线层或振动接触不良风险。",
                            "warning",
                            "IPC-9797 Table 4-1 & IEC 60352-5 Press-Fit Specification",
                            object_id=f"net:{net_name}",
                        )
                    )

    # 40. FAB_CAPABILITY_LIMIT_EXCEEDED (warning)：线宽/线距/过孔超出板厂能力极限
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        w = props.get("trace_width_mm")
        s = props.get("trace_clearance_mm")
        v_d = props.get("via_drill_mm")
        fab_id = str(props.get("target_fab_id", "")).lower()
        if (w is not None and float(w) < 0.09) or (s is not None and float(s) < 0.09) or (v_d is not None and float(v_d) < 0.20):
            from .fab_capabilities import audit_fab_capabilities

            rep_fab = audit_fab_capabilities(
                fab_id=fab_id or "jlcpcb_standard",
                min_trace_width_mm=float(w) if w is not None else 0.127,
                min_trace_clearance_mm=float(s) if s is not None else 0.127,
                min_via_drill_mm=float(v_d) if v_d is not None else 0.20,
            )
            if not rep_fab.is_compliant:
                v_desc = "; ".join(v.description for v in rep_fab.violations)
                issues.append(
                    _issue(
                        "FAB_CAPABILITY_LIMIT_EXCEEDED",
                        "物理几何特征超出板厂制造能力极限",
                        f"网络 {net_name} 存在超出 {rep_fab.fab_name} 制程能力指标: {v_desc}；"
                        "板厂工程预审 (CAM EQ) 将驳回订单或产生昂贵的高阶工艺附加费（IPC-6012）。",
                        "warning",
                        "IPC-6012 Class 2 / Fab House Process Limits",
                        object_id=f"net:{net_name}",
                    )
                )

    # 41. SILKSCREEN_OVER_EXPOSED_COPPER (warning)：丝印字符压在裸露焊接焊盘上
    for ref, m in modules.items():
        if ref == "__meta__":
            continue
        has_silk_clash = bool(m.get("silkscreen_over_pad", False))
        if has_silk_clash:
            issues.append(
                _issue(
                    "SILKSCREEN_OVER_EXPOSED_COPPER",
                    "丝印文字遮挡裸露焊盘铜皮",
                    f"器件 {ref} 丝印层文字/图形与裸露焊盘发生交叉重叠；"
                    "丝印油墨耐温沾染焊盘将导致焊锡无法润湿，产生虚焊与立碑缺陷（IPC-A-600J / IPC-7351B）。",
                    "warning",
                    "IPC-A-600J & IPC-7351B Silkscreen-to-Pad Clearance Rules",
                    object_id=f"comp:{ref}",
                )
            )

    # 42. CLASS3_ANNULAR_RING_BREAKOUT_FORBIDDEN (error)：Class 3 高可靠严禁孔破且外环宽 >= 0.050mm
    target_class = str(modules.get("__meta__", {}).get("ipc_class", "")).strip()
    if "3" in target_class:
        for conn in connections or []:
            props = conn.get("properties") or {}
            net_name = conn.get("net", "")
            ext_ring = props.get("annular_ring_mm")
            has_breakout = bool(props.get("hole_breakout", False))
            if has_breakout or (ext_ring is not None and float(ext_ring) < 0.050):
                issues.append(
                    _issue(
                        "CLASS3_ANNULAR_RING_BREAKOUT_FORBIDDEN",
                        "IPC Class 3 高可靠严禁钻孔破出且外环宽不足",
                        f"网络 {net_name} 环宽 {ext_ring}mm 或存在孔破破出；"
                        "IPC-6012E Class 3 航天/军工/医疗级硬性规定焊盘外环宽必须 ≥ 0.050mm (2.0 mil) 且零破出 (0° breakout)（IPC-6012E §3.6.2.1）。",
                        "error",
                        "IPC-6012E Table 3-5 & IPC-A-600J §2.8.1.3 Class 3 Acceptability",
                        object_id=f"net:{net_name}",
                    )
                )

    # 43. SMT_FEEDER_CAPACITY_EXCEEDED (warning)：SMT 贴片机供料飞达料枪槽位超限
    if modules:
        from .smt_feeder_optimizer import optimize_smt_feeder_setup

        cart_cap = int(modules.get("__meta__", {}).get("feeder_cart_capacity", 80))
        feeder_plan = optimize_smt_feeder_setup(modules, feeder_cart_capacity=cart_cap)
        if feeder_plan.slots_demanded > cart_cap:
            issues.append(
                _issue(
                    "SMT_FEEDER_CAPACITY_EXCEEDED",
                    "SMT 贴片机料车飞达料位超出单台容量",
                    f"当前设计需求 {feeder_plan.slots_demanded} 个飞达料槽，超过单台标准料车上限 ({cart_cap} 槽)；"
                    "需拆分双贴片机连线 (Ganging) 或分批次二次换型，将显著增加产线换线停机时间（IPC-9851）。",
                    "warning",
                    "IPC-9851 & Panasonic/Fuji SMT Feeder Trolley Capacity Standards",
                    object_id="mfg:smt_feeder",
                )
            )

    # 44. COPPER_POUR_CURRENT_DENSITY_EXCEEDED (warning)：大面积多边形覆铜颈缩区电流密度过载
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        pour_current = props.get("pour_current_a")
        if pour_current is not None and float(pour_current) > 0:
            from .copper_pour_analyzer import calculate_copper_pour_current_drop

            w_eff = float(props.get("pour_effective_width_mm", 20.0))
            w_bot = float(props.get("pour_bottleneck_width_mm", w_eff))
            cu_oz = float(props.get("copper_weight_oz", 1.0))
            rep_pour = calculate_copper_pour_current_drop(
                current_a=float(pour_current),
                copper_weight_oz=cu_oz,
                effective_width_mm=w_eff,
                bottleneck_width_mm=w_bot,
            )
            if not rep_pour.is_density_compliant:
                issues.append(
                    _issue(
                        "COPPER_POUR_CURRENT_DENSITY_EXCEEDED",
                        "大功率铜皮局部瓶颈区电流密度超标",
                        f"网络 {net_name} 覆铜在 {pour_current}A 负载下，颈缩区电流密度达 "
                        f"{rep_pour.bottleneck_current_density_a_per_mm2:.1f} A/mm² > 35.0 A/mm²；"
                        "高密度焦耳热无法有效散热，存在阻焊层碳化起泡或铜箔烧断高危（IPC-2152 §5.0）。",
                        "warning",
                        "IPC-2152 Section 5.0 & IEC 60092-352 Current Density Limits",
                        object_id=f"net:{net_name}",
                    )
                )

    # 45. MSL_FLOOR_LIFE_EXPIRED_WITHOUT_BAKE (warning)：潮敏器件车间开袋暴露时间超期未烘烤
    if modules:
        from .msl_manager import audit_component_msl_floor_life

        default_exp = float(modules.get("__meta__", {}).get("shop_floor_exposed_hours", 0.0))
        if default_exp > 0.0:
            rep_msl = audit_component_msl_floor_life(modules, exposed_hours_default=default_exp)
            for item in rep_msl.baking_action_items:
                ref_d = item["ref_des"]
                issues.append(
                    _issue(
                        "MSL_FLOOR_LIFE_EXPIRED_WITHOUT_BAKE",
                        "潮湿敏感贴片芯片暴露车间寿命超期未烘烤",
                        f"器件 {ref_d} ({item['package']}, {item['msl_level']}) 已开袋暴露 {item['exposed_hours']}h "
                        f"> 允许寿命 {item['allowed_hours']}h；直接过 260°C 回流焊极易引发水汽爆米花分层裂纹，"
                        f"推荐除湿烘烤方案: {item['baking_plan']}（JEDEC J-STD-033D）。",
                        "warning",
                        "JEDEC J-STD-033D Table 4-1 & IPC-M-109 Moisture Management",
                        object_id=f"comp:{ref_d}",
                    )
                )

    # 46. HIGH_SPEED_ROUGHNESS_LOSS_EXCESSIVE (warning)：高频走线铜箔粗糙度附加损耗超标
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        freq_ghz = props.get("operating_freq_ghz")
        foil = str(props.get("copper_foil_type", "standard_ed")).lower()
        if freq_ghz is not None and float(freq_ghz) >= 5.0 and "standard" in foil:
            from .skin_effect_analyzer import calculate_high_speed_skin_depth_loss

            rep_skin = calculate_high_speed_skin_depth_loss(
                frequency_ghz=float(freq_ghz),
                trace_width_mm=float(props.get("trace_width_mm", 0.150)),
                foil_type=foil,
            )
            if not rep_skin.is_roughness_acceptable:
                issues.append(
                    _issue(
                        "HIGH_SPEED_ROUGHNESS_LOSS_EXCESSIVE",
                        "高频信号铜箔微观粗糙度集肤损耗过高",
                        f"高速网络 {net_name} 在 {freq_ghz} GHz 频率下使用标称粗糙铜箔 ({foil})，"
                        f"集肤深度仅 {rep_skin.skin_depth_um:.2f}μm，粗糙度损耗惩罚系数 Ksr={rep_skin.roughness_correction_factor_ksr:.2f} "
                        f"(衰减增加 {rep_skin.roughness_loss_percentage:.1f}%)；建议升级为 HVLP/RTF 铜箔（IPC-4562B）。",
                        "warning",
                        "IPC-4562B §3.2 Table 3-1 & IPC-2141A High-Frequency Conductor Losses",
                        object_id=f"net:{net_name}",
                    )
                )

    # 47. BARE_BOARD_TEST_VOLTAGE_OVERSTRESS_RISK (warning)：细间距或敏感网络裸板电测试电压过压击穿风险
    target_class = str(modules.get("__meta__", {}).get("ipc_class", "Class 2")).strip()
    if "3" in target_class:
        for conn in connections or []:
            props = conn.get("properties") or {}
            net_name = conn.get("net", "")
            clr = props.get("trace_clearance_mm")
            if clr is not None and float(clr) < 0.100:
                issues.append(
                    _issue(
                        "BARE_BOARD_TEST_VOLTAGE_OVERSTRESS_RISK",
                        "高可靠板卡细间距走线裸板高压测试击穿风险",
                        f"网络 {net_name} 导线间距 {clr}mm < 0.100mm；IPC-9252B Class 3 默认 250V DC 绝缘电阻测试 "
                        "在微细空气间隙下存在电弧电离微击穿风险，测试程序必须降额至 100V 并延长驻留时间（IPC-9252B §4.4）。",
                        "warning",
                        "IPC-9252B Section 4.4 Table 4-1 Dielectric Breakdown Overstress Limits",
                        object_id=f"net:{net_name}",
                    )
                )

    # 48. IONIC_CONTAMINATION_EXCEEDANCE (warning)：组件后清洗 ROSE 离子污染超限枝晶风险
    meta_mod = modules.get("__meta__", {}) if modules else {}
    rose_val = meta_mod.get("rose_ionic_ug_cm2")
    if rose_val is not None and float(rose_val) > 0:
        from .ionic_contamination import analyze_ionic_contamination

        rep_ion = analyze_ionic_contamination(
            board_area_cm2=float(meta_mod.get("board_area_cm2", 100.0)),
            rose_measured_ug_cm2=float(rose_val),
            target_class=target_class or "Class 2",
            bias_voltage_v=float(meta_mod.get("max_bias_voltage_v", 5.0)),
            min_conductor_gap_mm=float(meta_mod.get("min_conductor_gap_mm", 0.20)),
        )
        if not rep_ion.is_rose_compliant or rep_ion.dendrite_risk_level == "high":
            issues.append(
                _issue(
                    "IONIC_CONTAMINATION_EXCEEDANCE",
                    "清洗后离子污染 (ROSE) 超限枝晶漏电风险",
                    f"ROSE 实测 {rep_ion.rose_measured_ug_cm2:.2f} μg/cm² 超出 {rep_ion.target_class} 限值 "
                    f"{rep_ion.rose_limit_ug_cm2:.2f} μg/cm² (枝晶风险: {rep_ion.dendrite_risk_level})；"
                    "残留卤化物活化剂在偏压下沿导体间隙生长枝晶/CAF 漏电通道，需水基皂洗复洗并做离子色谱定位物种（IPC-CH-65）。",
                    "warning",
                    "IPC-CH-65 & IPC-TM-650 2.3.25/2.3.28 Ionic Cleanliness Standards",
                    object_id="mfg:cleanliness",
                )
            )

    # 49. BLACK_PAD_NICKEL_CORROSION_RISK (warning)：ENIG 镀层参数失控黑盘脆断风险
    finish = str(meta_mod.get("surface_finish", "")).lower()
    if "enig" in finish or "enepig" in finish:
        from .enig_plating_analyzer import analyze_enig_plating

        rep_pl = analyze_enig_plating(
            finish_type=finish,
            gold_thickness_um=float(meta_mod.get("gold_thickness_um", 0.08)),
            nickel_thickness_um=float(meta_mod.get("nickel_thickness_um", 4.0)),
            phosphorus_wt_pct=float(meta_mod.get("phosphorus_wt_pct", 8.5)),
            palladium_thickness_um=(
                float(meta_mod["palladium_thickness_um"]) if "palladium_thickness_um" in meta_mod else None
            ),
            rework_cycles=int(meta_mod.get("rework_cycles", 0)),
            soldering_process=str(meta_mod.get("soldering_process", "reflow")),
        )
        if rep_pl.black_pad_risk == "high" or rep_pl.gold_embrittlement_risk:
            detail = (
                f"{rep_pl.finish_type}: Au {rep_pl.gold_thickness_um:.2f}μm / Ni {rep_pl.nickel_thickness_um:.1f}μm / "
                f"P {rep_pl.phosphorus_wt_pct:.1f}wt%，黑盘风险 {rep_pl.black_pad_risk}"
                + ("，且金厚超过 0.25μm 存在 AuSn₄ 焊点脆化" if rep_pl.gold_embrittlement_risk else "")
                + "；浸金槽电偶过腐蚀高磷镍晶界将形成不润湿泥裂界面，焊点在机械应力下脆断（IPC-4552A）。"
            )
            issues.append(
                _issue(
                    "BLACK_PAD_NICKEL_CORROSION_RISK",
                    "ENIG 表面处理参数失控引发黑盘脆断风险",
                    detail,
                    "warning",
                    "IPC-4552A & IPC-4556 Plating Specifications (Black Pad / Nickel Corrosion)",
                    object_id="fab:surface_finish",
                )
            )

    # 50. THERMAL_CYCLING_FATIGUE_RISK (warning)：关键封装热循环疲劳寿命不足
    for conn in connections or []:
        props = conn.get("properties") or {}
        net_name = conn.get("net", "")
        dnp = props.get("thermal_dnp_mm")
        if dnp is None or float(dnp) <= 0:
            continue
        from .thermal_fatigue import estimate_solder_joint_thermal_fatigue

        rep_fat = estimate_solder_joint_thermal_fatigue(
            component=net_name,
            dnp_mm=float(dnp),
            joint_height_mm=float(props.get("joint_height_mm", 0.10)),
            condition=str(props.get("thermal_cycling_condition", "TC3")),
            hot_dwell_min=float(props.get("hot_dwell_min", 10.0)),
            package_cte_ppm=float(props.get("package_cte_ppm", 14.0)),
            required_cycles=float(props.get("required_cycles", 3000.0)),
        )
        if not rep_fat.meets_requirement:
            issues.append(
                _issue(
                    "THERMAL_CYCLING_FATIGUE_RISK",
                    "关键焊点热循环疲劳寿命低于服役要求",
                    f"器件 {net_name} DNP {float(dnp):.1f}mm 在 {rep_fat.condition} "
                    f"({rep_fat.temp_min_c:.0f}~{rep_fat.temp_max_c:.0f}°C) 下 Engelmaier 寿命 "
                    f"{rep_fat.cycles_to_failure_ntf:,.0f} 循环 < 要求 {rep_fat.required_cycles:,.0f}；"
                    "CTE 失配剪切应变将率先撕开最远角焊点（IPC-9701）。缩短 DNP/降低 ΔT/欠填充。",
                    "warning",
                    "IPC-9701A & IPC-D-279 Engelmaier Thermal Fatigue Model",
                    object_id=f"net:{net_name}",
                )
            )

    # 51. CONFORMAL_COATING_CONTACT_RISK (warning)：三防漆渗入未掩膜触点风险
    meta_cc = modules.get("__meta__", {}) if modules else {}
    cc_type = str(meta_cc.get("conformal_coating", "")).upper().strip()
    if cc_type in ("AR", "ER", "UR", "SR", "XY"):
        from .conformal_coating import plan_conformal_coating

        rep_cc = plan_conformal_coating(
            coating_type=cc_type,
            measured_thickness_um=float(meta_cc.get("coating_thickness_um", 75.0)),
            modules=modules,
            requires_field_rework=bool(meta_cc.get("requires_field_rework", False)),
        )
        for r in rep_cc.unmasked_contact_risk:
            ref_c = r["ref"]
            issues.append(
                _issue(
                    "CONFORMAL_COATING_CONTACT_RISK",
                    "三防漆工艺存在触点渗入未掩膜失效风险",
                    f"器件 {ref_c} 声明免涂但未做掩膜验证：{r['issue']}；"
                    f"涂覆程序须在 {cc_type} 选择性喷涂前对连接器/测试点/开关完成掩膜并首件确认（IPC-A-610G §10.4）。",
                    "warning",
                    "IPC-CC-830C & IPC-A-610G §10.4 Coating Keep-out Requirements",
                    object_id=f"comp:{ref_c}",
                )
            )
        if rep_cc.reworkability_conflict:
            issues.append(
                _issue(
                    "CONFORMAL_COATING_CONTACT_RISK",
                    "三防漆选型与现场返修需求冲突",
                    f"{rep_cc.coating_type_name} 返修等级为 {rep_cc.rework_level}，"
                    "产品要求现场可返修——改选 Type AR 或为易损区域预留可剥离掩膜（IPC-WP-825）。",
                    "warning",
                    "IPC-WP-825 Conformal Coating Selection Guidelines",
                    object_id="mfg:conformal_coating",
                )
            )

    # 52. MTBF_RELIABILITY_BUDGET_SHORTFALL (warning)：整机 MTBF 低于可靠性分配目标
    meta_rel = modules.get("__meta__", {}) if modules else {}
    mtbf_target_h = meta_rel.get("mtbf_target_hours")
    if mtbf_target_h is not None and float(mtbf_target_h) > 0 and modules:
        from .mtbf_predictor import predict_assembly_mtbf

        rep_rel = predict_assembly_mtbf(
            modules=modules,
            ambient_temp_c=float(meta_rel.get("worst_ambient_c", 40.0)),
            environment=str(meta_rel.get("reliability_environment", "ground_fixed")),
            quality_level=int(meta_rel.get("quality_level", 2)),
        )
        if rep_rel.mtbf_hours < float(mtbf_target_h):
            worst_share = (
                f"（最大贡献: {rep_rel.dominant_parts[0]['part_class']} "
                f"{rep_rel.dominant_parts[0]['share_pct']:.0f}%）"
                if rep_rel.dominant_parts
                else ""
            )
            issues.append(
                _issue(
                    "MTBF_RELIABILITY_BUDGET_SHORTFALL",
                    "整机 MTBF 预测低于可靠性分配目标",
                    f"Telcordia SR-332 part-stress 预测 MTBF {rep_rel.mtbf_hours:,.0f}h "
                    f"({rep_rel.mtbf_hours / 8760.0:.1f} 年) < 目标 {float(mtbf_target_h):,.0f}h"
                    f"{worst_share}；降额关键器件温升、提升质量等级或冗余设计后复算（Telcordia SR-332）。",
                    "warning",
                    "Telcordia SR-332 Issue 3 Part-Stress Reliability Prediction",
                    object_id="sys:reliability",
                )
            )

    # 53. DROP_SHOCK_HIGH_RISK_PLACEMENT (warning)：大质量器件板角高应变区跌落脆断
    drop_comps = meta_rel.get("drop_test_components")
    if isinstance(drop_comps, list) and drop_comps:
        from .drop_shock import assess_drop_shock_reliability

        rep_drop = assess_drop_shock_reliability(
            board_width_mm=float(meta_rel.get("board_width_mm", 80.0)),
            board_height_mm=float(meta_rel.get("board_height_mm", 50.0)),
            board_mass_g=float(meta_rel.get("board_mass_g", 60.0)),
            components=drop_comps,
            test_g=float(meta_rel.get("drop_test_g", 1500.0)),
        )
        for c in rep_drop.components:
            if c.risk_level == "high":
                issues.append(
                    _issue(
                        "DROP_SHOCK_HIGH_RISK_PLACEMENT",
                        "器件跌落冲击惯性过载高风险",
                        f"器件 {c.ref} ({c.mass_g:.1f}g, {c.joint_count} 焊点) 在 1500G 脉冲下单点载荷 "
                        f"{c.per_joint_load_n:.0f}N 且处于板角高应变区；"
                        f"{c.mitigation}（JESD22-B111）。",
                        "warning",
                        "JEDEC JESD22-B111 Board-Level Drop Test Method",
                        object_id=f"comp:{c.ref}",
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
