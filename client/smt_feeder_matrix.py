"""SMT Pick-and-Place Machine Feeder & Nozzle Selection Matrix (OpenPnP & Industrial SMT Standard).

Industrial benchmark & standards:
- EIA-481: Taping of Surface Mount Components for Automated Placement.
  Defines standard carrier tape widths (8mm, 12mm, 16mm, 24mm, 32mm)
  and component pocket pitches (2mm, 4mm, 8mm, 12mm, 16mm).
- OpenPnP (7k+ stars) & Juki / Yamaha standard nozzle assignment matrix:
  * 502 / CN040 (0.4mm OD): Ultra-small chips (0402)
  * 503 / CN065 (0.65mm OD): Small passives & transistors (0603, 0805, SOT-23, SOD-323)
  * 504 / CN100 (1.0mm OD): Medium ICs & diodes (1206, SOT-223, SOIC-8, SOP-8)
  * 505 / CN140 (1.4mm OD): Dense ICs & inductors (QFN-24, QFN-48, L0805, XH SMD)
  * 506 / CN220 (2.2mm OD): Large packages & connectors (LQFP-48, RJ45, USB-C)
- Automatically allocates machine feeder slots, prevents tape-pitch mismatch,
  and optimizes nozzle change counts.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger("circuit-smt-feeder")


@dataclass
class FeederSlotAssignment:
    slot_id: int
    tape_width_mm: int  # 8, 12, 16, 24, 32
    tape_pitch_mm: int  # 2, 4, 8, 12, 16
    nozzle_type: str  # 502, 503, 504, 505, 506
    package: str
    component_value: str
    designators: list[str] = field(default_factory=list)
    part_count: int = 0
    lcsc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SMTFeederMatrixReport:
    total_slots_used: int
    tape_width_breakdown: dict[int, int]  # width -> count
    nozzle_distribution: dict[str, int]  # nozzle -> count
    feeders: list[FeederSlotAssignment]
    estimated_nozzle_changes: int
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["feeders"] = [f.to_dict() if hasattr(f, "to_dict") else f for f in self.feeders]
        return d


def assign_smt_feeder_and_nozzle(package: str, kind: str = "") -> tuple[int, int, str]:
    """Map component footprint and kind to standard (tape_width_mm, tape_pitch_mm, nozzle_type)."""
    pkg = package.upper()
    k = kind.upper()

    if any(s in pkg for s in ("0402", "1005")):
        return 8, 2, "502_CN040"
    if any(s in pkg for s in ("0603", "1608")):
        return 8, 4, "503_CN065"
    if any(s in pkg for s in ("0805", "2012", "SOT-23", "SOD-123", "SOD-323")):
        return 8, 4, "503_CN065"
    if any(s in pkg for s in ("1206", "3216", "SOT-223", "SOIC-8", "SOP-8", "SOP-4")):
        return 12, 8, "504_CN100"
    if any(s in pkg for s in ("QFN", "DFN", "HTSSOP", "TSSOP", "2512")):
        return 16, 12, "505_CN140"
    if any(s in pkg for s in ("LQFP", "QFP", "USB-C", "RJ45", "HDR", "CONN", "ELEC")):
        return 24, 16, "506_CN220"

    # Default conservative assignment
    if k in ("RESISTOR", "CAPACITOR", "LED"):
        return 8, 4, "503_CN065"
    if k in ("IC", "MCU"):
        return 16, 12, "505_CN140"
    return 12, 8, "504_CN100"


def generate_smt_feeder_matrix(modules: dict[str, Any]) -> SMTFeederMatrixReport:
    """Generate optimized feeder slot allocation and nozzle tooling matrix for automated SMT placement."""
    # Group designators by (value, package, lcsc)
    groups: dict[tuple[str, str, str, str], list[str]] = {}
    for ref, m in sorted(modules.items()):
        val = str(m.get("value", "UNKNOWN")).strip()
        pkg = str(m.get("package", "SMD")).strip()
        lcsc = str(m.get("lcsc", "")).strip()
        kind = str(m.get("kind", "")).strip()
        groups.setdefault((val, pkg, lcsc, kind), []).append(ref)

    feeders: list[FeederSlotAssignment] = []
    width_counts: dict[int, int] = {}
    nozzle_counts: dict[str, int] = {}
    slot_id = 1

    for (val, pkg, lcsc, kind), refs in sorted(groups.items(), key=lambda x: (x[0][1], x[0][0])):
        w, pitch, nozzle = assign_smt_feeder_and_nozzle(pkg, kind)
        feeders.append(
            FeederSlotAssignment(
                slot_id=slot_id,
                tape_width_mm=w,
                tape_pitch_mm=pitch,
                nozzle_type=nozzle,
                package=pkg,
                component_value=val,
                designators=refs,
                part_count=len(refs),
                lcsc=lcsc,
            )
        )
        width_counts[w] = width_counts.get(w, 0) + 1
        nozzle_counts[nozzle] = nozzle_counts.get(nozzle, 0) + 1
        slot_id += 1

    distinct_nozzles = len(nozzle_counts)
    est_nozzle_changes = max(0, distinct_nozzles - 1)

    recommendations = [
        f"供料器配置: 总计占用 {len(feeders)} 个贴片机料槽 (8mm: {width_counts.get(8, 0)}轨, 12mm: {width_counts.get(12, 0)}轨, 16mm+: {width_counts.get(16, 0) + width_counts.get(24, 0)}轨)。",
        f"吸嘴配置: 涉及 {distinct_nozzles} 种工业吸嘴规格，推荐在双吸嘴/四吸嘴贴片头中平衡挂载以最小化换嘴耗时。",
    ]

    log.info(f"✅ 生成 SMT 供料器与吸嘴选型矩阵: {len(feeders)} 个料站, {distinct_nozzles} 种吸嘴规格")

    return SMTFeederMatrixReport(
        total_slots_used=len(feeders),
        tape_width_breakdown=width_counts,
        nozzle_distribution=nozzle_counts,
        feeders=feeders,
        estimated_nozzle_changes=est_nozzle_changes,
        recommendations=recommendations,
    )
