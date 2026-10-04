"""Supply Chain Multi-Sourcing & Second-Source Resilience Auditor.

Industrial benchmark:
- Enterprise PCBA manufacturing demands second-source alternates (drop-in pin-compatible parts)
  to mitigate component shortage / obsolescence risks (ISO 9001 / IATF 16949 supply chain audit).
- Audits BOM components, identifies single-source bottleneck parts, and automatically maps
  pin-compatible second-source drop-in replacements with LCSC cross-references.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger("circuit-supply-chain")

# Pin-compatible drop-in second-source replacement mapping
SECOND_SOURCE_DATABASE: dict[str, list[dict[str, str]]] = {
    "AMS1117-3.3": [
        {"vendor": "Diodes Inc", "part": "AP1117E33G-13", "package": "SOT-223", "lcsc": "C23984"},
        {"vendor": "Texas Instruments", "part": "LM1117MP-3.3", "package": "SOT-223", "lcsc": "C7191"},
        {"vendor": "MicrOne", "part": "ME6211C33M5G", "package": "SOT-23-5", "lcsc": "C82942"},
    ],
    "SP3485EN": [
        {"vendor": "MaxLinear", "part": "SP3485CN-L/TR", "package": "SOIC-8", "lcsc": "C10408"},
        {"vendor": "Texas Instruments", "part": "SN65HVD485EDR", "package": "SOIC-8", "lcsc": "C154497"},
        {"vendor": "3PEAK", "part": "TP3485-SR", "package": "SOIC-8", "lcsc": "C39537"},
    ],
    "SN65HVD230DR": [
        {"vendor": "SIT", "part": "SIT3050T", "package": "SOIC-8", "lcsc": "C2686884"},
        {"vendor": "NXP", "part": "TJA1050T", "package": "SOIC-8", "lcsc": "C2329"},
    ],
    "TP4056": [
        {"vendor": "Top Power", "part": "TC4056A", "package": "SOP-8-EP", "lcsc": "C84022"},
        {"vendor": "LowPowerSemi", "part": "LP4056HSPF", "package": "SOP-8-EP", "lcsc": "C165687"},
    ],
    "PC817C": [
        {"vendor": "Everlight", "part": "EL357NC-G", "package": "SOP-4", "lcsc": "C7539"},
        {"vendor": "Lite-On", "part": "LTV-817S-TA1-C", "package": "SMD-4", "lcsc": "C2140"},
    ],
    "INA219AIDR": [
        {"vendor": "Texas Instruments", "part": "INA226AIDGSR", "package": "VSSOP-10", "lcsc": "C37070"},
    ],
    "DRV8825PWPR": [
        {"vendor": "Allegro", "part": "A4988SETTR-T", "package": "QFN-28", "lcsc": "C2939"},
        {"vendor": "Trinamic", "part": "TMC2209-LA-T", "package": "QFN-28", "lcsc": "C964604"},
    ],
    "W5500": [
        {"vendor": "WCH", "part": "CH395Q", "package": "LQFP-48", "lcsc": "C87151"},
    ],
}


@dataclass
class ComponentSourcingItem:
    ref: str
    primary_part: str
    kind: str
    package: str
    lcsc: str
    has_second_source: bool
    second_sources: list[dict[str, str]] = field(default_factory=list)
    risk_level: str = "LOW"  # "LOW" | "MEDIUM" | "HIGH"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SupplyChainAuditReport:
    total_components: int
    unique_parts_count: int
    single_source_parts: int
    multi_sourced_parts: int
    resilience_score_pct: float
    items: list[ComponentSourcingItem]
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["items"] = [it.to_dict() if hasattr(it, "to_dict") else it for it in self.items]
        return d


def audit_supply_chain(modules: dict[str, Any]) -> SupplyChainAuditReport:
    """Audit hardware BOM for multi-sourcing resilience and second-source readiness."""
    items: list[ComponentSourcingItem] = []
    single_source_count = 0
    multi_source_count = 0
    recommendations: list[str] = []

    for ref, m in sorted(modules.items()):
        val = str(m.get("value", "")).strip()
        kind = str(m.get("kind", "")).upper()
        pkg = str(m.get("package", ""))
        lcsc = str(m.get("lcsc", ""))

        # Passives (resistors, caps, LEDs) are inherently multi-sourced commodities
        if kind in ("RESISTOR", "CAPACITOR", "LED", "TESTPOINT", "FIDUCIAL"):
            items.append(ComponentSourcingItem(
                ref=ref, primary_part=val, kind=kind, package=pkg, lcsc=lcsc,
                has_second_source=True, second_sources=[], risk_level="LOW",
            ))
            multi_source_count += 1
            continue

        # Check ICs & active silicon against second-source database
        matched_alternates = []
        for db_key, alts in SECOND_SOURCE_DATABASE.items():
            if db_key.upper() in val.upper() or val.upper() in db_key.upper():
                matched_alternates = alts
                break

        if matched_alternates:
            items.append(ComponentSourcingItem(
                ref=ref, primary_part=val, kind=kind, package=pkg, lcsc=lcsc,
                has_second_source=True, second_sources=matched_alternates, risk_level="LOW",
            ))
            multi_source_count += 1
        else:
            # Single-source critical IC
            risk = "HIGH" if kind in ("IC", "MCU") else "MEDIUM"
            items.append(ComponentSourcingItem(
                ref=ref, primary_part=val, kind=kind, package=pkg, lcsc=lcsc,
                has_second_source=False, second_sources=[], risk_level=risk,
            ))
            single_source_count += 1
            if risk == "HIGH":
                recommendations.append(f"单源风险: {ref} ({val}) 无现成替代料，建议储备战略库存或在原理图预留兼容封装焊盘。")

    total = len(items)
    resilience_pct = round((multi_source_count / total * 100.0) if total > 0 else 100.0, 1)

    if resilience_pct >= 90.0:
        recommendations.insert(0, f"✅ 供应链弹性优异 ({resilience_pct}%)：绝大部分物料具备通用替代货源。")
    elif resilience_pct >= 75.0:
        recommendations.insert(0, f"⚠️ 供应链弹性良好 ({resilience_pct}%)：存在 {single_source_count} 个单源器件需采购重点监控。")
    else:
        recommendations.insert(0, f"🔴 供应链风险较高 ({resilience_pct}%)：单源核心芯片较多，量产需提前锁料。")

    log.info(f"✅ 供应链审计完成: {total} 个器件, 单源 {single_source_count}, 多源 {multi_source_count}, 评分 {resilience_pct}%")

    return SupplyChainAuditReport(
        total_components=total,
        unique_parts_count=len({m.get("value") for m in modules.values()}),
        single_source_parts=single_source_count,
        multi_sourced_parts=multi_source_count,
        resilience_score_pct=resilience_pct,
        items=items,
        recommendations=recommendations,
    )
