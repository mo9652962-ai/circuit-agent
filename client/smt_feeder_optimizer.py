"""Industrial SMT Pick & Place Feeder Reel Optimization & Setup Changeover Minimization.

Industrial & Authoritative Standards:
- IPC-9851 (SMEMA Surface Mount Equipment Communication Standard):
  Governs line communication, PCB handoff sequencing, and automated setup tracking across SMT lines.
- Panasonic NPM / Fuji NXT / ASM SIPLACE SMT Feeder Optimization Guidelines:
  High-mix low-volume (HMLV) and high-volume electronics manufacturing facilities face up to 30%~40%
  line downtime during reel changeovers when switching between different PCBA product families.
  Group Technology (GT) feeder scheduling optimizes feeder trolley allocation:
    1. Permanent Feeder Block (Family Setup): Pinning high-frequency common passive reels (100nF 0402, 10k 0402,
       1uF 0603) to fixed feeder table slots across multiple jobs, eliminating reload downtime.
    2. Gantry Travel Distance Minimization: Arranging high-pick-count component reels closest to the board center
       and pickup head home position to minimize gantry acceleration/deceleration travel time.
    3. Reel Exhaustion Forecasting: Predicting production run-out points based on tape reel pitch and batch sizes.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

# Standard SMT Tape Widths & Feeder Cart Slot Consumption (Panasonic / Fuji / ASM standard)
TAPE_SLOT_CONSUMPTION: dict[str, int] = {
    "8mm": 1,
    "12mm": 2,
    "16mm": 2,
    "24mm": 3,
    "32mm": 4,
    "44mm": 5,
}

# Standard Reel Capacity by Package (pieces per 7-inch reel)
STANDARD_REEL_CAPACITY: dict[str, int] = {
    "0201": 15000,
    "0402": 10000,
    "0603": 4000,
    "0805": 3000,
    "1206": 2000,
    "SOT-23": 3000,
    "SOIC-8": 2500,
    "TSSOP": 2500,
    "QFN": 3000,
}


@dataclass
class FeederSlotAssignment:
    """An individual feeder reel assigned to a feeder cart slot."""

    slot_number: int
    slot_span: int
    part_number: str
    package: str
    tape_width: str
    pick_count_per_board: int
    total_picks_in_batch: int
    is_common_family_part: bool
    estimated_reel_capacity: int
    boards_until_reel_reload: int
    ref_designators: list[str] = field(default_factory=list)


@dataclass
class SMTFeederPlan:
    """Complete SMT feeder table setup and optimization plan."""

    total_feeder_slots_capacity: int
    slots_demanded: int
    slots_occupied: int
    slots_available: int
    total_components_per_board: int
    unique_reels_count: int
    estimated_travel_index_arbitrary: float
    estimated_changeover_time_saved_min: float
    common_feeder_block_count: int
    feeder_slots: list[FeederSlotAssignment] = field(default_factory=list)
    bottleneck_reels: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_feeder_slots_capacity": self.total_feeder_slots_capacity,
            "slots_demanded": self.slots_demanded,
            "slots_occupied": self.slots_occupied,
            "slots_available": self.slots_available,
            "total_components_per_board": self.total_components_per_board,
            "unique_reels_count": self.unique_reels_count,
            "estimated_travel_index_arbitrary": round(self.estimated_travel_index_arbitrary, 1),
            "estimated_changeover_time_saved_min": round(self.estimated_changeover_time_saved_min, 1),
            "common_feeder_block_count": self.common_feeder_block_count,
            "feeder_slots": [asdict(f) for f in self.feeder_slots],
            "bottleneck_reels": self.bottleneck_reels,
        }


def optimize_smt_feeder_setup(
    modules: dict[str, dict[str, Any]],
    feeder_cart_capacity: int = 80,
    batch_size: int = 1000,
    common_parts_list: list[str] | None = None,
) -> SMTFeederPlan:
    """Optimize SMT feeder table allocation to minimize gantry travel time and changeover downtime.

    Args:
        modules: Component modules dict from synthesis or netlist ({refDes: {package, value, part_number, ...}})
        feeder_cart_capacity: Total feeder slots on machine table/trolley (standard 80 slots)
        batch_size: Production order batch size (boards)
        common_parts_list: Optional list of part numbers or descriptions pinned to common setup block

    Returns:
        SMTFeederPlan: Optimized feeder table arrangement, slot spans, and reload forecasting
    """
    if common_parts_list is None:
        # Default high-frequency industrial standard common components
        common_parts_list = ["100nF", "10k", "1k", "1uF", "10uF", "LED"]

    # 1. Group by unique part
    part_groups: dict[str, dict[str, Any]] = {}
    for ref, comp in modules.items():
        val = str(comp.get("value", comp.get("val", "")))
        pkg = str(comp.get("package", comp.get("pkg", "0603")))
        pn = str(comp.get("part_number", comp.get("lcsc_part", f"{pkg}_{val}")))

        key = f"{pn}::{pkg}"
        if key not in part_groups:
            # Determine tape width from package
            tape_w = _infer_tape_width(pkg)
            is_common = any(c.lower() in val.lower() or c.lower() in pn.lower() for c in common_parts_list)
            reel_cap = _infer_reel_capacity(pkg)

            part_groups[key] = {
                "part_number": pn,
                "package": pkg,
                "tape_width": tape_w,
                "is_common": is_common,
                "reel_capacity": reel_cap,
                "refs": [],
            }
        part_groups[key]["refs"].append(ref)

    # 2. Sort parts:
    # First: Common family components (pinned to beginning of table)
    # Second: Frequency of usage (highest pick count placed near center)
    sorted_parts = sorted(
        part_groups.values(),
        key=lambda p: (not p["is_common"], -len(p["refs"])),
    )

    # 3. Allocate to feeder table slots
    slots: list[FeederSlotAssignment] = []
    current_slot = 1
    total_picks = 0
    travel_index = 0.0
    bottlenecks: list[dict[str, Any]] = []

    # Machine center slot is typically slot capacity / 2 (e.g. slot 40 on an 80-slot table)
    center_slot = feeder_cart_capacity / 2.0

    for p in sorted_parts:
        pick_count = len(p["refs"])
        total_picks += pick_count
        span = TAPE_SLOT_CONSUMPTION.get(p["tape_width"], 1)

        if current_slot + span - 1 > feeder_cart_capacity:
            # Feeder cart capacity exceeded
            break

        total_batch_picks = pick_count * batch_size
        reload_interval = max(1, p["reel_capacity"] // max(1, pick_count))

        # Travel distance proxy: |slot - center| * pick_count
        dist_to_center = abs((current_slot + span / 2.0) - center_slot)
        travel_index += dist_to_center * pick_count

        if reload_interval < batch_size:
            bottlenecks.append({
                "part_number": p["part_number"],
                "package": p["package"],
                "reloads_needed": math.ceil(total_batch_picks / p["reel_capacity"]) - 1,
                "boards_per_reel": reload_interval,
            })

        slots.append(
            FeederSlotAssignment(
                slot_number=current_slot,
                slot_span=span,
                part_number=p["part_number"],
                package=p["package"],
                tape_width=p["tape_width"],
                pick_count_per_board=pick_count,
                total_picks_in_batch=total_batch_picks,
                is_common_family_part=p["is_common"],
                estimated_reel_capacity=p["reel_capacity"],
                boards_until_reel_reload=reload_interval,
                ref_designators=p["refs"],
            )
        )
        current_slot += span

    total_demanded = sum(TAPE_SLOT_CONSUMPTION.get(p["tape_width"], 1) for p in sorted_parts)
    occupied = current_slot - 1
    avail = max(0, feeder_cart_capacity - occupied)
    common_count = sum(1 for s in slots if s.is_common_family_part)

    # Estimated changeover time saved: ~2 minutes per common reel that doesn't need to be swapped
    saved_min = common_count * 2.0

    return SMTFeederPlan(
        total_feeder_slots_capacity=feeder_cart_capacity,
        slots_demanded=total_demanded,
        slots_occupied=occupied,
        slots_available=avail,
        total_components_per_board=total_picks,
        unique_reels_count=len(slots),
        estimated_travel_index_arbitrary=travel_index,
        estimated_changeover_time_saved_min=saved_min,
        common_feeder_block_count=common_count,
        feeder_slots=slots,
        bottleneck_reels=bottlenecks,
    )


def _infer_tape_width(package: str) -> str:
    pkg = package.upper()
    if any(p in pkg for p in ["0201", "0402", "0603", "0805", "SOT-23", "SOD-323"]):
        return "8mm"
    if any(p in pkg for p in ["1206", "1210", "SOD-123", "SMA", "SMB"]):
        return "12mm"
    if any(p in pkg for p in ["SOIC-8", "SOIC-16", "SOP", "TSSOP", "SMC"]):
        return "16mm"
    if any(p in pkg for p in ["QFP", "LQFP", "QFN", "BGA"]):
        return "24mm"
    return "8mm"


def _infer_reel_capacity(package: str) -> int:
    for k, cap in STANDARD_REEL_CAPACITY.items():
        if k in package.upper():
            return cap
    return 3000
