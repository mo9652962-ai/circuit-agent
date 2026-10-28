"""JLCPCB / PCBWay Headless Order Cost Budget & Submission Manifest Builder.

Industrial Context (2024~2025 ecosystem):
- JLCPCB Online API (https://jlcpcb.com/help/article/jlcpcb-online-api-available-now):
  REST endpoints for quote → order → tracking; requires an API key obtained by
  application. Community `jlcpcb-api` Python SDKs wrap it.
- PCBWay Partner API (https://www.pcbway.com/api_cooperation.html):
  PCB quotation / status review / place order / order status tracking for approved
  integration partners.
- Headless CI pattern (macOS/Linux developer view):
  A release pipeline validates the manufacturing package (circuit-agent's
  `validate_manufacturing_package`), computes the cost budget offline, and stages a
  submission manifest that a human (or an approved bot) executes against the vendor
  API. The offline stage needs no network, no keys — it is pure math over the
  vendor's public price ladders, so it can run in CI on every tag.
- macOS/Linux view: this module is stdlib-only, deterministic, and locale-free —
  safe to run under `uvx` on a developer laptop or in a Docker CI runner.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

# Public price ladders (USD, approximate 2024-2025 published rates; verify at order time)
FAB_PRICE_TABLES: dict[str, dict[str, Any]] = {
    "jlcpcb": {
        "name": "JLCPCB",
        "api_docs": "https://jlcpcb.com/help/article/jlcpcb-online-api-available-now",
        "setup_fee_usd": 0.0,
        "base_2layer_100x100_5pcs_usd": 2.0,
        "layer_mult": {2: 1.0, 4: 2.4, 6: 4.5},
        "qty_mult": {5: 1.0, 10: 1.6, 30: 3.2, 100: 7.5},
        "area_over_100x100_usd_per_dm2": 1.2,
        "finish_mult": {"hasl_lead_free": 1.0, "enig": 1.35, "osp": 1.0},
        "smt_setup_usd": 25.0,
        "shipping_mult": {"standard": 1.0, "dhl": 1.15},
        "lead_days": {"economy": 5, "standard": 3, "expedite": 2},
    },
    "pcbway": {
        "name": "PCBWay",
        "api_docs": "https://www.pcbway.com/api_cooperation.html",
        "setup_fee_usd": 5.0,
        "base_2layer_100x100_5pcs_usd": 5.0,
        "layer_mult": {2: 1.0, 4: 2.2, 6: 4.0},
        "qty_mult": {5: 1.0, 10: 1.7, 30: 3.5, 100: 8.0},
        "area_over_100x100_usd_per_dm2": 1.5,
        "finish_mult": {"hasl_lead_free": 1.0, "enig": 1.3, "osp": 1.0},
        "smt_setup_usd": 50.0,
        "shipping_mult": {"standard": 1.0, "dhl": 1.2},
        "lead_days": {"economy": 6, "standard": 4, "expedite": 2},
    },
}


@dataclass
class FabQuoteLine:
    """One vendor's cost estimate and lead time."""

    vendor: str
    pcb_cost_usd: float
    smt_cost_usd: float
    shipping_usd: float
    total_usd: float
    lead_days: int
    manifest_sha256: str


@dataclass
class FabOrderBudget:
    """Cross-vendor offline budget and submission manifest."""

    quotes: list[FabQuoteLine] = field(default_factory=list)
    recommended_vendor: str = ""
    savings_vs_max_usd: float = 0.0
    artifacts: list[str] = field(default_factory=list)
    submission_ready: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "quotes": [
                {
                    "vendor": q.vendor,
                    "pcb_usd": round(q.pcb_cost_usd, 2),
                    "smt_usd": round(q.smt_cost_usd, 2),
                    "shipping_usd": round(q.shipping_usd, 2),
                    "total_usd": round(q.total_usd, 2),
                    "lead_days": q.lead_days,
                    "manifest_sha256": q.manifest_sha256[:16] + "...",
                }
                for q in self.quotes
            ],
            "recommended_vendor": self.recommended_vendor,
            "savings_vs_max_usd": round(self.savings_vs_max_usd, 2),
            "artifacts": self.artifacts,
            "submission_ready": self.submission_ready,
            "notes": self.notes,
        }


