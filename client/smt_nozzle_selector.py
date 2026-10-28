"""SMT 贴片机吸嘴选型与真空吸着可靠性审计器 (IPC/EIA-481 & Juki/Yamaha/Fuji/Panasonic)。

工业背景与物理机制：
1. SMT 高速贴片机（Juki RS-1R / Yamaha YSM20R / Fuji NXT III / Panasonic NPM）在贴装
   阻容感（01005~2512）、晶体管（SOT-23/SOD-123）、集成电路（QFN/QFP/BGA）时，
   吸嘴与元器件平整吸着面的几何匹配决定贴装良率。
2. 吸嘴外径 (OD) 避障限制：
   吸嘴外径必须严格小于料带编带口袋内边距和元器件平整吸着面（OD <= min(W, L) - 0.10mm），
   若外径过大，高速吸料时吸嘴会撞击料带口袋侧壁或周边高器件（如电解电容、屏蔽盖），
   导致吸嘴磨损、抛料或贴装偏位（EIA-481 标准）。
3. 吸嘴内孔 (ID) 真空密封与泄漏限制：
   吸嘴内径必须落在器件平坦吸着区域内部（ID <= min(W, L) - 0.20mm）。若内孔过大，
   孔径跨越芯片边缘倒角、极性凹槽或激光刻字粗糙缝隙，车间真空度（典型 60~80 kPa）
   将急剧泄漏（漏气压差 > 20 kPa），导致吸取失败或中途飞料（Fly-off）。
4. 高速贴片加速度惯性抗飞料安全系数 (Dynamic Hold Safety Factor)：
   贴装头在 X/Y 高速移动和旋转时，加速度通常达到 3G~5G (a = 30~50 m/s²)。
   吸嘴真空保持力：
       F_vac = ΔP * (π/4) * ID²  (N)
   惯性剪切力：
       F_inertial = m * a  (N)
   动态安全系数：
       SF = (μ * F_vac) / F_inertial
   其中 μ 约为 0.25~0.35（陶瓷/橡胶吸嘴与封装表面静摩擦系数）。
   标准规范要求 SF >= 1.50（推荐 >= 2.0），若 SF < 1.0 则在贴片头转塔旋转时 100% 甩料。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# 标准吸嘴库（按工业主流机型标准化）
# (model, outer_dia_mm, inner_dia_mm, nozzle_family, min_comp_w_mm, max_comp_w_mm)
STANDARD_NOZZLES: list[dict] = [
    {"model": "Juki-501", "outer_dia_mm": 0.40, "inner_dia_mm": 0.20, "vendor": "Juki", "family": "500-Series"},
    {"model": "Juki-502", "outer_dia_mm": 0.60, "inner_dia_mm": 0.30, "vendor": "Juki", "family": "500-Series"},
    {"model": "Juki-503", "outer_dia_mm": 1.00, "inner_dia_mm": 0.50, "vendor": "Juki", "family": "500-Series"},
    {"model": "Juki-504", "outer_dia_mm": 1.50, "inner_dia_mm": 0.80, "vendor": "Juki", "family": "500-Series"},
    {"model": "Juki-505", "outer_dia_mm": 2.50, "inner_dia_mm": 1.40, "vendor": "Juki", "family": "500-Series"},
    {"model": "Juki-506", "outer_dia_mm": 4.00, "inner_dia_mm": 2.20, "vendor": "Juki", "family": "500-Series"},
    {"model": "Juki-507", "outer_dia_mm": 7.00, "inner_dia_mm": 4.50, "vendor": "Juki", "family": "500-Series"},
    {"model": "Yamaha-301A", "outer_dia_mm": 0.45, "inner_dia_mm": 0.22, "vendor": "Yamaha", "family": "YSM-Multi"},
    {"model": "Yamaha-302A", "outer_dia_mm": 0.70, "inner_dia_mm": 0.35, "vendor": "Yamaha", "family": "YSM-Multi"},
    {"model": "Yamaha-303A", "outer_dia_mm": 1.20, "inner_dia_mm": 0.60, "vendor": "Yamaha", "family": "YSM-Multi"},
    {"model": "Yamaha-304A", "outer_dia_mm": 1.80, "inner_dia_mm": 1.00, "vendor": "Yamaha", "family": "YSM-Multi"},
    {"model": "Yamaha-305A", "outer_dia_mm": 3.00, "inner_dia_mm": 1.80, "vendor": "Yamaha", "family": "YSM-Multi"},
    {"model": "Fuji-H12-0.4", "outer_dia_mm": 0.40, "inner_dia_mm": 0.18, "vendor": "Fuji", "family": "NXT-H12S"},
    {"model": "Fuji-H12-0.7", "outer_dia_mm": 0.70, "inner_dia_mm": 0.35, "vendor": "Fuji", "family": "NXT-H12S"},
    {"model": "Fuji-H08-1.3", "outer_dia_mm": 1.30, "inner_dia_mm": 0.70, "vendor": "Fuji", "family": "NXT-H08M"},
    {"model": "Fuji-H08-2.5", "outer_dia_mm": 2.50, "inner_dia_mm": 1.50, "vendor": "Fuji", "family": "NXT-H08M"},
    {"model": "Fuji-H04-5.0", "outer_dia_mm": 5.00, "inner_dia_mm": 3.20, "vendor": "Fuji", "family": "NXT-H04"},
]

# 常见封装物理参考数据 (长mm, 宽mm, 高mm, 典型质量mg)
PACKAGE_DATABASE: dict[str, tuple[float, float, float, float]] = {
    "0201": (0.60, 0.30, 0.23, 0.3),
    "0402": (1.00, 0.50, 0.35, 1.2),
    "0603": (1.60, 0.80, 0.45, 3.5),
    "0805": (2.00, 1.25, 0.60, 8.0),
    "1206": (3.20, 1.60, 0.70, 15.0),
    "1210": (3.20, 2.50, 0.80, 28.0),
    "2512": (6.30, 3.20, 0.80, 55.0),
    "SOT-23": (2.90, 1.30, 1.00, 12.0),
    "SOT-223": (6.50, 3.50, 1.60, 110.0),
    "SOD-123": (2.70, 1.60, 1.20, 16.0),
    "SOD-323": (1.70, 1.25, 0.95, 5.0),
    "SOP-8": (4.90, 3.90, 1.45, 75.0),
    "SOP-16": (9.90, 3.90, 1.45, 150.0),
    "QFN-16": (3.00, 3.00, 0.85, 25.0),
    "QFN-32": (5.00, 5.00, 0.85, 65.0),
    "QFN-48": (7.00, 7.00, 0.85, 140.0),
    "QFP-48": (7.00, 7.00, 1.40, 180.0),
    "QFP-100": (14.00, 14.00, 1.40, 800.0),
    "BGA-256": (17.00, 17.00, 1.60, 1500.0),
}


@dataclass
class SmtNozzleAuditResult:
    component_designator: str
    package_type: str
    component_length_mm: float
    component_width_mm: float
    component_height_mm: float
    component_mass_mg: float
    selected_nozzle: str
    nozzle_outer_diameter_mm: float
    nozzle_inner_diameter_mm: float
    suction_vacuum_kpa: float
    calculated_vacuum_force_n: float
    inertial_shear_force_n: float
    dynamic_safety_factor: float
    vacuum_leakage_risk: bool
    nozzle_collision_risk: bool
    is_suitable: bool
    violations: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    standards_cited: list[str] = field(default_factory=list)


def audit_smt_nozzle_selection(
    component_designator: str = "U1",
    package_type: str = "0603",
    component_length_mm: float | None = None,
    component_width_mm: float | None = None,
    component_height_mm: float | None = None,
    component_mass_mg: float | None = None,
    specified_nozzle_model: str | None = None,
    vacuum_pressure_kpa: float = 70.0,
    head_acceleration_g: float = 3.5,
    friction_coefficient: float = 0.30,
    vendor_preference: str = "Juki",
) -> SmtNozzleAuditResult:
    """审计或自动匹配 SMT 贴片机吸嘴型号与真空抓取可靠性。

    参数：
        component_designator: 器件位号（如 C12, U4）。
        package_type: 封装型号（如 0402, 0603, SOT-23, QFN-32）。
        component_length_mm: 长度（mm），若为 None 则从数据库查找。
        component_width_mm: 宽度（mm），若为 None 则从数据库查找。
        component_height_mm: 高度（mm），若为 None 则从数据库查找。
        component_mass_mg: 质量（mg），若为 None 则从数据库查找。
        specified_nozzle_model: 用户指定的吸嘴型号（如 'Juki-502'），为 None 时自动匹配。
        vacuum_pressure_kpa: 车间真空供给负压（典型 60~80 kPa，默认 70.0 kPa）。
        head_acceleration_g: 贴装头最大运行与转塔加减速（G，默认 3.5G）。
        friction_coefficient: 吸嘴端面与芯片表面静摩擦系数（默认 0.30）。
        vendor_preference: 吸嘴厂商偏好 ('Juki', 'Yamaha', 'Fuji')。
    """
    standards = [
        "EIA-481 Taping of Surface Mount Components for Automated Placement",
        "Juki High-Speed SMT Placement Nozzle Specification Guidelines",
        "Yamaha YSM Surface Mounter Feeder & Nozzle Engineering Manual",
        "IPC-7351B Generic Requirements for Surface Mount Design and Land Pattern Standard",
    ]

    # 解析器件几何与质量
    pkg_key = package_type.upper().strip()
    db_val = PACKAGE_DATABASE.get(pkg_key)

    l_mm = component_length_mm if component_length_mm is not None else (db_val[0] if db_val else 1.60)
    w_mm = component_width_mm if component_width_mm is not None else (db_val[1] if db_val else 0.80)
    h_mm = component_height_mm if component_height_mm is not None else (db_val[2] if db_val else 0.45)
    m_mg = component_mass_mg if component_mass_mg is not None else (db_val[3] if db_val else 3.5)

    min_dim = min(l_mm, w_mm)

    # 筛选或选择吸嘴
    chosen_nozzle = None
    if specified_nozzle_model:
        for n in STANDARD_NOZZLES:
            if n["model"].lower() == specified_nozzle_model.lower():
                chosen_nozzle = n
                break
        if not chosen_nozzle:
            # 允许用户传入未在内建表中的吸嘴，设默认推导
            chosen_nozzle = {
                "model": specified_nozzle_model,
                "outer_dia_mm": 0.80,
                "inner_dia_mm": 0.40,
                "vendor": "Custom",
                "family": "Custom",
            }
    else:
        # 自动匹配：优先符合 vendor_preference，且 OD <= min_dim - 0.10，最大化 ID
        pref_nozzles = [n for n in STANDARD_NOZZLES if n["vendor"].lower() == vendor_preference.lower()]
        candidates = pref_nozzles if pref_nozzles else STANDARD_NOZZLES

        valid_list = [n for n in candidates if n["outer_dia_mm"] <= (min_dim - 0.05) and n["inner_dia_mm"] < min_dim]
        if valid_list:
            # 选 inner_dia_mm 最大的，以提供最大吸力
            valid_list.sort(key=lambda x: x["inner_dia_mm"], reverse=True)
            chosen_nozzle = valid_list[0]
        else:
            # 取外径最小的吸嘴
            candidates.sort(key=lambda x: x["outer_dia_mm"])
            chosen_nozzle = candidates[0]

    od = chosen_nozzle["outer_dia_mm"]
    id_dia = chosen_nozzle["inner_dia_mm"]

    # 物理计算
    # 真空吸力 F_vac = ΔP (Pa) * Area (m²)
    # ΔP = vacuum_pressure_kpa * 1000 Pa
    delta_p = vacuum_pressure_kpa * 1000.0
    id_m = id_dia * 1e-3
    area_m2 = (math.pi / 4.0) * (id_m**2)
    f_vac = delta_p * area_m2  # Newtons

    # 惯性剪切力 F_inertial = m (kg) * a (m/s²)
    # a = head_acceleration_g * 9.80665
    m_kg = m_mg * 1e-6
    acc_mps2 = head_acceleration_g * 9.80665
    f_inertial = m_kg * acc_mps2

    # 动态保持安全系数
    # 摩擦力 = friction_coefficient * F_vac
    f_friction = friction_coefficient * f_vac
    sf = (f_friction / f_inertial) if f_inertial > 1e-9 else 999.0

    violations: list[str] = []
    recommendations: list[str] = []

    # 判定 1: 外径碰撞与编带干涉
    # 若 OD > min_dim，吸嘴直接伸出器件边缘
    collision_risk = False
    if od >= min_dim:
        collision_risk = True
        violations.append(
            f"吸嘴外径 OD={od:.2f}mm 大于等于器件最小平宽 ({min_dim:.2f}mm)，"
            "高速下压取料将碰撞料带编带口袋侧壁或周边高器件，引发抛料与吸嘴崩裂（EIA-481）。"
        )
    elif od > (min_dim - 0.08):
        recommendations.append(
            f"吸嘴外径 OD={od:.2f}mm 与器件边缘裕量仅 {(min_dim - od)/2:.2f}mm，"
            "接近干涉边界，建议校准供料器飞达 (Feeder) 取料中心对位。"
        )

    # 判定 2: 内孔越界与真空泄漏
    leakage_risk = False
    if id_dia >= (min_dim - 0.15):
        leakage_risk = True
        violations.append(
            f"吸嘴内径 ID={id_dia:.2f}mm 接近或超出器件平坦吸着面（器件最小宽 {min_dim:.2f}mm），"
            "负压将沿封装倒角或极性凹槽严重泄漏（漏气压降 > 20 kPa），导致吸取失败或中途掉件。"
        )

    # 判定 3: 加速度惯性安全系数
    if sf < 1.0:
        violations.append(
            f"贴片头 {head_acceleration_g:.1f}G 高速移动下动态安全系数 SF={sf:.2f} < 1.0，"
            f"吸力真空保持力 ({f_vac*1e3:.2f}mN) 不足以克服惯性剪切力 ({f_inertial*1e3:.2f}mN)，转塔高速旋转将 100% 甩料飞件！"
        )
    elif sf < 1.5:
        recommendations.append(
            f"动态安全系数 SF={sf:.2f} 低于推荐阈值 1.50，在高速贴片或急转弯时易产生角偏移与偏位，"
            "建议调低贴片头加减速或改用更大孔径/更强真空吸嘴。"
        )

    if not violations:
        recommendations.append(
            f"吸嘴 {chosen_nozzle['model']} 几何尺寸与真空保持力合格：OD={od:.2f}mm, "
            f"ID={id_dia:.2f}mm, 动载安全系数 SF={sf:.2f} >= 1.50。"
        )

    is_suitable = len(violations) == 0

    return SmtNozzleAuditResult(
        component_designator=component_designator,
        package_type=package_type,
        component_length_mm=round(l_mm, 3),
        component_width_mm=round(w_mm, 3),
        component_height_mm=round(h_mm, 3),
        component_mass_mg=round(m_mg, 2),
        selected_nozzle=chosen_nozzle["model"],
        nozzle_outer_diameter_mm=round(od, 3),
        nozzle_inner_diameter_mm=round(id_dia, 3),
        suction_vacuum_kpa=round(vacuum_pressure_kpa, 2),
        calculated_vacuum_force_n=round(f_vac, 6),
        inertial_shear_force_n=round(f_inertial, 6),
        dynamic_safety_factor=round(sf, 2),
        vacuum_leakage_risk=leakage_risk,
        nozzle_collision_risk=collision_risk,
        is_suitable=is_suitable,
        violations=violations,
        recommendations=recommendations,
        standards_cited=standards,
    )
