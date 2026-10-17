"""IPC-9797 / IEC 60352-5 汽车与工业无焊压接鱼眼端子过孔合规分析器 (Press-Fit Compliant Pin PTH Analyzer).

工业背景与安规基准：
- IPC-9797 & IEC 60352-5 无焊压接连接标准 (Solderless Press-in Connections):
  在汽车电子、大功率电源控制器与工业背板中，高电流连接器端子采用柔性鱼眼针 (Eye-of-the-Needle / Action Pin)
  直接压入金属化孔 (PTH)，彻底免除波峰焊或手工焊的热冲击。
- 严苛的过孔制造公差标准 (IPC-9797 Table 4-1):
  * 标称压接孔径: 典型值为 Φ1.00mm (+0.09mm / -0.06mm)，即成品孔径必须严格控制在 **0.94mm ~ 1.09mm** 之间；
  * 孔壁铜厚 (Copper Barrel Thickness): 必须满足 **t_cu >= 25μm (1 mil)** (IPC-6012 Class 3 工业级标准)，
    防止压入时孔壁铜皮撕裂脱落 (Hole Wall Barrel Separation)；
  * 底孔钻头公差: 通常为 Φ1.15mm ± 0.025mm。
- 机械力学失效评估：
  * 孔径过小 (D < 0.94mm): 压入力飙升 (>150N/pin)，极易压溃 PCB 内部走线层 (Inner-layer Tear)、
    翘曲板材或压碎连接器塑胶胶壳；
  * 孔径过大 (D > 1.09mm): 保持力不足 (<30N/pin)，在车载/工业振动环境下接触电阻漂移并发生微动磨损断路。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PressFitHoleCheck:
    pin_id: str
    connector_ref: str
    drill_dia_mm: float
    copper_thickness_um: float
    finished_hole_dia_mm: float
    min_spec_dia_mm: float
    max_spec_dia_mm: float
    est_insertion_force_n: float
    est_retention_force_n: float
    is_compliant: bool
    violation_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PressFitComplianceReport:
    total_pins_audited: int
    compliant_pins_count: int
    violating_pins_count: int
    is_all_compliant: bool
    checks: list[PressFitHoleCheck] = field(default_factory=list)
    ipc_standard: str = "IPC-9797 / IEC 60352-5 Press-Fit Specification"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["checks"] = [c.to_dict() for c in self.checks]
        return d


def calculate_press_fit_hole_compliance(
    pins: list[dict],
    nominal_finished_dia_mm: float = 1.00,
    tol_plus_mm: float = 0.09,
    tol_minus_mm: float = 0.06,
    min_copper_plating_um: float = 25.0,
) -> PressFitComplianceReport:
    """核算压接孔成品孔径、孔壁铜厚、压入力与保持力是否满足 IPC-9797 汽车级标准。

    pins: [{pin_id, connector_ref, drill_dia_mm, copper_thickness_um, finished_dia_mm}]
    """
    spec_min = round(nominal_finished_dia_mm - tol_minus_mm, 3)
    spec_max = round(nominal_finished_dia_mm + tol_plus_mm, 3)

    checks: list[PressFitHoleCheck] = []
    viol_count = 0

    for idx, p in enumerate(pins):
        pid = str(p.get("pin_id", f"PIN_{idx+1}"))
        ref = str(p.get("connector_ref", "CONN1"))
        d_drill = float(p.get("drill_dia_mm", 1.15))
        t_cu = float(p.get("copper_thickness_um", 25.0))

        # 成品孔径计算：若显式提供则取提供值，否则按 底孔 - 2*铜厚 估算
        if "finished_dia_mm" in p:
            d_finished = round(float(p["finished_dia_mm"]), 3)
        else:
            d_finished = round(d_drill - 2.0 * (t_cu / 1000.0), 3)

        # 压入力/保持力经验模型 (根据孔径公差偏离推算)
        # 标称 1.0mm 下: 压入力 ~80N, 保持力 ~50N
        interference_mm = max(0.0, 1.10 - d_finished)
        f_insert = round(30.0 + interference_mm * 500.0, 1)
        f_retain = round(20.0 + interference_mm * 300.0, 1)

        reasons = []
        if d_finished < spec_min:
            reasons.append(f"成品孔径 {d_finished:.3f}mm < 下限 {spec_min:.3f}mm (压入力达 {f_insert}N 过大，存在压裂内层风险)")
        elif d_finished > spec_max:
            reasons.append(f"成品孔径 {d_finished:.3f}mm > 上限 {spec_max:.3f}mm (保持力仅 {f_retain}N 不足，振动易松动断路)")

        if t_cu < min_copper_plating_um:
            reasons.append(f"孔壁铜厚 {t_cu:.1f}μm < IPC-6012 工业级下限 {min_copper_plating_um:.1f}μm (压接易导致孔壁分层撕裂)")

        is_ok = len(reasons) == 0
        if not is_ok:
            viol_count += 1

        checks.append(
            PressFitHoleCheck(
                pin_id=pid,
                connector_ref=ref,
                drill_dia_mm=d_drill,
                copper_thickness_um=t_cu,
                finished_hole_dia_mm=d_finished,
                min_spec_dia_mm=spec_min,
                max_spec_dia_mm=spec_max,
                est_insertion_force_n=f_insert,
                est_retention_force_n=f_retain,
                is_compliant=is_ok,
                violation_reason="; ".join(reasons) if reasons else "PASS",
            )
        )

    all_ok = viol_count == 0
    return PressFitComplianceReport(
        total_pins_audited=len(checks),
        compliant_pins_count=len(checks) - viol_count,
        violating_pins_count=viol_count,
        is_all_compliant=all_ok,
        checks=checks,
    )
