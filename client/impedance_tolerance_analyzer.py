"""多层板特征阻抗制造公差与灵敏度分析器 (Impedance Tolerance & Sensitivity Analyzer).

工业背景与仿真基准：
- IPC-2141A & Polar Instruments SI9000 制造公差仿真模型：
  在实际 PCB 压合与蚀刻制造过程中，工艺参数均存在公差波动：
  * 介质层厚度 H: 标称 ±10% 压合公差；
  * 走线线宽 W: 标称 ±10% (或 ±0.015mm 侧蚀补偿公差)；
  * 铜厚 T: 标称 ±15% 电镀公差；
  * 介电常数 Er: 标称 ±5% 树脂含量公差。
- 微带线特征阻抗经验解析方程 (IPC-2141A):
  Z0 = (87.0 / sqrt(Er + 1.41)) * ln(5.98 * H / (0.8 * W + T))
- 极差与合格率评估 (Worst-Case & Statistical Tolerance Window):
  * 最佳情况 (Z_min): H_min, W_max, T_max, Er_max
  * 最差情况 (Z_max): H_max, W_min, T_min, Er_min
  * 行业标准要求阻抗波动控制在标称值 ±10% 窗口内 (High-Speed Standard: 50Ω ± 5Ω, 90Ω ± 9Ω)。
    若极差超出 ±10%，将引起严重信号反射、眼图闭合与误码率超标。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ImpedanceToleranceReport:
    target_z0_ohms: float
    nominal_z0_ohms: float
    min_z0_ohms: float
    max_z0_ohms: float
    delta_z0_plus_pct: float
    delta_z0_minus_pct: float
    sensitivity_dZ_dW: float  # Ω/mm 线宽灵敏度导数
    sensitivity_dZ_dH: float  # Ω/mm 介质厚度灵敏度导数
    within_10pct_window: bool
    yield_estimate_pct: float
    ipc_standard: str = "IPC-2141A Controlled Impedance Tolerance Model"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _calc_microstrip_z0(w_mm: float, h_mm: float, t_mm: float, er: float) -> float:
    """IPC-2141A 表面微带线特征阻抗计算。"""
    w = max(0.05, float(w_mm))
    h = max(0.05, float(h_mm))
    t = max(0.01, float(t_mm))
    e = max(1.5, float(er))
    arg = 5.98 * h / (0.8 * w + t)
    if arg <= 1.0:
        arg = 1.05
    z = (87.0 / math.sqrt(e + 1.41)) * math.log(arg)
    return round(z, 2)


def analyze_impedance_tolerance(
    target_z0_ohms: float = 50.0,
    trace_width_mm: float = 0.38,
    dielectric_height_mm: float = 0.20,
    copper_thickness_mm: float = 0.035,
    dielectric_er: float = 4.2,
    width_tolerance_pct: float = 10.0,
    height_tolerance_pct: float = 10.0,
    thickness_tolerance_pct: float = 15.0,
    er_tolerance_pct: float = 5.0,
) -> ImpedanceToleranceReport:
    """执行板厂压合/蚀刻公差叠加下的极值阻抗分析与合格率评估。"""
    w = float(trace_width_mm)
    h = float(dielectric_height_mm)
    t = float(copper_thickness_mm)
    er = float(dielectric_er)

    z_nom = _calc_microstrip_z0(w, h, t, er)

    # 极值条件
    w_min = w * (1.0 - width_tolerance_pct / 100.0)
    w_max = w * (1.0 + width_tolerance_pct / 100.0)
    h_min = h * (1.0 - height_tolerance_pct / 100.0)
    h_max = h * (1.0 + height_tolerance_pct / 100.0)
    t_min = t * (1.0 - thickness_tolerance_pct / 100.0)
    t_max = t * (1.0 + thickness_tolerance_pct / 100.0)
    er_min = er * (1.0 - er_tolerance_pct / 100.0)
    er_max = er * (1.0 + er_tolerance_pct / 100.0)

    z_min = _calc_microstrip_z0(w_max, h_min, t_max, er_max)
    z_max = _calc_microstrip_z0(w_min, h_max, t_min, er_min)

    delta_plus = round(((z_max - z_nom) / z_nom) * 100.0, 1)
    delta_minus = round(((z_nom - z_min) / z_nom) * 100.0, 1)

    # 数值偏导数灵敏度
    dw = 0.01
    dz_dw = (_calc_microstrip_z0(w + dw, h, t, er) - _calc_microstrip_z0(w - dw, h, t, er)) / (2.0 * dw)
    dh = 0.01
    dz_dh = (_calc_microstrip_z0(w, h + dh, t, er) - _calc_microstrip_z0(w, h - dh, t, er)) / (2.0 * dh)

    # ±10% 目标容限检查
    z_target = float(target_z0_ohms)
    dev_target_plus = abs(z_max - z_target) / z_target
    dev_target_minus = abs(z_target - z_min) / z_target
    is_compliant = dev_target_plus <= 0.10 and dev_target_minus <= 0.10

    # 统计合格率估算 (假设正态分布，最坏极值为 3-sigma)
    max_dev = max(dev_target_plus, dev_target_minus)
    if max_dev <= 0.10:
        yield_est = 99.7
    elif max_dev <= 0.12:
        yield_est = 95.0
    elif max_dev <= 0.15:
        yield_est = 85.0
    else:
        yield_est = 65.0

    return ImpedanceToleranceReport(
        target_z0_ohms=z_target,
        nominal_z0_ohms=z_nom,
        min_z0_ohms=z_min,
        max_z0_ohms=z_max,
        delta_z0_plus_pct=delta_plus,
        delta_z0_minus_pct=delta_minus,
        sensitivity_dZ_dW=round(dz_dw, 1),
        sensitivity_dZ_dH=round(dz_dh, 1),
        within_10pct_window=is_compliant,
        yield_estimate_pct=yield_est,
    )
