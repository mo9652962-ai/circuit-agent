"""IPC-2152 导线短路熔断电流与短时瞬态热烧蚀求解器 (Onderdonk / Preece & IPC-2152 §5.3)。

工业背景与物理机制：
1. PCB 走线在承受电机启动浪涌、电源总线短路击穿或雷击过流脉冲时，属于短时绝热过程
   （Adiabatic Heating, 脉冲时间 t 通常在 1ms ~ 5s 内）。
2. I.M. Onderdonk 绝热熔断方程（IEEE / IPC-2152 标准基础方程）：
       I = A * sqrt( log10( (T_m - T_a) / (234 + T_a) + 1 ) / (33 * t) )
   其中：
   - I: 熔断电流 (A)
   - A: 导线截面积（圆密尔, Circular Mils，1 mm² = 1973.525 circular mils）
   - T_m: 极限温度（铜熔点为 1083°C；FR-4 环氧树脂爆板分层起泡临界温典型 260~288°C）
   - T_a: 初始环境工作温度（典型 25~70°C）
   - t: 故障持续脉冲时间（秒）
3. 动作积分 (Action Integral / Joule Integral, I²t)：
       I²t = (A² / 33) * log10( (T_m - T_a) / (234 + T_a) + 1 )  (A²s)
   该值代表引起铜皮汽化或基材碳化所需的最小瞬态热能量。
4. 内外层散热降额 (Internal vs External Trace Derating, IPC-2152 §5.3)：
   外层导线有空气对流和辐射散热；内层导线被导热极差的玻璃环氧树脂包围（k ≈ 0.25 W/m·K），
   热量完全封堵于芯板内，IPC-2152 规定内层导线抗过流熔断能力需按 65% 折减（I²t 降额至 ~42%）。
5. 级联保护配合裕量 (Protection Coordination Margin)：
   PCB 走线绝不可充当牺牲熔丝！若上游熔断器（Fuse）或自恢复保险丝（PTC）的熔断热能量
   I²t_fuse 接近或大于 PCB 走线分层热能量 I²t_delam（配合裕量 < 1.50），在短路故障发生时
   PCB 走线将先于保险丝起火烧断并碳化，酿成严重电气火灾。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# 铜材料物理常数
COPPER_MELT_TEMP_C = 1083.0  # 铜熔化温度
FR4_DELAM_TEMP_C = 280.0     # FR-4 玻璃转化分层起泡极限温度
MM2_TO_CIRCULAR_MILS = 1973.52524  # 1 mm² 对应的 circular mils


@dataclass
class TraceFusingResult:
    trace_width_mm: float
    copper_thickness_um: float
    trace_layer: str
    cross_section_mm2: float
    cross_section_circular_mils: float
    fault_current_a: float
    pulse_duration_s: float
    adiabatic_fusing_current_a: float
    fr4_delamination_current_a: float
    time_to_melt_s: float
    time_to_delamination_s: float
    action_integral_i2t_a2s: float
    trace_burnout_risk: bool
    coordination_margin_ok: bool
    is_safe: bool
    violations: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)


def calculate_trace_fusing_current(
    trace_width_mm: float = 0.50,
    copper_thickness_um: float = 35.0,  # 1oz copper
    trace_layer: str = "external",      # 'external' 或 'internal'
    fault_current_a: float = 15.0,
    pulse_duration_s: float = 0.10,     # 100ms 典型断路保护时间
    ambient_temp_c: float = 25.0,
    upstream_fuse_rating_a: float | None = None,
    upstream_fuse_i2t_a2s: float | None = None,
) -> TraceFusingResult:
    """计算 PCB 走线短时故障过流熔断极限、基材碳化起泡风险与上游保险丝级联配合裕量。

    参数：
        trace_width_mm: 走线宽度（mm）。
        copper_thickness_um: 铜厚（μm，1oz ≈ 35μm，2oz ≈ 70μm）。
        trace_layer: 所在层 ('external' 或 'internal')。
        fault_current_a: 预估短路冲击峰值电流（A）。
        pulse_duration_s: 短路故障持续时间（秒，典型 0.005 ~ 2.0s）。
        ambient_temp_c: 初始环境工作温度（°C，默认 25°C）。
        upstream_fuse_rating_a: 上游串联保险丝额定电流（A），可选。
        upstream_fuse_i2t_a2s: 上游保险丝标称熔断 I²t（A²s），可选。
    """
    standards = [
        "IPC-2152 Standard for Determining Current-Carrying Capacity in Printed Board Design §5.3",
        "I.M. Onderdonk Conductor Fusing Current Equation under Adiabatic Conditions",
        "UL 796 Standard for Tests for Printed-Wiring Boards (Flame and Thermal Delamination)",
        "IEC 60127 Miniature Fuses - Selection and Protection Coordination Guidelines",
    ]

    layer_clean = trace_layer.lower().strip()
    is_internal = "internal" in layer_clean or "inner" in layer_clean

    # 1. 计算导线截面积
    thickness_mm = copper_thickness_um * 1e-3
    area_mm2 = trace_width_mm * thickness_mm
    area_cmil = area_mm2 * MM2_TO_CIRCULAR_MILS

    # 2. 内层绝热降额系数
    # IPC-2152 §5.3: 内层走线热无法扩散至空气中，容许绝热能量降额至 45% (电流折减至 ~67%)
    derating_factor = 0.67 if is_internal else 1.00

    # 3. Onderdonk 方程计算完全熔断电流 (T_melt = 1083°C) 与分层电流 (T_delam = 280°C)
    # I = A * sqrt( log10( (Tm - Ta)/(234 + Ta) + 1 ) / (33 * t) )
    t_pulse = max(pulse_duration_s, 1e-4)
    denom = 234.0 + ambient_temp_c

    melt_log_term = math.log10((COPPER_MELT_TEMP_C - ambient_temp_c) / denom + 1.0)
    delam_log_term = math.log10((FR4_DELAM_TEMP_C - ambient_temp_c) / denom + 1.0)

    # 铜皮汽化熔断电流 (A)
    i_fuse_melt = area_cmil * math.sqrt(melt_log_term / (33.0 * t_pulse)) * derating_factor
    # 基材分层起泡电流 (A)
    i_delam = area_cmil * math.sqrt(delam_log_term / (33.0 * t_pulse)) * derating_factor

    # 4. 计算给定故障电流 fault_current_a 下的熔断时间 (秒)
    i_fault = max(fault_current_a, 0.01)
    # t = (A² / I²) * (log_term / 33)
    t_melt_calc = ((area_cmil / i_fault) ** 2) * (melt_log_term / 33.0) * (derating_factor**2)
    t_delam_calc = ((area_cmil / i_fault) ** 2) * (delam_log_term / 33.0) * (derating_factor**2)

    # 5. 走线焦耳积分 Action Integral I²t (A²s) 以分层温度核算
    trace_i2t_delam = (i_delam**2) * t_pulse

    # 6. 故障评估
    violations: list[str] = []
    recommendations: list[str] = []

    burnout_risk = False
    if fault_current_a >= i_delam:
        burnout_risk = True
        violations.append(
            f"故障短路电流 {fault_current_a:.1f}A 超过走线短时热极限 "
            f"({i_delam:.1f}A, 脉宽 {pulse_duration_s*1e3:.0f}ms)；"
            f"走线将在 {t_delam_calc*1e3:.1f}ms 内突破 FR-4 基材 280°C 爆板分层起泡阈值，面临着火断路风险（IPC-2152 §5.3）。"
        )
    elif fault_current_a >= (i_delam * 0.80):
        recommendations.append(
            f"故障电流 {fault_current_a:.1f}A 达到走线热安全耐受阈值的 {(fault_current_a/i_delam)*100:.1f}%，"
            "建议加宽走线或增厚铜皮以留出足够过流安全裕量。"
        )

    # 7. 保险丝级联配合核验
    coordination_margin_ok = True
    if upstream_fuse_i2t_a2s is not None and upstream_fuse_i2t_a2s > 0:
        # 配合要求：走线起泡能量必须至少是上游保险丝熔断能量的 2.0 倍
        ratio = trace_i2t_delam / upstream_fuse_i2t_a2s
        if ratio < 1.50:
            coordination_margin_ok = False
            violations.append(
                f"走线绝热耐受 I²t={trace_i2t_delam:.2f} A²s 与上游保险丝 I²t={upstream_fuse_i2t_a2s:.2f} A²s 配合裕量不足 "
                f"(比值 {ratio:.2f} < 1.50)；短路发生时 PCB 走线可能先于或伴随保险丝起火碳化！"
            )
        elif ratio < 2.00:
            recommendations.append(
                f"走线与上游保险丝 I²t 配合裕量比为 {ratio:.2f}，略低于工业推荐值 2.00，建议提升走线截面。"
            )
    elif upstream_fuse_rating_a is not None and upstream_fuse_rating_a > 0:
        if upstream_fuse_rating_a >= i_delam:
            coordination_margin_ok = False
            violations.append(
                f"上游保险丝额定电流 ({upstream_fuse_rating_a:.1f}A) 大于等于走线短时过流极限 ({i_delam:.1f}A)，"
                "保护器件无法对走线提供有效热保护，走线可能充当牺牲熔丝！"
            )

    if not violations:
        recommendations.append(
            f"走线过流与熔断指标合格：线宽 {trace_width_mm:.2f}mm / 铜厚 {copper_thickness_um:.0f}μm ({trace_layer})，"
            f"耐受 {fault_current_a:.1f}A 持续 {pulse_duration_s*1e3:.0f}ms 安全，I²t 耐受值 {trace_i2t_delam:.2f} A²s。"
        )

    is_safe = (not burnout_risk) and coordination_margin_ok

    return TraceFusingResult(
        trace_width_mm=round(trace_width_mm, 3),
        copper_thickness_um=round(copper_thickness_um, 1),
        trace_layer=trace_layer,
        cross_section_mm2=round(area_mm2, 5),
        cross_section_circular_mils=round(area_cmil, 2),
        fault_current_a=round(fault_current_a, 2),
        pulse_duration_s=round(pulse_duration_s, 4),
        adiabatic_fusing_current_a=round(i_fuse_melt, 2),
        fr4_delamination_current_a=round(i_delam, 2),
        time_to_melt_s=round(t_melt_calc, 4),
        time_to_delamination_s=round(t_delam_calc, 4),
        action_integral_i2t_a2s=round(trace_i2t_delam, 4),
        trace_burnout_risk=burnout_risk,
        coordination_margin_ok=coordination_margin_ok,
        is_safe=is_safe,
        violations=violations,
        recommendations=recommendations,
        standards_cited=standards,
    )
