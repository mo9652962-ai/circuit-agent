"""SMT 底面元件波峰焊排布朝向角与阴影效应审计器 (Wave Soldering Component Orientation & Shadowing Auditor).

工业背景与工艺标准：
- IPC-7351B Section 3.1.4 & SMTA Wave Soldering Guidelines:
  当混装板底面的表面贴装元件直接通过 260°C 液态波峰焊时，元件几何朝向决定焊接质量：
  1. 双端片式无源件 (0603 / 0805 / 1206 电阻电容):
     - 正确朝向：元件长轴必须**垂直于波峰流向** (Perpendicular, 90° ± 15°)。
       两端引脚同时切入锡波受热均匀；若平行于流向，前导端先受热先润湿，后导端受冷推拉，
       极易产生立碑 (Tombstoning) 与一端虚焊开路缺陷。
  2. 多引脚小外形 IC (SOIC / SOP / TSSOP):
     - 正确朝向：芯片本体长轴必须**平行于波峰流向** (Parallel, 0° 或 180° ± 15°)。
       引脚排列方向与锡流平行流动；若垂直于流向，密集引脚并排横截锡流将在后沿形成
       严重连锡桥连短路 (Bridging)。
  3. 波峰流体动力学阴影效应 (Hydrodynamic Wave Shadowing):
     高元件 (如电感、二极管、变压器) 在下风向形成锡波无法冲刷的死角区 (Shadow Zone)，
     阴影区长度通常为元件高度的 3 倍 (L_shadow >= 3 x H_comp)。阴影区内布置贴片件极易发生漏焊。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class OrientationIssue:
    ref: str
    package: str
    rotation_deg: float
    flow_direction: str
    issue_type: str  # "PARALLEL_PASSIVE_TOMBSTONE" / "PERPENDICULAR_SOIC_BRIDGING" / "WAVE_SHADOW_DEFICIT"
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WaveSolderOrientationReport:
    total_components_audited: int
    flow_direction: str
    compliant_count: int
    misoriented_count: int
    shadowed_count: int
    is_fully_compliant: bool
    issues: list[OrientationIssue] = field(default_factory=list)
    ipc_standard: str = "IPC-7351B Section 3.1.4 & SMTA Wave Soldering Guidelines"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["issues"] = [i.to_dict() for i in self.issues]
        return d


def calculate_wave_solder_orientation_audit(
    modules: dict[str, dict],
    flow_direction: str = "X+",  # "X+" (左向右), "X-", "Y+" (下向上), "Y-"
) -> WaveSolderOrientationReport:
    """审计底面贴片元件波峰焊接朝向角合规性与高器件阴影效应。"""
    issues: list[OrientationIssue] = []
    is_x_flow = "X" in flow_direction.upper()

    total = 0
    misoriented = 0
    shadowed = 0

    components = []
    for ref, m in sorted((modules or {}).items()):
        if ref == "__meta__":
            continue
        pkg = str(m.get("package", "")).upper()
        rot = float(m.get("rotation_deg", 0.0) or 0.0) % 180.0
        pos = m.get("position") or [0.0, 0.0]
        x = float(pos[0]) if len(pos) >= 2 else 0.0
        y = float(pos[1]) if len(pos) >= 2 else 0.0
        h = float(m.get("height_mm", 1.0) or 1.0)
        components.append((ref, pkg, rot, x, y, h))

    total = len(components)

    for ref, pkg, rot, x, y, h in components:
        # 1. 片式双端阻容无源件 (0603/0805/1206)
        is_chip_passive = any(k in pkg for k in ("0402", "0603", "0805", "1206"))
        if is_chip_passive:
            # X+ 流向下，0°/180° 为平行（错误），90° 为垂直（正确）
            # Y+ 流向下，90° 为平行（错误），0° 为垂直（正确）
            is_parallel_to_flow = (rot < 30.0 or rot > 150.0) if is_x_flow else (60.0 <= rot <= 120.0)
            if is_parallel_to_flow:
                misoriented += 1
                issues.append(
                    OrientationIssue(
                        ref=ref,
                        package=pkg,
                        rotation_deg=rot,
                        flow_direction=flow_direction,
                        issue_type="PARALLEL_PASSIVE_TOMBSTONE",
                        detail=f"片式无源件 {ref} ({pkg}) 旋转角 {rot:.0f}° 与波峰流向 {flow_direction} 平行；两端引脚切入锡波受热不均，极易产生立碑 (Tombstoning) 与虚焊缺陷。",
                    )
                )

        # 2. 多脚小外形芯片 (SOIC / SOP / TSSOP)
        is_soic = any(k in pkg for k in ("SOIC", "SOP", "TSSOP"))
        if is_soic:
            # 芯片长轴应与流向平行
            is_perpendicular_to_flow = (60.0 <= rot <= 120.0) if is_x_flow else (rot < 30.0 or rot > 150.0)
            if is_perpendicular_to_flow:
                misoriented += 1
                issues.append(
                    OrientationIssue(
                        ref=ref,
                        package=pkg,
                        rotation_deg=rot,
                        flow_direction=flow_direction,
                        issue_type="PERPENDICULAR_SOIC_BRIDGING",
                        detail=f"IC 芯片 {ref} ({pkg}) 旋转角 {rot:.0f}° 与波峰流向 {flow_direction} 垂直；密集引脚横截锡流将在脱锡边缘引发密集焊锡桥连短路 (Bridging)。",
                    )
                )

    # 3. 阴影效应检测：高件 (H >= 3.0mm) 下风向 3xH 范围内若有矮件
    for i in range(len(components)):
        c1 = components[i]
        if c1[5] >= 3.0:  # tall component
            shadow_len = c1[5] * 3.0
            for j in range(len(components)):
                if i == j:
                    continue
                c2 = components[j]
                # 判断 c2 是否在 c1 的下风向阴影区内
                if is_x_flow:
                    dx = c2[3] - c1[3]  # x2 - x1
                    dy = abs(c2[4] - c1[4])  # |y2 - y1|
                    if 0.0 < dx <= shadow_len and dy <= 3.0:
                        shadowed += 1
                        issues.append(
                            OrientationIssue(
                                ref=c2[0],
                                package=c2[1],
                                rotation_deg=c2[2],
                                flow_direction=flow_direction,
                                issue_type="WAVE_SHADOW_DEFICIT",
                                detail=f"元件 {c2[0]} 落在高大器件 {c1[0]} (高度 {c1[5]}mm) 的波峰流体阴影区内 (间距 {dx:.1f}mm <= 阴影区 {shadow_len:.1f}mm)；锡波流动受阻极易引发漏焊与少锡缺陷。",
                            )
                        )
                else:
                    dy = c2[4] - c1[4]  # y2 - y1
                    dx = abs(c2[3] - c1[3])  # |x2 - x1|
                    if 0.0 < dy <= shadow_len and dx <= 3.0:
                        shadowed += 1
                        issues.append(
                            OrientationIssue(
                                ref=c2[0],
                                package=c2[1],
                                rotation_deg=c2[2],
                                flow_direction=flow_direction,
                                issue_type="WAVE_SHADOW_DEFICIT",
                                detail=f"元件 {c2[0]} 落在高大器件 {c1[0]} (高度 {c1[5]}mm) 的波峰流体阴影区内 (间距 {dy:.1f}mm <= 阴影区 {shadow_len:.1f}mm)；锡波流动受阻极易引发漏焊与少锡缺陷。",
                            )
                        )

    compliant_cnt = max(0, total - misoriented - shadowed)
    is_ok = len(issues) == 0

    return WaveSolderOrientationReport(
        total_components_audited=total,
        flow_direction=flow_direction,
        compliant_count=compliant_cnt,
        misoriented_count=misoriented,
        shadowed_count=shadowed,
        is_fully_compliant=is_ok,
        issues=issues,
    )
