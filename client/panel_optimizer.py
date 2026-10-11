"""拼版网格利用率优化器 (Panel Grid Utilization Optimizer).

工业背景与优化基准：
- PCB 拼版 (Panelization) 的核心经济指标是**基材利用率 (Material Utilization)**：
  利用率 = Σ(单板面积) / 拼版总面积 (含工艺边与板间距)；
- EMS/板厂约束：嘉立创/板厂标准拼版上限 300×300mm (超出加收超高板费)，
  SMT 传送导轨适配工艺边宽度 3~5mm (IPC-SMEMA-9851)；
- 优化策略：在 grid_x × grid_y ∈ 1..N 的组合里，枚举工艺边双侧/四侧布局，
  过滤超出最大拼版尺寸的方案，按利用率降序输出 Top-N 推荐方案。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PanelOption:
    grid_x: int
    grid_y: int
    rail_sides: str  # "left_right" / "all_four"
    depaneling: str  # "v_cut" / "mouse_bites"
    panel_width_mm: float
    panel_height_mm: float
    utilization_pct: float
    boards: int
    feasible: bool = True
    rejected_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PanelOptimizeReport:
    board_width_mm: float
    board_height_mm: float
    max_panel_mm: float
    best: PanelOption | None = None
    ranked: list[PanelOption] = field(default_factory=list)
    rejected_count: int = 0
    ipc_standard: str = "IPC-2221B Section 8.4 / IPC-SMEMA-9851"

    def to_dict(self) -> dict[str, Any]:
        return {
            "board_width_mm": self.board_width_mm,
            "board_height_mm": self.board_height_mm,
            "max_panel_mm": self.max_panel_mm,
            "best": self.best.to_dict() if self.best else None,
            "ranked": [o.to_dict() for o in self.ranked],
            "rejected_count": self.rejected_count,
        }


def optimize_panel_grid(
    board_width_mm: float = 50.0,
    board_height_mm: float = 40.0,
    max_grid: int = 4,
    max_panel_mm: float = 300.0,
    rail_width_mm: float = 5.0,
    v_cut_spacing_mm: float = 0.0,
    mouse_bites_spacing_mm: float = 2.0,
) -> PanelOptimizeReport:
    """枚举拼版网格组合并按基材利用率排序，过滤超尺寸方案。"""
    bw = max(1.0, float(board_width_mm))
    bh = max(1.0, float(board_height_mm))
    N = max(1, int(max_grid))
    max_panel = max(50.0, float(max_panel_mm))
    rail = max(3.0, float(rail_width_mm))

    options: list[PanelOption] = []
    rejected = 0

    for gx in range(1, N + 1):
        for gy in range(1, N + 1):
            for rail_sides in ("left_right", "all_four"):
                for depan, spacing in (("v_cut", v_cut_spacing_mm), ("mouse_bites", mouse_bites_spacing_mm)):
                    boards_w = gx * bw + (gx - 1) * spacing
                    boards_h = gy * bh + (gy - 1) * spacing
                    pw = boards_w + (2 * rail if rail_sides in ("left_right", "all_four") else 0.0)
                    ph = boards_h + (2 * rail if rail_sides == "all_four" else 0.0)

                    opt = PanelOption(
                        grid_x=gx,
                        grid_y=gy,
                        rail_sides=rail_sides,
                        depaneling=depan,
                        panel_width_mm=round(pw, 2),
                        panel_height_mm=round(ph, 2),
                        utilization_pct=round((gx * gy * bw * bh) / (pw * ph) * 100.0, 1),
                        boards=gx * gy,
                    )
                    if pw > max_panel or ph > max_panel:
                        opt.feasible = False
                        opt.rejected_reason = f"panel {pw:g}x{ph:g}mm exceeds {max_panel:g}x{max_panel:g}mm limit"
                        rejected += 1
                    options.append(opt)

    feasible = [o for o in options if o.feasible]
    feasible.sort(key=lambda o: (o.utilization_pct, o.boards), reverse=True)
    best = feasible[0] if feasible else None
    return PanelOptimizeReport(
        board_width_mm=bw,
        board_height_mm=bh,
        max_panel_mm=max_panel,
        best=best,
        ranked=feasible[:10],
        rejected_count=rejected,
    )
