"""IPC-2221B / IEC 62368-1 高压安规防爬电隔离铣槽计算器 (Creepage Isolation Slot Calculator).

工业背景与安规标准：
- IPC-2221B Table 6-1 电气间隙 (Clearance) 与爬电距离 (Creepage)：
  强电/弱电高压隔离（如 220V AC 市电输入、24V/48V 工业总线与 3.3V/5V 低压逻辑电路交界处）：
  * 151V ~ 250V: 外层裸露导体要求爬电间隙 ≥ 1.25mm (带防尘涂覆) 或 ≥ 2.5mm (未涂覆)；
  * 251V ~ 500V: 外层裸露导体要求爬电间隙 ≥ 2.5mm；
  * IEC 62368-1 / IEC 60950 强化绝缘 (Reinforced Insulation): 基本爬电距离要求 ≥ 4.0mm ~ 5.0mm。
- 防爬电空气隔离槽 (Air Isolation Slot) 原理：
  当 PCB 布局空间紧凑，两高压导体之间的表面直线距离不足安规要求时，工业标准解法是
  在两焊盘之间开凿贯通的**空气隔离铣槽**（宽 1.0~1.5mm，两端超出导体边缘 ≥ 2.0mm）。
  开槽后表面爬电轨迹被物理切断，绝缘介质转化为空气，爬电路径转化为绕行铣槽边缘的周长路径，
  等效爬电距离大幅提升，满足安规认证审查。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

# IPC-2221B Table 6-1 裸露导体推荐最小爬电距离 (mm)
IPC2221_CREEPAGE_TABLE: list[tuple[float, float]] = [
    (15.0, 0.13),
    (30.0, 0.25),
    (50.0, 0.60),
    (100.0, 0.60),
    (150.0, 0.80),
    (250.0, 1.25),
    (500.0, 2.50),
    (1000.0, 5.00),
]


@dataclass
class CreepageSlotResult:
    voltage_v: float
    required_creepage_mm: float
    direct_surface_dist_mm: float
    is_slot_required: bool
    slot_width_mm: float
    slot_length_mm: float
    slot_start: tuple[float, float]
    slot_end: tuple[float, float]
    effective_creepage_with_slot_mm: float
    is_compliant: bool
    ipc_standard: str = "IPC-2221B Table 6-1 / IEC 62368-1 Air Isolation Slot"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_required_creepage(voltage_v: float, is_reinforced: bool = False) -> float:
    """根据工作电压查询 IPC-2221B / IEC 62368-1 最小爬电要求 (mm)。"""
    v = abs(float(voltage_v))
    req = 5.0
    for max_v, clr in IPC2221_CREEPAGE_TABLE:
        if v <= max_v:
            req = clr
            break
    if is_reinforced:
        req = max(req * 2.0, 4.0)
    return req


def calculate_creepage_isolation_slot(
    voltage_v: float,
    cond1_coords: tuple[float, float],
    cond2_coords: tuple[float, float],
    conductor_radius_mm: float = 1.0,
    slot_width_mm: float = 1.2,
    slot_extension_mm: float = 2.0,
    is_reinforced_insulation: bool = False,
) -> CreepageSlotResult:
    """计算高压爬电距离是否超标，并在必要时规划垂直贯通空气隔离铣槽。"""
    req_creepage = get_required_creepage(voltage_v, is_reinforced=is_reinforced_insulation)

    x1, y1 = cond1_coords
    x2, y2 = cond2_coords
    center_dist = math.hypot(x2 - x1, y2 - y1)
    direct_dist = max(0.0, center_dist - 2.0 * conductor_radius_mm)

    is_slot_needed = direct_dist < req_creepage

    # 铣槽中心垂直平分线
    mid_x = (x1 + x2) / 2.0
    mid_y = (y1 + y2) / 2.0

    dx = x2 - x1
    dy = y2 - y1
    if center_dist > 0:
        ux = dx / center_dist
        uy = dy / center_dist
    else:
        ux, uy = 1.0, 0.0

    # 垂直法向向量
    nx = -uy
    ny = ux

    # 铣槽长度覆盖两导体并外延
    slot_half_len = conductor_radius_mm + slot_extension_mm
    total_slot_len = round(2.0 * slot_half_len, 2)

    s_start = (round(mid_x - slot_half_len * nx, 2), round(mid_y - slot_half_len * ny, 2))
    s_end = (round(mid_x + slot_half_len * nx, 2), round(mid_y + slot_half_len * ny, 2))

    # 绕槽边缘等效爬电路径：绕行铣槽两端的周长
    # Path ≈ 2 * sqrt((center_dist/2)^2 + (slot_half_len)^2)
    effective_creepage = round(2.0 * math.hypot(center_dist / 2.0, slot_half_len) - 2.0 * conductor_radius_mm, 2)
    compliant = effective_creepage >= req_creepage if is_slot_needed else (direct_dist >= req_creepage)

    return CreepageSlotResult(
        voltage_v=float(voltage_v),
        required_creepage_mm=round(req_creepage, 2),
        direct_surface_dist_mm=round(direct_dist, 2),
        is_slot_required=is_slot_needed,
        slot_width_mm=float(slot_width_mm) if is_slot_needed else 0.0,
        slot_length_mm=total_slot_len if is_slot_needed else 0.0,
        slot_start=s_start if is_slot_needed else (0.0, 0.0),
        slot_end=s_end if is_slot_needed else (0.0, 0.0),
        effective_creepage_with_slot_mm=effective_creepage if is_slot_needed else round(direct_dist, 2),
        is_compliant=compliant,
    )
