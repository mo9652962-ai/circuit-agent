"""SMT 贴片机吸嘴碰撞与高器件净空分析器 (SMT Nozzle Z-Clearance & Height Envelope Analyzer).

工业背景与工艺标准：
- IPC-SM-782 / OpenPnP / Yamaha / Panasonic 表面贴装工艺规范：
  在高速自动化贴片生产线中，贴片机吸嘴（Nozzle Body）在高速贴装微小无源件（0402/0603/0805，
  高度 ≤ 1.5mm）时，若紧邻位置已贴装大体积高元器件（如电解电容、变压器、排针、功率电感，
  高度 ≥ 4.0mm），吸嘴锥形外壁（Nozzle Outer Diameter）在下压冲程中极易与相邻高元件发生
  机械碰撞击碎元件或产生贴装偏位（Placement Shift / Head Crash）。
- 工艺规范与贴装时序优化：
  1. 高度分层原则：贴装序列必须严格遵循「由矮到高」原则（矮件第一阶梯先贴，高件最后贴装）；
  2. 净空禁布区（Clearance Keepout Envelope）：高差 ΔH ≥ 3.0mm 的相邻元件，
     水平边缘间距必须满足 D ≥ 2.0mm（满足吸嘴锥形外壁下压通道）；
  3. 风险预警：水平间距 < 2.0mm 的高矮元件对直接标记为 COLLISION_RISK。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

# 默认元件典型高度估算 (mm)
PACKAGE_HEIGHT_ESTIMATES_MM: dict[str, float] = {
    "0402": 0.5,
    "0603": 0.8,
    "0805": 1.25,
    "1206": 1.6,
    "SOT-23": 1.1,
    "SOT-223": 1.7,
    "SOIC-8": 1.75,
    "QFN-32": 0.9,
    "LQFP-48": 1.4,
    "BGA-64": 1.2,
    "ELECTROLYTIC-D8": 10.5,
    "TRANSFORMER": 12.0,
    "RELAY": 15.0,
    "PINHEADER": 8.5,
    "TERMINAL": 10.0,
    "TYPE-C": 3.2,
}


@dataclass
class CollisionPair:
    low_ref: str
    high_ref: str
    low_height_mm: float
    high_height_mm: float
    height_delta_mm: float
    center_dist_mm: float
    is_collision_risk: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SMTPlacementClearanceReport:
    total_components: int
    low_components_count: int  # H <= 2.0mm
    medium_components_count: int  # 2.0 < H <= 4.0mm
    tall_components_count: int  # H > 4.0mm
    collision_risks_count: int
    placement_priority_layers: list[list[str]] = field(default_factory=list)
    collision_pairs: list[CollisionPair] = field(default_factory=list)
    ipc_standard: str = "IPC-SM-782 / OpenPnP Placement Sequence Guidance"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["collision_pairs"] = [p.to_dict() for p in self.collision_pairs]
        return d


def _estimate_height(m: dict) -> float:
    if "height_mm" in m:
        return float(m["height_mm"])
    pkg = str(m.get("package", "")).upper()
    val = str(m.get("value", "")).upper()
    for k, h in PACKAGE_HEIGHT_ESTIMATES_MM.items():
        if k in pkg or k in val:
            return h
    kind = str(m.get("kind", "")).upper()
    if kind in ("CONNECTOR", "RELAY", "TRANSFORMER"):
        return 8.5
    return 1.2  # 默认普通贴片高度


def calculate_smt_placement_clearance(
    modules: dict[str, dict],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    min_tall_component_height_mm: float = 4.0,
    min_clearance_envelope_mm: float = 2.0,
) -> SMTPlacementClearanceReport:
    """分析 SMT 贴装吸嘴高低元件碰撞干涉，并输出由矮到高的分层贴装序列。"""
    components = []
    for ref, m in sorted((modules or {}).items()):
        if ref == "__meta__":
            continue
        h = _estimate_height(m)
        pos = m.get("position") or [board_width_mm / 2.0, board_height_mm / 2.0]
        x = float(pos[0]) if len(pos) >= 2 else board_width_mm / 2.0
        y = float(pos[1]) if len(pos) >= 2 else board_height_mm / 2.0
        components.append((ref, h, x, y))

    low_list = [c[0] for c in components if c[1] <= 2.0]
    med_list = [c[0] for c in components if 2.0 < c[1] <= 4.0]
    tall_list = [c[0] for c in components if c[1] > 4.0]

    # 分层贴装序列：矮件先贴 (第1批)，中件 (第2批)，高件最后 (第3批)
    layers = [l for l in (low_list, med_list, tall_list) if l]

    # 碰撞对检测
    collision_pairs: list[CollisionPair] = []
    risks = 0
    for i in range(len(components)):
        for j in range(i + 1, len(components)):
            c1, c2 = components[i], components[j]
            h_diff = abs(c1[1] - c2[1])
            if h_diff >= (min_tall_component_height_mm - 1.0):
                dist = math.hypot(c1[2] - c2[2], c1[3] - c2[3])
                low_c = c1 if c1[1] < c2[1] else c2
                high_c = c2 if c1[1] < c2[1] else c1
                is_risk = dist < min_clearance_envelope_mm
                if is_risk:
                    risks += 1
                collision_pairs.append(
                    CollisionPair(
                        low_ref=low_c[0],
                        high_ref=high_c[0],
                        low_height_mm=round(low_c[1], 2),
                        high_height_mm=round(high_c[1], 2),
                        height_delta_mm=round(h_diff, 2),
                        center_dist_mm=round(dist, 2),
                        is_collision_risk=is_risk,
                    )
                )

    return SMTPlacementClearanceReport(
        total_components=len(components),
        low_components_count=len(low_list),
        medium_components_count=len(med_list),
        tall_components_count=len(tall_list),
        collision_risks_count=risks,
        placement_priority_layers=layers,
        collision_pairs=collision_pairs,
    )
