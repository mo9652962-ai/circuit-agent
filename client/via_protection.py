"""IPC-4761 Via Protection Type Solver (Tent / Plug / Fill / Cap Selection).

Industrial benchmark & standards:
- IPC-4761: Design Guide for Protection of Vias in Bare Printed Boards.
  Defines seven via protection structures (Type I ~ VII) and their applicability:
  * Type I  : Tented (solder mask over, one side) — free vias away from assembly.
  * Type II : Tented (both sides).
  * Type III: Single-side plugged (mask ink / via plug material).
  * Type IV : Tented and plugged.
  * Type V  : Filled (non-conductive or conductive epoxy, flush).
  * Type VI : Filled and covered (mask over fill).
  * Type VII: Filled and CAPPED (plated over fill) — the ONLY acceptable structure for
    via-in-pad (VIPPO) on BGA lands: prevents solder wicking down the barrel during reflow,
    which starves the joint and causes head-in-pillow (HiP) / opens (IPC-A-610G).
- Selection matrix:
  * Via inside BGA / QFN signal land (in-pad): Type VII mandatory (cap plating over fill).
  * Via inside QFN/Power exposed thermal pad: Type V or VI (non-conductive fill preferred;
    conductive fill only when junction heat shunting is required).
  * Via inside BGA dogbone escape channel (between balls, not in pad): Type IV
    (tented + plugged) to block paste/flux migration under the package.
  * Free routing via (open field): Type I / II (mask tent) — lowest cost.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

IPC4761_TYPES: dict[str, str] = {
    "I": "单面阻焊覆盖 (Tented, one side)",
    "II": "双面阻焊覆盖 (Tented, both sides)",
    "III": "单面塞孔 (Plugged, one side)",
    "IV": "覆盖+塞孔 (Tented and plugged)",
    "V": "树脂填孔 (Filled, flush)",
    "VI": "填孔+覆盖 (Filled and covered)",
    "VII": "填孔+电镀盖帽 (Filled and capped, VIPPO)",
}


@dataclass
class ViaProtectionPlan:
    via_id: str
    context: str  # "bga_in_pad" / "thermal_pad" / "bga_pitch_channel" / "free"
    recommended_type: str  # "I".."VII"
    protection_desc: str
    solder_wicking_risk: str  # "NONE" / "LOW" / "HIGH"
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ViaProtectionReport:
    total_vias: int
    type_distribution: dict[str, int]
    wicking_risk_count: int
    plans: list[ViaProtectionPlan] = field(default_factory=list)
    ipc_standard: str = "IPC-4761 Design Guide for Protection of Vias"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _recommend_single(via: dict) -> ViaProtectionPlan:
    vid = str(via.get("id", "VIA"))
    in_pad = bool(via.get("in_pad", False))
    land_type = str(via.get("land_type", "signal")).lower()  # "bga" / "thermal" / "signal"
    in_bga_pitch = bool(via.get("in_bga_pitch", False))

    if in_pad and land_type == "bga":
        return ViaProtectionPlan(
            via_id=vid,
            context="bga_in_pad",
            recommended_type="VII",
            protection_desc=IPC4761_TYPES["VII"],
            solder_wicking_risk="HIGH" if not via.get("vippo_filled", False) else "NONE",
            rationale="盘中孔 (VIPPO) 在 BGA 焊盘上必须 Type VII 填孔+电镀盖帽，否则回流焊锡膏沿孔壁毛细渗流导致焊料饥饿与枕头效应 (IPC-4761 / IPC-A-610G)。",
        )
    if in_pad and land_type == "thermal":
        return ViaProtectionPlan(
            via_id=vid,
            context="thermal_pad",
            recommended_type="V",
            protection_desc=IPC4761_TYPES["V"],
            solder_wicking_risk="LOW",
            rationale="热沉焊盘导热过孔推荐 Type V 树脂填孔（优先非导电填料）；仅当需要垂直导热分流时选用导电填料，且填孔平整度需满足钢网印刷。",
        )
    if in_bga_pitch:
        return ViaProtectionPlan(
            via_id=vid,
            context="bga_pitch_channel",
            recommended_type="IV",
            protection_desc=IPC4761_TYPES["IV"],
            solder_wicking_risk="LOW",
            rationale="BGA 通道内过孔推荐 Type IV 覆盖+塞孔，阻断回流焊助焊剂/锡珠在封装底部迁移短路。",
        )
    return ViaProtectionPlan(
        via_id=vid,
        context="free",
        recommended_type="II",
        protection_desc=IPC4761_TYPES["II"],
        solder_wicking_risk="NONE",
        rationale="开阔区过孔采用 Type II 双面阻焊覆盖即可，成本最低且满足阻焊完整性 (IPC-4761)。",
    )


def calculate_via_protection_plan(vias: list[dict]) -> ViaProtectionReport:
    """Select IPC-4761 protection type for every via according to its assembly context."""
    plans = [_recommend_single(v) for v in vias]
    dist: dict[str, int] = {}
    wicking = 0
    for p in plans:
        dist[p.recommended_type] = dist.get(p.recommended_type, 0) + 1
        if p.solder_wicking_risk == "HIGH":
            wicking += 1
    return ViaProtectionReport(
        total_vias=len(plans),
        type_distribution=dist,
        wicking_risk_count=wicking,
        plans=plans,
    )
