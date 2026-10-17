"""PCB 板厂工艺极限能力档案库与 DFM 硬公差审查器 (PCB Fab House Capabilities & DFM Limit Checker).

工业背景与制造能力基准：
- 面向真实 macOS 个人开发者与外部 Linux CI/CD 流水线：
  开发者在将设计送板厂打样时，若线宽/间距/过孔钻径超出了板厂的基础工艺能力范围，
  板厂在工程预审 (CAM EQ, Engineering Query) 阶段会直接驳回订单，
  导致交期延误数天甚至产生高额的高精度制程溢价 (Advanced Capability Surcharge)。
- 全球四大知名板厂工艺能力矩阵 (公开制造规格)：
  1. JLCPCB (嘉立创):
     - Standard Tier (免费基础工艺): 线宽/线距 >= 0.09mm (3.5mil 4层板), 过孔钻孔 >= 0.20mm (盘径 >= 0.45mm), 最小机械槽宽 >= 0.6mm;
     - Advanced Tier: 线宽/线距 >= 0.075mm (3.0mil), 过孔钻孔 >= 0.15mm;
  2. PCBWay:
     - Standard: 线宽/线距 >= 0.10mm (4.0mil), 最小钻孔 >= 0.20mm;
     - Advanced: 线宽/线距 >= 0.075mm (3.0mil), 最小钻孔 >= 0.15mm;
  3. OSH Park (北美高星开源硬件常用):
     - 2-layer / 4-layer: 线宽/线距 >= 5.0mil (0.127mm), 最小钻孔 >= 10.0mil (0.254mm);
  4. Eurocircuits (欧洲高可靠性标杆):
     - Standard: 线宽/线距 >= 0.10mm (4.0mil), 最小外层孔环 >= 0.125mm.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FabCapabilityProfile:
    fab_id: str
    fab_name: str
    tier: str  # "standard" or "advanced"
    min_trace_width_mm: float
    min_trace_clearance_mm: float
    min_via_drill_mm: float
    min_via_pad_mm: float
    min_annular_ring_mm: float
    max_aspect_ratio: float
    min_mechanical_slot_width_mm: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FAB_PROFILES: dict[str, FabCapabilityProfile] = {
    "jlcpcb_standard": FabCapabilityProfile(
        fab_id="jlcpcb_standard",
        fab_name="JLCPCB (嘉立创标准工艺)",
        tier="standard",
        min_trace_width_mm=0.090,  # 3.5 mil
        min_trace_clearance_mm=0.090,
        min_via_drill_mm=0.200,
        min_via_pad_mm=0.450,
        min_annular_ring_mm=0.125,
        max_aspect_ratio=8.0,
        min_mechanical_slot_width_mm=0.600,
        source="JLCPCB Manufacturing Capabilities (Multi-layer Standard Tier)",
    ),
    "jlcpcb_advanced": FabCapabilityProfile(
        fab_id="jlcpcb_advanced",
        fab_name="JLCPCB (嘉立创高精高密工艺)",
        tier="advanced",
        min_trace_width_mm=0.075,  # 3.0 mil
        min_trace_clearance_mm=0.075,
        min_via_drill_mm=0.150,
        min_via_pad_mm=0.350,
        min_annular_ring_mm=0.100,
        max_aspect_ratio=10.0,
        min_mechanical_slot_width_mm=0.500,
        source="JLCPCB Advanced Capability Table",
    ),
    "pcbway_standard": FabCapabilityProfile(
        fab_id="pcbway_standard",
        fab_name="PCBWay (标准工艺)",
        tier="standard",
        min_trace_width_mm=0.100,  # 4.0 mil
        min_trace_clearance_mm=0.100,
        min_via_drill_mm=0.200,
        min_via_pad_mm=0.450,
        min_annular_ring_mm=0.125,
        max_aspect_ratio=8.0,
        min_mechanical_slot_width_mm=0.800,
        source="PCBWay Standard PCB Capabilities",
    ),
    "oshpark_standard": FabCapabilityProfile(
        fab_id="oshpark_standard",
        fab_name="OSH Park (North America Open Hardware)",
        tier="standard",
        min_trace_width_mm=0.127,  # 5.0 mil
        min_trace_clearance_mm=0.127,
        min_via_drill_mm=0.254,  # 10 mil
        min_via_pad_mm=0.508,
        min_annular_ring_mm=0.127,
        max_aspect_ratio=7.0,
        min_mechanical_slot_width_mm=1.000,
        source="OSH Park Design Specs & Rules",
    ),
}


@dataclass
class FabCapabilityViolation:
    parameter: str
    actual_value_mm: float
    limit_value_mm: float
    description: str


@dataclass
class FabCapabilityAuditReport:
    fab_id: str
    fab_name: str
    tier: str
    is_compliant: bool
    violations_count: int
    violations: list[FabCapabilityViolation] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    ipc_standard: str = "IPC-6012 Class 2 / Fab House Capabilities Spec"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["violations"] = [asdict(v) for v in self.violations]
        return d


def audit_fab_capabilities(
    fab_id: str = "jlcpcb_standard",
    min_trace_width_mm: float = 0.127,
    min_trace_clearance_mm: float = 0.127,
    min_via_drill_mm: float = 0.200,
    min_via_pad_mm: float = 0.450,
    board_thickness_mm: float = 1.600,
    min_slot_width_mm: float = 0.800,
) -> FabCapabilityAuditReport:
    """根据指定板厂工艺能力档案核对设计硬指标是否达标。"""
    fab = FAB_PROFILES.get(fab_id.lower().strip(), FAB_PROFILES["jlcpcb_standard"])
    violations: list[FabCapabilityViolation] = []
    recs: list[str] = []

    # 1. 线宽
    if min_trace_width_mm < fab.min_trace_width_mm:
        violations.append(
            FabCapabilityViolation(
                parameter="trace_width",
                actual_value_mm=round(min_trace_width_mm, 4),
                limit_value_mm=fab.min_trace_width_mm,
                description=f"最小线宽 {min_trace_width_mm}mm < {fab.fab_name} 下限 {fab.min_trace_width_mm}mm",
            )
        )
        recs.append(f"将细走线加粗至 ≥ {fab.min_trace_width_mm}mm，或切换至 Advanced 高密工艺档")

    # 2. 线距
    if min_trace_clearance_mm < fab.min_trace_clearance_mm:
        violations.append(
            FabCapabilityViolation(
                parameter="trace_clearance",
                actual_value_mm=round(min_trace_clearance_mm, 4),
                limit_value_mm=fab.min_trace_clearance_mm,
                description=f"最小线距 {min_trace_clearance_mm}mm < {fab.fab_name} 下限 {fab.min_trace_clearance_mm}mm",
            )
        )
        recs.append(f"调整导体间距至 ≥ {fab.min_trace_clearance_mm}mm 以避免蚀刻桥连短路")

    # 3. 过孔孔径
    if min_via_drill_mm < fab.min_via_drill_mm:
        violations.append(
            FabCapabilityViolation(
                parameter="via_drill",
                actual_value_mm=round(min_via_drill_mm, 4),
                limit_value_mm=fab.min_via_drill_mm,
                description=f"最小过孔钻孔 {min_via_drill_mm}mm < {fab.fab_name} 下限 {fab.min_via_drill_mm}mm",
            )
        )
        recs.append(f"过孔机械钻孔孔径放大至 ≥ {fab.min_via_drill_mm}mm，否则需使用激光微孔打孔")

    # 4. 孔环
    annular = (min_via_pad_mm - min_via_drill_mm) / 2.0
    if annular < fab.min_annular_ring_mm:
        violations.append(
            FabCapabilityViolation(
                parameter="annular_ring",
                actual_value_mm=round(annular, 4),
                limit_value_mm=fab.min_annular_ring_mm,
                description=f"过孔焊环单边宽度 {annular:.3f}mm < 要求的 {fab.min_annular_ring_mm}mm",
            )
        )
        recs.append("增大过孔外径焊盘以提供足够的机械对准焊环")

    # 5. 深径比
    if min_via_drill_mm > 0:
        aspect = board_thickness_mm / min_via_drill_mm
        if aspect > fab.max_aspect_ratio:
            violations.append(
                FabCapabilityViolation(
                    parameter="aspect_ratio",
                    actual_value_mm=round(aspect, 2),
                    limit_value_mm=fab.max_aspect_ratio,
                    description=f"钻孔深径比 {aspect:.1f}:1 > 板厂电镀极限 {fab.max_aspect_ratio:.0f}:1",
                )
            )
            recs.append("增加过孔孔径或减小板厚以确保孔壁充分沉铜")

    # 6. 机械槽宽
    if min_slot_width_mm < fab.min_mechanical_slot_width_mm:
        violations.append(
            FabCapabilityViolation(
                parameter="mechanical_slot_width",
                actual_value_mm=round(min_slot_width_mm, 4),
                limit_value_mm=fab.min_mechanical_slot_width_mm,
                description=f"机械铣槽宽度 {min_slot_width_mm}mm < 最小成型刀具直径 {fab.min_mechanical_slot_width_mm}mm",
            )
        )
        recs.append(f"扩大成型铣槽宽度至 ≥ {fab.min_mechanical_slot_width_mm}mm")

    is_ok = len(violations) == 0
    return FabCapabilityAuditReport(
        fab_id=fab.fab_id,
        fab_name=fab.fab_name,
        tier=fab.tier,
        is_compliant=is_ok,
        violations_count=len(violations),
        violations=violations,
        recommendations=recs,
    )