def budget_fab_order(
    layers: int = 2,
    qty: int = 5,
    board_w_mm: float = 70.0,
    board_h_mm: float = 50.0,
    surface_finish: str = "hasl_lead_free",
    include_smt: bool = False,
    smt_parts: int = 0,
    shipping: str = "standard",
    lead_priority: str = "standard",
    artifacts: dict[str, str] | None = None,
) -> FabOrderBudget:
    """Compute offline cross-vendor cost budget and stage a submission manifest.

    Args:
        layers: 2 / 4 / 6.
        qty: Panel quantity (5/10/30/100 ladder).
        board_w_mm / board_h_mm: Outline size (mm).
        surface_finish: 'hasl_lead_free' | 'enig' | 'osp'.
        include_smt: Whether PCBA assembly is requested.
        smt_parts: Number of SMT placements (drives the setup amortization note).
        shipping: 'standard' | 'dhl'.
        lead_priority: 'economy' | 'standard' | 'expedite'.
        artifacts: Manufacturing artifacts {filename: content} — a SHA-256 manifest
            is computed over them for tamper-evident submission.

    Returns:
        FabOrderBudget: per-vendor quotes, recommendation, and manifest digest.
    """
    budget = FabOrderBudget()
    area_dm2 = (board_w_mm / 100.0) * (board_h_mm / 100.0)
    over_area = max(0.0, area_dm2 - 1.0)  # first 1 dm² (100×100) is in the base

    manifest_sha = ""
    if artifacts:
        h = hashlib.sha256()
        for name in sorted(artifacts):
            data = artifacts[name]
            raw = data.encode("utf-8") if isinstance(data, str) else data
            h.update(name.encode("utf-8"))
            h.update(raw)
        manifest_sha = h.hexdigest()
        budget.artifacts = sorted(artifacts)

    for vid, tbl in FAB_PRICE_TABLES.items():
        l_mult = tbl["layer_mult"].get(layers)
        q_mult = tbl["qty_mult"].get(qty)
        f_mult = tbl["finish_mult"].get(surface_finish, 1.0)
        if l_mult is None or q_mult is None:
            budget.notes.append(f"{vid}: layers={layers}/qty={qty} 不在公开阶梯，需询价。")
            continue

        pcb = (
            tbl["setup_fee_usd"]
            + tbl["base_2layer_100x100_5pcs_usd"] * l_mult * q_mult * f_mult
            + over_area * tbl["area_over_100x100_usd_per_dm2"] * (qty / 5.0)
        )

        smt = 0.0
        if include_smt:
            # setup amortized over qty; per-part placement folded into setup for ladder simplicity
            smt = tbl["smt_setup_usd"] + (smt_parts / 100.0) * (tbl["smt_setup_usd"] / 10.0)

        shipping_cost = 5.0 * tbl["shipping_mult"].get(shipping, 1.0)
        priority_mult = {"economy": 0.9, "standard": 1.0, "expedite": 1.6}.get(lead_priority, 1.0)
        total = (pcb + smt) * priority_mult + shipping_cost

        budget.quotes.append(
            FabQuoteLine(
                vendor=tbl["name"],
                pcb_cost_usd=pcb,
                smt_cost_usd=smt,
                shipping_usd=shipping_cost,
                total_usd=total,
                lead_days=tbl["lead_days"].get(lead_priority, 5),
                manifest_sha256=manifest_sha or "no-artifacts",
            )
        )

    if budget.quotes:
        cheapest = min(budget.quotes, key=lambda q: q.total_usd)
        dearest = max(budget.quotes, key=lambda q: q.total_usd)
        budget.recommended_vendor = cheapest.vendor
        budget.savings_vs_max_usd = dearest.total_usd - cheapest.total_usd
        # A tie on lead days resolves to the cheaper vendor
        same_lead = [q for q in budget.quotes if q.lead_days == cheapest.lead_days]
        if same_lead:
            budget.recommended_vendor = min(same_lead, key=lambda q: q.total_usd).vendor

    budget.submission_ready = bool(manifest_sha) and len(budget.quotes) > 0
    if not manifest_sha:
        budget.notes.append("未提供制造交付件——提交清单无 SHA-256 防篡改账本，上线前须补齐。")
    budget.notes.append(
        "价格为公开阶梯的离线预算 (2024~2025)；下单前以厂商 API/网页实时报价为准。"
        " JLCPCB 需 API key 申请；PCBWay 需合作伙伴审批。"
    )
    return budget
