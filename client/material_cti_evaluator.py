"""IPC-2221B / IEC 62368-1 基材漏电起痕指数 CTI 与安规爬电评定器 (Comparative Tracking Index Evaluator).

工业背景与安规基准：
- IEC 62368-1 / UL 796 / GB 4943.1 / IPC-2221B 绝缘与漏电起痕标准：
  PCB 基板的**相对漏电起痕指数 (Comparative Tracking Index, CTI)** 决定材料组别 (Material Group)：
  * 组别 I (Group I): CTI ≥ 600V (高 CTI 高频/高压特种覆铜板，如生益 S1000-2M CTI 600)；
  * 组别 II (Group II): 400V ≤ CTI < 600V；
  * 组别 IIIa (Group IIIa): 175V ≤ CTI < 400V (标准普通 FR-4 板材，行业普遍 CTI 标称 175V)；
  * 组别 IIIb (Group IIIb): 100V ≤ CTI < 175V。
- 污染等级 (Pollution Degree)：
  * 等级 1: 无污染或仅干燥非导电性污染；
  * 等级 2: 正常室内商用/工业环境，偶见非导电污染或短时结露（标准默认工业基准）；
  * 等级 3: 恶劣工业现场，存在重度粉尘、导电性污染或长期湿气冷凝。
- 安规倍率规律：
  普通 FR-4 (Group IIIa) 在等级 2/3 下所要求的爬电距离几乎是 Group I (高 CTI 600) 的两倍！
  若高压走线空间受限，选用普通 FR-4 将导致安规审查直接判定爬电不足被一票否决。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# IEC 62368-1 Table 25 污染等级 2 下工作有效值电压 vs 各材料组别爬电距离基准 (mm)
CTI_CREEPAGE_PD2_TABLE: list[tuple[float, float, float, float]] = [
    (50.0, 0.60, 0.85, 1.20),
    (100.0, 0.70, 1.00, 1.40),
    (150.0, 0.80, 1.10, 1.60),
    (250.0, 1.25, 1.80, 2.50),
    (300.0, 1.60, 2.20, 3.20),
    (400.0, 2.00, 2.80, 4.00),
    (600.0, 3.20, 4.50, 6.30),
    (1000.0, 5.00, 7.10, 10.00),
]


@dataclass
class MaterialCTIReport:
    working_voltage_v: float
    substrate_cti_v: float
    material_group: str  # "Group I", "Group II", "Group IIIa", "Group IIIb"
    pollution_degree: int  # 1, 2, 3
    insulation_type: str  # "Basic", "Functional", "Reinforced"
    required_creepage_mm: float
    actual_clearance_mm: float
    is_compliant: bool
    safety_margin_pct: float
    recommend_high_cti_laminate: bool
    ipc_standard: str = "IEC 62368-1 Table 25 & IPC-2221B Material Group CTI Criteria"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_material_group(cti_v: float) -> str:
    """按 CTI 电压判定绝缘材料组别。"""
    c = float(cti_v)
    if c >= 600.0:
        return "Group I"
    if c >= 400.0:
        return "Group II"
    if c >= 175.0:
        return "Group IIIa"
    return "Group IIIb"


def evaluate_material_cti_creepage(
    working_voltage_v: float = 220.0,
    actual_clearance_mm: float = 2.0,
    substrate_cti_v: float = 175.0,  # 默认普通 FR-4 CTI 175V
    pollution_degree: int = 2,
    insulation_type: str = "Basic",  # "Basic" 或 "Reinforced" (2倍)
) -> MaterialCTIReport:
    """核算基材 CTI 等级在对应工作电压与污染等级下的安规爬电裕量。"""
    v = abs(float(working_voltage_v))
    dist = max(0.01, float(actual_clearance_mm))
    group = get_material_group(substrate_cti_v)
    pd = 2 if pollution_degree not in (1, 2, 3) else pollution_degree

    # 查询基础爬电距离
    g_idx = 1 if group == "Group I" else (2 if group == "Group II" else 3)
    base_clr = 5.0
    for v_max, g1, g2, g3 in CTI_CREEPAGE_PD2_TABLE:
        if v <= v_max:
            base_clr = (g1, g2, g3)[g_idx - 1]
            break

    # 污染等级与绝缘类型修正
    req = base_clr
    if pd == 1:
        req = req * 0.75
    elif pd == 3:
        req = req * 1.40

    is_reinf = "REINF" in insulation_type.upper()
    if is_reinf:
        req = req * 2.0

    req = round(req, 2)
    compliant = dist >= req
    margin = round(((dist - req) / req) * 100.0, 1)
    need_high_cti = (not compliant) and (group in ("Group IIIa", "Group IIIb"))

    return MaterialCTIReport(
        working_voltage_v=v,
        substrate_cti_v=float(substrate_cti_v),
        material_group=group,
        pollution_degree=pd,
        insulation_type="Reinforced" if is_reinf else "Basic",
        required_creepage_mm=req,
        actual_clearance_mm=dist,
        is_compliant=compliant,
        safety_margin_pct=margin,
        recommend_high_cti_laminate=need_high_cti,
    )
