"""SMT/THT 混装装配工艺路线规划器 (Assembly Process Route Planner).

工业背景与工艺基准：
- EMS 代工厂 (Foxconn / Jabil / JLC SMT) 标准 PCBA 工艺路线 (Routing)：
  根据每个器件的封装类型将其分配到对应工序，并输出整板工序序列：
  1. SPI 锡膏检测 → 2. SMT 回流焊 (SMD 器件) → 3. AOI 光学检测 →
  4. THT 插件 (AI/手动) → 5. 波峰焊 / 选择焊 (THT 器件) → 6. 手工补焊 →
  7. ICT 在线测试 → 8. FCT 功能测试 → 9. 三防涂覆 (可选) → 10. 包装出货。
- 器件工序分类规则：
  * THT_WAVE: DIP / TO-220 / Radial / PinHeader / Terminal / Relay 等 → 波峰焊
    （波峰焊适配性受高度、耐温、遮蔽效应约束——IPC-A-610G §7）；
  * THT_MANUAL: 大体积电解电容 / 散热器 / 变压器 等 → 手工焊（波峰热冲击过大）；
  * SMD_REFLOW: 其余表面贴装 → 回流焊 (Profile 按 Pb-free 235~250°C)；
  * MECHANICAL: 安装孔 / 支撑柱 / 铆钉 → 装配工序，不参与焊接。
- 混装板需评估二次回流风险：底面 SMD 需 Red Glue 点胶波峰或第二面回流排程。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

THT_WAVE_PATTERNS = re.compile(r"(DIP|TO-?220|TO-?247|TO-?92|RADIAL|PINHEADER|PIN-?HEADER|TERMINAL|RELAY|SCREW)", re.IGNORECASE)
THT_MANUAL_PATTERNS = re.compile(r"(HEATSINK|HEAT-?SINK|TRANSFORMER|ELECTROLYTIC-D|SNAPIN|SNAP-IN|POWER-MODULE)", re.IGNORECASE)
MECHANICAL_PATTERNS = re.compile(r"(MOUNT|HOLE|STANDOFF|RIVET|SCREW-BOSS)", re.IGNORECASE)

PROCESS_STAGES = [
    "SPI (锡膏检测)",
    "SMT Reflow (SMD 回流焊)",
    "AOI (炉后光学检测)",
    "THT Insert (插件)",
    "Wave / Selective Solder (波峰/选择焊)",
    "Manual Soldering (手工补焊)",
    "ICT (在线测试)",
    "FCT (功能测试)",
    "Conformal Coating (三防涂覆, 可选)",
    "Packing (包装)",
]


@dataclass
class ComponentRoute:
    ref: str
    package: str
    process: str  # "SMD_REFLOW" / "THT_WAVE" / "THT_MANUAL" / "MECHANICAL"
    stage: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessPlanReport:
    total_components: int
    smd_count: int
    tht_wave_count: int
    tht_manual_count: int
    mechanical_count: int
    is_mixed_assembly: bool
    stages: list[str] = field(default_factory=lambda: list(PROCESS_STAGES))
    routes: list[ComponentRoute] = field(default_factory=list)
    ipc_standard: str = "IPC-A-610G Section 7 / EMS Standard Routing"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_components": self.total_components,
            "smd_count": self.smd_count,
            "tht_wave_count": self.tht_wave_count,
            "tht_manual_count": self.tht_manual_count,
            "mechanical_count": self.mechanical_count,
            "is_mixed_assembly": self.is_mixed_assembly,
            "stages": self.stages,
            "routes": [r.to_dict() for r in self.routes],
        }


def _classify(package: str, kind: str, value: str = "") -> tuple[str, str, str]:
    """返回 (process, stage, notes)。"""
    pkg = str(package)
    k = str(kind).upper()
    v = str(value).upper()
    if MECHANICAL_PATTERNS.search(pkg) or k in ("MOUNT_HOLE", "HOLE", "STANDOFF"):
        return "MECHANICAL", "Assembly (机械装配)", "不参与焊接工序"
    if THT_MANUAL_PATTERNS.search(pkg) or "ELECTROLYTIC" in k or "ELECTROLYTIC" in v:
        return "THT_MANUAL", "Manual Soldering (手工补焊)", "大体积/热敏感件波峰热冲击过大，手工焊接"
    if THT_WAVE_PATTERNS.search(pkg):
        return "THT_WAVE", "Wave / Selective Solder (波峰/选择焊)", "通孔件波峰焊，注意遮蔽效应与元件高度"
    return "SMD_REFLOW", "SMT Reflow (SMD 回流焊)", "Pb-free 回流 235~250°C"


def generate_assembly_process_plan(modules: dict[str, dict]) -> ProcessPlanReport:
    """为每个器件分配工序并输出整板工艺路线 (Routing)。"""
    routes: list[ComponentRoute] = []
    counts = {"SMD_REFLOW": 0, "THT_WAVE": 0, "THT_MANUAL": 0, "MECHANICAL": 0}

    for ref, m in sorted((modules or {}).items()):
        if ref == "__meta__":
            continue
        pkg = str(m.get("package", ""))
        kind = str(m.get("kind", ""))
        val = str(m.get("value", ""))
        process, stage, notes = _classify(pkg, kind, val)
        counts[process] += 1
        routes.append(ComponentRoute(ref=ref, package=pkg, process=process, stage=stage, notes=notes))

    mixed = counts["SMD_REFLOW"] > 0 and (counts["THT_WAVE"] + counts["THT_MANUAL"]) > 0
    return ProcessPlanReport(
        total_components=len(routes),
        smd_count=counts["SMD_REFLOW"],
        tht_wave_count=counts["THT_WAVE"],
        tht_manual_count=counts["THT_MANUAL"],
        mechanical_count=counts["MECHANICAL"],
        is_mixed_assembly=mixed,
        routes=routes,
    )
