"""PCB 制造费用估算器 (PCB Fabrication Cost Estimator).

工业背景与计价基准：
- 板厂 (嘉立创/捷多邦/PCBWay) 公开阶梯计价模型：
  1. 基础板费按**层数** (2/4/6 层) 与**数量阶梯** (5/10/30/100 件) 阶梯计价；
  2. 面积超限加价：超过基准面积 (2 层 100×100mm / 4 层 100×100mm) 按 dm² 线性加收；
  3. 板厚选项 (0.6/0.8/1.0/1.2/1.6/2.0mm) —— 非标厚度加收；
  4. 阻焊/丝印颜色：绿色免费，白/黑/蓝/黄/红/哑光 加收；
  5. 表面工艺：HASL 有铅免费 / 沉金 ENIG 加收 / 沉银 / OSP；
  6. 交期：常规 3-4 天免费，加急 24/48h 按比例加收。
- 输出为**估算值** (Estimate)，实际以板厂实时报价为准。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# 基础板费 (CNY, 数量阶梯: 5/10/30/100) —— 公开计价基准估算
BASE_PRICE_CNY: dict[int, tuple[float, float, float, float]] = {
    2: (30.0, 45.0, 90.0, 240.0),        # 双层
    4: (122.0, 150.0, 300.0, 800.0),     # 四层
    6: (320.0, 420.0, 900.0, 2400.0),    # 六层
}
BASE_AREA_MM2 = 100.0 * 100.0  # 基准面积 100×100mm
PRICE_PER_DM2_CNY = {2: 15.0, 4: 40.0, 6: 100.0}  # 超面积每 dm² 加收

SOLDER_MASK_COLORS: dict[str, float] = {
    "green": 0.0, "red": 25.0, "yellow": 25.0, "blue": 25.0,
    "black": 40.0, "white": 40.0, "matte_black": 60.0, "matte_green": 60.0,
}
SURFACE_FINISHES: dict[str, float] = {
    "hasl_lead": 0.0, "hasl_lead_free": 15.0, "enig": 80.0, "osp": 0.0, "silver": 45.0,
}
THICKNESS_SURCHARGE: dict[str, float] = {
    "1.6": 0.0, "0.6": 30.0, "0.8": 20.0, "1.0": 15.0, "1.2": 10.0, "2.0": 35.0,
}
LEAD_TIME_DAYS: dict[str, float] = {"normal": 1.0, "fast_48h": 1.5, "urgent_24h": 2.5}


@dataclass
class FabCostResult:
    layers: int
    quantity: int
    board_width_mm: float
    board_height_mm: float
    area_dm2: float
    base_price_cny: float
    area_surcharge_cny: float
    color_surcharge_cny: float
    surface_surcharge_cny: float
    thickness_surcharge_cny: float
    lead_time_factor: float
    total_cost_cny: float
    unit_cost_cny: float
    breakdown_note: str = "Estimate only — actual price per fab house real-time quote"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_fab_cost(
    layers: int = 4,
    quantity: int = 5,
    board_width_mm: float = 100.0,
    board_height_mm: float = 100.0,
    solder_mask_color: str = "green",
    surface_finish: str = "hasl_lead_free",
    thickness_mm: str = "1.6",
    lead_time: str = "normal",
) -> FabCostResult:
    """按板厂公开阶梯计价模型估算 PCB 制造费用 (估算值)。"""
    n_layers = layers if layers in BASE_PRICE_CNY else 4
    qty_tier_idx = 0 if quantity <= 5 else (1 if quantity <= 10 else (2 if quantity <= 30 else 3))
    qty = max(1, int(quantity))

    base = BASE_PRICE_CNY[n_layers][qty_tier_idx]

    area_mm2 = float(board_width_mm) * float(board_height_mm)
    area_dm2 = area_mm2 / 10000.0  # 1 dm² = 100×100mm
    area_extra_per_pc = max(0.0, area_dm2 - 1.0) * PRICE_PER_DM2_CNY[n_layers]

    color_fee = SOLDER_MASK_COLORS.get(solder_mask_color, 25.0)
    surface_fee = SURFACE_FINISHES.get(surface_finish, 15.0)
    thick_fee = THICKNESS_SURCHARGE.get(str(thickness_mm), 0.0)
    lead_factor = LEAD_TIME_DAYS.get(lead_time, 1.0)

    # base 为该数量档整批总价；超面积加收按每片面积 × 数量；颜色/表面/板厚按订单加收
    total = (base + area_extra_per_pc * qty + color_fee + surface_fee + thick_fee) * lead_factor
    unit = total / qty

    return FabCostResult(
        layers=n_layers,
        quantity=qty,
        board_width_mm=round(float(board_width_mm), 1),
        board_height_mm=round(float(board_height_mm), 1),
        area_dm2=round(area_dm2, 3),
        base_price_cny=round(base, 2),
        area_surcharge_cny=round(area_extra_per_pc * qty, 2),
        color_surcharge_cny=round(color_fee, 2),
        surface_surcharge_cny=round(surface_fee, 2),
        thickness_surcharge_cny=round(thick_fee, 2),
        lead_time_factor=lead_factor,
        total_cost_cny=round(total, 2),
        unit_cost_cny=round(unit, 2),
    )
